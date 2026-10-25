import SwiftUI

/// Full-screen stage for showing SignBridge to an audience: big camera, big text, and what happened so far.
struct DemoView: View {
    @ObservedObject var engine: EngineClient
    let exit: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 28) {
            VStack(alignment: .leading, spacing: 18) {
                header
                camera
                stage
                FloorStatus(engine: engine, font: .title2.weight(.semibold))
                if let caption = engine.captions.last { captionCard(caption) }
                QuickReplies(engine: engine, size: .large)
            }
            history.frame(width: 360)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(
            ZStack {
                Brand.stage
                RadialGradient(colors: [Brand.indigo.opacity(0.18), .clear], center: .topLeading, startRadius: 0, endRadius: 900)
            }
        )
        .environment(\.colorScheme, .dark)
        .tint(Brand.accent)
        .background { shortcuts }
        .overlay(alignment: .topTrailing) {
            Button("Exit Demo", action: exit).keyboardShortcut(.cancelAction).buttonStyle(.borderless)
                .foregroundStyle(.tertiary).padding(10)
        }
    }

    private var header: some View {
        HStack(spacing: 14) {
            Logo(size: 52)
            VStack(alignment: .leading, spacing: 0) {
                Text("SignBridge").font(.system(size: 32, weight: .heavy, design: .rounded))
                Text("ASL in your Google Meet calls").font(.title3).foregroundStyle(.secondary)
            }
            StatePill(state: engine.state).scaleEffect(1.3).padding(.leading, 18)
            Spacer()
            CameraIndicator(on: engine.cameraOn).scaleEffect(1.2)
            Label("Google Meet", systemImage: "video.fill")
                .font(.title3.weight(.semibold)).foregroundStyle(.white)
                .padding(.horizontal, 16).padding(.vertical, 8)
                .background(Brand.gradient, in: Capsule())
                .padding(.leading, 12)
        }
    }

    private var camera: some View {
        let color = SignState.color(engine.signState)
        return LivePreview(engine: engine, maxHeight: .infinity)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(color.opacity(engine.signState == nil || engine.signState == "idle" ? 0 : 1), lineWidth: 5))
            .overlay(alignment: .topLeading) {
                if engine.signState != nil {
                    HStack(spacing: 12) {
                        SignStateBadge(state: engine.signState, size: 40)
                        Text(SignState.label(engine.signState)).font(.title2.weight(.bold))
                    }
                    .padding(.leading, 8).padding(.trailing, 20).padding(.vertical, 8)
                    .background(.ultraThinMaterial, in: Capsule())
                    .padding(18)
                }
            }
            .overlay(alignment: .bottom) {
                if let h = engine.holding { LetterHold(letter: h.0, progress: h.1, large: true).padding(20) }
            }
            .animation(.easeInOut(duration: 0.25), value: engine.signState)
    }

    /// Backup keys for a live demo: W start, C send, X cancel, N say it now, 1-3 the demo script's phrases.
    private var shortcuts: some View {
        let phrases = DemoScript.phrases
        return ZStack {
            Button("") { engine.gesture("wake") }.keyboardShortcut("w", modifiers: [])
            Button("") { engine.gesture("confirm") }.keyboardShortcut("c", modifiers: [])
            Button("") { engine.gesture("cancel") }.keyboardShortcut("x", modifiers: [])
            Button("") { engine.gesture("now") }.keyboardShortcut("n", modifiers: [])
            ForEach(Array(phrases.enumerated()), id: \.offset) { i, p in
                Button("") { engine.fake(p) }.keyboardShortcut(KeyEquivalent(Character("\(i + 1)")), modifiers: [])
            }
        }
        .opacity(0).allowsHitTesting(false)
    }

    /// What's happening now, sized for the back of the room.
    private var stage: some View {
        VStack(alignment: .leading, spacing: 18) {
            if engine.autocomplete != nil {
                AutocompleteBar(engine: engine, large: true)
            } else {
                switch engine.state {
                case "listening", "thinking":
                    if engine.glosses.isEmpty {
                        SignHints(large: true)
                    } else {
                        HStack(spacing: 14) {
                            ForEach(Array(engine.glosses.enumerated()), id: \.offset) { _, g in
                                Chip(text: g, size: 34).transition(.scale.combined(with: .opacity))
                            }
                            if engine.state == "thinking" {
                                Image(systemName: "arrow.right").font(.title).foregroundStyle(.tertiary)
                                Label("Claude is writing…", systemImage: "sparkles")
                                    .font(.title2.weight(.semibold)).foregroundStyle(Brand.indigo)
                                    .symbolEffect(.pulse)
                            }
                        }
                        .animation(.spring(duration: 0.35), value: engine.glosses)
                    }
                case "confirming", "sending":
                    HStack(spacing: 8) {
                        ForEach(Array(engine.glosses.enumerated()), id: \.offset) { _, g in Keycap(text: g, tint: .secondary) }
                    }
                    .scaleEffect(1.4, anchor: .leading)
                    Text(engine.sentence ?? "").font(.system(size: 54, weight: .bold, design: .rounded))
                        .fixedSize(horizontal: false, vertical: true)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    HStack(spacing: 12) {
                        Label(RouteInfo.label(target: engine.target), systemImage: RouteInfo.icon)
                            .font(.title2.weight(.semibold)).foregroundStyle(Brand.accent)
                        Spacer()
                        if engine.state == "confirming" {
                            Text("Sign YES to send, NO to cancel").font(.title2).foregroundStyle(.secondary)
                        } else {
                            ProgressView()
                            Text("Speaking…").font(.title2).foregroundStyle(.secondary)
                        }
                    }
                default:
                    SignHints(waiting: true, large: true)
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .leading)
        .padding(26)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).strokeBorder(stageBorder, lineWidth: 1.5))
        .fixedSize(horizontal: false, vertical: true)
        .animation(.easeInOut(duration: 0.25), value: engine.state)
    }

    private var stageBorder: Color {
        switch engine.state {
        case "confirming", "sending": Brand.detected.opacity(0.6)
        case "thinking": Brand.indigo.opacity(0.6)
        case "listening": Brand.signing.opacity(0.45)
        default: Brand.hairline
        }
    }

    /// The other side's latest words, as a live caption.
    private func captionCard(_ caption: String) -> some View {
        HStack(alignment: .center, spacing: 16) {
            Text("THEM").font(.system(size: 13, weight: .heavy)).tracking(1.2)
                .foregroundStyle(.black).padding(.horizontal, 10).padding(.vertical, 5)
                .background(Color.white.opacity(0.85), in: Capsule())
            Text(caption).font(.system(size: 30, weight: .semibold)).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).strokeBorder(Brand.hairline))
        .transition(.opacity).id(caption)
    }

    /// Recent phrases, as a timeline: signs, sentence, and whether it was said.
    private var history: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                IconBadge(systemName: "clock.arrow.circlepath", tint: Brand.accent, size: 30)
                Text("CONVERSATION").font(.system(size: 13, weight: .bold)).tracking(1.2).foregroundStyle(.secondary)
            }
            .padding(.top, 64)
            if engine.history.isEmpty {
                Text("Phrases you send or cancel show up here.").foregroundStyle(.tertiary)
            }
            ScrollView {
                VStack(spacing: 0) {
                    ForEach(Array(engine.history.enumerated()), id: \.element.id) { i, item in
                        HStack(alignment: .top, spacing: 14) {
                            VStack(spacing: 0) {
                                Circle().fill(item.sent ? Brand.detected : Color.gray).frame(width: 12, height: 12).padding(.top, 18)
                                Rectangle().fill(Color.white.opacity(i == engine.history.count - 1 ? 0 : 0.12)).frame(width: 2)
                            }
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(item.glosses.joined(separator: " · ")).font(.caption.weight(.bold)).tracking(0.4)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text(item.date, style: .time).font(.caption).foregroundStyle(.tertiary)
                                }
                                Text(item.sentence).font(.system(size: 19, weight: .semibold))
                                    .fixedSize(horizontal: false, vertical: true)
                                Label(item.sent ? "Said in the call" : "Cancelled",
                                      systemImage: item.sent ? "checkmark.circle.fill" : "xmark.circle")
                                    .font(.callout.weight(.medium))
                                    .foregroundStyle(item.sent ? Brand.detected : .secondary)
                            }
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Brand.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Brand.hairline))
                            .padding(.bottom, 12)
                        }
                        .opacity(item.sent ? 1 : 0.6)
                        .transition(.move(edge: .top).combined(with: .opacity))
                    }
                }
                .animation(.spring(duration: 0.4), value: engine.history.map(\.id))
            }
        }
    }
}
