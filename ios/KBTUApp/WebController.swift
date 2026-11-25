import SafariServices
import UIKit
import WebKit

// The web app in one web view, and the bridge it talks to (web/src/lib/native.ts). The page finds
// window.kbNative = { v, caps } before any of its scripts and calls webkit.messageHandlers.kb.postMessage({ cmd, ... }),
// which answers with a promise. Only our own site's main frame is answered.
//
// VERSION: bump it with a new capability or a changed message, here and in native.ts's comment; the web checks
// capabilities, never the version, so an old app keeps working with a newer web.
final class WebController: UIViewController, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandlerWithReply, WKHTTPCookieStoreObserver {
    static let version = 1
    static let caps = ["apple", "push", "scan"]
    private let home = URL(string: Bundle.main.object(forInfoDictionaryKey: "KBHome") as? String ?? "https://kbtu.sow.kz/")!
    private let cookie = "__Host-kb-session"
    private var web: WKWebView!
    private var loaded = false
    private var themeWatch: NSKeyValueObservation?
    private let apple = AppleSignIn()
    private weak var scanner: Scanner?
    private weak var popup: UIViewController?

    override var preferredStatusBarStyle: UIStatusBarStyle {
        guard let c = web?.themeColor else { return .default }
        var white: CGFloat = 0
        _ = c.getWhite(&white, alpha: nil)
        return white < 0.5 ? .lightContent : .darkContent
    }

    override func loadView() {
        let config = WKWebViewConfiguration()
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
        // the page's theme-color is its ground: the status bar's text follows it (a dark page in a light phone too)
        themeWatch = web.observe(\.themeColor) { [weak self] _, _ in self?.setNeedsStatusBarAppearanceUpdate() }
        view = web
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        restoreSession { [weak self] in self?.load(start: "") }
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
            if mine == nil { Keychain.delete() }  // signed out (the server cleared it)
        }
    }

    // ---- loading and notification taps ----

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

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loaded = true
    }

    // the process behind the page died (memory): load again rather than leave a blank screen
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        loaded = false
        load(start: "")
    }

    // ---- where links go: our site and Telegram's sign-in page here, everything else outside ----

    private func ours(_ url: URL?) -> Bool {
        url?.scheme == "https" && (url?.host == home.host || url?.host == "oauth.telegram.org")
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

    // window.open: Telegram's sign-in button opens its page as a popup and hears back through window.opener, so that
    // one is a web view on top sharing this one's process; any other new window is a link going outside
    func webView(_ webView: WKWebView, createWebViewWith config: WKWebViewConfiguration, for action: WKNavigationAction,
                 windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard let url = action.request.url else { return nil }
        guard url.host == "oauth.telegram.org" else { outside(url); return nil }
        let child = WKWebView(frame: .zero, configuration: config)
        child.uiDelegate = self
        let sheet = UIViewController()
        sheet.view = child
        popup = sheet
        present(sheet, animated: true)
        return child
    }

    func webViewDidClose(_ webView: WKWebView) {
        if webView !== web { popup?.dismiss(animated: true) }
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

    // ---- the bridge ----

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler reply: @escaping (Any?, String?) -> Void) {
        let origin = message.frameInfo.securityOrigin
        guard message.frameInfo.isMainFrame, origin.protocol == "https", origin.host == home.host,
              let body = message.body as? [String: Any], let cmd = body["cmd"] as? String else {
            return reply(nil, "refused")
        }
        switch cmd {
        case "apple":
            guard let nonce = body["nonce"] as? String, nonce.count >= 32 else { return reply(nil, "nonce") }
            apple.start(nonce: nonce, window: view.window) { token in reply(token.map { ["token": $0] }, nil) }
        case "push":
            Push.shared.token { token in reply(token.map { ["token": $0] }, nil) }
        case "scan":
            scanner?.dismiss(animated: false)
            let s = Scanner(prompt: body["text"] as? String ?? "") { [weak self] code in self?.scanned(code) }
            scanner = s
            present(s, animated: true)
            reply(nil, nil)
        case "scanClose":
            scanner?.dismiss(animated: true)
            reply(nil, nil)
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
