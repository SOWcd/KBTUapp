// The QR encoder (qrcode-generator, ~6 KB gzip) is out of the first chunk: only the badge's code is drawn from the
// start, and that one is encoded when the app is idle (ui/Qr.svelte, `lazy`). Every screen that shows a code at once
// imports lib/qrnow.ts, which hands the encoder over as its chunk loads, so its code is there in its first frame.
import type qrcode from 'qrcode-generator';

export type Encoder = typeof qrcode;
export const qr = $state<{ enc: Encoder | null }>({ enc: null });
let loading: Promise<unknown> | null = null;
// a failed fetch (offline, a deploy in between) is tried again on the next need, not kept
export const loadQr = () => (loading ??= import('qrcode-generator').then((m) => (qr.enc = m.default), (e) => { loading = null; throw e; }));
export function setQr(enc: Encoder): void { qr.enc = enc; }
