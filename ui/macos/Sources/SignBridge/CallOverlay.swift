import AppKit
import Combine
import SwiftUI

/// SignBridge during a call: a slim strip that floats over every window (fullscreen Meet
/// included) and never takes focus, so the signer watches Meet, not a second window. It shows
/// the signing state, what's been signed, the autocomplete while spelling, what the voice is
/// doing, and one-tap replies. Drag it anywhere; it remembers where.
@MainActor
final class CallOverlay {
    static let shownKey = "callOverlayShown"
    private static let originKey = "callOverlayOrigin"
    private let engine: EngineClient
    private let openPreview: () -> Void
    private var panel: NSPanel?
    private var moved: NSObjectProtocol?

    var isShown: Bool { panel?.isVisible ?? false }

    init(engine: EngineClient, openPreview: @escaping () -> Void) {
        self.engine = engine
        self.openPreview = openPreview
    }

    func toggle() { isShown ? hide() : show() }

    func show() {
        let panel = self.panel ?? makePanel()
        self.panel = panel
        let size = NSSize(width: 880, height: 112)
        if let saved = UserDefaults.standard.string(forKey: Self.originKey) {
            panel.setFrame(NSRect(origin: NSPointFromString(saved), size: size), display: true)
        } else if let screen = NSScreen.main {
            // Bottom middle, above Meet's own control bar.
            let f = screen.visibleFrame
            panel.setFrame(NSRect(x: f.midX - size.width / 2, y: f.minY + 96, width: size.width, height: size.height), display: true)
        }
        panel.orderFrontRegardless()
        UserDefaults.standard.set(true, forKey: Self.shownKey)
    }

    func hide() {
        panel?.orderOut(nil)
        UserDefaults.standard.set(false, forKey: Self.shownKey)
    }

    private func makePanel() -> NSPanel {
        let p = NSPanel(contentRect: .zero, styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: false)
        p.level = .floating
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.hidesOnDeactivate = false
        p.isMovableByWindowBackground = true
        p.contentView = NSHostingView(rootView: CallOverlayView(
            engine: engine, openPreview: openPreview, close: { [weak self] in self?.hide() }))
        let key = Self.originKey
        moved = NotificationCenter.default.addObserver(forName: NSWindow.didMoveNotification, object: p, queue: .main) { [weak p] _ in
            guard let origin = p?.frame.origin else { return }
            UserDefaults.standard.set(NSStringFromPoint(origin), forKey: key)
        }
        return p
    }
}

struct CallOverlayView: View {
    @ObservedObject var engine: EngineClient
    let openPreview: () -> Void
    let close: () -> Void

    var body: some View {
        HStack(spacing: 16) {
            SignStateBadge(state: engine.signState, size: 52)
            VStack(alignment: .leading, spacing: 6) {
                signing.lineLimit(1)
                voice.lineLimit(1)
            }
            Spacer(minLength: 8)
            if engine.state == "confirming" {
                Button { engine.gesture("confirm") } label: { Label("Send", systemImage: "paperplane.fill") }
                    .buttonStyle(PillButtonStyle(fill: Brand.detected))
                OverlayButton(icon: "xmark", help: "Cancel (NO)") { engine.gesture("cancel") }
            } else if engine.speechState == "waiting" || (engine.state == "listening" && !engine.glosses.isEmpty) {
                Button { engine.gesture("now") } label: { Label("Say now", systemImage: "bolt.fill") }
                    .buttonStyle(PillButtonStyle(fill: Brand.signing, text: .black))
                    .help("Speak right away, without waiting for a pause (the NOW sign)")
            }
            Divider().frame(height: 40).overlay(Color.white.opacity(0.12))
            Menu {
                Button("Introduce me") { engine.introduce() }
                Divider()
                ForEach(engine.quickReplies, id: \.text) { reply in
                    Button(reply.urgent ? "\(reply.text)  (right away)" : reply.text) { engine.quickReply(reply.text) }
                }
            } label: {
                OverlayIcon(icon: "text.bubble.fill")
            }
            .menuStyle(.button).buttonStyle(.plain).menuIndicator(.hidden).fixedSize()
            .help("Quick replies, said in your voice")
            OverlayButton(icon: "macwindow", help: "Open SignBridge", action: openPreview)
            OverlayButton(icon: "chevron.down", help: "Hide (menu bar > Call Overlay)", action: close)
        }
        .controlSize(.large)
        .padding(.leading, 20).padding(.trailing, 16).padding(.vertical, 14)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.ultraThickMaterial, in: RoundedRectangle(cornerRadius: 26, style: .continuous))
        .background(Color.black.opacity(0.35), in: RoundedRectangle(cornerRadius: 26, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 26, style: .continuous)
            .strokeBorder(LinearGradient(colors: [SignState.color(engine.signState).opacity(0.9),
                                                  SignState.color(engine.signState).opacity(0.25)],
                                         startPoint: .leading, endPoint: .trailing), lineWidth: 2))
        .animation(.easeInOut(duration: 0.25), value: engine.signState)
        .environment(\.colorScheme, .dark)
        .tint(Brand.accent)
    }

    /// Line 1: the letter being held, the word being spelled and its suggestion, or the signs so far.
    @ViewBuilder private var signing: some View {
        if let h = engine.holding {
            HStack(spacing: 12) {
                Text(h.0).font(.system(size: 22, weight: .heavy, design: .rounded))
                    .frame(width: 34, height: 34).background(Brand.raised, in: RoundedRectangle(cornerRadius: 8))
                ProgressView(value: h.1).frame(width: 160).tint(Brand.signing)
                Text("Hold still…").font(.title3).foregroundStyle(.secondary)
            }
        } else if let a = engine.autocomplete {
            HStack(spacing: 10) {
                Text(a.letters.map(String.init).joined(separator: " ")).font(.system(size: 24, weight: .heavy, design: .rounded))
                if let top = a.top {
                    Image(systemName: "arrow.right").font(.headline).foregroundStyle(.tertiary)
                    Text(top.term).font(.system(size: 24, weight: .bold, design: .rounded))
                        .padding(.horizontal, 10).padding(.vertical, 1)
                        .background(Brand.gradient, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    Keycap(text: "YES", tint: Brand.detected)
                    Text("to use it").foregroundStyle(.secondary)
                }
            }
        } else if !engine.glosses.isEmpty {
            HStack(spacing: 8) {
                ForEach(Array(engine.glosses.suffix(6).enumerated()), id: \.offset) { _, g in Chip(text: g, size: 17) }
            }
        } else if engine.state == "thinking" {
            Label("Writing it in English…", systemImage: "sparkles").font(.title2.weight(.semibold)).foregroundStyle(Brand.indigo)
        } else if engine.state == "confirming", let sentence = engine.sentence {
            Text("\u{201C}\(sentence)\u{201D}").font(.title2.weight(.semibold))
        } else {
            Text(engine.cameraOn ? "Sign when you're ready" : "SignBridge is paused")
                .font(.title2.weight(.semibold)).foregroundStyle(.secondary)
        }
    }

    /// Line 2: what the voice is doing, or the last thing it said.
    @ViewBuilder private var voice: some View {
        Group {
            switch engine.speechState {
            case "waiting":
                Label("Waiting for a pause: \u{201C}\(engine.speechText)\u{201D}", systemImage: "hourglass").foregroundStyle(Brand.signing)
            case "interjecting":
                Label("Jumping in…", systemImage: "hand.raised.fill").foregroundStyle(.orange)
            case "speaking":
                Label("Speaking: \u{201C}\(engine.speechText)\u{201D}", systemImage: "speaker.wave.2.fill").foregroundStyle(Brand.accent)
            default:
                if let said = engine.meetLog.last(where: { $0.who == "you" })?.text {
                    Label("Said: \u{201C}\(said)\u{201D}", systemImage: "checkmark.circle.fill").foregroundStyle(.secondary)
                } else if engine.themTalking {
                    Label("They're talking", systemImage: "waveform").foregroundStyle(.secondary)
                } else {
                    Label("FINISH sends · NOW says it right away", systemImage: "hand.raised").foregroundStyle(.tertiary)
                }
            }
        }
        .font(.system(size: 15, weight: .medium))
    }
}

/// A round icon, the overlay's button look.
struct OverlayIcon: View {
    let icon: String
    var body: some View {
        Image(systemName: icon).font(.system(size: 17, weight: .semibold))
            .foregroundStyle(.white.opacity(0.9))
            .frame(width: 40, height: 40)
            .background(Color.white.opacity(0.1), in: Circle())
            .overlay(Circle().strokeBorder(Color.white.opacity(0.12)))
    }
}

/// A filled capsule button drawn by hand: the overlay never takes focus, and macOS draws its own
/// prominent buttons gray in a window that isn't key.
struct PillButtonStyle: ButtonStyle {
    var fill: Color
    var text: Color = .white
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .bold))
            .foregroundStyle(text)
            .padding(.horizontal, 18).frame(height: 40)
            .background(fill.opacity(configuration.isPressed ? 0.75 : 1), in: Capsule())
            .shadow(color: fill.opacity(0.45), radius: 8, y: 2)
            .contentShape(Capsule())
    }
}

struct OverlayButton: View {
    let icon: String, help: String
    let action: () -> Void
    var body: some View {
        Button(action: action) { OverlayIcon(icon: icon) }.buttonStyle(.plain).help(help)
    }
}
