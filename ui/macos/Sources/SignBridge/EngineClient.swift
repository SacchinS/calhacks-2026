import AppKit
import Foundation

/// One finished phrase, for the demo's history.
struct HistoryItem: Identifiable {
    let id = UUID()
    let glosses: [String], sentence: String, route: String, sent: Bool, date: Date
}

/// Launches the Python engine (app.py, protocol in ui/server.py) and talks JSON lines with it.
/// Inside the app bundle it uses the bundled Python; in development it uses the repo's .venv.
@MainActor
final class EngineClient: ObservableObject {
    // Status mirrored from the engine
    @Published var running = false
    @Published var state = "idle"
    @Published var mode = "off"
    @Published var glosses: [String] = []
    @Published var sentence: String?
    @Published var route: String?
    @Published var log: [String] = []
    @Published var holding: (String, Double)? = nil
    @Published var target: String?
    @Published var fps = 0.0
    @Published var engineError: String?
    @Published var framingHint = ""
    @Published var framingOK = false
    @Published var practiceDone: [String] = []
    @Published var practiceTodo: [String] = []
    @Published var frame: NSImage?
    @Published var config: [String: Any] = [:]
    @Published var checks: [String: (ok: Bool, detail: String)] = [:]
    @Published var lastCalibration: String?
    @Published var lastRouteTest: (route: String, ok: Bool, detail: String)?
    @Published var history: [HistoryItem] = []  // newest first
    // calhacks-2026 additions: where English goes, Meet captions, Claude Code's reply, mock signs
    @Published var outputMode = "claude_code"
    @Published var components: [String: String] = [:]
    @Published var claudeCodeWorking = false
    @Published var cameraOn = false
    /// Turn-aware speaking in Meet: our voice's state ("idle", "waiting", "interjecting",
    /// "speaking"), the sentence it's about to say, and whether the other side is talking.
    @Published var speechState = "idle"
    @Published var speechText = ""
    @Published var themTalking = false
    /// One-tap replies for calls (meet.quick_replies); urgent ones are said without waiting.
    @Published var quickReplies: [(text: String, urgent: Bool)] = []
    /// Someone on the call said your name (MentionBanner shows it over every window).
    struct MentionAlert: Equatable { let text: String; let question: Bool; let final: Bool; let turn: Int }
    @Published var mention: MentionAlert?
    /// The Meet call so far: what the signer said ("you") and the other side's captions ("them").
    @Published var meetLog: [(who: String, text: String)] = []
    private var captionPartial = false
    @Published var mockRecognizer = false
    @Published var captions: [String] = []
    @Published var replies: [String] = []
    @Published var sent: [(mode: String, text: String)] = []
    private var pending: (glosses: [String], sentence: String, route: String)?
    /// Arguments for the engine, e.g. --mock (everything after the app's own binary path).
    let engineArguments = Array(CommandLine.arguments.dropFirst())

    private var process: Process?
    private var input: FileHandle?
    private var buffer = Data()
    private var stopping = false

    var onboarded: Bool { (config["onboarded"] as? Bool) ?? false }

    // MARK: launching

    static func locate() -> (python: URL, resources: URL, pythonPath: String)? {
        let fm = FileManager.default
        if let res = Bundle.main.resourceURL {
            let py = res.appendingPathComponent("python/bin/python3")
            if fm.isExecutableFile(atPath: py.path) {
                let engine = res.appendingPathComponent("engine")
                let path = [engine.path, res.appendingPathComponent("site-packages").path]
                return (py, engine, path.joined(separator: ":"))
            }
        }
        guard let root = devRoot() else { return nil }
        let py = root.appendingPathComponent(".venv/bin/python")
        guard fm.isExecutableFile(atPath: py.path) else { return nil }
        return (py, root, root.path)
    }

    /// Development: ENGINE_ROOT (set by the Makefile), or the first folder above this binary with app.py.
    nonisolated static func devRoot() -> URL? {
        if let root = ProcessInfo.processInfo.environment["ENGINE_ROOT"] { return URL(fileURLWithPath: root) }
        var dir = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath().deletingLastPathComponent()
        while dir.path != "/" {
            if FileManager.default.fileExists(atPath: dir.appendingPathComponent("app.py").path) { return dir }
            dir = dir.deletingLastPathComponent()
        }
        return nil
    }

    func start() {
        guard process == nil else { return }
        guard let loc = Self.locate() else {
            engineError = "Couldn't find the SignBridge engine. Reinstall the app."
            return
        }
        let p = Process()
        p.executableURL = loc.python
        p.arguments = ["app.py"] + engineArguments
        p.currentDirectoryURL = loc.resources
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = loc.pythonPath
        env["PYTHONUNBUFFERED"] = "1"
        env["PATH"] = (env["PATH"] ?? "/usr/bin:/bin") + ":/opt/homebrew/bin:/usr/local/bin:" +
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin").path
        p.environment = env
        let inPipe = Pipe(), outPipe = Pipe()
        p.standardInput = inPipe
        p.standardOutput = outPipe
        // Engine logs: the terminal in development (make mock), a log file in the app bundle.
        let bundled = Bundle.main.resourceURL.map { loc.resources.path.hasPrefix($0.path) } ?? false
        p.standardError = bundled ? (FileHandle(forWritingAtPath: Self.logPath()) ?? FileHandle.standardError)
            : FileHandle.standardError
        outPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            Task { @MainActor in self?.receive(data) }
        }
        p.terminationHandler = { [weak self] proc in
            Task { @MainActor in self?.ended(code: proc.terminationStatus) }
        }
        do {
            try p.run()
        } catch {
            engineError = "Couldn't start the engine: \(error.localizedDescription)"
            return
        }
        process = p
        input = inPipe.fileHandleForWriting
        running = true
        engineError = nil
        if !bundled { forwardTerminalInput() }
    }

    /// `make mock` in a terminal: lines typed there are mock signs, like the mock-sign box.
    private func forwardTerminalInput() {
        guard isatty(STDIN_FILENO) == 1, FileHandle.standardInput.readabilityHandler == nil else { return }
        FileHandle.standardError.write(Data("Mock signs: type gloss + Enter (#word = fingerspell, /yes /no /send ...)\n".utf8))
        let splitter = LineSplitter()
        FileHandle.standardInput.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            for line in splitter.lines(adding: data) {
                Task { @MainActor in self?.mockInput(line) }
            }
        }
    }

    static func logPath() -> String {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/calhacks-2026")  // not SignBridge's: that's the earlier app's log
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("engine.log")
        FileManager.default.createFile(atPath: file.path, contents: nil)
        return file.path
    }

    func stop() {
        stopping = true
        send(["cmd": "quit"])
        process?.waitUntilExit()
    }

    private func ended(code: Int32) {
        process = nil
        input = nil
        running = false
        if !stopping {
            engineError = "The engine stopped (code \(code)). Restarting… Details: ~/Library/Logs/calhacks-2026/engine.log"
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in self?.start() }
        }
    }

    // MARK: commands

    func send(_ command: [String: Any]) {
        guard let input, let data = try? JSONSerialization.data(withJSONObject: command) else { return }
        input.write(data + Data([0x0A]))
    }

    func setMode(_ mode: String) { send(["cmd": "mode", "mode": mode]) }
    func setPreview(_ on: Bool) {
        send(["cmd": "preview", "on": on])
        if !on { frame = nil }
    }
    func gesture(_ name: String) { send(["cmd": "gesture", "name": name]) }
    func fake(_ glosses: [String]) { send(["cmd": "fake", "glosses": glosses]) }
    func check(_ name: String) {
        checks[name] = nil
        send(["cmd": "check", "name": name])
    }
    func testRoute(_ route: String, text: String) {
        lastRouteTest = nil
        send(["cmd": "test_route", "route": route, "text": text])
    }
    func calibrate() { send(["cmd": "calibrate"]) }
    func saveConfig(_ values: [String: Any]) { send(["cmd": "config", "values": values]) }
    func introduce() { send(["cmd": "introduce"]) }
    func quickReply(_ text: String) { send(["cmd": "quick_reply", "text": text]) }
    func setOutputMode(_ mode: String) { send(["cmd": "output_mode", "mode": mode]) }
    func mockInput(_ text: String) {
        if !text.trimmingCharacters(in: .whitespaces).isEmpty { send(["cmd": "mock_input", "text": text]) }
    }

    // MARK: events

    private func receive(_ data: Data) {
        if data.isEmpty { return }
        buffer.append(data)
        while let nl = buffer.firstIndex(of: 0x0A) {
            let line = buffer.subdata(in: buffer.startIndex..<nl)
            buffer.removeSubrange(buffer.startIndex...nl)
            if let obj = try? JSONSerialization.jsonObject(with: line) as? [String: Any] {
                handle(obj)
            }
        }
    }

    private func handle(_ e: [String: Any]) {
        switch e["type"] as? String {
        case "ready":
            config = e["config"] as? [String: Any] ?? [:]
            quickReplies = (e["quick_replies"] as? [[String: Any]] ?? []).compactMap { r in
                (r["text"] as? String).map { (text: $0, urgent: r["urgent"] as? Bool ?? false) }
            }
        case "config":
            config = e["config"] as? [String: Any] ?? config
        case "status":
            let newState = e["state"] as? String ?? "idle"
            // Voice and Meet send without confirming, so remember the phrase while sending too.
            if newState == "confirming" || (newState == "sending" && pending == nil),
               let intent = e["intent"] as? [String: Any], let text = intent["sentence"] as? String {
                pending = (e["glosses"] as? [String] ?? [], text, intent["route"] as? String ?? "")
            }
            if newState == "idle", state == "sending" || state == "confirming", let p = pending {
                history.insert(HistoryItem(glosses: p.glosses, sentence: p.sentence, route: p.route,
                                           sent: state == "sending", date: Date()), at: 0)
                history = Array(history.prefix(20))
                pending = nil
            }
            state = newState
            mode = e["mode"] as? String ?? "off"
            glosses = e["glosses"] as? [String] ?? []
            let intent = e["intent"] as? [String: Any]
            sentence = intent?["sentence"] as? String
            route = intent?["route"] as? String
            log = e["log"] as? [String] ?? []
            target = e["target"] as? String
            fps = e["fps"] as? Double ?? 0
            engineError = e["error"] as? String
            if let h = e["holding"] as? [Any], let name = h.first as? String, let prog = h.last as? Double {
                holding = (name, prog)
            } else {
                holding = nil
            }
            let framing = e["framing"] as? [String: Any]
            framingHint = framing?["hint"] as? String ?? ""
            framingOK = framing?["ok"] as? Bool ?? false
            let practice = e["practice"] as? [String: Any]
            practiceDone = practice?["done"] as? [String] ?? []
            practiceTodo = practice?["todo"] as? [String] ?? []
            outputMode = e["output_mode"] as? String ?? outputMode
            components = e["components"] as? [String: String] ?? components
            claudeCodeWorking = e["claude_code_working"] as? Bool ?? false
            cameraOn = e["camera_on"] as? Bool ?? false
            let speech = e["speech"] as? [String: Any]
            speechState = speech?["state"] as? String ?? "idle"
            speechText = speech?["text"] as? String ?? ""
            themTalking = e["them_talking"] as? Bool ?? false
            mockRecognizer = e["mock"] as? Bool ?? mockRecognizer
        case "frame":
            if let b64 = e["jpeg"] as? String, let data = Data(base64Encoded: b64) {
                frame = NSImage(data: data)
            }
        case "check":
            if let name = e["name"] as? String {
                checks[name] = (e["ok"] as? Bool ?? false, e["detail"] as? String ?? "")
            }
        case "calibrated":
            lastCalibration = e["message"] as? String
        case "route_tested":
            lastRouteTest = (e["route"] as? String ?? "", e["ok"] as? Bool ?? false, e["detail"] as? String ?? "")
        case "caption":
            // A partial caption (still being spoken) is replaced by the next one for that turn.
            let text = e["text"] as? String ?? ""
            if captionPartial, !captions.isEmpty { captions.removeLast() }
            if captionPartial, meetLog.last?.who == "them" { meetLog.removeLast() }
            captions = Array((captions + [text]).suffix(30))
            meetLog = Array((meetLog + [("them", text)]).suffix(60))
            captionPartial = !(e["final"] as? Bool ?? true)
        case "reply":
            replies = Array((replies + [e["text"] as? String ?? ""]).suffix(60))
        case "sent":
            sent = Array((sent + [(e["mode"] as? String ?? "", e["text"] as? String ?? "")]).suffix(60))
            if e["mode"] as? String == "meet" {
                meetLog = Array((meetLog + [("you", e["text"] as? String ?? "")]).suffix(60))
            }
        case "mention":
            mention = MentionAlert(text: e["text"] as? String ?? "", question: e["question"] as? Bool ?? false,
                                   final: e["final"] as? Bool ?? true, turn: e["turn"] as? Int ?? 0)
        case "error":
            engineError = e["message"] as? String
        default:
            break
        }
    }
}

/// Splits incoming bytes into lines. Used from one serial file-handle queue only.
final class LineSplitter: @unchecked Sendable {
    private var pending = Data()
    func lines(adding data: Data) -> [String] {
        pending.append(data)
        var lines: [String] = []
        while let nl = pending.firstIndex(of: 0x0A) {
            lines.append(String(decoding: pending[pending.startIndex..<nl], as: UTF8.self))
            pending.removeSubrange(pending.startIndex...nl)
        }
        return lines
    }
}
