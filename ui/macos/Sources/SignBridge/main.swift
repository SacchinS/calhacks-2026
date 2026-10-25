import AppKit
import AVFoundation
import SwiftUI

/// Menu-bar app: a status item with a menu, plus windows for setup, the live preview and settings.
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let engine = EngineClient()
    private var statusItem: NSStatusItem!
    private var windows: [String: NSWindow] = [:]
    private var listening = false
    private var mentionBanner: MentionBanner?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.image = Brand.menuBarImage(listening: false)
        let menu = NSMenu()
        menu.delegate = self
        statusItem.menu = menu
        engine.start()
        mentionBanner = MentionBanner(engine: engine)
        // First launch: walk through setup once the engine has reported its config.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [weak self] in
            guard let self else { return }
            if !self.engine.onboarded { self.showSetup() } else { self.showPreview() }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        engine.stop()
    }

    // Rebuild the menu each time it opens so it shows the current state.
    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        let states = ["idle": "Watching for signs", "listening": "Listening to your signs",
                      "thinking": "Writing your sentence", "confirming": "Waiting for YES or NO",
                      "sending": "Sending"]
        let state = engine.running ? (listening ? states[engine.state] ?? engine.state : "Paused") : "Starting…"
        let header = NSMenuItem(title: "", action: nil, keyEquivalent: "")
        header.attributedTitle = NSAttributedString(
            string: "SignBridge\n", attributes: [.font: NSFont.boldSystemFont(ofSize: 13)])
            .appending(NSAttributedString(string: state, attributes: [
                .font: NSFont.systemFont(ofSize: 12), .foregroundColor: NSColor.secondaryLabelColor]))
        menu.addItem(header)
        if let error = engine.engineError {
            menu.addItem(NSMenuItem(title: "⚠︎ \(error.prefix(60))", action: nil, keyEquivalent: ""))
        }
        menu.addItem(.separator())
        menu.addItem(item(listening ? "Pause SignBridge" : "Start SignBridge", #selector(toggleListening), "s"))
        menu.addItem(item("Show Preview", #selector(showPreview), "p"))
        menu.addItem(item("Demo Mode", #selector(showDemo), "d"))
        let displays = NSMenu()
        for screen in NSScreen.screens {
            let i = item(screen.localizedName, #selector(showDemoOnDisplay(_:)), "")
            i.representedObject = screen.localizedName
            i.state = screen.localizedName == UserDefaults.standard.string(forKey: demoScreenKey) ? .on : .off
            displays.addItem(i)
        }
        let demoOn = NSMenuItem(title: "Demo Mode On", action: nil, keyEquivalent: "")
        demoOn.submenu = displays
        menu.addItem(demoOn)
        menu.addItem(.separator())
        menu.addItem(item("Run Setup…", #selector(showSetup), ""))
        menu.addItem(item("Reset SignBridge…", #selector(resetApp), ""))
        menu.addItem(item("Settings…", #selector(showSettings), ","))
        menu.addItem(.separator())
        menu.addItem(item("Quit SignBridge", #selector(quit), "q"))
    }

    private func item(_ title: String, _ action: Selector, _ key: String) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: action, keyEquivalent: key)
        i.target = self
        return i
    }

    @objc func toggleListening() {
        listening.toggle()
        engine.setMode(listening ? "run" : "off")
        statusItem.button?.image = Brand.menuBarImage(listening: listening)
    }

    func startListening() {
        if !listening { toggleListening() }
    }

    @objc func showPreview() {
        if !listening { startListening() }
        engine.setPreview(true)
        open("preview", title: "SignBridge", size: NSSize(width: 720, height: 820),
             view: PreviewView(engine: engine, showDemo: { [weak self] in self?.showDemo() }), seamless: true) { [weak self] in self?.engine.setPreview(false) }
        windows["preview"]?.appearance = NSAppearance(named: .darkAqua)
    }

    @objc func showSetup() {
        if listening { toggleListening() }
        open("setup", title: "Set up SignBridge", size: NSSize(width: 820, height: 620),
             view: SetupView(engine: engine, finish: { [weak self] in
                 self?.windows["setup"]?.close()
                 self?.startListening()
                 self?.showPreview()
             }), seamless: true) { [weak self] in
            self?.engine.setPreview(false)
            if self?.listening == false { self?.engine.setMode("off") }
        }
    }

    /// Full-screen stage for an audience. Esc leaves it.
    @objc func showDemo() {
        if !listening { startListening() }
        engine.setPreview(true)
        open("demo", title: "SignBridge Demo", size: NSSize(width: 1280, height: 800),
             view: DemoView(engine: engine, exit: { [weak self] in self?.windows["demo"]?.close() }),
             seamless: true) { [weak self] in
            if self?.windows["preview"] == nil { self?.engine.setPreview(false) }
        }
        if let w = windows["demo"] {
            w.appearance = NSAppearance(named: .darkAqua)
            w.collectionBehavior.insert(.fullScreenPrimary)
            watchDemo(w)
            if !w.styleMask.contains(.fullScreen) {
                placeOnDemoDisplay(w)
                w.toggleFullScreen(nil)
            }
        }
    }

    // MARK: Demo Mode display (calhacks-2026 addition): remember it, and send Demo Mode to any display.

    private let demoScreenKey = "demo.screen"
    private var demoObservers: [NSObjectProtocol] = []
    private var demoMovePending = false

    @objc func showDemoOnDisplay(_ sender: NSMenuItem) {
        guard let name = sender.representedObject as? String else { return }
        UserDefaults.standard.set(name, forKey: demoScreenKey)
        if let w = windows["demo"], w.styleMask.contains(.fullScreen), w.screen?.localizedName != name {
            demoMovePending = true  // a fullscreen window can't move: leave fullscreen, then move (watchDemo)
            w.toggleFullScreen(nil)
        } else {
            showDemo()
        }
    }

    /// Center the window on the remembered display (the main one if it's not connected).
    private func placeOnDemoDisplay(_ w: NSWindow) {
        let name = UserDefaults.standard.string(forKey: demoScreenKey)
        guard let screen = NSScreen.screens.first(where: { $0.localizedName == name }) else { return }
        let area = screen.visibleFrame
        let size = NSSize(width: min(w.frame.width, area.width), height: min(w.frame.height, area.height))
        w.setFrame(NSRect(x: area.midX - size.width / 2, y: area.midY - size.height / 2,
                          width: size.width, height: size.height), display: true)
    }

    private func watchDemo(_ w: NSWindow) {
        guard demoObservers.isEmpty else { return }
        let center = NotificationCenter.default
        let remember: @Sendable (Notification) -> Void = { note in
            MainActor.assumeIsolated {
                if let name = (note.object as? NSWindow)?.screen?.localizedName {
                    UserDefaults.standard.set(name, forKey: "demo.screen")
                }
            }
        }
        demoObservers = [
            center.addObserver(forName: NSWindow.didEnterFullScreenNotification, object: w, queue: .main, using: remember),
            center.addObserver(forName: NSWindow.didChangeScreenNotification, object: w, queue: .main, using: remember),
            center.addObserver(forName: NSWindow.didExitFullScreenNotification, object: w, queue: .main) { [weak self] note in
                MainActor.assumeIsolated {
                    guard let self, self.demoMovePending, let w = note.object as? NSWindow else { return }
                    self.demoMovePending = false
                    self.placeOnDemoDisplay(w)
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { w.toggleFullScreen(nil) }
                }
            },
            center.addObserver(forName: NSWindow.willCloseNotification, object: w, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated {
                    self?.demoObservers.forEach { NotificationCenter.default.removeObserver($0) }
                    self?.demoObservers = []
                }
            },
        ]
    }


    @objc func showSettings() {
        open("settings", title: "SignBridge Settings", size: NSSize(width: 480, height: 470),
             view: SettingsView(engine: engine, runSetup: { [weak self] in self?.showSetup() },
                                resetApp: { [weak self] in self?.resetApp() }))
    }

    /// Start over: the settings back to their defaults, then setup again. Asks first.
    @objc func resetApp() {
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "Reset SignBridge?"
        alert.informativeText = "Your name, voice, signing position and settings go back to their defaults, and setup starts again. Your recorded signs and API keys stay."
        alert.addButton(withTitle: "Reset")
        alert.addButton(withTitle: "Cancel")
        alert.showsSuppressionButton = true
        alert.suppressionButton?.title = "Also forget remembered words"
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        engine.reset(forgetWords: alert.suppressionButton?.state == .on)
        windows["settings"]?.close()
        showSetup()
    }

    @objc func quit() { NSApp.terminate(nil) }

    private func open<V: View>(_ key: String, title: String, size: NSSize, view: V, seamless: Bool = false,
                               onClose: (() -> Void)? = nil) {
        if let w = windows[key] {
            w.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let w = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                         styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        w.title = title
        if seamless {  // content runs under a transparent title bar
            w.styleMask.insert(.fullSizeContentView)
            w.titlebarAppearsTransparent = true
            w.titleVisibility = .hidden
        }
        w.contentView = NSHostingView(rootView: view)
        w.isReleasedWhenClosed = false
        w.center()
        let observer = WindowCloseObserver { [weak self] in
            self?.windows[key] = nil
            onClose?()
        }
        w.delegate = observer
        objc_setAssociatedObject(w, "closeObserver", observer, .OBJC_ASSOCIATION_RETAIN)
        windows[key] = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

final class WindowCloseObserver: NSObject, NSWindowDelegate {
    let onClose: () -> Void
    init(_ onClose: @escaping () -> Void) { self.onClose = onClose }
    func windowWillClose(_ notification: Notification) { onClose() }
}

MainActor.assumeIsolated {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
