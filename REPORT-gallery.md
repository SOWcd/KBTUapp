# Gallery place labels

## Changes

- Added the Gallery place-label clause to the Russian, Kazakh and English privacy policies. The general consent version remains `2026-11-unified1`.
- The first photo selection opens a short in-app prompt. Skipping or dismissing it continues the upload without reading GPS for a label. After approval, the app looks for GPS locally and sends one place label when it can read a location. The first successful upload records the choice for the account under the Gallery policy version `place1`. The server discards a valid label on an explicit decline or when the account has no current approval.
- Removed event auto-association inferred from EXIF capture time and the off-campus label. This keeps the place label as the sole EXIF-derived value sent by the Gallery. Legacy explicit album attachment still uses the event and album permissions. Its event picker now checks ordinary event visibility before returning candidates.

## Adversarial review against `main`

- **Upload bytes.** The raw request body sent by the Gallery is a canvas-produced JPEG with optional application segments and comments removed from its header. The file picker preview uses a local object URL. The app tries `createImageBitmap` and then a local image URL for decoding, which also covers older webviews that lack `createImageBitmap`. HEIC follows the same path if the webview can decode it. If decoding or JPEG encoding fails, the upload stops before any bytes are sent. If GPS is missing or unreadable, a decodable image uploads without a label. [WebKit canvas serialization](https://github.com/WebKit/WebKit/blob/main/Source/WebCore/html/HTMLCanvasElement.cpp), [WebKit’s Apple-platform image encoder](https://github.com/WebKit/WebKit/blob/main/Source/WebCore/platform/graphics/cg/ImageUtilitiesCG.cpp)
- **API ingress and storage.** The previous Gallery route accepted original files from direct clients, and the shared media saver could store their EXIF capture time. The Gallery route now validates JPEG segments before Pillow decodes them. It allows image segments and a thumbnail-free JFIF header and rejects EXIF, other application segments, comments and trailing bytes. The server re-encodes the image for storage and skips capture-time extraction. A direct caller can still transmit arbitrary bytes to HTTP ingress. The Gallery refuses those that violate the format. Event-album uploads have their own route and policy disclosure.
- **Place values and ownership.** The API and SQLite both enforce `main`, `b2`, `dorm` and `away`. A valid label is a client assertion, so the server cannot verify where the photo was taken. File lookup scopes duplicates to the posting account. An identical upload by another account gets a separate photo row, and retries leave existing labels alone. The API has no relabel operation.
- **Deletion.** `_DEL_GONE` covers the existing `gallery_photos` rows and the new `gallery_consents` table. Account deletion also clears the author's moderation snapshots and removes their photo files when no other row uses them. The final upload transaction checks the current verified student row and rejects a request that continues after the row was removed.

## Verification

- `npm run check` reported zero errors and warnings. `npm test` passed all 325 tests across 51 files.
- All 31 focused Gallery and schema tests passed with uvloop, selected temporarily because the sandbox blocks the standard asyncio socket wake-up used by FastAPI's test client.
- A progressive JPEG fixture passed from mocked canvas output through the app's byte cleanup and the server's JPEG validation and storage. Both local decoder paths removed application segments and comments. Decode and encode failures rejected the upload body.
- Browser capture and native iOS HEIC verification were unavailable in this environment. The sandbox blocked both local HTTP binding and Chromium startup.
