import AuthenticationServices
import CryptoKit
import UIKit

// Sign in with Apple (Bridge "apple"): Apple's own sheet, no name or email asked (the policy keeps only Apple's ID for
// this app). The request carries SHA-256 of the web's one-time nonce; the server checks the token's nonce against it.
final class AppleSignIn: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    private var done: ((String?) -> Void)?
    private weak var window: UIWindow?

    func start(nonce: String, window: UIWindow?, done: @escaping (String?) -> Void) {
        self.done = done
        self.window = window
        let request = ASAuthorizationAppleIDProvider().createRequest()
        request.requestedScopes = []
        request.nonce = SHA256.hash(data: Data(nonce.utf8)).map { String(format: "%02x", $0) }.joined()
        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.presentationContextProvider = self
        controller.performRequests()
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        let token = (authorization.credential as? ASAuthorizationAppleIDCredential)?.identityToken
        finish(token.flatMap { String(data: $0, encoding: .utf8) })
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        finish(nil)  // closed, or no Apple ID on the phone: the web says nothing
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        window ?? ASPresentationAnchor()
    }

    private func finish(_ token: String?) {
        done?(token)
        done = nil
    }
}
