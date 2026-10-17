// Cutlab — нативное окно macOS вокруг монтажки (http://127.0.0.1:8777).
// Шапка приложения стоит в одной строке с кнопками окна (как в JetBrains): заголовок прозрачный,
// содержимое под ним; окно тянется за пустые места шапки (области кнопок присылает страница).
// Сборка: tools/cutlab_app/build.sh
import Cocoa
import WebKit

let NIK = "/Users/romanroak/NIK"
let URL_BASE = "http://127.0.0.1:8777"

func serverAlive() -> Bool {
    guard let url = URL(string: URL_BASE + "/api/ping") else { return false }
    var req = URLRequest(url: url); req.timeoutInterval = 0.5
    let sem = DispatchSemaphore(value: 0); var ok = false
    URLSession.shared.dataTask(with: req) { _, resp, _ in ok = (resp as? HTTPURLResponse)?.statusCode == 200; sem.signal() }.resume()
    _ = sem.wait(timeout: .now() + 0.8)
    return ok
}

func startServer() {
    // логин-оболочка — тот же python3, что в Терминале; arch -arm64 — numpy у нас только под Apple Silicon
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/zsh")
    p.arguments = ["-lc", "cd '\(NIK)' && nohup arch -arm64 python3 studio/editor/server.py >> studio/editor/server.log 2>&1 &"]
    try? p.run(); p.waitUntilExit()
}

/// Полоса над шапкой: пустые места тянут окно (двойной клик — развернуть), над кнопками — пропускает клики в страницу.
final class DragStrip: NSView {
    var holes: [NSRect] = []
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? {
        let p = convert(point, from: superview)
        guard bounds.contains(p) else { return nil }
        return holes.contains(where: { $0.contains(p) }) ? nil : self
    }
    override func mouseDown(with event: NSEvent) {
        if event.clickCount == 2 { window?.performZoom(nil) } else { window?.performDrag(with: event) }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKUIDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    let strip = DragStrip()
    var headerH: CGFloat = 40

    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()
        let cfg = WKWebViewConfiguration()
        cfg.mediaTypesRequiringUserActionForPlayback = []
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")      // правый клик → «Проверить элемент»
        if #available(macOS 12.3, *) { cfg.preferences.isElementFullscreenEnabled = true }   // кадр плеера во весь экран (Fullscreen API)
        let ucc = WKUserContentController()
        ucc.add(self, name: "cutlab")
        ucc.addUserScript(WKUserScript(source: "window.CUTLAB_NATIVE = { lightsW: 78 }; document.documentElement.classList.add('native');",
                                       injectionTime: .atDocumentStart, forMainFrameOnly: true))
        cfg.userContentController = ucc

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1600, height: 1000),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.title = "Cutlab"
        window.minSize = NSSize(width: 1100, height: 700)
        window.backgroundColor = NSColor(calibratedRed: 0.078, green: 0.078, blue: 0.086, alpha: 1)
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("CutlabMain")
        if !window.setFrameUsingName("CutlabMain") { window.center() }

        web = WKWebView(frame: .zero, configuration: cfg)
        web.uiDelegate = self; web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        let root = NSView(); window.contentView = root
        web.translatesAutoresizingMaskIntoConstraints = false
        strip.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(web); root.addSubview(strip)
        NSLayoutConstraint.activate([
            web.leadingAnchor.constraint(equalTo: root.leadingAnchor), web.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            web.topAnchor.constraint(equalTo: root.topAnchor), web.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            strip.leadingAnchor.constraint(equalTo: root.leadingAnchor), strip.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            strip.topAnchor.constraint(equalTo: root.topAnchor),
        ])
        stripHeight = strip.heightAnchor.constraint(equalToConstant: headerH); stripHeight.isActive = true
        window.makeKeyAndOrderFront(nil)
        placeLights()
        NotificationCenter.default.addObserver(forName: NSWindow.didResizeNotification, object: window, queue: .main) { [weak self] _ in self?.placeLights() }
        for nm in [NSWindow.didExitFullScreenNotification, NSWindow.didEnterFullScreenNotification] {
            NotificationCenter.default.addObserver(forName: nm, object: window, queue: .main) { [weak self] _ in self?.placeLights() }
        }

        loadWhenReady(tries: 0)
        NSApp.activate(ignoringOtherApps: true)
    }
    var stripHeight: NSLayoutConstraint!

    func loadWhenReady(tries: Int) {
        DispatchQueue.global().async {
            let alive = serverAlive()
            if !alive && tries == 0 { startServer() }
            DispatchQueue.main.async {
                if alive { self.web.load(URLRequest(url: URL(string: URL_BASE + "/")!)) }
                else if tries < 60 { DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.loadWhenReady(tries: tries + 1) } }
                else { self.web.loadHTMLString("<body style='background:#141416;color:#ccc;font:14px -apple-system;padding:80px'>Сервер Cutlab не запустился — см. studio/editor/server.log</body>", baseURL: nil) }
            }
        }
    }

    /// Кнопки окна — по центру шапки по вертикали, как в JetBrains.
    func placeLights() {
        let kinds: [NSWindow.ButtonType] = [.closeButton, .miniaturizeButton, .zoomButton]
        guard let close = window.standardWindowButton(.closeButton), let bar = close.superview else { return }
        let barH = bar.frame.height
        var right: CGFloat = 0
        for k in kinds {
            guard let b = window.standardWindowButton(k) else { continue }
            let y = barH - headerH / 2 - b.frame.height / 2       // x системный, меняем только высоту
            b.setFrameOrigin(NSPoint(x: b.frame.origin.x, y: y))
            right = max(right, b.frame.maxX)
        }
        let pad = window.styleMask.contains(.fullScreen) ? 12 : right + 14
        web?.evaluateJavaScript("document.documentElement.style.setProperty('--lights-w','\(Int(pad))px')", completionHandler: nil)
    }

    // страница присылает высоту шапки и прямоугольники кнопок (туда клики проходят, остальное тянет окно)
    func userContentController(_ ucc: WKUserContentController, didReceive m: WKScriptMessage) {
        guard let d = m.body as? [String: Any] else { return }
        if let h = d["h"] as? Double { headerH = CGFloat(h); stripHeight.constant = headerH; placeLights() }
        if let rs = d["holes"] as? [[Double]] { strip.holes = rs.map { NSRect(x: $0[0], y: $0[1], width: $0[2], height: $0[3]) } }
        if let url = d["open"] as? String, let u = URL(string: url) { NSWorkspace.shared.open(u) }
        // плеер во весь экран без Fullscreen API — окно целиком в полноэкранный режим и обратно
        if let fs = d["fullscreen"] as? Bool, fs != window.styleMask.contains(.fullScreen) { window.toggleFullScreen(nil) }
    }

    // target=_blank и window.open — в браузере по умолчанию
    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures f: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url { NSWorkspace.shared.open(u) }
        return nil
    }
    // <input type=file> — стандартный диалог выбора
    func webView(_ w: WKWebView, runOpenPanelWith p: WKOpenPanelParameters, initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.allowsMultipleSelection = p.allowsMultipleSelection; panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { r in done(r == .OK ? panel.urls : nil) }
    }
    func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage s: String, initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = s; a.beginSheetModal(for: window) { _ in done() }
    }
    func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage s: String, initiatedByFrame f: WKFrameInfo, completionHandler done: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = s; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Отмена")
        a.beginSheetModal(for: window) { r in done(r == .alertFirstButtonReturn) }
    }
    func webViewWebContentProcessDidTerminate(_ w: WKWebView) { w.reload() }
    func webView(_ w: WKWebView, didFinish n: WKNavigation!) { placeLights() }

    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows v: Bool) -> Bool { if !v { window.makeKeyAndOrderFront(nil) }; return true }
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    func buildMenu() {
        let main = NSMenu()
        func item(_ title: String, _ sel: Selector?, _ key: String, _ mods: NSEvent.ModifierFlags = .command) -> NSMenuItem {
            let i = NSMenuItem(title: title, action: sel, keyEquivalent: key); i.keyEquivalentModifierMask = mods; return i
        }
        let app = NSMenu(); app.addItem(item("О Cutlab", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""))
        app.addItem(.separator()); app.addItem(item("Скрыть Cutlab", #selector(NSApplication.hide(_:)), "h"))
        app.addItem(item("Выйти из Cutlab", #selector(NSApplication.terminate(_:)), "q"))
        // «Правка» без ⌘Z: отмену и повтор ведёт сама монтажка (её горячие клавиши)
        let edit = NSMenu(title: "Правка")
        edit.addItem(item("Вырезать", #selector(NSText.cut(_:)), "x")); edit.addItem(item("Копировать", #selector(NSText.copy(_:)), "c"))
        edit.addItem(item("Вставить", #selector(NSText.paste(_:)), "v")); edit.addItem(item("Выделить всё", #selector(NSText.selectAll(_:)), "a"))
        let view = NSMenu(title: "Вид")
        view.addItem(item("Обновить", #selector(reload), "r"))
        view.addItem(item("Во весь экран", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]))
        let win = NSMenu(title: "Окно")
        win.addItem(item("Свернуть", #selector(NSWindow.performMiniaturize(_:)), "m")); win.addItem(item("Масштаб", #selector(NSWindow.performZoom(_:)), ""))
        for (title, menu) in [("Cutlab", app), ("Правка", edit), ("Вид", view), ("Окно", win)] {
            let top = NSMenuItem(title: title, action: nil, keyEquivalent: ""); top.submenu = menu; main.addItem(top)
        }
        NSApp.mainMenu = main; NSApp.windowsMenu = win
    }
    @objc func reload() { web.reload() }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
