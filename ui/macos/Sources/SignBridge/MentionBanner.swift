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
        HStack(alignment: .center, spacing: 18) {
            Image(systemName: mention.question ? "questionmark" : "person.wave.2.fill")
                .font(.system(size: 30, weight: .heavy))
                .foregroundStyle(Color.yellow)
                .frame(width: 64, height: 64)
                .background(Color.black, in: Circle())
                .scaleEffect(flash ? 1.08 : 1)
            VStack(alignment: .leading, spacing: 6) {
                Text(title.uppercased()).font(.system(size: 14, weight: .heavy)).tracking(1.2).opacity(0.7)
                Text("\u{201C}\(mention.text)\u{201D}").font(.system(size: 26, weight: .bold, design: .rounded))
                    .lineLimit(2).minimumScaleFactor(0.7)
            }
            Spacer(minLength: 0)
        }
        .foregroundStyle(.black)
        .padding(.horizontal, 22).padding(.vertical, 16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .background(
            LinearGradient(colors: [Color(red: 1, green: 0.88, blue: 0.3), Color(red: 1, green: 0.74, blue: 0.16)],
                           startPoint: .topLeading, endPoint: .bottomTrailing),
            in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous)
            .strokeBorder(Color.white.opacity(flash ? 0.9 : 0.3), lineWidth: flash ? 6 : 1.5))
        .shadow(color: .black.opacity(0.35), radius: 16, y: 6)
        .padding(10)
        .onTapGesture(perform: dismiss)
        .onAppear {
            withAnimation(.easeInOut(duration: 0.35).repeatCount(5, autoreverses: true)) { flash = true }
        }
        .help("Click to dismiss")
    }

    private var title: String {
        let who = name.isEmpty ? "You" : name
        return mention.question ? "\(who), you were asked" : "\(who), you were mentioned"
    }
}
