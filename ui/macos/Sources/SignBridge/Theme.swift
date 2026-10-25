import AppKit
import SwiftUI

/// SignBridge's look: native macOS dark windows, cards with icon headers, and one brand blue
/// (the app icon's #0A84FF) that leans into indigo where it's the hero. Colors carry meaning:
/// yellow while signing, green when a sign is recognized or said, the brand while speaking.
enum Brand {
    static let accent = Color(red: 0.04, green: 0.52, blue: 1.0)       // #0A84FF, the app icon
    static let indigo = Color(red: 0.37, green: 0.36, blue: 0.90)      // #5E5CE6
    static let gradient = LinearGradient(colors: [accent, indigo], startPoint: .topLeading, endPoint: .bottomTrailing)
    static let signing = Color(red: 1.0, green: 0.78, blue: 0.20)      // the box while signing
    static let detected = Color(red: 0.20, green: 0.83, blue: 0.53)    // recognized, said
    static let background = Color(white: 0.105)
    static let stage = Color(white: 0.075)       // Demo Mode, a little darker for the projector
    static let surface = Color(white: 0.155)     // cards on the background
    static let raised = Color(white: 0.20)       // things inside cards
    static let hairline = Color.white.opacity(0.08)

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

/// The app icon, or the same design drawn here when running unbundled (swift run): a hand and
/// a speech bubble on the brand tile.
struct Logo: View {
    var size: CGFloat = 64
    var body: some View {
        if Bundle.main.url(forResource: "AppIcon", withExtension: "icns") != nil {
            Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: size, height: size)
        } else {
            RoundedRectangle(cornerRadius: size * 0.225, style: .continuous).fill(Brand.gradient)
                .overlay(RoundedRectangle(cornerRadius: size * 0.225, style: .continuous)
                    .strokeBorder(.white.opacity(0.25), lineWidth: max(0.5, size / 80)))
                .overlay(alignment: .bottomLeading) {
                    Image(systemName: "hand.raised").font(.system(size: size * 0.38, weight: .semibold))
                        .padding(.leading, size * 0.13).padding(.bottom, size * 0.11)
                }
                .overlay(alignment: .topTrailing) {
                    Image(systemName: "ellipsis.bubble.fill").font(.system(size: size * 0.22, weight: .semibold))
                        .padding(.trailing, size * 0.1).padding(.top, size * 0.1)
                }
                .foregroundStyle(.white)
                .shadow(color: Brand.accent.opacity(0.35), radius: size * 0.08, y: size * 0.03)
                .frame(width: size * 0.86, height: size * 0.86)
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

/// A recognized sign, as a tag.
struct Chip: View {
    let text: String
    var size: CGFloat = 20
    var body: some View {
        Text(text).font(.system(size: size, weight: .bold, design: .rounded)).tracking(0.5)
            .padding(.horizontal, size * 0.7).padding(.vertical, size * 0.35)
            .background(Brand.accent.opacity(0.16), in: RoundedRectangle(cornerRadius: size * 0.5, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: size * 0.5, style: .continuous).strokeBorder(Brand.accent.opacity(0.5)))
    }
}

/// A sign's name the way a keyboard shows a key, for "FINISH sends" hints.
struct Keycap: View {
    let text: String
    var tint: Color = .white
    var body: some View {
        Text(text).font(.system(size: 11, weight: .heavy, design: .rounded)).tracking(0.6)
            .foregroundStyle(tint)
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 5, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 5, style: .continuous).strokeBorder(tint.opacity(0.35)))
    }
}

/// An SF Symbol on a tinted rounded square: card headers, settings rows, status lines.
struct IconBadge: View {
    let systemName: String
    var tint: Color = Brand.accent
    var size: CGFloat = 26
    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: size * 0.5, weight: .semibold))
            .foregroundStyle(tint)
            .frame(width: size, height: size)
            .background(tint.opacity(0.16), in: RoundedRectangle(cornerRadius: size * 0.3, style: .continuous))
    }
}

/// A titled panel: an icon badge and title on top, then the content. Everything in the main
/// window, Demo Mode and Settings sits in one of these.
struct Card<Content: View, Trailing: View>: View {
    let title: String
    let icon: String
    var tint: Color = Brand.accent
    var padding: CGFloat = 16
    @ViewBuilder var trailing: Trailing
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                IconBadge(systemName: icon, tint: tint, size: 24)
                Text(title.uppercased()).font(.system(size: 11, weight: .bold)).tracking(1.1).foregroundStyle(.secondary)
                Spacer(minLength: 0)
                trailing
            }
            content
        }
        .padding(padding)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Brand.hairline))
    }
}

extension Card where Trailing == EmptyView {
    init(title: String, icon: String, tint: Color = Brand.accent, padding: CGFloat = 16,
         @ViewBuilder content: () -> Content) {
        self.init(title: title, icon: icon, tint: tint, padding: padding, trailing: { EmptyView() }, content: content)
    }
}

/// The signing box's state, the same colors as the box drawn on the camera: gray hands down,
/// yellow signing, green when a sign was recognized.
enum SignState {
    static func color(_ state: String?) -> Color {
        switch state {
        case "signing": Brand.signing
        case "detected": Brand.detected
        default: Color(white: 0.5)
        }
    }
    static func icon(_ state: String?) -> String {
        switch state {
        case "signing": "hand.raised.fill"
        case "detected": "checkmark"
        default: "hand.raised"
        }
    }
    static func label(_ state: String?) -> String {
        switch state {
        case "signing": "Signing"
        case "detected": "Got it: drop your hands"
        default: "Hands down"
        }
    }
}

/// The signing state as a round badge, pulsing while signing.
struct SignStateBadge: View {
    let state: String?
    var size: CGFloat = 44
    @State private var pulse = false
    var body: some View {
        let color = SignState.color(state)
        ZStack {
            Circle().fill(color.opacity(0.18))
            Circle().strokeBorder(color, lineWidth: max(2, size / 16))
            Image(systemName: SignState.icon(state)).font(.system(size: size * 0.42, weight: .bold)).foregroundStyle(color)
                .contentTransition(.symbolEffect(.replace))
        }
        .frame(width: size, height: size)
        .background(
            Circle().stroke(color.opacity(0.6), lineWidth: 2)
                .scaleEffect(pulse ? 1.45 : 1).opacity(pulse ? 0 : 0.9)
                .opacity(state == "signing" ? 1 : 0)
        )
        .animation(.easeInOut(duration: 0.25), value: state)
        .onAppear {
            withAnimation(.easeOut(duration: 1.2).repeatForever(autoreverses: false)) { pulse = true }
        }
        .help(SignState.label(state))
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
/// Preview's test phrases (the release check-in in MVP.md). Live, the words are spelled F and
/// P, one letter each, and autocomplete finishes them. A Deaf signer must approve them before the demo.
enum DemoScript {
    static let phrases: [[String]] = [
        ["#FIGMA", "COLOR", "PROBLEM"],              // 1 "There's a color problem in Figma."
        ["ME", "MEET", "#PRANAV", "TOMORROW"],        // 2 "I'll meet with Pranav tomorrow."
        ["HELLO,", "NICE", "MEET", "YOU"],            // 3 a greeting, to open the call
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
