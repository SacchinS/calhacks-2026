import SwiftUI

/// While a word is being fingerspelled: the letters so far, the top suggestion, and smaller
/// alternates. YES (or a click) takes a suggestion; NO dismisses them for this word.
struct AutocompleteBar: View {
    @ObservedObject var engine: EngineClient
    var large = false

    var body: some View {
        if let a = engine.autocomplete {
            HStack(alignment: .center, spacing: large ? 16 : 10) {
                Image(systemName: "hand.point.up.left").foregroundStyle(Brand.accent)
                Text(a.letters.map(String.init).joined(separator: " "))
                    .font(.system(size: large ? 30 : 20, weight: .bold, design: .monospaced))
                if a.dismissed {
                    Text("Spelling it out. NO again to start over.").foregroundStyle(.secondary)
                } else if let top = a.top {
                    Image(systemName: "arrow.right").foregroundStyle(.secondary)
                    Button { engine.acceptSuggestion(0) } label: {
                        Text(top.term).font(.system(size: large ? 34 : 22, weight: .semibold))
                    }
                    .buttonStyle(.borderedProminent)
                    .help("Sign YES to use \(top.term)")
                    ForEach(Array(a.alternates.enumerated()), id: \.offset) { i, w in
                        Button { engine.acceptSuggestion(i + 1) } label: {
                            Text(w.term).font(large ? .title3 : .callout)
                        }
                        .buttonStyle(.bordered)
                    }
                } else if a.letters.count >= 2 {
                    Text("New word. YES keeps it as spelled.").foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                if !a.dismissed, a.top != nil {
                    Text("YES to use · NO to dismiss").font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(Brand.accent.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
            .transition(.opacity)
        }
    }
}

/// Typed fingerspelling, for when the camera can't read letters yet: each letter typed is a
/// fingerspelled letter, Return takes the suggestion, Escape dismisses it.
struct SpellBox: View {
    @ObservedObject var engine: EngineClient
    @State private var text = ""
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "character.cursor.ibeam").foregroundStyle(Brand.accent)
            TextField("Fingerspell by typing: letters suggest a word, Return uses it", text: $text)
                .textFieldStyle(.roundedBorder)
                .onChange(of: text) { old, new in
                    if new.count > old.count, new.hasPrefix(old) { engine.letters(String(new.dropFirst(old.count))) }
                }
                .onSubmit {
                    engine.acceptSuggestion(0)
                    text = ""
                }
                .onExitCommand {
                    engine.dismissSuggestions()
                    if engine.autocomplete?.dismissed ?? false { text = "" }
                }
        }
        .onChange(of: engine.autocomplete == nil) { _, gone in if gone { text = "" } }
    }
}

/// Settings > Remembered words: what autocomplete keeps, with delete buttons.
struct RememberedWords: View {
    @ObservedObject var engine: EngineClient
    var body: some View {
        Section {
            if engine.vocab.isEmpty {
                Text("No words yet. Words you fingerspell, and names and jargon the other side says in calls, show up here.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            ForEach(engine.vocab) { word in
                DisclosureGroup {
                    ForEach(word.uses) { use in
                        HStack {
                            Text(use.source == "fingerspelled" ? "You spelled it" : "Heard in a call")
                            Text(use.usedAt, format: .dateTime.month().day().hour().minute()).foregroundStyle(.secondary)
                            if !use.tags.isEmpty { Text(use.tags.joined(separator: ", ")).foregroundStyle(.tertiary) }
                            Spacer()
                            Button(role: .destructive) { engine.deleteUse(use.id) } label: { Image(systemName: "trash") }
                                .buttonStyle(.borderless).help("Forget this time")
                        }
                        .font(.caption)
                    }
                } label: {
                    HStack {
                        Text(word.term).fontWeight(.semibold)
                        Text(word.kind).font(.caption).foregroundStyle(.secondary)
                        Text("\(word.count)×").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        if !word.tags.isEmpty {
                            Text(word.tags.joined(separator: ", ")).font(.caption).foregroundStyle(.tertiary).lineLimit(1)
                        }
                        Spacer()
                        Text(word.lastUsed, format: .relative(presentation: .named)).font(.caption).foregroundStyle(.secondary)
                        Button(role: .destructive) { engine.deleteWord(word.term) } label: { Image(systemName: "trash") }
                            .buttonStyle(.borderless).help("Forget \(word.term)")
                    }
                }
            }
        } header: {
            Text("Remembered words")
        } footer: {
            let s = engine.autocompleteStats
            Text("Kept in a file on this Mac: the word, a few topic tags, and when it was used. Never sentences or captions. \(s.accepted) suggestions used, \(s.lettersSaved) letters saved.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .onAppear { engine.listVocab() }
    }
}
