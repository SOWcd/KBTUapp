import CoreImage.CIFilterBuiltins
import UIKit

// Bundled with the app, shown when the site can't load (no network, our server down): on the web boot screen's ground,
// a retry, and my tickets with their QR drawn here, so the door can scan them with no network. Its words follow the
// app's language (the web sends it with the tickets), else the phone's.
final class OfflineView: UIView {
    private let lang: String

    init(lang: String, tickets: [Tickets.Ticket], retry: @escaping () -> Void) {
        self.lang = lang
        super.init(frame: .zero)
        backgroundColor = UIColor(named: "Ground")

        let scroll = UIScrollView()
        scroll.alwaysBounceVertical = true
        scroll.translatesAutoresizingMaskIntoConstraints = false
        addSubview(scroll)
        let stack = UIStackView()
        stack.axis = .vertical
        stack.alignment = .center
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(stack)
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: topAnchor),
            scroll.bottomAnchor.constraint(equalTo: bottomAnchor),
            scroll.leadingAnchor.constraint(equalTo: leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: trailingAnchor),
            stack.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor, constant: tickets.isEmpty ? 160 : 72),
            stack.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor, constant: -40),
            stack.leadingAnchor.constraint(equalTo: scroll.frameLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: scroll.frameLayoutGuide.trailingAnchor, constant: -24),
        ])

        let icon = UIImageView(image: UIImage(systemName: "wifi.slash"))
        icon.tintColor = .secondaryLabel
        icon.preferredSymbolConfiguration = UIImage.SymbolConfiguration(pointSize: 40, weight: .semibold)
        stack.addArrangedSubview(icon)
        stack.addArrangedSubview(label(text("offline.title"), .title2, .label, bold: true))
        stack.addArrangedSubview(label(text("offline.text"), .body, .secondaryLabel))
        var config = UIButton.Configuration.filled()
        config.title = text("offline.retry")
        config.cornerStyle = .capsule
        config.baseBackgroundColor = WebController.accent
        config.contentInsets = NSDirectionalEdgeInsets(top: 12, leading: 28, bottom: 12, trailing: 28)
        // the tap answers at once (a spinner in the button); the screen stays until the site comes, or comes back anew
        let button = UIButton(configuration: config, primaryAction: UIAction { action in
            guard let b = action.sender as? UIButton, b.configuration?.showsActivityIndicator == false else { return }
            b.configuration?.showsActivityIndicator = true
            retry()
        })
        stack.addArrangedSubview(button)
        stack.setCustomSpacing(28, after: button)

        guard !tickets.isEmpty else { return }
        stack.addArrangedSubview(label(text("offline.tickets"), .title3, .label, bold: true))
        stack.addArrangedSubview(label(text("offline.ticketsHint"), .subheadline, .secondaryLabel))
        for t in tickets { stack.addArrangedSubview(card(t)) }
    }

    required init?(coder: NSCoder) { fatalError("not from a storyboard") }

    private func text(_ key: String) -> String {
        let bundle = lang.isEmpty ? nil : Bundle.main.path(forResource: lang, ofType: "lproj").flatMap { Bundle(path: $0) }
        return (bundle ?? .main).localizedString(forKey: key, value: nil, table: nil)
    }

    private func label(_ s: String, _ style: UIFont.TextStyle, _ color: UIColor, bold: Bool = false) -> UILabel {
        let l = UILabel()
        l.text = s
        l.textColor = color
        l.numberOfLines = 0
        l.textAlignment = .center
        let font = UIFont.preferredFont(forTextStyle: style)
        l.font = bold ? UIFont(descriptor: font.fontDescriptor.withSymbolicTraits(.traitBold) ?? font.fontDescriptor, size: 0) : font
        return l
    }

    // one ticket: the QR on white (a door scanner reads dark on light), then what and when
    private func card(_ t: Tickets.Ticket) -> UIView {
        let box = UIStackView()
        box.axis = .vertical
        box.alignment = .center
        box.spacing = 6
        box.isLayoutMarginsRelativeArrangement = true
        box.directionalLayoutMargins = NSDirectionalEdgeInsets(top: 20, leading: 16, bottom: 20, trailing: 16)
        box.backgroundColor = .secondarySystemGroupedBackground
        box.layer.cornerRadius = 24
        box.layer.cornerCurve = .continuous
        let qr = UIImageView(image: Self.qr(t.qr))
        qr.layer.magnificationFilter = .nearest
        qr.backgroundColor = .white
        qr.layer.cornerRadius = 12
        qr.contentMode = .scaleAspectFit
        qr.isAccessibilityElement = true
        qr.accessibilityLabel = t.title
        NSLayoutConstraint.activate([qr.widthAnchor.constraint(equalToConstant: 232), qr.heightAnchor.constraint(equalToConstant: 232)])
        box.addArrangedSubview(qr)
        box.setCustomSpacing(14, after: qr)
        box.addArrangedSubview(label(t.title, .headline, .label))
        let when = DateFormatter()
        when.locale = lang.isEmpty ? .current : Locale(identifier: lang)
        when.timeZone = TimeZone(identifier: "Asia/Almaty")  // the events' own time, wherever the phone is
        when.setLocalizedDateFormatFromTemplate("EEEdMMMMHHmm")
        let line = [when.string(from: Date(timeIntervalSince1970: t.at)), t.place].filter { !$0.isEmpty }.joined(separator: " · ")
        box.addArrangedSubview(label(line, .subheadline, .secondaryLabel))
        return box
    }

    // the QR of the same text the web draws (TicketView), scaled by whole modules and drawn without smoothing: crisp
    private static func qr(_ text: String) -> UIImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        filter.correctionLevel = "M"
        guard let image = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 8, y: 8)),
              let cg = CIContext().createCGImage(image, from: image.extent) else { return nil }
        return UIImage(cgImage: cg)
    }
}
