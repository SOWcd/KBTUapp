import SafariServices
import UIKit
import WebKit

// The web app in one web view, and the bridge it talks to (web/src/lib/native.ts). The page finds
// window.kbNative = { v, caps } before any of its scripts and calls webkit.messageHandlers.kb.postMessage({ cmd, ... }),
// which answers with a promise. Only our own site's main frame is answered, and the web view is bound to our domain
// (WKAppBoundDomains, limitsNavigationsToAppBoundDomains): the bridge never reaches another site's script.
//
// VERSION: bump it with a new capability or a changed message, here and in native.ts's comment; the web checks
// capabilities, never the version, so an old app keeps working with a newer web.
final class WebController: UIViewController, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandlerWithReply, WKHTTPCookieStoreObserver,
                           UITabBarDelegate {
    static let version = 2
    static let caps = ["apple", "push", "scan", "tabs", "tickets", "tglink"]
    /// the web's accent ink (tokens.css --accent-text), for the tab bar's selected item and the offline screen
    static let accent = UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 143 / 255.0, green: 168 / 255.0, blue: 1, alpha: 1)
        : UIColor(red: 42 / 255.0, green: 87 / 255.0, blue: 230 / 255.0, alpha: 1) }
    private let home = URL(string: Bundle.main.object(forInfoDictionaryKey: "KBHome") as? String ?? "https://kbtu.sow.kz/")!
    private let cookie = "__Host-kb-session"
    private var web: WKWebView!
    private var loaded = false
    private var themeWatch: NSKeyValueObservation?
    private let apple = AppleSignIn()
    private let telegram = TelegramLink()
    private weak var scanner: Scanner?
    private let tabBar = UITabBar()
    private var tabIds: [String] = []
    private var tabsShown = false
    private var offline: OfflineView?

    /// the page's own theme (its theme-color is its ground), which may differ from the phone's
    private var pageDark: Bool? {
        guard let c = web?.themeColor else { return nil }
        var white: CGFloat = 0
        _ = c.getWhite(&white, alpha: nil)
        return white < 0.5
    }

    override var preferredStatusBarStyle: UIStatusBarStyle {
        if offline != nil { return .default }
        guard let dark = pageDark else { return .default }
        return dark ? .lightContent : .darkContent
    }

    override func loadView() {
        let config = WKWebViewConfiguration()
        config.limitsNavigationsToAppBoundDomains = true  // Info.plist WKAppBoundDomains: our site (and t.me's post frames)
        let caps = WebController.caps.map { "\"\($0)\"" }.joined(separator: ",")
        config.userContentController.addUserScript(WKUserScript(
            source: "window.kbNative={v:\(WebController.version),caps:[\(caps)]};", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        config.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "kb")
        config.applicationNameForUserAgent = "KBTUApp/\(WebController.version)"
        config.allowsInlineMediaPlayback = true
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.isOpaque = false  // the ground under the page is the launch screen's colour: no white flash in dark
        web.backgroundColor = UIColor(named: "Ground")
        web.scrollView.backgroundColor = UIColor(named: "Ground")
        web.scrollView.contentInsetAdjustmentBehavior = .never  // the page pads itself (viewport-fit=cover, env(safe-area-inset-*))
        // the page's theme-color is its ground: the status bar's text and the tab bar follow it (a dark page in a light phone too)
        themeWatch = web.observe(\.themeColor) { [weak self] _, _ in self?.themeChanged() }

        // the page fills the screen and the tab bar floats over its bottom in the system's material, as in any iPhone app;
        // the page ends its content above the bar (tokens.css data-ntabs: --nav-h is the bar's 49 pt)
        let root = UIView()
        root.backgroundColor = UIColor(named: "Ground")
        web.frame = root.bounds
        web.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        root.addSubview(web)
        styleTabBar()
        tabBar.delegate = self
        tabBar.isHidden = true  // until the signed-in app sends its tabs (not on the entrance)
        tabBar.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(tabBar)
        NSLayoutConstraint.activate([
            tabBar.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            tabBar.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            tabBar.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            tabBar.topAnchor.constraint(equalTo: root.safeAreaLayoutGuide.bottomAnchor, constant: -49),
        ])
        view = root
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        restoreSession { [weak self] in self?.load(start: "") }
    }

    private func themeChanged() {
        setNeedsStatusBarAppearanceUpdate()
        tabBar.overrideUserInterfaceStyle = pageDark.map { $0 ? .dark : .light } ?? .unspecified
    }

    // ---- the session: the cookie the server set, copied to the Keychain and put back at launch ----

    private func restoreSession(then: @escaping () -> Void) {
        let store = web.configuration.websiteDataStore.httpCookieStore
        guard let token = Keychain.read(), let host = home.host, let c = HTTPCookie(properties: [
            .name: cookie, .value: token, .domain: host, .path: "/", .secure: "TRUE",
            HTTPCookiePropertyKey("HttpOnly"): "TRUE", .sameSitePolicy: HTTPCookieStringPolicy.sameSiteLax.rawValue,
            .expires: Date().addingTimeInterval(60 * 86400)]) else {
            store.add(self)
            return then()
        }
        store.setCookie(c) { [weak self] in
            if let self { store.add(self) }
            then()
        }
    }

    func cookiesDidChange(in store: WKHTTPCookieStore) {
        store.getAllCookies { [cookie, home] all in
            let mine = all.first { $0.name == cookie && $0.domain == home.host }
            if let value = mine?.value, value != Keychain.read() { Keychain.write(value) }
            if mine == nil {  // signed out (the server cleared it): nothing of the account stays on the phone
                Keychain.delete()
                Tickets.clear()
            }
        }
    }

    // ---- loading, the offline screen and notification taps ----

    private func load(start: String) {
        var url = URLComponents(url: home, resolvingAgainstBaseURL: false)!
        if !start.isEmpty { url.queryItems = [URLQueryItem(name: "startapp", value: start)] }
        web.load(URLRequest(url: url.url!))
    }

    /// A notification's place: at launch the page loads there; open already, the page is told (kb:open).
    func open(start: String) {
        guard isViewLoaded, !start.isEmpty, start.range(of: "^[A-Za-z0-9_-]{1,64}$", options: .regularExpression) != nil else { return }
        if !loaded { return load(start: start) }
        web.evaluateJavaScript("dispatchEvent(new CustomEvent('kb:open', { detail: '\(start)' }))")
    }

    // a new page (a reload after signing out, the entrance): no tabs until it sends its own
    func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        if webView === web { showTabs(false) }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loaded = true
        hideOffline()
    }

    // the site didn't come (no network, a captive portal, our server down): the bundled screen instead of a blank one
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let e = error as NSError
        if webView === web && e.domain == NSURLErrorDomain && e.code != NSURLErrorCancelled { showOffline() }
    }

    // the connection went after the page began (a retry on a weak network): the offline screen again, not a spinner forever
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        let e = error as NSError
        if webView === web && offline != nil && e.domain == NSURLErrorDomain && e.code != NSURLErrorCancelled { showOffline() }
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if webView === web, response.isForMainFrame, let http = response.response as? HTTPURLResponse, http.statusCode >= 500 {
            decisionHandler(.cancel)
            return showOffline()
        }
        decisionHandler(.allow)
    }

    // shown again after a retry that failed: the new one replaces the old in place (the same screen, its spinner gone)
    private func showOffline() {
        loaded = false
        showTabs(false)
        offline?.removeFromSuperview()
        let saved = Tickets.load()
        let o = OfflineView(lang: saved.lang, tickets: saved.tickets) { [weak self] in self?.load(start: "") }
        o.frame = view.bounds
        o.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(o)
        offline = o
        setNeedsStatusBarAppearanceUpdate()
    }

    private func hideOffline() {
        guard let o = offline else { return }
        offline = nil
        UIView.animate(withDuration: 0.25, animations: { o.alpha = 0 }, completion: { _ in o.removeFromSuperview() })
        setNeedsStatusBarAppearanceUpdate()
    }

    // the process behind the page died (memory): load again rather than leave a blank screen
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        loaded = false
        load(start: "")
    }

    // ---- where links go: our site here, everything else outside (Telegram's sign-in: the system's sheet, TelegramLink) ----

    private func ours(_ url: URL?) -> Bool {
        url?.scheme == "https" && url?.host == home.host
    }

    private func outside(_ url: URL) {
        if url.scheme == "https" && url.host != "t.me" {
            present(SFSafariViewController(url: url), animated: true)
        } else {
            UIApplication.shared.open(url)  // t.me, tg:, mailto:, tel: — their own apps
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        if action.targetFrame?.isMainFrame == false || ours(url) || url.scheme == "about" || url.scheme == "blob" || url.scheme == "data" {
            return decisionHandler(.allow)
        }
        decisionHandler(.cancel)
        outside(url)
    }

    // window.open: a link going outside; no second web view (no popup ever shares this one's bridge)
    func webView(_ webView: WKWebView, createWebViewWith config: WKWebViewConfiguration, for action: WKNavigationAction,
                 windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { outside(url) }
        return nil
    }

    // the page's alert/confirm (rare: the app has its own sheets) as the system's
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping () -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
        (presentedViewController ?? self).present(a, animated: true)
    }

    // the page's own camera (getUserMedia) on our site: no second question after the system's one
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo,
                 type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(origin.protocol == "https" && origin.host == home.host ? .grant : .prompt)
    }

    // ---- the tab bar: the web's tabs, drawn natively; a tap switches the web's tab, the web says which is on ----

    private static let symbols = ["afisha": "ticket", "forum": "bubble.left.and.bubble.right", "club": "person.3", "profile": "person.crop.circle"]

    private func styleTabBar() {
        // the web's dock ink for the others (tokens.css --dock-ink), its accent for the one on
        let ink = UIColor { $0.userInterfaceStyle == .dark
            ? UIColor(red: 235 / 255.0, green: 235 / 255.0, blue: 245 / 255.0, alpha: 0.5)
            : UIColor(red: 11 / 255.0, green: 20 / 255.0, blue: 51 / 255.0, alpha: 0.45) }
        let a = UITabBarAppearance()
        a.configureWithDefaultBackground()
        for item in [a.stackedLayoutAppearance, a.inlineLayoutAppearance, a.compactInlineLayoutAppearance] {
            item.normal.iconColor = ink
            item.normal.titleTextAttributes = [.foregroundColor: ink]
            item.selected.iconColor = WebController.accent
            item.selected.titleTextAttributes = [.foregroundColor: WebController.accent]
        }
        tabBar.standardAppearance = a
        tabBar.scrollEdgeAppearance = a  // the same at rest: no bar that changes as the page scrolls under it
        tabBar.tintColor = WebController.accent
    }

    private func setTabs(_ items: [[String: Any]], active: String, hidden: Bool) {
        let ids = items.compactMap { $0["id"] as? String }.filter { $0.range(of: "^[a-z]{1,16}$", options: .regularExpression) != nil }
        guard ids.count == items.count else { return }
        let titles = items.map { $0["title"] as? String ?? "" }
        if ids != tabIds || titles != (tabBar.items ?? []).map({ $0.title ?? "" }) {
            tabIds = ids
            var built: [UITabBarItem] = []
            for (i, id) in ids.enumerated() {
                let symbol = WebController.symbols[id] ?? "circle"
                let item = UITabBarItem(title: titles[i], image: UIImage(systemName: symbol),
                                        selectedImage: UIImage(systemName: symbol + ".fill") ?? UIImage(systemName: symbol))
                item.tag = i
                built.append(item)
            }
            tabBar.setItems(built, animated: false)
        }
        for (i, item) in (tabBar.items ?? []).enumerated() {
            item.badgeValue = (items[i]["dot"] as? Bool) == true ? "" : nil  // an empty badge: the web's dot
        }
        if let i = ids.firstIndex(of: active), let items = tabBar.items { tabBar.selectedItem = items[i] }
        showTabs(!hidden && !ids.isEmpty)
    }

    // slides away under a sheet the way the web's bar did, and back
    private func showTabs(_ on: Bool) {
        guard on != tabsShown else { return }
        tabsShown = on
        if on && tabBar.isHidden {
            tabBar.transform = CGAffineTransform(translationX: 0, y: tabBar.bounds.height)
            tabBar.isHidden = false
        }
        UIView.animate(withDuration: 0.4, delay: 0, usingSpringWithDamping: 0.9, initialSpringVelocity: 0, options: [.beginFromCurrentState], animations: {
            self.tabBar.transform = on ? .identity : CGAffineTransform(translationX: 0, y: self.tabBar.bounds.height)
        }, completion: { _ in
            if !self.tabsShown { self.tabBar.isHidden = true }
        })
    }

    func tabBar(_ tabBar: UITabBar, didSelect item: UITabBarItem) {
        guard tabIds.indices.contains(item.tag) else { return }
        web.evaluateJavaScript("window.kbNative && window.kbNative.tab && window.kbNative.tab('\(tabIds[item.tag])'); void 0")
    }

    // ---- the bridge ----

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler reply: @escaping (Any?, String?) -> Void) {
        let origin = message.frameInfo.securityOrigin
        guard message.frameInfo.isMainFrame, message.webView === web, origin.protocol == "https", origin.host == home.host,
              let body = message.body as? [String: Any], let cmd = body["cmd"] as? String else {
            return reply(nil, "refused")
        }
        switch cmd {
        case "apple":
            guard let nonce = body["nonce"] as? String, nonce.count >= 32 else { return reply(nil, "nonce") }
            apple.start(nonce: nonce, window: view.window) { token in reply(token.map { ["token": $0] }, nil) }
        case "push":
            Push.shared.token { token, denied in
                if denied { reply(["denied": true], nil) } else { reply(token.map { ["token": $0] }, nil) }
            }
        case "scan":
            scanner?.dismiss(animated: false)
            let s = Scanner(prompt: body["text"] as? String ?? "") { [weak self] code in self?.scanned(code) }
            scanner = s
            present(s, animated: true)
            reply(nil, nil)
        case "scanClose":
            scanner?.dismiss(animated: true)
            reply(nil, nil)
        case "tabs":
            guard let items = body["items"] as? [[String: Any]], items.count <= 6 else { return reply(nil, "items") }
            setTabs(items, active: body["active"] as? String ?? "", hidden: body["hidden"] as? Bool ?? false)
            reply(nil, nil)
        case "tickets":
            guard let list = body["tickets"] as? [[String: Any]] else { return reply(nil, "tickets") }
            let tickets = list.prefix(50).compactMap { t -> Tickets.Ticket? in
                guard let title = t["title"] as? String, let qr = t["qr"] as? String, (1...64).contains(qr.count) else { return nil }
                return Tickets.Ticket(title: String(title.prefix(200)), at: (t["at"] as? NSNumber)?.doubleValue ?? 0,
                                      place: String((t["place"] as? String ?? "").prefix(200)), qr: qr)
            }
            let lang = body["lang"] as? String ?? ""
            Tickets.save(Array(tickets), lang: ["ru", "kk", "en"].contains(lang) ? lang : "")
            reply(nil, nil)
        case "tglink":
            // only Telegram's sign-in page: the sheet is no general browser for the page to open
            guard let s = body["url"] as? String, let url = URL(string: s), url.scheme == "https", url.host == "oauth.telegram.org" else {
                return reply(nil, "url")
            }
            telegram.start(url: url, window: view.window) { back in reply(back.map { ["url": $0.absoluteString] }, nil) }
        default:
            reply(nil, "unknown")
        }
    }

    // a code to the page's handler (native.ts scan); it answers true to close the scanner
    private func scanned(_ code: String) {
        guard let json = try? JSONSerialization.data(withJSONObject: [code]), let arg = String(data: json, encoding: .utf8) else { return }
        web.evaluateJavaScript("!!(window.kbNative && window.kbNative.scanned && window.kbNative.scanned(\(arg)[0]))") { [weak self] done, _ in
            if (done as? Bool) == true { self?.scanner?.dismiss(animated: true) }
        }
    }
}
