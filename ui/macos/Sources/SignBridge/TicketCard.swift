import AppKit
import SwiftUI

/// The live Jira ticket Claude drafts from the call (Preview's call panel and Demo Mode). It
/// shows only the draft's fields, never the call's captions or notes. Nothing reaches Jira until
/// the signer approves the version on the card: a signed YES, the confirm key, or Approve & Create.
struct TicketCard: View {
    @ObservedObject var engine: EngineClient
    var large = false
    /// The rows that just changed, highlighted for a moment after each new version.
    @State private var lit: Set<String> = []
    /// The last tentative draft shown, and that draft frozen while it's being created.
    @State private var shown: TicketDraft?
    @State private var frozen: TicketDraft?

    var body: some View {
        if let ticket = engine.ticket {
            card(ticket)
                .onAppear { shown = ticket.draft; light(ticket) }
                .onChange(of: ticket.version) { _, _ in light(ticket) }
                .onChange(of: ticket.draft) { _, d in if ticket.state == "tentative" { shown = d } }
                .onChange(of: ticket.state) { _, new in
                    frozen = new == "creating" ? (frozen ?? shown ?? ticket.draft) : nil
                }
                .transition(.opacity)
        }
    }

    private func light(_ ticket: TicketUpdate) {
        let version = ticket.version
        withAnimation(.easeOut(duration: 0.2)) { lit = ticket.highlighted }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            guard engine.ticket?.version == version else { return }
            withAnimation(.easeOut(duration: 0.6)) { lit = [] }
        }
    }

    private func card(_ ticket: TicketUpdate) -> some View {
        let draft = (ticket.state == "creating" ? frozen : nil) ?? ticket.draft ?? TicketDraft()
        return VStack(alignment: .leading, spacing: large ? 14 : 10) {
            header(ticket)
            if ticket.state == "created" {
                created(ticket)
            }
            Text(draft.summary.isEmpty ? "—" : draft.summary)
                .font(large ? .system(size: 28, weight: .bold) : .title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
                .lit(lit.contains("summary"))
            if !draft.description.isEmpty {
                Text(draft.description).font(large ? .title3 : .callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .lit(lit.contains("description"))
            }
            fields(draft)
            if !draft.words.isEmpty {
                HStack(spacing: 6) {
                    ForEach(draft.words, id: \.term) { w in
                        Text(w.term).font(large ? .callout.weight(.semibold) : .caption.weight(.semibold))
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(Brand.accent.opacity(0.18), in: Capsule())
                            .help(w.tags.isEmpty ? "Remembered word" : "Remembered word: " + w.tags.joined(separator: ", "))
                    }
                }
            }
            if !draft.reasons.isEmpty {
                Text("From this call: " + draft.reasons.joined(separator: " · "))
                    .font(large ? .callout : .caption).foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
                    .lit(lit.contains("reasons"))
            }
            footer(ticket)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(large ? 22 : 16)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: large ? 20 : 14))
        .overlay(RoundedRectangle(cornerRadius: large ? 20 : 14)
            .strokeBorder(ticket.approvable ? Color.green.opacity(0.7) : Color.white.opacity(0.08),
                          lineWidth: ticket.approvable ? 2 : 1))
        .animation(.easeInOut(duration: 0.25), value: ticket.state)
    }

    private func header(_ ticket: TicketUpdate) -> some View {
        HStack(spacing: 8) {
            Label("Jira ticket", systemImage: "checklist").font(large ? .title3.weight(.semibold) : .headline)
                .foregroundStyle(Brand.accent)
            badge(ticket)
            if ticket.mock {
                Text("Mock Jira").font(.caption.weight(.bold))
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(Color.orange.opacity(0.2), in: Capsule()).foregroundStyle(.orange)
                    .help("Not connected to Jira: nothing real is created")
            }
            Spacer()
            if ticket.version > 0 {
                Text("v\(ticket.version)").font(.caption.monospacedDigit()).foregroundStyle(.tertiary)
                    .help("The draft version Approve & Create sends")
            }
        }
    }

    private func badge(_ ticket: TicketUpdate) -> some View {
        let (text, color): (String, Color) = switch ticket.state {
        case "tentative": ticket.ready ? ("Ready", .green) : ("Tentative", .yellow)
        case "creating": ("Creating", Brand.accent)
        case "created": ("Created", .green)
        case "failed": ("Failed", .red)
        default: (ticket.state.capitalized, .gray)
        }
        return Text(text).font(large ? .callout.weight(.bold) : .caption.weight(.bold))
            .padding(.horizontal, 9).padding(.vertical, 3)
            .background(color.opacity(0.2), in: Capsule()).foregroundStyle(color)
    }

    private func fields(_ draft: TicketDraft) -> some View {
        Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: large ? 6 : 4) {
            if !draft.asked.isEmpty { row("asked", "Asked", draft.asked) }
            row("assignee", "Assignee", assignee(draft))
            row("due", "Due", Self.date(draft.due))
            row("labels", "Labels", draft.labels.isEmpty ? "—" : draft.labels.joined(separator: ", "))
            if let b = draft.blocks {
                row("related", "Blocks", b.summary.isEmpty ? b.key : "\(b.key) · \(b.summary)")
            }
            if let d = draft.possibleDuplicate {
                row("possible_duplicate", "Possible duplicate", d.summary.isEmpty ? d.key : "\(d.key) · \(d.summary)")
            }
        }
        .font(large ? .title3 : .callout)
    }

    private func row(_ id: String, _ name: String, _ value: String) -> some View {
        GridRow {
            Text(name).foregroundStyle(.secondary)
            Text(value).fontWeight(.semibold).frame(maxWidth: .infinity, alignment: .leading)
        }
        .lit(lit.contains(id))
    }

    private func assignee(_ draft: TicketDraft) -> String {
        guard draft.assignee == "signer" else { return "—" }
        let name = engine.config["signer_name"] as? String ?? ""
        return name.isEmpty ? "You" : name
    }

    /// "2026-10-26" as "Oct 26, 2026"; "—" when there's no date.
    static func date(_ iso: String) -> String {
        guard !iso.isEmpty else { return "—" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: iso) else { return iso }
        return d.formatted(date: .abbreviated, time: .omitted)
    }

    private func created(_ ticket: TicketUpdate) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 14) {
                Text(ticket.key.isEmpty ? "—" : ticket.key)
                    .font(.system(size: large ? 48 : 32, weight: .heavy).monospacedDigit())
                Spacer()
                Button {
                    if let u = URL(string: ticket.url) { NSWorkspace.shared.open(u) }
                } label: { Label("Open in Jira", systemImage: "arrow.up.right.square") }
                    .buttonStyle(.borderedProminent)
                    .disabled(ticket.mock || URL(string: ticket.url) == nil)
                    .help(ticket.mock ? "Mock Jira: there's no real issue to open" : ticket.url)
            }
            Label(ticket.auditSaved ? "Audit saved" : "Audit not saved",
                  systemImage: ticket.auditSaved ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                .foregroundStyle(ticket.auditSaved ? .green : .orange)
            if let linked = ticket.linked, !linked.isEmpty {
                Label("Blocks \(linked)", systemImage: "link")
            }
            ForEach(ticket.warnings, id: \.self) { w in
                Label(w, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .font(large ? .title3 : .callout)
    }

    @ViewBuilder private func footer(_ ticket: TicketUpdate) -> some View {
        switch ticket.state {
        case "tentative" where ticket.ready:
            VStack(alignment: .leading, spacing: 8) {
                Label("Sign YES to create", systemImage: "hand.thumbsup.fill")
                    .font(large ? .title2.weight(.bold) : .headline).foregroundStyle(.green)
                if !ticket.announce.isEmpty {
                    Text("When it's created, I'll say: \u{201C}\(ticket.announce.replacingOccurrences(of: "{key}", with: "…"))\u{201D}")
                        .font(large ? .callout : .caption).foregroundStyle(.secondary)
                }
                HStack {
                    let version = ticket.version
                    Button { engine.approveTicket(version: version) } label: {
                        Label("Approve & Create", systemImage: "checkmark.circle.fill")
                    }
                    .buttonStyle(.borderedProminent).tint(.green)
                    .help("Creates draft v\(version) in Jira")
                    Button { engine.dismissTicket() } label: { Label("Dismiss", systemImage: "xmark") }
                }
                .controlSize(large ? .large : .regular)
            }
        case "tentative":
            HStack {
                Label("Listening…", systemImage: "waveform").foregroundStyle(.secondary)
                Spacer()
                Button { engine.dismissTicket() } label: { Label("Dismiss", systemImage: "xmark") }
                    .controlSize(large ? .large : .regular)
            }
            .font(large ? .title3 : .callout)
        case "creating":
            HStack(spacing: 10) {
                ProgressView().controlSize(.small)
                Text("Creating in Jira…").foregroundStyle(.secondary)
            }
            .font(large ? .title3 : .callout)
        case "failed":
            VStack(alignment: .leading, spacing: 8) {
                Label(ticket.error.isEmpty ? "Couldn't create it in Jira." : ticket.error,
                      systemImage: "xmark.octagon.fill")
                    .foregroundStyle(.red).fixedSize(horizontal: false, vertical: true)
                HStack {
                    let version = ticket.version
                    Button { engine.retryTicket(version: version) } label: { Label("Retry", systemImage: "arrow.clockwise") }
                        .buttonStyle(.borderedProminent)
                        .help("Create draft v\(version) again (the same request, so Jira won't get a duplicate)")
                    Button { engine.dismissTicket() } label: { Label("Dismiss", systemImage: "xmark") }
                }
                .controlSize(large ? .large : .regular)
            }
            .font(large ? .title3 : .callout)
        default:
            EmptyView()
        }
    }
}

private extension View {
    /// A field Claude just changed: briefly tinted so the signer sees what was added.
    func lit(_ on: Bool) -> some View {
        padding(.horizontal, 4).padding(.vertical, 1)
            .background(Color.yellow.opacity(on ? 0.28 : 0), in: RoundedRectangle(cornerRadius: 5))
    }
}
