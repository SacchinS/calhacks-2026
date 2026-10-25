import SwiftUI

/// Live view for the user and for demos: camera with tracking, what was signed, Claude's sentence and route.
struct PreviewView: View {
    @ObservedObject var engine: EngineClient
    var showGuide: () -> Void = {}
    var showDemo: () -> Void = {}
    private let fakePhrases = DemoScript.phrases

    private var live: Bool { engine.state == "listening" }

    var body: some View {
        GeometryReader { geo in
            // Wide windows (fullscreen, a big display): camera on the left, everything else beside it.
            if geo.size.width >= 1000 && geo.size.width > geo.size.height * 1.2 {
                VStack(spacing: 14) {
                    topBar
                    HStack(alignment: .top, spacing: 18) {
                        camera
                        VStack(spacing: 14) {
                            OutputModePicker(engine: engine)
                            transcript
                            OutputPanel(engine: engine, maxHeight: .infinity)
                            Spacer(minLength: 0)
                            if engine.mockRecognizer { MockSignBox(engine: engine) }
                            controls
                        }
                        .frame(width: min(560, geo.size.width * 0.38))
                    }
                }
            } else {
                VStack(spacing: 14) {
                    topBar
                    OutputModePicker(engine: engine)
                    camera
                    transcript
                    OutputPanel(engine: engine)
                    if engine.mockRecognizer { MockSignBox(engine: engine) }
                    controls
                }
            }
        }
        .padding([.horizontal, .bottom], 18).padding(.top, 6)
        .frame(minWidth: 600, minHeight: 700)
        .background(Brand.background)
        .environment(\.colorScheme, .dark)
        .tint(Brand.accent)
        .ignoresSafeArea(.container, edges: .top)
    }

    // MARK: pieces

    private var camera: some View {
        ZStack(alignment: .bottom) {
            LivePreview(engine: engine, maxHeight: .infinity).frame(maxHeight: .infinity)
                .overlay(RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(Brand.accent, lineWidth: live ? 3 : 0))
                .animation(.easeInOut(duration: 0.3), value: live)
            if let h = engine.holding {
                HStack(spacing: 10) {
                    Image(systemName: GestureInfo.icon(h.0))
                    Text(GestureInfo.name(h.0)).bold()
                    ProgressView(value: h.1).frame(width: 110).tint(.white)
                }
                .padding(.horizontal, 14).padding(.vertical, 8)
                .background(.ultraThinMaterial, in: Capsule()).padding(12)
                .transition(.opacity)
            }
        }
    }

    private var topBar: some View {
        HStack(spacing: 12) {
            Spacer().frame(width: 58)  // room for the window buttons
            Logo(size: 28)
            Text("SignBridge").font(.headline)
            StatePill(state: engine.state)
            Spacer()
            if engine.claudeCodeWorking { ClaudeCodeWorking() }
            if let target = engine.target, engine.state != "idle" {
                Label(target, systemImage: "macwindow").foregroundStyle(.secondary)
            }
            CameraIndicator(on: engine.cameraOn)
            if engine.fps > 0 {
                Text("\(Int(engine.fps)) fps").font(.caption.monospacedDigit()).foregroundStyle(.tertiary)
            }
        }
    }

    private var transcript: some View {
        VStack(alignment: .leading, spacing: 12) {
            switch engine.state {
            case "listening", "thinking":
                if engine.glosses.isEmpty {
                    Text("Sign, then rest your hands.").font(.title2).foregroundStyle(.secondary)
                } else {
                    HStack(spacing: 8) {
                        ForEach(Array(engine.glosses.enumerated()), id: \.offset) { _, g in Chip(text: g) }
                        if engine.state == "thinking" {
                            Image(systemName: "arrow.right").foregroundStyle(.secondary)
                            ProgressView().controlSize(.small)
                            Text("Claude is writing…").foregroundStyle(.secondary)
                        }
                    }
                }
            case "confirming", "sending":
                HStack(spacing: 6) {
                    ForEach(Array(engine.glosses.enumerated()), id: \.offset) { _, g in
                        Text(g).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    }
                }
                Text(engine.sentence ?? "").font(.system(size: 30, weight: .semibold))
                    .fixedSize(horizontal: false, vertical: true)
                HStack {
                    Label(RouteInfo.label(engine.route, target: engine.target), systemImage: RouteInfo.icon(engine.route)).foregroundStyle(Brand.accent).font(.headline)
                    Spacer()
                    if engine.state == "confirming" {
                        Text("Sign YES to send, NO to cancel").foregroundStyle(.secondary)
                    } else {
                        ProgressView().controlSize(.small)
                    }
                }
            default:
                HStack(spacing: 10) {
                    Image(systemName: "hand.raised").font(.title2).foregroundStyle(Brand.accent)
                    Text(engine.mockRecognizer ? "Type signs below to start." : "Start signing.").font(.title2).foregroundStyle(.secondary)
                }
            }
            if engine.state == "idle", let last = engine.log.last {  // e.g. what was just sent, or an error
                Text(last).font(.caption).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .leading)
        .padding(16)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.white.opacity(0.08)))
        .animation(.easeInOut(duration: 0.2), value: engine.state)
    }

    private var controls: some View {
        HStack(spacing: 10) {
            switch engine.state {
            case "idle":
                Button { engine.gesture("wake") } label: { Label("Start", systemImage: "hand.raised") }
                    .buttonStyle(.borderedProminent)
            case "confirming":
                Button { engine.gesture("confirm") } label: { Label("Send", systemImage: "hand.thumbsup") }
                    .buttonStyle(.borderedProminent).tint(.green)
                Button { engine.gesture("cancel") } label: { Label("Cancel", systemImage: "hand.thumbsdown") }
            default:
                Button { engine.gesture("cancel") } label: { Label("Cancel", systemImage: "hand.thumbsdown") }
            }
            Spacer()
            Button(action: showGuide) { Label("Signs", systemImage: "book") }.buttonStyle(.borderless)
            Button(action: showDemo) { Label("Demo", systemImage: "arrow.up.left.and.arrow.down.right") }
                .buttonStyle(.borderless)
            Menu {
                ForEach(fakePhrases, id: \.self) { p in
                    Button(DemoScript.label(p)) { engine.fake(p) }
                }
            } label: {
                Label("Test phrases", systemImage: "text.badge.plus")
            }
            .menuStyle(.borderlessButton).fixedSize()
        }
        .controlSize(.large)
    }
}

/// The Meet call as a conversation: what the signer said (spoken for them) and the other side's
/// captions, plus the call intro button.
struct MeetPanel: View {
    @ObservedObject var engine: EngineClient
    var maxHeight: CGFloat
    var title: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label(title, systemImage: "captions.bubble").font(.headline).foregroundStyle(Brand.accent)
                Spacer()
                Button { engine.introduce() } label: { Label("Introduce me", systemImage: "person.wave.2") }
                    .help("Say who's calling and that you sign through SignBridge")
            }
            FloorStatus(engine: engine)
            QuickReplies(engine: engine)
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        if engine.meetLog.isEmpty {
                            Text("Your words and the other side's captions show up here.").foregroundStyle(.tertiary)
                        }
                        ForEach(Array(engine.meetLog.suffix(40).enumerated()), id: \.offset) { i, line in
                            HStack(alignment: .firstTextBaseline, spacing: 10) {
                                Text(line.who == "you" ? "You" : "Them").font(.caption.weight(.bold))
                                    .foregroundStyle(line.who == "you" ? Brand.accent : .secondary)
                                    .frame(width: 40, alignment: .leading)
                                Text(line.text).font(.title3.weight(line.who == "you" ? .regular : .semibold))
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .id(i)
                        }
                    }
                }
                .onChange(of: engine.meetLog.count) { _, n in proxy.scrollTo(min(n, 40) - 1, anchor: .bottom) }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 70, maxHeight: maxHeight, alignment: .topLeading)
        .padding(16)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.white.opacity(0.08)))
    }
}

/// One-tap replies spoken in your voice. Urgent ones (orange) are said right away; the rest
/// wait for a pause, like anything you sign.
struct QuickReplies: View {
    @ObservedObject var engine: EngineClient
    var size: ControlSize = .regular
    var body: some View {
        if !engine.quickReplies.isEmpty {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: size == .large ? 220 : 150), spacing: 6)],
                      alignment: .leading, spacing: 6) {
                ForEach(engine.quickReplies, id: \.text) { reply in
                    Button { engine.quickReply(reply.text) } label: {
                        Text(reply.text).lineLimit(1).frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .tint(reply.urgent ? .orange : nil)
                    .help(reply.urgent ? "Said right away" : "Said at the next pause")
                }
            }
            .controlSize(size)
        }
    }
}

/// Who has the floor in the call, and when SignBridge will speak your approved words.
struct FloorStatus: View {
    @ObservedObject var engine: EngineClient
    var font: Font = .callout.weight(.semibold)
    var body: some View {
        if let (icon, text, color) = line {
            Label(text, systemImage: icon)
                .font(font).foregroundStyle(color)
                .lineLimit(2)
                .transition(.opacity)
        }
    }
    private var line: (String, String, Color)? {
        switch engine.speechState {
        case "waiting":
            return ("hourglass", "Waiting for a pause to say: \"\(engine.speechText)\"", .yellow)
        case "interjecting":
            return ("hand.raised.fill", "Jumping in: \"Sorry, can I jump in?\"", .orange)
        case "speaking":
            return ("speaker.wave.2.fill", "Speaking: \"\(engine.speechText)\"", Brand.accent)
        default:
            return engine.themTalking ? ("waveform", "They're talking", .secondary) : nil
        }
    }
}

/// Always visible: whether the webcam is on. Video never leaves the Mac.
struct CameraIndicator: View {
    let on: Bool
    var body: some View {
        Label(on ? "Camera on" : "Camera off", systemImage: on ? "video.fill" : "video.slash")
            .font(.subheadline.weight(.semibold))
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background((on ? Color.red : Color.gray).opacity(0.18), in: Capsule())
            .foregroundStyle(on ? .red : .secondary)
            .help("Video stays on this Mac: only the recognized sign words leave it, as text.")
    }
}

/// Shown in every mode while Claude Code builds in the background.
struct ClaudeCodeWorking: View {
    var body: some View {
        HStack(spacing: 7) {
            ProgressView().controlSize(.small)
            Text("Claude Code is working").font(.subheadline.weight(.semibold))
        }
        .padding(.horizontal, 11).padding(.vertical, 5)
        .background(Color.purple.opacity(0.16), in: Capsule())
        .foregroundStyle(.purple)
    }
}

struct StatePill: View {
    let state: String
    var body: some View {
        HStack(spacing: 7) {
            PulseDot(color: color, active: state == "listening" || state == "thinking")
            Text(label).font(.subheadline.weight(.semibold))
        }
        .padding(.horizontal, 11).padding(.vertical, 5)
        .background(color.opacity(0.16), in: Capsule())
        .foregroundStyle(color)
    }
    private var label: String {
        ["idle": "Waiting", "listening": "Listening", "thinking": "Thinking", "confirming": "Confirm",
         "sending": "Sending"][state] ?? state
    }
    private var color: Color {
        ["idle": .gray, "listening": Brand.accent, "thinking": .purple, "confirming": .yellow,
         "sending": .green][state] ?? .gray
    }
}

// MARK: calhacks-2026 additions, in the same style

/// Where English goes: Claude Code (after a signed YES), a voice for Siri and dictation, or a Meet call.
struct OutputModePicker: View {
    @ObservedObject var engine: EngineClient
    var body: some View {
        Picker("Send to", selection: Binding(get: { engine.outputMode }, set: { engine.setOutputMode($0) })) {
            ForEach(OutputMode.all, id: \.self) { mode in
                Label(OutputMode.label(mode), systemImage: OutputMode.icon(mode)).tag(mode)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .controlSize(.large)
    }
}

/// Claude Code's reply in Claude Code mode, or the other side's captions in Meet mode.
struct OutputPanel: View {
    @ObservedObject var engine: EngineClient
    var maxHeight: CGFloat = 130
    var body: some View {
        switch engine.outputMode {
        case "claude_code":
            panel("Claude Code" + mock("claude_code"), icon: "chevron.left.forwardslash.chevron.right",
                  lines: engine.replies.filter { !$0.isEmpty }, empty: "Claude Code's reply shows up here.",
                  font: .system(.callout, design: .monospaced),
                  note: engine.claudeCodeWorking ? "Still working. Siri, Voice, and Meet keep working meanwhile." : nil)
        case "siri":
            panel("Typed to Siri" + mock("siri"), icon: "mic.circle.fill", lines: sent("siri"),
                  empty: "Questions typed to Siri show up here.", font: .title3.weight(.semibold),
                  note: "Siri answers in its own window, top right of the screen.")
        case "voice":
            panel("Spoken" + mock("tts"), icon: "speaker.wave.2.fill", lines: sent("voice"),
                  empty: "What SignBridge says into the virtual mic shows up here.",
                  font: .title3.weight(.semibold),
                  note: "Pick BlackHole 2ch as the mic in the app you're using, then start its dictation.")
        case "meet":
            // Taller than the other panels: the conversation plus the quick-reply buttons.
            MeetPanel(engine: engine, maxHeight: max(maxHeight, 320), title: "Call" + mock("captions"))
        default:
            EmptyView()
        }
    }

    private func sent(_ mode: String) -> [String] {
        engine.sent.filter { $0.mode == mode }.map(\.text)
    }

    private func mock(_ component: String) -> String {
        engine.components[component] == "mock" ? " (mock)" : ""
    }

    private func panel(_ title: String, icon: String, lines: [String], empty: String, font: Font,
                       note: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon).font(.headline).foregroundStyle(Brand.accent)
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
                        if lines.isEmpty { Text(empty).foregroundStyle(.tertiary) }
                        ForEach(Array(lines.suffix(30).enumerated()), id: \.offset) { i, line in
                            Text(line).font(font).textSelection(.enabled).id(i)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .onChange(of: lines.count) { _, _ in proxy.scrollTo(min(lines.count, 30) - 1, anchor: .bottom) }
            }
            if let note { Text(note).font(.caption).foregroundStyle(.secondary) }
        }
        .frame(maxWidth: .infinity, minHeight: 70, maxHeight: maxHeight, alignment: .topLeading)
        .padding(16)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.white.opacity(0.08)))
    }
}

/// Typed signs for the mock recognizer: `food store /\ ww make`, `#sarah` (fingerspelled), face markers
/// after the signs they cover (`/\`, `[q]`, `[wh]`, `[neg]`, `[nod]`), and `/send /yes /no /clear`.
struct MockSignBox: View {
    @ObservedObject var engine: EngineClient
    @State private var text = ""
    @FocusState private var focused: Bool
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "keyboard").foregroundStyle(Brand.accent)
            TextField("Type signs: food store /\\ ww make · #sarah · [q] [wh] [neg] · /send /yes /no /clear", text: $text)
                .textFieldStyle(.roundedBorder).focused($focused).onSubmit(submit)
            Button("Sign", action: submit).buttonStyle(.borderedProminent)
        }
        .controlSize(.large)
        .onAppear { focused = true }
    }
    private func submit() {
        engine.mockInput(text)
        text = ""
        focused = true
    }
}
