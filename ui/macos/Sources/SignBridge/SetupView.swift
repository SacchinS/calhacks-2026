import AppKit
import AVFoundation
import SwiftUI

enum SetupStep: Int, CaseIterable, Identifiable {
    case welcome, camera, speaker, voice, framing, done
    var id: Int { rawValue }
    var title: String {
        switch self {
        case .welcome: "Welcome"
        case .camera: "Camera"
        case .speaker: "Your voice"
        case .voice: "Call audio"
        case .framing: "Position"
        case .done: "Done"
        }
    }
    var icon: String {
        switch self {
        case .welcome: "hand.wave"
        case .camera: "camera"
        case .speaker: "person.wave.2"
        case .voice: "speaker.wave.2"
        case .framing: "person.crop.rectangle"
        case .done: "checkmark.seal"
        }
    }
}

func openSettingsPane(_ anchor: String) {
    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(anchor)") {
        NSWorkspace.shared.open(url)
    }
}

/// First-run setup wizard. Each step checks something and explains how to fix it.
struct SetupView: View {
    @ObservedObject var engine: EngineClient
    let finish: () -> Void
    var startAt: SetupStep = .welcome
    @State private var step: SetupStep = .welcome
    @State private var completed: Set<SetupStep> = []

    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 10) {
                    Logo(size: 38)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("SignBridge").font(.headline)
                        Text("Setup").font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                .padding(.horizontal, 16).padding(.top, 40).padding(.bottom, 6)
                List(SetupStep.allCases, selection: Binding(get: { step }, set: { if let s = $0 { go(s) } })) { s in
                    Label {
                        Text(s.title)
                    } icon: {
                        Image(systemName: completed.contains(s) ? "checkmark.circle.fill" : s.icon)
                            .foregroundStyle(completed.contains(s) ? .green : .secondary)
                    }
                    .tag(s)
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)
                VStack(alignment: .leading, spacing: 6) {
                    let total = SetupStep.allCases.count - 2
                    let finished = completed.subtracting([.welcome, .done]).count
                    Text("\(finished) of \(total) done").font(.caption).foregroundStyle(.secondary)
                    ProgressView(value: Double(finished), total: Double(total)).tint(Brand.accent)
                }
                .padding(16)
            }
            .frame(width: 200)
            .background(SidebarBackground())

            VStack(alignment: .leading, spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) { page }
                        .padding(28).padding(.top, 16).frame(maxWidth: .infinity, alignment: .leading)
                }
                Divider()
                HStack {
                    if step != .welcome { Button("Back") { go(SetupStep(rawValue: step.rawValue - 1)!) } }
                    Spacer()
                    if step == .done {
                        Button("Start SignBridge") {
                            engine.saveConfig(["onboarded": true])
                            finish()
                        }
                        .buttonStyle(.borderedProminent).controlSize(.large)
                        .keyboardShortcut(.defaultAction)
                    } else {
                        Button(completed.contains(step) || step == .welcome ? "Continue" : "Skip for now") {
                            if step == .welcome { completed.insert(.welcome) }
                            go(SetupStep(rawValue: step.rawValue + 1)!)
                        }
                        .buttonStyle(.borderedProminent).controlSize(.large)
                        .keyboardShortcut(.defaultAction)
                    }
                }
                .padding(16)
            }
        }
        .tint(Brand.accent)
        .ignoresSafeArea(.container, edges: .top)
        .onAppear { go(startAt) }
    }

    private func go(_ s: SetupStep) {
        step = s
        // Camera steps need the engine's camera and preview; others don't.
        engine.setMode(s == .framing ? "framing" : "off")
        engine.setPreview(s == .framing)
    }

    private func done(_ s: SetupStep, _ ok: Bool) {
        if ok { completed.insert(s) } else { completed.remove(s) }
    }

    @ViewBuilder private var page: some View {
        switch step {
        case .welcome: WelcomePage()
        case .camera: CameraPage(done: { done(.camera, $0) })
        case .speaker: SpeakerPage(engine: engine, done: { done(.speaker, $0) })
        case .voice: VoicePage(engine: engine, done: { done(.voice, $0) })
        case .framing: FramingPage(engine: engine, done: { done(.framing, $0) })
        case .done: DonePage(skipped: SetupStep.allCases.filter { ![.welcome, .done].contains($0) && !completed.contains($0) })
        }
    }
}

// MARK: pages

struct PageHeader: View {
    let title: String, subtitle: String
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.largeTitle.bold())
            Text(subtitle).font(.title3).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
        .padding(.bottom, 16)
    }
}

struct StatusLine: View {
    let ok: Bool?, text: String
    var body: some View {
        HStack(alignment: .top) {
            Image(systemName: ok == nil ? "circle.dotted" : ok! ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                .foregroundStyle(ok == nil ? Color.secondary : ok! ? Color.green : Color.orange)
            Text(text).fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 4)
    }
}

struct WelcomePage: View {
    var body: some View {
        HStack(spacing: 18) {
            Logo(size: 88)
            VStack(alignment: .leading, spacing: 4) {
                TitleText("SignBridge", font: .system(size: 40, weight: .heavy, design: .rounded))
                Text("Sign in your Google Meet calls. SignBridge speaks for you and captions the call.")
                    .font(.title3).foregroundStyle(.secondary)
            }
        }
        .padding(.bottom, 18)
        Storyboard()
        Label("Video never leaves this Mac. Only text goes to Claude: what you sign, and the call's captions so it can draft Jira tickets. Nothing reaches Jira until you approve it.", systemImage: "lock.fill")
            .fixedSize(horizontal: false, vertical: true)
            .foregroundStyle(.secondary).padding(.top, 10)
        Text("Setup takes about 3 minutes.").foregroundStyle(.secondary).padding(.top, 14)
    }
}

struct CameraPage: View {
    let done: (Bool) -> Void
    @State private var status = AVCaptureDevice.authorizationStatus(for: .video)
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    var body: some View {
        PageHeader(title: "Camera", subtitle: "SignBridge watches your hands. Video stays on your Mac.")
        switch status {
        case .authorized:
            StatusLine(ok: true, text: "Camera access is on.")
        case .notDetermined:
            Button("Allow Camera Access") {
                AVCaptureDevice.requestAccess(for: .video) { _ in
                    DispatchQueue.main.async { refresh() }
                }
            }
            .controlSize(.large)
        default:
            StatusLine(ok: false, text: "Camera access is off. Turn on SignBridge in Privacy & Security > Camera.")
            Button("Open Camera Settings") { openSettingsPane("Privacy_Camera") }
        }
        Color.clear.frame(height: 1).onAppear { refresh() }.onReceive(timer) { _ in refresh() }
    }
    private func refresh() {
        let now = AVCaptureDevice.authorizationStatus(for: .video)
        if now != status { status = now }
        done(status == .authorized)
    }
}

struct VoicePage: View {
    @ObservedObject var engine: EngineClient
    let done: (Bool) -> Void
    var body: some View {
        PageHeader(title: "Voice in calls",
                   subtitle: "SignBridge speaks for you in Google Meet through a virtual microphone.")
        if let r = engine.checks["voice"] {
            StatusLine(ok: r.ok, text: r.detail)
            if r.ok {
                Text("In Meet's settings, choose **BlackHole 2ch** as the microphone.").padding(.top, 6)
                Text("For captions, choose a **Multi-Output Device** with your speakers and **BlackHole 16ch** as Meet's speaker (make one in Audio MIDI Setup).")
                    .foregroundStyle(.secondary)
                Button("Play a test phrase into it") { engine.testRoute("voice", text: "SignBridge voice test.") }
                RouteResult(engine: engine, route: "voice",
                            okText: "Played. You won't hear it here; someone in your call would.")
            } else {
                Text("Install the free BlackHole driver: open Terminal and run").padding(.top, 6)
                Text("brew install blackhole-2ch").font(.body.monospaced()).textSelection(.enabled)
                    .padding(8).background(.quaternary, in: RoundedRectangle(cornerRadius: 6))
                Button("Check Again") { engine.check("voice") }
            }
        } else {
            ProgressView().onAppear { engine.check("voice") }
        }
        Color.clear.frame(height: 1).onChange(of: engine.checks["voice"]?.ok) { _, ok in done(ok ?? false) }
    }
}

/// The result of the last test send for one route.
struct RouteResult: View {
    @ObservedObject var engine: EngineClient
    let route: String, okText: String
    var body: some View {
        if let r = engine.lastRouteTest, r.route == route {
            StatusLine(ok: r.ok, text: r.ok ? okText : (r.detail.isEmpty ? "That didn't work." : r.detail))
        }
    }
}

/// The camera feed. With a finite maxHeight it's a 4:3 box (setup); with .infinity it fills
/// whatever space it gets, and the video fits inside (Preview and Demo Mode, any window size).
struct LivePreview: View {
    @ObservedObject var engine: EngineClient
    var maxHeight: CGFloat = 340
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10).fill(.black)
            if let image = engine.frame {
                Image(nsImage: image).resizable().aspectRatio(contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            } else {
                if let error = engine.engineError {
                    VStack(spacing: 10) {
                        Image(systemName: "video.slash").font(.system(size: 34)).foregroundStyle(Brand.accent)
                        Text(error).foregroundStyle(.white).multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                        if error.localizedCaseInsensitiveContains("camera") {
                            Button("Open Camera Settings") { openSettingsPane("Privacy_Camera") }
                        }
                    }
                    .padding(24)
                } else if engine.mockRecognizer {
                    VStack(spacing: 10) {
                        Image(systemName: "keyboard").font(.system(size: 34)).foregroundStyle(Brand.accent)
                        Text("No camera with the mock recognizer.\nType signs below.").foregroundStyle(.white)
                            .multilineTextAlignment(.center)
                    }
                } else {
                    VStack {
                        ProgressView()
                        Text("Starting the camera…").foregroundStyle(.white).padding(.top, 6)
                    }
                }
            }
        }
        .modifier(CameraSizing(maxHeight: maxHeight))
    }
}

private struct CameraSizing: ViewModifier {
    let maxHeight: CGFloat
    func body(content: Content) -> some View {
        if maxHeight == .infinity {
            content.frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            content.aspectRatio(4 / 3, contentMode: .fit).frame(maxHeight: maxHeight)
        }
    }
}

struct FramingPage: View {
    @ObservedObject var engine: EngineClient
    let done: (Bool) -> Void
    var body: some View {
        PageHeader(title: "Your position", subtitle: "Sit where you'll sign. Your head, shoulders and chest should show.")
        LivePreview(engine: engine)
        StatusLine(ok: engine.framingHint.isEmpty ? nil : engine.framingOK, text: engine.framingHint.isEmpty
                   ? "Looking for you…" : engine.framingHint)
        HStack {
            Button("Save This Position") { engine.calibrate() }.controlSize(.large).disabled(!engine.framingOK)
            if let msg = engine.lastCalibration { Text(msg).foregroundStyle(.secondary) }
        }
        Text("Sign inside the box: it turns yellow while you sign and green when a sign is recognized. Drop your hands between signs.")
            .foregroundStyle(.secondary).padding(.top, 4)
        Color.clear.frame(height: 1).onChange(of: engine.lastCalibration) { _, msg in done(msg?.hasPrefix("Saved") ?? false) }
    }
}

/// "Your voice": pick the Cartesia voice that speaks for you in calls, after hearing each one.
struct SpeakerPage: View {
    @ObservedObject var engine: EngineClient
    let done: (Bool) -> Void
    var body: some View {
        PageHeader(title: "Your voice",
                   subtitle: "This voice says what you sign in your calls. Play each one, then pick the one that sounds like you.")
        VStack(spacing: 8) {
            ForEach(engine.voices) { voice in
                let picked = engine.voiceID == voice.id
                HStack(spacing: 12) {
                    Text(String(voice.name.prefix(1))).font(.system(size: 20, weight: .bold, design: .rounded))
                        .foregroundStyle(.white).frame(width: 42, height: 42)
                        .background(picked ? AnyShapeStyle(Brand.gradient) : AnyShapeStyle(Color.gray.opacity(0.5)), in: Circle())
                    VStack(alignment: .leading, spacing: 2) {
                        Text(voice.name).font(.headline)
                        Text(voice.about).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if picked {
                        Label("Your voice", systemImage: "checkmark.circle.fill").font(.callout.weight(.semibold))
                            .foregroundStyle(Brand.accent)
                    }
                    if engine.previewing == voice.id {
                        ProgressView().controlSize(.small)
                    } else {
                        Button { engine.previewVoice(voice.id) } label: { Label("Play", systemImage: "play.fill") }
                            .help("Hear \(voice.name) on this Mac's speakers")
                    }
                }
                .padding(12)
                .background(picked ? Brand.accent.opacity(0.10) : Color.primary.opacity(0.04),
                            in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(picked ? Brand.accent.opacity(0.6) : .clear, lineWidth: 1.5))
                .contentShape(Rectangle())
                .onTapGesture { engine.chooseVoice(voice.id) }
            }
        }
        .padding(.top, 6)
        if let p = engine.lastPreview, !p.ok {
            StatusLine(ok: false, text: "Couldn't play it: \(p.detail). Check the Cartesia key in .env.")
        }
        Color.clear.frame(height: 1)
            .onAppear { done(!engine.voiceID.isEmpty) }
            .onChange(of: engine.voiceID) { _, id in done(!id.isEmpty) }
    }
}

struct DonePage: View {
    let skipped: [SetupStep]
    static let steps = [
        ("Join your Meet call", "Microphone: BlackHole 2ch. Speaker: your Multi-Output Device, for captions.", "video.fill"),
        ("Sign inside the box", "One sign each time you raise your hands. Spell names letter by letter; YES takes the suggestion.", "hand.raised.fill"),
        ("Sign FINISH", "Claude writes it in English and your voice says it in the call. NOW says it right away.", "speaker.wave.2.fill"),
        ("Turn on Call Overlay", "From the menu bar: follow along on top of Meet without switching windows.", "rectangle.bottomhalf.inset.filled"),
    ]
    var body: some View {
        PageHeader(title: "You're set", subtitle: "SignBridge lives in the menu bar (the hand icon).")
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(Self.steps.enumerated()), id: \.offset) { i, step in
                HStack(spacing: 14) {
                    Text("\(i + 1)").font(.system(size: 17, weight: .bold, design: .rounded)).foregroundStyle(.white)
                        .frame(width: 34, height: 34).background(Brand.gradient, in: Circle())
                    VStack(alignment: .leading, spacing: 2) {
                        Text(step.0).font(.headline)
                        Text(step.1).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: step.2).font(.title2).foregroundStyle(Brand.accent)
                }
                .padding(14)
                .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
        if !skipped.isEmpty {
            Text("Not finished: \(skipped.map(\.title).joined(separator: ", ")). You can run setup again from the menu bar.")
                .foregroundStyle(.orange).padding(.top, 16)
        }
    }
}
