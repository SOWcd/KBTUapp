import AVFoundation
import UIKit

// The door's QR scanner (Bridge "scan"): the camera in a half sheet, the web's result above it. Every code read goes to
// the web (onCode), which says whether to close; the same code again within two seconds is the same ticket held still.
final class Scanner: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    private let session = AVCaptureSession()
    private let prompt: String
    private let onCode: (String) -> Void
    private var last = ("", Date.distantPast)

    init(prompt: String, onCode: @escaping (String) -> Void) {
        self.prompt = prompt
        self.onCode = onCode
        super.init(nibName: nil, bundle: nil)
        if let sheet = sheetPresentationController {
            sheet.detents = [.medium(), .large()]
            sheet.prefersGrabberVisible = true
            sheet.largestUndimmedDetentIdentifier = .medium  // the web's answer above stays bright and tappable
        }
    }

    required init?(coder: NSCoder) { fatalError("not from a storyboard") }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        let label = UILabel()
        label.text = prompt
        label.textColor = .white
        label.font = .preferredFont(forTextStyle: .subheadline)
        label.textAlignment = .center
        label.numberOfLines = 2
        label.translatesAutoresizingMaskIntoConstraints = false
        guard let camera = AVCaptureDevice.default(for: .video), let input = try? AVCaptureDeviceInput(device: camera),
              session.canAddInput(input) else { return }
        session.addInput(input)
        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else { return }
        session.addOutput(output)
        output.setMetadataObjectsDelegate(self, queue: .main)
        output.metadataObjectTypes = [.qr]
        let preview = AVCaptureVideoPreviewLayer(session: session)
        preview.videoGravity = .resizeAspectFill
        view.layer.addSublayer(preview)
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            label.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            label.topAnchor.constraint(equalTo: view.topAnchor, constant: 28),
        ])
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        view.layer.sublayers?.compactMap { $0 as? AVCaptureVideoPreviewLayer }.forEach { $0.frame = view.bounds }
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        DispatchQueue.global(qos: .userInitiated).async { [session] in session.startRunning() }
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        DispatchQueue.global(qos: .userInitiated).async { [session] in session.stopRunning() }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput objects: [AVMetadataObject], from connection: AVCaptureConnection) {
        guard let code = (objects.first as? AVMetadataMachineReadableCodeObject)?.stringValue else { return }
        if code == last.0 && Date().timeIntervalSince(last.1) < 2 { return }
        last = (code, Date())
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        onCode(code)
    }
}
