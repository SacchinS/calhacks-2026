import Foundation

/// Any JSON value, kept as it came, so fields the app doesn't know yet survive a decode and encode.
enum JSONValue: Codable, Equatable {
    case null, bool(Bool), number(Double), string(String), array([JSONValue]), object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let b): try c.encode(b)
        case .number(let n): try c.encode(n)
        case .string(let s): try c.encode(s)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }

    var string: String? { if case .string(let s) = self { return s }; return nil }
    var bool: Bool? { if case .bool(let b) = self { return b }; return nil }
    var int: Int? { if case .number(let n) = self, n.isFinite { return Int(n) }; return nil }
    var array: [JSONValue]? { if case .array(let a) = self { return a }; return nil }
    var object: [String: JSONValue]? { if case .object(let o) = self { return o }; return nil }
    var strings: [String] { array?.compactMap(\.string) ?? [] }

    static func strings(_ list: [String]) -> JSONValue { .array(list.map { JSONValue.string($0) }) }
    static func issue(_ issue: TicketIssue?) -> JSONValue { issue.map { JSONValue.object($0.json) } ?? .null }
}

/// A JSON object read field by field: a field with the wrong type falls back to its default
/// instead of failing the whole ticket, and the fields not read are kept in `extra`.
private struct Fields {
    var rest: [String: JSONValue]
    mutating func take(_ key: String) -> JSONValue? { rest.removeValue(forKey: key) }
    mutating func string(_ key: String) -> String { take(key)?.string ?? "" }
    mutating func strings(_ key: String) -> [String] { take(key)?.strings ?? [] }
}

/// Decodes as a JSON object through `init(json:)` and encodes back through `json`.
protocol JSONObjectCodable: Codable {
    init(json: [String: JSONValue])
    var json: [String: JSONValue] { get }
}

extension JSONObjectCodable {
    init(from decoder: Decoder) throws { self.init(json: try [String: JSONValue](from: decoder)) }
    func encode(to encoder: Encoder) throws { try json.encode(to: encoder) }
}

/// A Jira issue the engine found: the release issue a ticket blocks, a possible duplicate, a similar one.
struct TicketIssue: JSONObjectCodable, Equatable {
    var key = "", summary = "", url = ""
    var extra: [String: JSONValue] = [:]

    init(key: String = "", summary: String = "", url: String = "") {
        self.key = key; self.summary = summary; self.url = url
    }

    init(json: [String: JSONValue]) {
        var f = Fields(rest: json)
        key = f.string("key"); summary = f.string("summary"); url = f.string("url")
        extra = f.rest
    }

    var json: [String: JSONValue] {
        var o = extra
        o["key"] = .string(key)
        o["summary"] = .string(summary)
        o["url"] = .string(url)
        return o
    }

    static func from(_ value: JSONValue?) -> TicketIssue? {
        guard let o = value?.object else { return nil }
        let issue = TicketIssue(json: o)
        return issue.key.isEmpty ? nil : issue
    }
}

/// What Claude has drafted so far (`draft` in the ticket event).
struct TicketDraft: JSONObjectCodable, Equatable {
    /// A remembered word the draft used (Moss), with its tags.
    struct Word: Equatable { var term: String, tags: [String] }

    var summary = "", description = "", asked = ""
    /// "signer" when it's the signer's own task, otherwise "".
    var assignee = ""
    var due = ""  // YYYY-MM-DD or ""
    var labels: [String] = [], people: [String] = [], reasons: [String] = []
    var blocks: TicketIssue?
    var possibleDuplicate: TicketIssue?
    var words: [Word] = []
    var extra: [String: JSONValue] = [:]

    init(summary: String = "", description: String = "") {
        self.summary = summary; self.description = description
    }

    init(json: [String: JSONValue]) {
        var f = Fields(rest: json)
        summary = f.string("summary"); description = f.string("description"); asked = f.string("asked")
        assignee = f.string("assignee"); due = f.string("due")
        labels = f.strings("labels"); people = f.strings("people"); reasons = f.strings("reasons")
        blocks = TicketIssue.from(f.take("blocks"))
        possibleDuplicate = TicketIssue.from(f.take("possible_duplicate"))
        words = (f.take("words")?.array ?? []).compactMap { w in
            guard let o = w.object, let term = o["term"]?.string else { return nil }
            return Word(term: term, tags: o["tags"]?.strings ?? [])
        }
        extra = f.rest
    }

    var json: [String: JSONValue] {
        var o = extra
        o["summary"] = .string(summary)
        o["description"] = .string(description)
        o["asked"] = .string(asked)
        o["assignee"] = .string(assignee)
        o["due"] = .string(due)
        o["labels"] = .strings(labels)
        o["people"] = .strings(people)
        o["reasons"] = .strings(reasons)
        o["blocks"] = .issue(blocks)
        o["possible_duplicate"] = .issue(possibleDuplicate)
        o["words"] = .array(words.map { w -> JSONValue in
            .object(["term": .string(w.term), "tags": .strings(w.tags)])
        })
        return o
    }
}

/// The live Jira ticket (the `ticket` event, and `status.ticket`; protocol in ui/server.py).
struct TicketUpdate: JSONObjectCodable, Equatable {
    /// tentative, creating, created, failed, dismissed or none.
    var state = "none"
    var version = 0
    var ready = false
    /// The draft fields that changed in this version (engine names: assign_to_signer, blocks, ...).
    var changed: [String] = []
    var draft: TicketDraft?
    var similar: [TicketIssue] = [], release: [TicketIssue] = []
    /// What the app says in the call once it's created; {key} becomes the new key.
    var announce = ""
    var key = "", url = ""
    var linked: String?
    var auditSaved = false
    var warnings: [String] = []
    var error = ""
    var mock = false
    var draftMs: Int?, createMs: Int?
    var extra: [String: JSONValue] = [:]
    /// Unknown fields inside `jira`, kept for the round trip.
    var jiraExtra: [String: JSONValue] = [:]

    init(state: String, version: Int = 0, ready: Bool = false, draft: TicketDraft? = nil) {
        self.state = state; self.version = version; self.ready = ready; self.draft = draft
    }

    init(json: [String: JSONValue]) {
        var f = Fields(rest: json)
        state = f.take("state")?.string ?? "none"
        version = f.take("version")?.int ?? 0
        ready = f.take("ready")?.bool ?? false
        changed = f.strings("changed")
        draft = f.take("draft")?.object.map(TicketDraft.init(json:))
        var jira = Fields(rest: f.take("jira")?.object ?? [:])
        similar = (jira.take("similar")?.array ?? []).compactMap(TicketIssue.from)
        release = (jira.take("release")?.array ?? []).compactMap(TicketIssue.from)
        jiraExtra = jira.rest
        announce = f.string("announce"); key = f.string("key"); url = f.string("url")
        linked = f.take("linked")?.string
        auditSaved = f.take("audit_saved")?.bool ?? false
        warnings = f.strings("warnings")
        error = f.string("error")
        mock = f.take("mock")?.bool ?? false
        draftMs = f.take("draft_ms")?.int
        createMs = f.take("create_ms")?.int
        extra = f.rest
    }

    var json: [String: JSONValue] {
        var jira = jiraExtra
        jira["similar"] = .array(similar.map { JSONValue.object($0.json) })
        jira["release"] = .array(release.map { JSONValue.object($0.json) })
        var o = extra
        o["state"] = .string(state)
        o["version"] = .number(Double(version))
        o["ready"] = .bool(ready)
        o["changed"] = .strings(changed)
        o["draft"] = draft.map { JSONValue.object($0.json) } ?? .null
        o["jira"] = .object(jira)
        o["announce"] = .string(announce)
        o["key"] = .string(key)
        o["url"] = .string(url)
        o["linked"] = linked.map { JSONValue.string($0) } ?? .null
        o["audit_saved"] = .bool(auditSaved)
        o["warnings"] = .strings(warnings)
        o["error"] = .string(error)
        o["mock"] = .bool(mock)
        o["draft_ms"] = draftMs.map { JSONValue.number(Double($0)) } ?? .null
        o["create_ms"] = createMs.map { JSONValue.number(Double($0)) } ?? .null
        return o
    }

    /// Whether the card shows at all (dismissed and none hide it).
    var visible: Bool { ["tentative", "creating", "created", "failed"].contains(state) }
    /// Approve & Create (or a signed YES) would create this version now.
    var approvable: Bool { state == "tentative" && ready && draft != nil }

    /// The fields the card highlights for this version, by the card's row names.
    var highlighted: Set<String> {
        Set(changed.map { ["assign_to_signer": "assignee", "blocks": "related"][$0] ?? $0 })
    }

    /// A ticket from the engine's JSON (a `ticket` event or `status.ticket`): nil for null,
    /// for something that isn't a ticket, and for the states that hide the card.
    static func parse(_ object: Any?) -> TicketUpdate? {
        guard var o = object as? [String: Any] else { return nil }
        o.removeValue(forKey: "type")  // the event's own tag, not part of the ticket
        guard let data = try? JSONSerialization.data(withJSONObject: o),
              let ticket = try? JSONDecoder().decode(TicketUpdate.self, from: data) else { return nil }
        return ticket.visible ? ticket : nil
    }
}
