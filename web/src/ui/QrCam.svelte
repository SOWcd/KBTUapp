<script lang="ts">
  // Our own QR camera (the door scanner's since Oct 15, the admin's award scanner since Oct 22: owner, "our scanner
  // everywhere, not Telegram's"). Decoding: the phone's own BarcodeDetector where it has one (Android), else ZXing in
  // wasm (iPhone: WebKit has none), served from our origin. The same code staying in view counts once per 4 s.
  // `live` goes 'failed' when the camera is refused or missing: the parent then offers Telegram's popup.
  import { onMount } from 'svelte';

  let { onscan, paused = false, live = $bindable() }: { onscan: (text: string) => void; paused?: boolean; live?: 'off' | 'on' | 'failed' } = $props();
  live = 'mediaDevices' in navigator ? 'off' : 'failed';

  let video: HTMLVideoElement;
  type Detector = { detect(src: HTMLVideoElement): Promise<{ rawValue: string }[]> };
  async function detector(): Promise<Detector> {
    const N = (window as unknown as { BarcodeDetector?: { new (o: object): Detector; getSupportedFormats(): Promise<string[]> } }).BarcodeDetector;
    if (N && (await N.getSupportedFormats().catch((): string[] => [])).includes('qr_code')) return new N({ formats: ['qr_code'] });
    const [{ BarcodeDetector, prepareZXingModule }, { default: wasm }] = await Promise.all([import('barcode-detector/ponyfill'), import('zxing-wasm/reader/zxing_reader.wasm?url')]);
    prepareZXingModule({ overrides: { locateFile: (p: string, prefix: string) => (p.endsWith('.wasm') ? wasm : prefix + p) } });
    return new BarcodeDetector({ formats: ['qr_code'] });
  }

  onMount(() => {
    if (live === 'failed') return;
    let gone = false, dead = false, stream: MediaStream | null = null, last = { v: '', at: 0 };
    const stop = () => { stream?.getTracks().forEach((x) => x.stop()); stream = null; };
    (async () => {
      try {
        // the stream is kept the moment it comes: if the decoder failed first (offline, a chunk gone after a deploy)
        // it is stopped then, not left running with the light on
        const um = navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 } }, audio: false })
          .then((st) => { stream = st; if (gone || dead) stop(); return st; });
        um.catch(() => {}); // refused after the decoder already failed: nothing to report twice
        const [d, st] = await Promise.all([detector(), um]);
        if (gone) return;
        video.srcObject = st;
        await video.play();
        live = 'on';
        while (!gone) {
          if (!paused && video.readyState >= 2) {
            const v = (await d.detect(video).catch(() => []))[0]?.rawValue;
            const now = Date.now();
            if (v && !paused && !gone && !(v === last.v && now - last.at < 4000)) { last = { v, at: now }; onscan(v); }
          }
          await new Promise((r) => setTimeout(r, 120));
        }
      } catch { dead = true; stop(); if (!gone) live = 'failed'; }
    })();
    return () => { gone = true; stop(); };
  });
</script>

<video bind:this={video} playsinline muted></video>

<style>
  video { width: 100%; height: 100%; object-fit: cover; display: block; }
</style>
