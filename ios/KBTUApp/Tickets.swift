import Foundation

// My tickets for the door with no network (Bridge "tickets"): the web sends them whenever its list changes, only what
// the door needs (the title, time and place to find the right one, and the QR's text, "KBTU" + the code). One file in
// Application Support, not backed up; emptied when the person signs out or the session cookie goes.
enum Tickets {
    struct Ticket: Codable {
        let title: String
        let at: Double  // the start, Unix seconds
        let place: String
        let qr: String
    }

    private struct Saved: Codable {
        var lang: String
        var tickets: [Ticket]
    }

    private static var file: URL? {
        guard let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return nil }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("tickets.json")
    }

    private static func read() -> Saved? {
        guard let url = file, let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(Saved.self, from: data)
    }

    static func load() -> (lang: String, tickets: [Ticket]) {
        let saved = read()
        return (saved?.lang ?? "", saved?.tickets ?? [])
    }

    /// lang: the app's language for the offline screen ("" keeps the one saved)
    static func save(_ tickets: [Ticket], lang: String) {
        guard var url = file else { return }
        let saved = Saved(lang: lang.isEmpty ? (read()?.lang ?? "") : lang, tickets: tickets)
        guard let data = try? JSONEncoder().encode(saved) else { return }
        try? data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try? url.setResourceValues(values)
    }

    static func clear() {
        if read()?.tickets.isEmpty == false { save([], lang: "") }
    }
}
