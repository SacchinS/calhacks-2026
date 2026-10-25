import SwiftUI

struct SettingsView: View {
    @ObservedObject var engine: EngineClient
    let runSetup: () -> Void
    var resetApp: () -> Void = {}
    @State private var letterHold = 2.5
    @State private var saved = false
    @State private var signerName = ""
    @State private var review = false
    @State private var callSaved = false

    var body: some View {
        Form {
            Section {
                HStack(spacing: 12) {
                    Logo(size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("SignBridge").font(.headline)
                        Text("Version \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "dev")")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Run Setup Again", action: runSetup)
                }
            }
            Section {
                setting("Letter hold", "Hold a fingerspelled letter still this long for it to count.",
                        value: $letterHold, range: 1.6...4, text: String(format: "%.1f s", letterHold))
                Text("One sign each time you raise your hands: drop them between signs. Sign FINISH to send what you've signed, or NOW to say it right away.")
                    .font(.caption).foregroundStyle(.secondary)
            } header: {
                Label("Signing", systemImage: "hand.raised.fill")
            } footer: {
                HStack {
                    if saved { Label("Saved", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                    Spacer()
                    Button("Save") {
                        engine.saveConfig(["letter_hold": (letterHold * 10).rounded() / 10])
                        withAnimation { saved = true }
                    }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                }
                .padding(.top, 8)
            }
            Section {
                TextField("Your name", text: $signerName, prompt: Text("e.g. Sam"))
                Toggle("Review before speaking", isOn: $review)
                Text("\"Introduce me\" (the call overlay's replies menu) says: \"Hi, this is \(signerName.isEmpty ? "<name>" : signerName). I'm Deaf and signing through SignBridge, so there may be a short pause before I answer.\" Useful on calls with people who don't know you. With review on, SignBridge waits for you to sign YES (NO drops it) before saying anything.")
                    .font(.caption).foregroundStyle(.secondary)
            } header: {
                Label("Calls", systemImage: "video.fill")
            } footer: {
                HStack {
                    if callSaved { Label("Saved", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                    Spacer()
                    Button("Save") {
                        engine.saveConfig(["signer_name": signerName.trimmingCharacters(in: .whitespaces),
                                           "review_before_speaking": review])
                        withAnimation { callSaved = true }
                    }
                }
                .padding(.top, 8)
            }
            RememberedWords(engine: engine)
            Section("Privacy") {
                Label("Video never leaves this Mac. Hand tracking and sign recognition run here.", systemImage: "video.slash")
                Label("Claude gets text only: the signs it turns into English and, while Jira tickets are on, the call's captions and your sentences to draft a ticket. Cartesia gets only the English to speak, plus the other side's call audio for captions.", systemImage: "text.bubble")
                Label("Nothing reaches Jira until you sign YES (or press Add) on a ticket, and then only the ticket itself, never the captions.", systemImage: "ticket")
                Label("Nothing is saved: no video, no transcripts (ticket notes stay in memory for the call). Autocomplete keeps only words, a few topic tags, and when they were used, in a file on this Mac.", systemImage: "externaldrive.badge.xmark")
            }
            .font(.callout)
            Section {
                Button("Reset SignBridge…", role: .destructive, action: resetApp)
                Text("Puts every setting back to its default and runs setup again. Recorded signs and API keys stay.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .tint(Brand.accent)
        .onChange(of: letterHold) { _, _ in saved = false }
        .onChange(of: signerName) { _, _ in callSaved = false }
        .onChange(of: review) { _, _ in callSaved = false }
        .onAppear {
            letterHold = engine.config["letter_hold"] as? Double ?? 2.5
            signerName = engine.config["signer_name"] as? String ?? ""
            review = engine.config["review_before_speaking"] as? Bool ?? false
        }
    }

    private func setting(_ title: String, _ help: String, value: Binding<Double>, range: ClosedRange<Double>,
                         text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title)
                Spacer()
                Text(text).monospacedDigit().foregroundStyle(.secondary)
            }
            Slider(value: value, in: range).labelsHidden()
            Text(help).font(.caption).foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }
}
