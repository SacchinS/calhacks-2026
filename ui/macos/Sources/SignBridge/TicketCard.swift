import AppKit
import SwiftUI

/// The Jira ticket Claude drafts from the call (language/tickets.py): tentative while the
/// conversation fills it in, ready once you've agreed to do it, then added to Jira when you
/// sign YES (or press Add). Nothing reaches Jira before that.
enum TicketLook {
    static func tint(_ t: EngineClient.Ticket) -> Color {
        switch t.state {
        case "created": Brand.detected
        case "failed": .orange
        case "creating": Brand.accent
        default: t.ready ? Brand.detected : Brand.indigo
        }
    }
    static func icon(_ t: EngineClient.Ticket) -> String {
        switch t.state {
        case "created": "checkmark.seal.fill"
        case "failed": "exclamationmark.triangle.fill"
        case "creating": "arrow.up.circle.fill"
        default: t.ready ? "checkmark.circle" : "sparkles"
        }
    }
    static func status(_ t: EngineClient.Ticket) -> String {
        switch t.state {
        case "created": "Added to Jira as \(t.key)"
        case "failed": "Couldn't add it\(t.error.isEmpty ? "" : ": \(t.error)")"
        case "creating": "Adding to Jira…"
        default: t.ready ? "Ready to add" : "Drafting from the call"
        }
    }
    /// The draft's field names as a person would say them.
    static func changed(_ fields: [String]) -> String {
        let names = ["summary": "title", "description": "details", "assign_to_signer": "owner", "assignee": "owner",
                     "due": "due date", "blocks": "blocks", "labels": "labels", "ready": "", "reasons": "", "asked": "asked"]
        var seen = Set<String>()
        return fields.compactMap { names[$0] ?? $0 }.filter { !$0.isEmpty && seen.insert($0).inserted }.joined(separator: ", ")
    }
}

/// The ticket as a card: main window and Demo Mode.
struct TicketCard: View {
    @ObservedObject var engine: EngineClient
    var large = false
    /// The fields that changed in the newest version, lit for a moment (from Eleyn's card).
    @State private var lit: Set<String> = []

    var body: some View {
        if let t = engine.ticket {
            let tint = TicketLook.tint(t)
            Card(title: "Jira ticket", icon: "ticket.fill", tint: tint, trailing: {
                HStack(spacing: 6) {
                    if t.mock { Text("MOCK JIRA").font(.system(size: 10, weight: .heavy)).tracking(0.8).foregroundStyle(.orange) }
                    if t.state == "tentative" { Text("v\(t.version)").font(.caption.monospacedDigit()).foregroundStyle(.tertiary) }
                }
            }) {
                VStack(alignment: .leading, spacing: large ? 14 : 10) {
                    HStack(spacing: 8) {
                        if t.state == "creating" { ProgressView().controlSize(.small) } else {
                            Image(systemName: TicketLook.icon(t)).foregroundStyle(tint)
                        }
                        Text(TicketLook.status(t)).font(.callout.weight(.semibold)).foregroundStyle(tint)
                        if t.state == "tentative", !t.changed.isEmpty, t.version > 1 {
                            Text("· updated \(TicketLook.changed(t.changed))").font(.caption).foregroundStyle(.tertiary).lineLimit(1)
                        }
                    }
                    Text(t.summary).font(.system(size: large ? 26 : 19, weight: .bold, design: .rounded))
                        .fixedSize(horizontal: false, vertical: true)
                        .lit(lit.contains("summary"), tint)
                    if !t.description.isEmpty {
                        Text(t.description).font(large ? .title3 : .callout).foregroundStyle(.secondary)
                            .lineLimit(large ? 4 : 3).fixedSize(horizontal: false, vertical: true)
                            .lit(lit.contains("description"), tint)
                    }
                    FlowRow(spacing: 6) {
                        if t.assignee == "signer" { fact("person.fill", "Owner: you").lit(lit.contains("assign_to_signer"), tint) }
                        if !t.asked.isEmpty { fact("text.bubble", "Asked by \(t.asked)").lit(lit.contains("asked"), tint) }
                        if !t.due.isEmpty { fact("calendar", "Due \(Self.day(t.due))").lit(lit.contains("due"), tint) }
                        if let b = t.blocks { fact("arrow.triangle.branch", "Blocks \(b.key)").lit(lit.contains("blocks"), tint) }
                        ForEach(t.labels, id: \.self) { fact("tag", $0).lit(lit.contains("labels"), tint) }
                    }
                    if let d = t.duplicate {
                        Label("Maybe a duplicate of \(d.key): \(d.summary)", systemImage: "doc.on.doc")
                            .font(.caption).foregroundStyle(.orange)
                    }
                    actions(t)
                }
            }
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(tint.opacity(0.45), lineWidth: 1.5))
            .animation(.easeInOut(duration: 0.25), value: t)
            .transition(.move(edge: .top).combined(with: .opacity))
            .onAppear { light(t) }
            .onChange(of: t.version) { _, _ in if let t = engine.ticket { light(t) } }
        }
    }

    @ViewBuilder private func actions(_ t: EngineClient.Ticket) -> some View {
        HStack(spacing: 10) {
            switch t.state {
            case "tentative" where t.ready:
                Button { engine.approveTicket() } label: { Label("Add to Jira", systemImage: "plus.circle.fill") }
                    .buttonStyle(PillButtonStyle(fill: Brand.detected))
                Keycap(text: "YES", tint: Brand.detected)
                Text("adds it ·").foregroundStyle(.secondary)
                Keycap(text: "NO", tint: .secondary)
                Text("drops it").foregroundStyle(.secondary)
            case "tentative":
                Text("It becomes ready once you agree to do it.").font(.caption).foregroundStyle(.tertiary)
                Spacer()
                Button("Dismiss") { engine.dismissTicket() }.buttonStyle(.borderless).foregroundStyle(.secondary)
            case "created":
                if let url = URL(string: t.url), !t.url.isEmpty, !t.mock {
                    Button { NSWorkspace.shared.open(url) } label: { Label("Open \(t.key)", systemImage: "arrow.up.right.square") }
                }
                if t.auditSaved { Label("Approval saved in Jira", systemImage: "checkmark.shield").font(.caption).foregroundStyle(.secondary) }
                Spacer()
                Button("Done") { engine.dismissTicket() }.buttonStyle(.borderless).foregroundStyle(.secondary)
                    .help("Clear it; SignBridge starts drafting the next one")
            case "failed":
                Button { engine.approveTicket() } label: { Label("Try again", systemImage: "arrow.clockwise") }
                    .help("Same version, so Jira won't get it twice")
                Spacer()
                Button("Dismiss") { engine.dismissTicket() }.buttonStyle(.borderless).foregroundStyle(.secondary)
            default:
                EmptyView()
            }
        }
        .font(large ? .title3 : .callout)
    }

    /// Light what changed in this version, then let it fade.
    private func light(_ t: EngineClient.Ticket) {
        guard t.state == "tentative", t.version > 1 else { return }
        let version = t.version
        withAnimation(.easeOut(duration: 0.2)) { lit = Set(t.changed) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            guard engine.ticket?.version == version else { return }
            withAnimation(.easeOut(duration: 0.6)) { lit = [] }
        }
    }

    private func fact(_ icon: String, _ text: String) -> some View {
        Label(text, systemImage: icon).font(large ? .callout.weight(.medium) : .caption.weight(.medium))
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(Color.white.opacity(0.07), in: Capsule())
    }

    /// "2026-10-26" as "Oct 26".
    static func day(_ iso: String) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: iso) else { return iso }
        return d.formatted(.dateTime.month(.abbreviated).day())
    }
}

extension View {
    /// A field that just changed: a tinted glow behind it for a moment.
    func lit(_ on: Bool, _ tint: Color) -> some View {
        padding(.horizontal, on ? 4 : 0)
            .background(tint.opacity(on ? 0.22 : 0), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
    }
}

/// The ticket in one line, for the call overlay.
struct TicketStrip: View {
    @ObservedObject var engine: EngineClient

    var body: some View {
        if let t = engine.ticket {
            let tint = TicketLook.tint(t)
            HStack(spacing: 12) {
                Image(systemName: "ticket.fill").font(.system(size: 18, weight: .semibold)).foregroundStyle(tint)
                    .frame(width: 52)
                VStack(alignment: .leading, spacing: 2) {
                    Text(TicketLook.status(t).uppercased()).font(.system(size: 11, weight: .heavy)).tracking(0.8).foregroundStyle(tint)
                    Text(t.summary).font(.system(size: 17, weight: .semibold)).lineLimit(1)
                }
                Spacer(minLength: 8)
                switch t.state {
                case "tentative" where t.ready:
                    Keycap(text: "YES", tint: Brand.detected)
                    Button { engine.approveTicket() } label: { Label("Add to Jira", systemImage: "plus") }
                        .buttonStyle(PillButtonStyle(fill: Brand.detected))
                case "creating":
                    ProgressView().controlSize(.small)
                case "created":
                    OverlayButton(icon: "checkmark", help: "Done: clear it", action: engine.dismissTicket)
                default:
                    OverlayButton(icon: "xmark", help: "Dismiss this ticket", action: engine.dismissTicket)
                }
            }
            .padding(.top, 10)
            .overlay(alignment: .top) { Rectangle().fill(Color.white.opacity(0.1)).frame(height: 1) }
        }
    }
}
