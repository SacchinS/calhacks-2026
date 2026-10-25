import SwiftUI

/// The main window: the camera with tracking, what's being signed, Claude's sentence to send, and
/// the sentences said so far. The call itself (captions, quick replies) lives in the call overlay.
struct PreviewView: View {
    @ObservedObject var engine: EngineClient

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
                            transcript
                            SentList(engine: engine, maxHeight: .infinity)
                            Spacer(minLength: 0)
                            if engine.mockRecognizer { MockSignBox(engine: engine) } else { SpellBox(engine: engine) }
                            controls
                        }
                        .frame(width: min(560, geo.size.width * 0.38))
                    }
                }
            } else {
                VStack(spacing: 14) {
                    topBar
                    camera
                    transcript
                    SentList(engine: engine, maxHeight: 220)
                    if engine.mockRecognizer { MockSignBox(engine: engine) } else { SpellBox(engine: engine) }
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
                if engine.glosses.isEmpty && engine.autocomplete == nil {
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
                    Label(RouteInfo.label(target: engine.target), systemImage: RouteInfo.icon).foregroundStyle(Brand.accent).font(.headline)
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
            AutocompleteBar(engine: engine)
            FloorStatus(engine: engine)  // waiting for a pause, or speaking
            if engine.state == "idle", let last = engine.log.last {  // e.g. what was just sent, or an error
                Text(last).font(.caption).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .leading)
        .padding(16)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.white.opacity(0.08)))
        .animation(.easeInOut(duration: 0.2), value: engine.state)
        .animation(.easeInOut(duration: 0.15), value: engine.autocomplete)
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
            // NOW: say it right away instead of waiting for the pause (or end the sentence that way).
            if engine.speechState == "waiting" || (engine.state == "listening" && !engine.glosses.isEmpty) {
                Button { engine.gesture("now") } label: { Label("Say now", systemImage: "bolt.fill") }
                    .help("Speak right away, without waiting for a pause (the NOW sign)")
            }
            Spacer()
        }
        .controlSize(.large)
    }
}

/// The sentences said for you so far, newest at the bottom.
struct SentList: View {
    @ObservedObject var engine: EngineClient
    var maxHeight: CGFloat
    private var said: [String] { engine.meetLog.filter { $0.who == "you" }.suffix(40).map(\.text) }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Said", systemImage: RouteInfo.icon).font(.headline).foregroundStyle(Brand.accent)
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        if said.isEmpty {
                            Text("Sentences you send show up here.").foregroundStyle(.tertiary)
                        }
                        ForEach(Array(said.enumerated()), id: \.offset) { i, text in
                            Text(text).font(.title3).textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading).id(i)
                        }
                    }
                }
                .onChange(of: said.count) { _, n in proxy.scrollTo(n - 1, anchor: .bottom) }
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

/// Typed signs for the mock recognizer: `hello nice meet-you`, `#sarah` (fingerspelled), `~p` (letters
/// one at a time, for autocomplete), face markers
/// after the signs they cover (`/\`, `[q]`, `[wh]`, `[neg]`, `[nod]`), and `/send /now /yes /no /clear`.
struct MockSignBox: View {
    @ObservedObject var engine: EngineClient
    @State private var text = ""
    @FocusState private var focused: Bool
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "keyboard").foregroundStyle(Brand.accent)
            TextField("Type signs: ~f /yes color problem /now · #sarah · ~p (letters) · [q] [wh] [neg] · /send /now /yes /no /clear", text: $text)
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
