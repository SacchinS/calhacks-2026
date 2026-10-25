import SwiftUI

/// The main window: the camera with tracking, what's being signed, Claude's sentence to send, and
/// the sentences said so far. The call itself (captions, quick replies) lives in the call overlay.
struct PreviewView: View {
    @ObservedObject var engine: EngineClient

    var body: some View {
        GeometryReader { geo in
            // Wide windows (fullscreen, a big display): camera on the left, everything else beside it.
            if geo.size.width >= 1000 && geo.size.width > geo.size.height * 1.2 {
                VStack(spacing: 16) {
                    topBar
                    HStack(alignment: .top, spacing: 18) {
                        camera
                        VStack(spacing: 14) {
                            transcript
                            SentList(engine: engine, maxHeight: .infinity)
                            input
                            controls
                        }
                        .frame(width: min(540, geo.size.width * 0.38))
                    }
                }
            } else {
                VStack(spacing: 14) {
                    topBar
                    camera
                    transcript
                    SentList(engine: engine, maxHeight: 200)
                    input
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

    private var topBar: some View {
        HStack(spacing: 12) {
            Spacer().frame(width: 58)  // room for the window buttons
            Logo(size: 30)
            Text("SignBridge").font(.system(size: 17, weight: .bold, design: .rounded))
            StatePill(state: engine.state)
            Spacer()
            if let target = engine.target {
                Label(target, systemImage: "video.fill").font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(Color.white.opacity(0.06), in: Capsule())
            }
            CameraIndicator(on: engine.cameraOn)
            if engine.fps > 0 {
                Text("\(Int(engine.fps)) fps").font(.caption.monospacedDigit()).foregroundStyle(.tertiary)
            }
        }
        .frame(height: 38)
    }

    /// The camera, framed in the signing box's color, with the state and the letter being held.
    private var camera: some View {
        let color = SignState.color(engine.signState)
        return LivePreview(engine: engine, maxHeight: .infinity).frame(maxHeight: .infinity)
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(color.opacity(engine.signState == nil || engine.signState == "idle" ? 0 : 1), lineWidth: 3))
            .overlay(alignment: .topLeading) {
                if engine.signState != nil {
                    HStack(spacing: 8) {
                        SignStateBadge(state: engine.signState, size: 26)
                        Text(SignState.label(engine.signState)).font(.callout.weight(.semibold))
                    }
                    .padding(.leading, 6).padding(.trailing, 12).padding(.vertical, 6)
                    .background(.ultraThinMaterial, in: Capsule())
                    .padding(12)
                }
            }
            .overlay(alignment: .bottom) {
                if let h = engine.holding { LetterHold(letter: h.0, progress: h.1).padding(14).transition(.opacity) }
            }
            .animation(.easeInOut(duration: 0.25), value: engine.signState)
    }

    private var transcript: some View {
        Card(title: title, icon: icon, tint: tint) {
            VStack(alignment: .leading, spacing: 14) {
                switch engine.state {
                case "listening", "thinking":
                    if engine.glosses.isEmpty && engine.autocomplete == nil {
                        SignHints()
                    } else if !engine.glosses.isEmpty {
                        FlowRow(spacing: 8) {
                            ForEach(Array(engine.glosses.enumerated()), id: \.offset) { _, g in Chip(text: g) }
                            if engine.state == "thinking" {
                                HStack(spacing: 8) {
                                    ProgressView().controlSize(.small)
                                    Text("Claude is writing…").foregroundStyle(.secondary)
                                }
                                .padding(.leading, 4)
                            }
                        }
                    }
                case "confirming", "sending":
                    HStack(spacing: 6) {
                        ForEach(Array(engine.glosses.enumerated()), id: \.offset) { _, g in Keycap(text: g, tint: .secondary) }
                    }
                    Text(engine.sentence ?? "").font(.system(size: 28, weight: .semibold, design: .rounded))
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 8) {
                        Label(RouteInfo.label(target: engine.target), systemImage: RouteInfo.icon)
                            .foregroundStyle(Brand.accent).font(.headline)
                        Spacer()
                        if engine.state == "confirming" {
                            Keycap(text: "YES", tint: Brand.detected)
                            Text("or").foregroundStyle(.secondary)
                            Keycap(text: "FINISH", tint: Brand.accent)
                            Text("sends").foregroundStyle(.secondary)
                            Keycap(text: "NO", tint: .secondary)
                            Text("cancels").foregroundStyle(.secondary)
                        } else {
                            ProgressView().controlSize(.small)
                        }
                    }
                default:
                    SignHints(waiting: true, mock: engine.mockRecognizer)
                }
                AutocompleteBar(engine: engine)
                FloorStatus(engine: engine)
                if engine.state == "idle", let last = engine.log.last {  // e.g. what was just sent, or an error
                    Text(last).font(.caption).foregroundStyle(.tertiary)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 74, alignment: .topLeading)
        }
        .fixedSize(horizontal: false, vertical: true)
        .animation(.easeInOut(duration: 0.2), value: engine.state)
        .animation(.easeInOut(duration: 0.15), value: engine.autocomplete)
    }

    private var title: String {
        switch engine.state {
        case "thinking": "Writing it in English"
        case "confirming": "Ready to say"
        case "sending": "Saying it"
        case "listening": engine.autocomplete != nil ? "Spelling" : "Signing"
        default: "Ready"
        }
    }
    private var icon: String {
        switch engine.state {
        case "thinking": "sparkles"
        case "confirming", "sending": "text.bubble.fill"
        default: engine.autocomplete != nil ? "character.cursor.ibeam" : "hand.raised.fill"
        }
    }
    private var tint: Color {
        switch engine.state {
        case "thinking": Brand.indigo
        case "confirming", "sending": Brand.detected
        case "listening": Brand.signing
        default: Brand.accent
        }
    }

    @ViewBuilder private var input: some View {
        if engine.mockRecognizer { MockSignBox(engine: engine) } else { SpellBox(engine: engine) }
    }

    private var controls: some View {
        HStack(spacing: 10) {
            switch engine.state {
            case "idle":
                Button { engine.gesture("wake") } label: { Label("Start", systemImage: "hand.raised.fill") }
                    .buttonStyle(.borderedProminent)
            case "confirming":
                Button { engine.gesture("confirm") } label: { Label("Send", systemImage: "paperplane.fill") }
                    .buttonStyle(.borderedProminent).tint(Brand.detected)
                Button { engine.gesture("cancel") } label: { Label("Cancel", systemImage: "xmark") }
            default:
                if engine.state == "listening" && !engine.glosses.isEmpty {
                    Button { engine.gesture("confirm") } label: { Label("Finish", systemImage: "paperplane.fill") }
                        .buttonStyle(.borderedProminent)
                        .help("Send what you've signed (the FINISH sign)")
                }
                Button { engine.gesture("cancel") } label: { Label("Cancel", systemImage: "xmark") }
            }
            // NOW: say it right away instead of waiting for the pause (or end the sentence that way).
            if engine.speechState == "waiting" || (engine.state == "listening" && !engine.glosses.isEmpty) {
                Button { engine.gesture("now") } label: { Label("Say now", systemImage: "bolt.fill") }
                    .tint(Brand.signing)
                    .help("Speak right away, without waiting for a pause (the NOW sign)")
            }
            Spacer()
        }
        .controlSize(.large)
    }
}

/// What to sign, as keycaps: shown while nothing has been signed yet.
struct SignHints: View {
    var waiting = false
    var mock = false
    var large = false
    var body: some View {
        VStack(alignment: .leading, spacing: large ? 14 : 10) {
            Text(mock ? "Type signs below to start." : waiting ? "Raise your hands into the box to sign." : "Sign inside the box, then drop your hands.")
                .font(.system(size: large ? 34 : 20, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary.opacity(0.85))
            FlowRow(spacing: large ? 22 : 14) {
                hint("FINISH", Brand.accent, "sends")
                hint("NOW", Brand.signing, "says it right away")
                hint("YES", Brand.detected, "takes a suggestion")
            }
            .font(large ? .title3 : .callout)
        }
    }
}

extension SignHints {
    private func hint(_ sign: String, _ tint: Color, _ what: String) -> some View {
        HStack(spacing: 6) {
            Keycap(text: sign, tint: tint).scaleEffect(large ? 1.3 : 1).padding(.horizontal, large ? 6 : 0)
            Text(what).foregroundStyle(.secondary).fixedSize()
        }
    }
}

/// A held fingerspelled letter and how long until it counts.
struct LetterHold: View {
    let letter: String
    let progress: Double
    var large = false
    var body: some View {
        let s: CGFloat = large ? 1.5 : 1
        HStack(spacing: 12 * s) {
            ZStack {
                Circle().stroke(.white.opacity(0.2), lineWidth: 4 * s)
                Circle().trim(from: 0, to: progress).stroke(Brand.signing, style: StrokeStyle(lineWidth: 4 * s, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text(letter).font(.system(size: 22 * s, weight: .heavy, design: .rounded))
            }
            .frame(width: 46 * s, height: 46 * s)
            VStack(alignment: .leading, spacing: 2) {
                Text("Letter \(letter)").font(.system(size: 17 * s, weight: .bold))
                Text(progress >= 1 ? "Got it" : "Hold still…").font(.system(size: 13 * s)).foregroundStyle(.secondary)
            }
        }
        .padding(.leading, 8 * s).padding(.trailing, 18 * s).padding(.vertical, 8 * s)
        .background(.ultraThinMaterial, in: Capsule())
        .overlay(Capsule().strokeBorder(Brand.signing.opacity(0.5)))
    }
}

/// Lays children out left to right, wrapping onto new lines (gloss chips).
struct FlowRow: Layout {
    var spacing: CGFloat = 8
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(proposal.width ?? .infinity, subviews)
        return CGSize(width: rows.map(\.width).max() ?? 0, height: rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(0, rows.count - 1)))
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(bounds.width, subviews) {
            var x = bounds.minX
            for i in row.items {
                let size = subviews[i].sizeThatFits(.unspecified)
                subviews[i].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: .unspecified)
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }
    private func arrange(_ width: CGFloat, _ subviews: Subviews) -> [(items: [Int], width: CGFloat, height: CGFloat)] {
        var rows: [(items: [Int], width: CGFloat, height: CGFloat)] = [([], 0, 0)]
        for (i, view) in subviews.enumerated() {
            let size = view.sizeThatFits(.unspecified)
            if !rows[rows.count - 1].items.isEmpty, rows[rows.count - 1].width + spacing + size.width > width {
                rows.append(([], 0, 0))
            }
            let gap = rows[rows.count - 1].items.isEmpty ? 0 : spacing
            rows[rows.count - 1].items.append(i)
            rows[rows.count - 1].width += gap + size.width
            rows[rows.count - 1].height = max(rows[rows.count - 1].height, size.height)
        }
        return rows
    }
}

/// The sentences said for you so far, newest at the bottom and brightest.
struct SentList: View {
    @ObservedObject var engine: EngineClient
    var maxHeight: CGFloat
    private var said: [String] { engine.meetLog.filter { $0.who == "you" }.suffix(40).map(\.text) }
    var body: some View {
        Card(title: "Said in the call", icon: RouteInfo.icon, tint: Brand.detected, trailing: {
            if !said.isEmpty { Text("\(said.count)").font(.caption.weight(.bold).monospacedDigit()).foregroundStyle(.tertiary) }
        }) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        if said.isEmpty {
                            Text("Sentences you send show up here.").foregroundStyle(.tertiary)
                        }
                        ForEach(Array(said.enumerated()), id: \.offset) { i, text in
                            let latest = i == said.count - 1
                            HStack(alignment: .firstTextBaseline, spacing: 10) {
                                Image(systemName: "checkmark.circle.fill").font(.callout)
                                    .foregroundStyle(Brand.detected.opacity(latest ? 1 : 0.5))
                                Text(text).font(.system(size: latest ? 19 : 16, weight: latest ? .semibold : .regular))
                                    .foregroundStyle(latest ? .primary : .secondary)
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .id(i)
                        }
                    }
                }
                .onChange(of: said.count) { _, n in proxy.scrollTo(n - 1, anchor: .bottom) }
            }
        }
        .frame(maxHeight: maxHeight)
    }
}

/// One-tap replies spoken in your voice. Urgent ones (orange) are said right away; the rest
/// wait for a pause, like anything you sign.
struct QuickReplies: View {
    @ObservedObject var engine: EngineClient
    var size: ControlSize = .regular
    var body: some View {
        if !engine.quickReplies.isEmpty {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: size == .large ? 220 : 150), spacing: 8)],
                      alignment: .leading, spacing: 8) {
                ForEach(engine.quickReplies, id: \.text) { reply in
                    Button { engine.quickReply(reply.text) } label: {
                        HStack(spacing: 6) {
                            if reply.urgent { Image(systemName: "bolt.fill") }
                            Text(reply.text).lineLimit(1)
                        }
                        .frame(maxWidth: .infinity)
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
            HStack(spacing: 10) {
                IconBadge(systemName: icon, tint: color, size: 26)
                Text(text).font(font).foregroundStyle(color).lineLimit(2)
            }
            .padding(.vertical, 6).padding(.horizontal, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .transition(.opacity)
        }
    }
    private var line: (String, String, Color)? {
        switch engine.speechState {
        case "waiting":
            return ("hourglass", "Waiting for a pause to say: \u{201C}\(engine.speechText)\u{201D}", Brand.signing)
        case "interjecting":
            return ("hand.raised.fill", "Jumping in: \u{201C}Sorry, can I jump in?\u{201D}", .orange)
        case "speaking":
            return ("speaker.wave.2.fill", "Speaking: \u{201C}\(engine.speechText)\u{201D}", Brand.accent)
        default:
            return engine.themTalking ? ("waveform", "They're talking", .secondary) : nil
        }
    }
}

/// Always visible: whether the webcam is on. Video never leaves the Mac.
struct CameraIndicator: View {
    let on: Bool
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(on ? Color.red : Color.gray).frame(width: 7, height: 7)
            Text(on ? "Camera on" : "Camera off")
        }
        .font(.subheadline.weight(.semibold))
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background((on ? Color.red : Color.gray).opacity(0.16), in: Capsule())
        .foregroundStyle(on ? Color(red: 1, green: 0.45, blue: 0.42) : .secondary)
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
        .overlay(Capsule().strokeBorder(color.opacity(0.3)))
        .foregroundStyle(color)
    }
    private var label: String {
        ["idle": "Ready", "listening": "Listening", "thinking": "Thinking", "confirming": "Confirm",
         "sending": "Speaking"][state] ?? state
    }
    private var color: Color {
        ["idle": .gray, "listening": Brand.accent, "thinking": Brand.indigo, "confirming": Brand.signing,
         "sending": Brand.detected][state] ?? .gray
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
