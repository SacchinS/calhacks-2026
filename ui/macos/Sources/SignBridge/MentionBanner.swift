import AppKit
import Combine
import SwiftUI

/// A banner over every window (fullscreen Meet included) when someone says your name: the
/// signer is usually watching the call, not SignBridge, and gets no sound cue. It flashes,
/// shows what was said, never takes focus, and goes away after a few seconds or on click.
@MainActor
final class MentionBanner {
    private let engine: EngineClient
    private var panel: NSPanel?
    private var hideWork: DispatchWorkItem?
    private var watch: AnyCancellable?

    init(engine: EngineClient) {
        self.engine = engine
        watch = engine.$mention.compactMap { $0 }.sink { [weak self] m in self?.show(m) }
    }

    private func show(_ m: EngineClient.MentionAlert) {
        let view = MentionBannerView(mention: m, name: engine.config["signer_name"] as? String ?? "") { [weak self] in
            self?.hide()
        }
        let panel = self.panel ?? makePanel()
        panel.contentView = NSHostingView(rootView: view)
        let size = NSSize(width: 760, height: 150)
        if let screen = NSScreen.main {
            let f = screen.visibleFrame
            panel.setFrame(NSRect(x: f.midX - size.width / 2, y: f.maxY - size.height - 12, width: size.width, height: size.height), display: true)
        }
        panel.orderFrontRegardless()
        self.panel = panel
        hideWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.hide() }
        hideWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + (m.final ? 9 : 12), execute: work)
    }

    private func hide() { panel?.orderOut(nil) }

    private func makePanel() -> NSPanel {
        let p = NSPanel(contentRect: .zero, styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: false)
        p.level = .statusBar
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.hidesOnDeactivate = false
        return p
    }
}

struct MentionBannerView: View {
    let mention: EngineClient.MentionAlert
    let name: String
    let dismiss: () -> Void
    @State private var flash = false

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            Image(systemName: mention.question ? "questionmark.bubble.fill" : "person.wave.2.fill")
                .font(.system(size: 40, weight: .bold))
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.system(size: 22, weight: .heavy))
                Text("\u{201C}\(mention.text)\u{201D}").font(.system(size: 24, weight: .semibold))
                    .lineLimit(3).minimumScaleFactor(0.7)
            }
            Spacer(minLength: 0)
        }
        .foregroundStyle(.black)
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color.yellow, in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).strokeBorder(Color.orange, lineWidth: flash ? 8 : 2))
        .onTapGesture(perform: dismiss)
        .onAppear {
            withAnimation(.easeInOut(duration: 0.35).repeatCount(5, autoreverses: true)) { flash = true }
        }
        .help("Click to dismiss")
    }

    private var title: String {
        let who = name.isEmpty ? "You" : name
        return mention.question ? "\(who), you were asked:" : "\(who), you were mentioned:"
    }
}
