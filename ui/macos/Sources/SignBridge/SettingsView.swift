import SwiftUI

struct SettingsView: View {
    @ObservedObject var engine: EngineClient
    let runSetup: () -> Void
    var resetApp: () -> Void = {}
    @State private var still = 0.5
    @State private var phraseRest = 1.5
    @State private var minConf = 0.6
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
                setting("Pause between signs", "Hold still this long to end one sign.",
                        value: $still, range: 0.3...1.2, text: String(format: "%.1f s", still))
                setting("Rest to finish", "Hands down this long sends the phrase to Claude.",
                        value: $phraseRest, range: 0.8...3, text: String(format: "%.1f s", phraseRest))
                setting("Minimum confidence", "Signs the model is less sure of are ignored.",
                        value: $minConf, range: 0.3...0.95, text: "\(Int((minConf * 100).rounded()))%")
            } header: {
                Text("Recognition")
            } footer: {
                HStack {
                    if saved { Label("Saved", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                    Spacer()
                    Button("Save") {
                        engine.saveConfig(["still": (still * 10).rounded() / 10, "phrase_rest": (phraseRest * 10).rounded() / 10,
                                           "min_conf": (minConf * 20).rounded() / 20])
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
                Text("\"Introduce me\" in a call says: \"Hi, this is \(signerName.isEmpty ? "<name>" : signerName). I'm Deaf and signing through SignBridge, so there may be a short pause before I answer.\" Useful on calls with people who don't know you. With review on, SignBridge waits for you to sign YES (NO drops it) before saying anything.")
                    .font(.caption).foregroundStyle(.secondary)
            } header: {
                Text("Calls")
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
                Label("Claude gets only the recognized sign words, as text. Cartesia gets only the English to speak, plus the other side's call audio for captions.", systemImage: "text.bubble")
                Label("Nothing is recorded: no video, no transcripts. Autocomplete keeps only words, a few topic tags, and when they were used, in a file on this Mac.", systemImage: "externaldrive.badge.xmark")
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
        .onChange(of: [still, phraseRest, minConf]) { _, _ in saved = false }
        .onChange(of: signerName) { _, _ in callSaved = false }
        .onChange(of: review) { _, _ in callSaved = false }
        .onAppear {
            still = engine.config["still"] as? Double ?? 0.5
            phraseRest = engine.config["phrase_rest"] as? Double ?? 1.5
            minConf = engine.config["min_conf"] as? Double ?? 0.6
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
