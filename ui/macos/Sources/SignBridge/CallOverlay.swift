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
        let size = NSSize(width: 820, height: 96)
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
        HStack(spacing: 14) {
            SignStateDot(state: engine.signState)
            VStack(alignment: .leading, spacing: 4) {
                signing.lineLimit(1)
                voice.lineLimit(1)
            }
            Spacer(minLength: 8)
            if engine.speechState == "waiting" || (engine.state == "listening" && !engine.glosses.isEmpty) {
                Button { engine.gesture("now") } label: { Label("Say now", systemImage: "bolt.fill") }
                    .help("Speak right away, without waiting for a pause (the NOW sign)")
            }
            if engine.state == "confirming" {
                Button { engine.gesture("confirm") } label: { Label("Send", systemImage: "checkmark") }.tint(.green)
                Button { engine.gesture("cancel") } label: { Image(systemName: "xmark") }
            }
            Menu {
                ForEach(engine.quickReplies, id: \.text) { reply in
                    Button(reply.urgent ? "\(reply.text)  (right away)" : reply.text) { engine.quickReply(reply.text) }
                }
            } label: {
                Image(systemName: "text.bubble")
            }
            .menuStyle(.borderlessButton).fixedSize()
            .help("Quick replies, said in your voice")
            Button(action: openPreview) { Image(systemName: "macwindow") }
                .buttonStyle(.borderless).help("Open SignBridge")
            Button(action: close) { Image(systemName: "xmark.circle.fill") }
                .buttonStyle(.borderless).foregroundStyle(.secondary).help("Hide (menu bar > Call Overlay)")
        }
        .controlSize(.large)
        .padding(.horizontal, 18).padding(.vertical, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.ultraThickMaterial, in: RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).strokeBorder(SignStateDot.color(engine.signState).opacity(0.7), lineWidth: 2))
        .environment(\.colorScheme, .dark)
        .tint(Brand.accent)
    }

    /// Line 1: the letter being held, the word being spelled and its suggestion, or the signs so far.
    @ViewBuilder private var signing: some View {
        if let h = engine.holding {
            HStack(spacing: 10) {
                Text("Letter \(h.0)").font(.title3.weight(.bold))
                ProgressView(value: h.1).frame(width: 120).tint(.white)
            }
        } else if let a = engine.autocomplete {
            HStack(spacing: 10) {
                Text(a.letters.map(String.init).joined(separator: " ")).font(.title3.weight(.bold).monospaced())
                if let top = a.top {
                    Image(systemName: "arrow.right").foregroundStyle(.secondary)
                    Text(top.term).font(.title3.weight(.semibold)).foregroundStyle(Brand.accent)
                    Text("sign YES to use it").foregroundStyle(.secondary)
                }
            }
        } else if !engine.glosses.isEmpty {
            Text(engine.glosses.joined(separator: "  ")).font(.title3.weight(.semibold))
        } else if engine.state == "thinking" {
            Text("Writing it in English…").font(.title3).foregroundStyle(.secondary)
        } else if engine.state == "confirming", let sentence = engine.sentence {
            Text("\u{201C}\(sentence)\u{201D}  Sign YES to say it").font(.title3.weight(.semibold))
        } else {
            Text(engine.cameraOn ? "Sign when you're ready" : "SignBridge is paused").font(.title3).foregroundStyle(.secondary)
        }
    }

    /// Line 2: what the voice is doing, or the last thing it said.
    @ViewBuilder private var voice: some View {
        switch engine.speechState {
        case "waiting":
            Label("Waiting for a pause to say: \u{201C}\(engine.speechText)\u{201D}", systemImage: "hourglass").foregroundStyle(.yellow)
        case "interjecting":
            Label("Jumping in…", systemImage: "hand.raised.fill").foregroundStyle(.orange)
        case "speaking":
            Label("Speaking: \u{201C}\(engine.speechText)\u{201D}", systemImage: "speaker.wave.2.fill").foregroundStyle(Brand.accent)
        default:
            if let said = engine.meetLog.last(where: { $0.who == "you" })?.text {
                Label("Said: \u{201C}\(said)\u{201D}", systemImage: "checkmark.circle").foregroundStyle(.secondary)
            } else if engine.themTalking {
                Label("They're talking", systemImage: "waveform").foregroundStyle(.secondary)
            } else {
                Text(" ")
            }
        }
    }
}

/// The signing box's state as a dot: gray hands down, yellow signing, green recognized.
struct SignStateDot: View {
    let state: String?
    var body: some View {
        Circle().fill(Self.color(state)).frame(width: 18, height: 18)
            .overlay(Circle().strokeBorder(.white.opacity(0.3), lineWidth: 1))
            .help(["signing": "Signing", "detected": "Sign recognized: drop your hands for the next"][state ?? ""] ?? "Hands down")
    }
    static func color(_ state: String?) -> Color {
        switch state {
        case "signing": .yellow
        case "detected": .green
        default: .gray
        }
    }
}
