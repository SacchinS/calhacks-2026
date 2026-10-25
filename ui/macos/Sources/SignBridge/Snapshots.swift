import AppKit
import SwiftUI

/// Development only: `SignBridge --snapshot <folder>` draws each screen offscreen from sample
/// state (no engine, no camera) into PNGs, so the UI can be reviewed without running a call.
@MainActor
enum Snapshots {
    static func run(into folder: URL) {
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        func save<V: View>(_ name: String, _ size: CGSize, _ view: V, dark: Bool = true) {
            let host = NSHostingView(rootView: view.frame(width: size.width, height: size.height)
                .environment(\.colorScheme, dark ? .dark : .light))
            host.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
            host.frame = CGRect(origin: .zero, size: size)
            let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isOpaque = false
            window.backgroundColor = .clear  // the logo and the overlay keep their transparent corners
            window.contentView = host
            window.appearance = host.appearance
            host.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.4))  // let onAppear and animations settle
            guard let rep = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { return }
            host.cacheDisplay(in: host.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?.write(to: folder.appendingPathComponent("\(name).png"))
        }

        let idle = sample { _ in }
        let signing = sample { e in
            e.state = "listening"; e.signState = "signing"; e.glosses = ["COLOR", "PROBLEM"]
        }
        let spelling = sample { e in
            e.state = "listening"; e.signState = "signing"; e.glosses = []
            e.autocomplete = .init(letters: "F", top: .init(term: "Figma", kind: "term"),
                                   alternates: [.init(term: "Firebase", kind: "term"), .init(term: "Fiona", kind: "name")],
                                   dismissed: false, search: "moss")
        }
        let holding = sample { e in
            e.state = "listening"; e.signState = "signing"; e.glosses = ["ME", "MEET"]; e.holding = ("P", 0.62)
        }
        let confirming = sample { e in
            e.state = "confirming"; e.signState = "idle"; e.glosses = ["FIGMA", "COLOR", "PROBLEM"]
            e.sentence = "There's a color problem in Figma."
        }
        let waiting = sample { e in
            e.state = "idle"; e.signState = "detected"; e.speechState = "waiting"
            e.speechText = "There's a color problem in Figma."; e.themTalking = true
        }

        save("logo", CGSize(width: 512, height: 512), Logo(size: 512, glow: false))
        func ticket(_ state: String, ready: Bool, version: Int, changed: [String] = [], key: String = "") -> EngineClient.Ticket {
            .init(state: state, version: version, ready: ready, changed: changed,
                  summary: "Fix the dashboard chart colors in Figma",
                  description: "The redesigned charts use colors that don't match the release palette. Meet with Pranav to align them before the release.",
                  asked: "Sam", assignee: ready ? "signer" : "", due: ready ? "2026-10-26" : "", labels: ["design"],
                  people: ["Pranav"], reasons: [], blocks: ready ? .init(key: "SB-3", summary: "Dashboard release") : nil,
                  duplicate: nil, key: key, url: "", auditSaved: state == "created", error: "", mock: false)
        }
        let drafting = sample { e in e.ticket = ticket("tentative", ready: false, version: 1) }
        let readyTicket = sample { e in
            e.signState = "idle"; e.ticket = ticket("tentative", ready: true, version: 3, changed: ["assign_to_signer", "due", "blocks"])
        }
        let created = sample { e in e.ticket = ticket("created", ready: true, version: 3, key: "SB-12") }
        save("ticket-drafting", CGSize(width: 720, height: 820), PreviewView(engine: drafting))
        save("ticket-ready", CGSize(width: 720, height: 820), PreviewView(engine: readyTicket))
        save("ticket-overlay", CGSize(width: 880, height: 182), CallOverlayView(engine: readyTicket, openPreview: {}, close: {}))
        save("ticket-demo", CGSize(width: 1440, height: 900), DemoView(engine: created, exit: {}))
        save("preview-idle", CGSize(width: 720, height: 820), PreviewView(engine: idle))
        save("preview-signing", CGSize(width: 720, height: 820), PreviewView(engine: signing))
        save("preview-spelling", CGSize(width: 720, height: 820), PreviewView(engine: spelling))
        save("preview-confirm", CGSize(width: 720, height: 820), PreviewView(engine: confirming))
        save("preview-wide", CGSize(width: 1280, height: 800), PreviewView(engine: waiting))
        save("overlay-signing", CGSize(width: 880, height: 112), CallOverlayView(engine: signing, openPreview: {}, close: {}))
        save("overlay-spelling", CGSize(width: 880, height: 112), CallOverlayView(engine: spelling, openPreview: {}, close: {}))
        save("overlay-holding", CGSize(width: 880, height: 112), CallOverlayView(engine: holding, openPreview: {}, close: {}))
        save("overlay-waiting", CGSize(width: 880, height: 112), CallOverlayView(engine: waiting, openPreview: {}, close: {}))
        save("overlay-idle", CGSize(width: 880, height: 112), CallOverlayView(engine: idle, openPreview: {}, close: {}))
        save("demo", CGSize(width: 1440, height: 900), DemoView(engine: waiting, exit: {}))
        save("demo-spelling", CGSize(width: 1440, height: 900), DemoView(engine: spelling, exit: {}))
        save("mention", CGSize(width: 760, height: 150),
             MentionBannerView(mention: .init(text: "Sacchin, can you sort it out with Pranav?", question: true, final: true, turn: 1),
                               name: "Sacchin", dismiss: {}))
        save("settings", CGSize(width: 480, height: 640), SettingsView(engine: idle, runSetup: {}))
        for step in SetupStep.allCases {
            save("setup-\(step.rawValue)-\(step.title.lowercased().replacingOccurrences(of: " ", with: "-"))",
                 CGSize(width: 820, height: 620), SetupView(engine: idle, finish: {}, startAt: step), dark: false)
        }
    }

    /// An engine with the demo's sample state, changed by `edit`.
    private static func sample(_ edit: (EngineClient) -> Void) -> EngineClient {
        let e = EngineClient()
        e.running = true; e.mode = "run"; e.cameraOn = true; e.fps = 30; e.target = "Google Meet"
        e.frame = cameraStandIn()
        e.config = ["onboarded": true, "signer_name": "Sacchin", "letter_hold": 2.5, "voice_id": "a"]
        e.quickReplies = [("One moment", false), ("Sorry, can I jump in?", true), ("Sounds good", false), ("Could you repeat that?", false)]
        e.voices = [.init(id: "a", name: "Skylar", about: "Warm and friendly"), .init(id: "b", name: "Daniel", about: "Calm and clear"),
                    .init(id: "c", name: "Gemma", about: "Bright and upbeat")]
        e.meetLog = [("them", "The dashboard's ready. Pranav redesigned the charts in Figma."),
                     ("you", "There's a color problem in Figma."), ("them", "Sacchin, can you sort it out with Pranav?"),
                     ("you", "I'll meet with Pranav tomorrow.")]
        e.captions = ["Sacchin, can you sort it out with Pranav?"]
        e.history = [HistoryItem(glosses: ["ME", "MEET", "PRANAV", "TOMORROW"], sentence: "I'll meet with Pranav tomorrow.",
                                 route: "voice", sent: true, date: Date()),
                     HistoryItem(glosses: ["FIGMA", "COLOR", "PROBLEM"], sentence: "There's a color problem in Figma.",
                                 route: "voice", sent: true, date: Date().addingTimeInterval(-40))]
        e.autocompleteStats = .init(accepted: 2, lettersSaved: 9, words: 15, latencyMs: 44, searchMs: 41, search: "moss")
        edit(e)
        return e
    }

    /// A dark stand-in for the camera: a person's outline and the signing box.
    private static func cameraStandIn() -> NSImage {
        NSImage(size: NSSize(width: 640, height: 480), flipped: true) { r in
            NSGradient(colors: [NSColor(white: 0.20, alpha: 1), NSColor(white: 0.08, alpha: 1)])?.draw(in: r, angle: 90)
            NSColor(white: 0.32, alpha: 1).setFill()
            NSBezierPath(ovalIn: NSRect(x: 270, y: 70, width: 100, height: 124)).fill()
            NSBezierPath(roundedRect: NSRect(x: 180, y: 210, width: 280, height: 300), xRadius: 90, yRadius: 90).fill()
            NSColor(red: 1, green: 0.82, blue: 0, alpha: 1).setStroke()
            let box = NSBezierPath(rect: NSRect(x: 64, y: 24, width: 512, height: 360)); box.lineWidth = 4; box.stroke()
            return true
        }
    }
}
