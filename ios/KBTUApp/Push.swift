import UIKit
import UserNotifications

// This iPhone's push token for the web (Bridge "push"): Apple's prompt the first time, the token at every launch (it
// can change). The web hands it to the server for its own session (POST /api/me/devices).
final class Push {
    static let shared = Push()
    private var waiting: [(String?) -> Void] = []

    func token(_ done: @escaping (String?) -> Void) {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            DispatchQueue.main.async {
                guard granted else { return done(nil) }
                self.waiting.append(done)
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    func got(_ token: Data?) {
        let hex = token.map { $0.map { String(format: "%02x", $0) }.joined() }
        let all = waiting
        waiting.removeAll()
        all.forEach { $0(hex) }
    }
}
