import AuthenticationServices
import UIKit

// Settings → Link Telegram (Bridge "tglink"): Telegram's sign-in page in the system's sign-in sheet, not a page or popup
// in the web view (a popup there loses window.opener on iOS 17.5+). The server sends Telegram's return through /tg-back
// to kbtuapp://tglink?state=…#tgAuthResult=…, which closes the sheet; that URL goes back to the web, which checks the
// state it made and links the proof (web/src/lib/native.ts telegramProof). Not a registered URL scheme: only this sheet
// ever receives it.
final class TelegramLink: NSObject, ASWebAuthenticationPresentationContextProviding {
    static let scheme = "kbtuapp"  // server logic/apple.py APP_SCHEME
    private var session: ASWebAuthenticationSession?
    private weak var window: UIWindow?

    func start(url: URL, window: UIWindow?, done: @escaping (URL?) -> Void) {
        session?.cancel()
        self.window = window
        let s = ASWebAuthenticationSession(url: url, callbackURLScheme: TelegramLink.scheme) { [weak self] back, _ in
            DispatchQueue.main.async {
                self?.session = nil
                done(back)  // nil: closed by the person, or failed
            }
        }
        s.presentationContextProvider = self
        s.prefersEphemeralWebBrowserSession = false  // Safari's Telegram sign-in, if any, saves typing the phone number
        session = s
        if !s.start() {
            session = nil
            done(nil)
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        window ?? ASPresentationAnchor()
    }
}
