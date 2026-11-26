import UIKit
import UserNotifications

// The iPhone app: one web view over the production web app (WebController), plus what a web page can't do well on an
// iPhone: Sign in with Apple, notifications, a native QR scanner and a session kept in the Keychain (Bridge.swift).
@main
final class AppDelegate: UIResponder, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    var window: UIWindow?
    private let web = WebController()

    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        // the Keychain outlives an uninstall: a fresh install starts signed out
        if !UserDefaults.standard.bool(forKey: "installed") {
            Keychain.delete()
            UserDefaults.standard.set(true, forKey: "installed")
        }
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.backgroundColor = UIColor(named: "Ground")
        window?.rootViewController = web
        window?.makeKeyAndVisible()
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken token: Data) {
        Push.shared.got(token)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        Push.shared.got(nil)
    }

    // a notification while the app is open: shown as a banner all the same
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        done([.banner, .sound])
    }

    // a tapped notification opens its place in the app (the server's "start", the bot button's startapp)
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler done: @escaping () -> Void) {
        web.open(start: response.notification.request.content.userInfo["start"] as? String ?? "")
        done()
    }
}
