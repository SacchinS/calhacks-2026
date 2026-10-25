import AppKit
import SwiftUI

/// SignBridge's look: native macOS. Standard dark grays and one solid accent (the system accent
/// color, blue by default). No gradients or glows.
enum Brand {
    static let accent = Color.accentColor
    static let background = Color(white: 0.118)  // #1E1E1E, a macOS dark window
    static let stage = Color(white: 0.09)        // Demo Mode, a little darker for the projector
    static let surface = Color(white: 0.165)     // #2A2A2A, cards on the background

    /// Menu bar glyph from the bundle (a template image, so it follows light and dark menu bars).
    static func menuBarImage(listening: Bool) -> NSImage? {
        let name = listening ? "menubar-on" : "menubar"
        guard let url = Bundle.main.url(forResource: name, withExtension: "svg"), let image = NSImage(contentsOf: url)
        else { return NSImage(systemSymbolName: listening ? "hand.raised.fill" : "hand.raised",
                              accessibilityDescription: "SignBridge") }
        image.size = NSSize(width: 18, height: 18)
        image.isTemplate = true
        image.accessibilityDescription = "SignBridge"
        return image
    }
}

/// The app icon, or an accent-colored tile when running unbundled (swift run).
struct Logo: View {
    var size: CGFloat = 64
    var body: some View {
        if Bundle.main.url(forResource: "AppIcon", withExtension: "icns") != nil {
            Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: size, height: size)
        } else {
            RoundedRectangle(cornerRadius: size * 0.225).fill(Brand.accent).frame(width: size * 0.8, height: size * 0.8)
                .overlay(Image(systemName: "hand.raised").font(.system(size: size * 0.4)).foregroundStyle(.white))
                .frame(width: size, height: size)
        }
    }
}

/// The app's name as a title.
struct TitleText: View {
    let text: String, font: Font
    init(_ text: String, font: Font) { self.text = text; self.font = font }
    var body: some View {
        Text(text).font(font).foregroundStyle(.primary)
    }
}

/// A small rounded tag, used for recognized signs.
struct Chip: View {
    let text: String
    var body: some View {
        Text(text).font(.system(.title3).weight(.semibold))
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Brand.accent.opacity(0.18), in: Capsule())
            .overlay(Capsule().strokeBorder(Brand.accent.opacity(0.45)))
    }
}

/// A dot that pulses while something is live.
struct PulseDot: View {
    let color: Color
    var active = true
    @State private var on = false
    var body: some View {
        Circle().fill(color).frame(width: 9, height: 9)
            .overlay(Circle().stroke(color, lineWidth: 2).scaleEffect(on ? 2.2 : 1).opacity(on ? 0 : 0.8))
            .onAppear { on = active }
            .animation(active ? .easeOut(duration: 1.1).repeatForever(autoreverses: false) : .default, value: on)
            .onChange(of: active) { _, a in on = a }
    }
}

extension NSAttributedString {
    func appending(_ other: NSAttributedString) -> NSAttributedString {
        let s = NSMutableAttributedString(attributedString: self)
        s.append(other)
        return s
    }
}

/// The native translucent sidebar background.
struct SidebarBackground: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let v = NSVisualEffectView()
        v.material = .sidebar
        v.blendingMode = .behindWindow
        v.state = .followsWindowActiveState
        return v
    }
    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {}
}

/// Where the English goes: spoken in the call.
enum RouteInfo {
    static let icon = "speaker.wave.2.fill"
    static func label(target: String?) -> String { "Say it in \(target ?? "the call")" }
}

/// The Meet demo's draft glosses (MVP.md, docs/asl-demo-script-research.md), in demo order, in
/// the mock-sign syntax (`#word` = a fingerspelled word). Demo Mode's backup keys 1-3 and
/// Preview's test phrases. Live, the words are spelled P-R and F-I and autocomplete finishes
/// them. A Deaf signer must approve them before the demo.
enum DemoScript {
    static let phrases: [[String]] = [
        ["HELLO,", "#PRIYANKA,", "NICE", "MEET-YOU"],   // 1 greeting, with the name heard in the call
        ["#FIGMA"],                                     // 2 "where should we put the feedback?"
        ["THANK-YOU"],                                  // 3
    ]
    static func label(_ phrase: [String]) -> String { phrase.joined(separator: " ") }
}

/// How each control gesture is shown.
enum GestureInfo {
    static func name(_ g: String) -> String {
        if g.count == 1 { return "Letter \(g)" }  // a fingerspelled letter being held
        return ["wake": "Start", "confirm": "Send", "cancel": "Cancel"][g] ?? g.capitalized
    }
    static func icon(_ g: String) -> String {
        if g.count == 1 { return "hand.point.up.left" }
        return ["wake": "hand.raised", "confirm": "hand.thumbsup", "cancel": "hand.thumbsdown"][g] ?? "hand.raised"
    }
}
