import SwiftUI

/// "How it works" on the welcome page: four steps that light up in turn, each with a small animation.
struct Storyboard: View {
    @State private var active = 0
    private let timer = Timer.publish(every: 2.6, on: .main, in: .common).autoconnect()
    private let steps: [(String, String)] = [
        ("Sign", "Raise your hands into the box: one sign, then drop them."),
        ("Fingerspell", "Spell a letter; it suggests the word."),
        ("Claude writes it", "Your signs become a sentence."),
        ("Said in the call", "FINISH sends it, in your voice."),
    ]

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            ForEach(steps.indices, id: \.self) { i in
                let on = i == active
                VStack(alignment: .leading, spacing: 8) {
                    visual(i, on: on)
                        .frame(maxWidth: .infinity).frame(height: 118)
                        .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
                    HStack(spacing: 6) {
                        Text("\(i + 1)").font(.caption.weight(.bold)).foregroundStyle(.white)
                            .frame(width: 18, height: 18)
                            .background(on ? AnyShapeStyle(Brand.accent) : AnyShapeStyle(Color.secondary.opacity(0.4)),
                                        in: Circle())
                        Text(steps[i].0).font(.headline)
                    }
                    Text(steps[i].1).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .background(.quaternary.opacity(on ? 0.7 : 0.35), in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Brand.accent, lineWidth: on ? 2 : 0))
                .opacity(on ? 1 : 0.55)
                .scaleEffect(on ? 1.0 : 0.97)
                .onTapGesture { active = i }
            }
        }
        .animation(.easeInOut(duration: 0.35), value: active)
        .onReceive(timer) { _ in active = (active + 1) % steps.count }
    }

    @ViewBuilder private func visual(_ i: Int, on: Bool) -> some View {
        switch i {
        case 0:
            ZStack {
                RoundedRectangle(cornerRadius: 8).strokeBorder(on ? Brand.signing : Color.secondary.opacity(0.4), lineWidth: 2.5)
                    .frame(width: 92, height: 72)
                Image(systemName: on ? "hand.raised.fill" : "hand.raised").font(.system(size: 38))
                    .foregroundStyle(on ? Brand.signing : .secondary)
                    .symbolEffect(.bounce, value: on)
            }
        case 1:
            VStack(spacing: 8) {
                Text("P").font(.system(size: 28, weight: .heavy, design: .rounded))
                Image(systemName: "arrow.down").foregroundStyle(.secondary).font(.caption)
                Chip(text: "Pranav").scaleEffect(0.8)
                    .opacity(on ? 1 : 0.25)
                    .animation(.easeIn(duration: 0.5).delay(on ? 0.6 : 0), value: on)
            }
        case 2:
            VStack(spacing: 8) {
                Chip(text: "COLOR PROBLEM", size: 13)
                Image(systemName: "arrow.down").foregroundStyle(.secondary).font(.caption)
                Text("“There's a color problem.”").font(.system(.callout).weight(.semibold)).multilineTextAlignment(.center)
                    .opacity(on ? 1 : 0.25)
                    .animation(.easeIn(duration: 0.5).delay(on ? 0.6 : 0), value: on)
            }
        default:
            VStack(spacing: 6) {
                Image(systemName: "speaker.wave.2.fill").font(.system(size: 40))
                    .foregroundStyle(on ? AnyShapeStyle(Color.green) : AnyShapeStyle(Color.secondary))
                    .symbolEffect(.bounce, value: on)
                Label("Spoken", systemImage: "checkmark.circle.fill").font(.caption.weight(.semibold))
                    .foregroundStyle(.green).opacity(on ? 1 : 0)
                    .animation(.easeIn(duration: 0.3).delay(on ? 0.7 : 0), value: on)
            }
        }
    }
}
