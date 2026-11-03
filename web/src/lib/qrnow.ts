// Imported by a screen that shows a QR in its first frame (lib/qr.svelte.ts): the encoder comes with its chunk.
import qrcode from 'qrcode-generator';
import { setQr } from './qr.svelte';

setQr(qrcode);
