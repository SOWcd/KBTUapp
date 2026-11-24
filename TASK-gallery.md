# Gallery place labels: policy, consent, adversarial review

Branch gallery-redo (this worktree). The new gallery reads EXIF GPS on the phone, maps it to one of four labels
(main / b2 / dorm / off campus; web/src/lib/place.ts) and sends only the label (gallery_photos.place, migration 219);
the uploaded file must carry no location metadata.

1. Policy: AGENTS.md "Personal data" rule. Add a short clause to server/kbtu/i18n/legal/*.html (ru binding, kk, en):
   when you add a photo to the Gallery, the app reads the location stored in the photo on your device and sends us
   only one of four labels (KBTU (main building), building 2, dorm, off campus); coordinates never leave your device and the
   uploaded photo contains no location data. Do NOT change the consent version (CONSENT in logic/account.py).
2. In-feature consent, like appeals.CONSENT: the first time a person adds a gallery photo, one short ask; without it
   upload the photo with no place label (never block the upload). Minimal code, match the surrounding style,
   UI strings in all three i18n files.
3. Adversarial review of the whole branch diff vs main: can coordinates or any EXIF/GPS reach the server (check the
   actual bytes uploaded: canvas re-encode? HEIC? original file sent anywhere?), can a client send an arbitrary place
   value, can someone else's photo be relabelled, does account deletion cover the new column/table (_DEL_GONE).
   Fix what is real.
4. Run: cd server && .venv/bin/python -m pytest -q -n 4 tests ; cd web && npm run check && npm test. All green.
Write findings and what you changed to REPORT-gallery.md. You cannot commit: leave changes in the working tree.
