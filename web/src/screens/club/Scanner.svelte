<script lang="ts">
  import { withNick } from '../../lib/perms';
  // The door scanner (Member+, full screen): our own camera on top (owner, Oct 15: so the screen around it
  // is ours: the result, the count, haptics, without a popup closing after each scan), Telegram's QR popup when the
  // camera is refused or missing, the typed code anywhere. It takes a
  // ticket or a badge QR (§4.4): a badge registers a person who didn't sign up, on a free event, at the door.
  // Each answer shows big — a name and avatar to compare with the face at the door. After a good scan the
  // camera comes back by itself so a queue moves fast; an error waits for a tap. A club's own event has no tickets
  // (`names`): it opens on the people expected, marked by name ("Who came").
  import { onMount, untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import UserSearch from '@lucide/svelte/icons/user-search';
  import Search from '@lucide/svelte/icons/search';
  import { api, type CheckinResult, type DoorPerson, type EventFull, type Id } from '../../lib/api';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { eventById } from '../../lib/state/data.svelte';
  import { t, tn, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time } from '../../lib/time';
  import { haptic, inTelegram, scanQr, closeScanner, tg } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, id, names = false }: { overlay: Overlay; id: Id; names?: boolean } = $props();

  let detail = $state<EventFull | null>(null);
  $effect(() => { api.event(id).then((d) => (detail = d)).catch(() => {}); });
  const e = $derived(eventById(id) ?? detail);
  const camera = inTelegram && /^(ios|android)$/.test(tg.platform) && tg.can('6.4');
  // our camera: on until it fails (refused, none), then Telegram's popup takes over. Decoding: the phone's own
  // BarcodeDetector where it has one (Android), else ZXing in wasm (iPhone: WebKit has none), served from our origin
  let video = $state<HTMLVideoElement>();
  let live = $state<'off' | 'on' | 'failed'>('mediaDevices' in navigator ? 'off' : 'failed');
  let stream: MediaStream | null = null;
  let last = { v: '', at: 0 };
  type Detector = { detect(src: HTMLVideoElement): Promise<{ rawValue: string }[]> };
  async function detector(): Promise<Detector> {
    const N = (window as unknown as { BarcodeDetector?: { new (o: object): Detector; getSupportedFormats(): Promise<string[]> } }).BarcodeDetector;
    if (N && (await N.getSupportedFormats().catch((): string[] => [])).includes('qr_code')) return new N({ formats: ['qr_code'] });
    const [{ BarcodeDetector, prepareZXingModule }, { default: wasm }] = await Promise.all([import('barcode-detector/ponyfill'), import('zxing-wasm/reader/zxing_reader.wasm?url')]);
    prepareZXingModule({ overrides: { locateFile: (p: string, prefix: string) => (p.endsWith('.wasm') ? wasm : prefix + p) } });
    return new BarcodeDetector({ formats: ['qr_code'] });
  }
  async function startCam() {
    try {
      const [d, st] = await Promise.all([detector(), navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 } }, audio: false })]);
      stream = st;
      if (gone || !video) { stopCam(); return; }
      video.srcObject = st;
      await video.play();
      live = 'on';
      while (!gone) {
        if (!busy && video.readyState >= 2) {
          const v = (await d.detect(video).catch(() => []))[0]?.rawValue;
          const now = Date.now();  // the same code stays in view: once per 4 s
          if (v && !busy && !(v === last.v && now - last.at < 4000)) { last = { v, at: now }; void check(v); }
        }
        await new Promise((r) => setTimeout(r, 120));
      }
    } catch { stopCam(); if (!gone) live = 'failed'; }
  }
  function stopCam() { stream?.getTracks().forEach((x) => x.stop()); stream = null; }

  let res = $state<CheckinResult | null>(null);
  let seq = $state(0);
  let count = $state<{ came: number; going: number } | null>(null);
  let code = $state('');
  let busy = $state(false);
  let panel: HTMLDivElement;
  let gone = false;

  // the capsule's title, live as the door fills up: "Scanner · 12 of 44" (SPEC §8.2)
  $effect(() => { overlay.title = names ? (count ? t('cap.marks', count) : t('door.title')) : count ? t('cap.scanner', count) : t('studio.scanner'); overlay.icon = ScanLine; });

  const MSG = { other_event: 'scan.other', cancelled: 'scan.cancelled', not_found: 'scan.notFound', closed: 'scan.closed', paid: 'scan.paid' } as const;

  async function check(raw: string) {
    if (busy || !raw.trim()) return;
    busy = true;
    try {
      const r = await api.checkin(id, raw);
      res = r; seq++;
      if (r.result === 'ok' || r.result === 'already') count = { came: r.came, going: r.going };
      if (r.result === 'ok') {
        haptic.ok();
        code = '';
        if (camera && live === 'failed') setTimeout(() => { if (!gone) scan(); }, 1100); // the popup: the next one in the queue
      } else haptic.error(); // "already" too: a ticket used twice is a problem at the door
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); } finally { busy = false; }
  }
  const scan = () => scanQr(t('scan.prompt'), (text) => { void check(text); return true; });

  // ---- no QR (a dead phone): find them among the people going and check in by hand (§4.4) ----
  let byName = $state(untrack(() => names));
  let people = $state<DoorPerson[] | null>(null);
  let who = $state('');
  let undoFor = $state<number | null>(null); // just checked in by hand: "Undo" on the result for a few seconds
  let undoTimer: ReturnType<typeof setTimeout> | undefined;
  const norm = (s: string) => s.toLowerCase().replace(/\u0451/g, '\u0435'); // Russian yo → ye
  const found = $derived((people ?? []).filter((d) => !who.trim() || norm(withNick(d.person.realName, d.person)).includes(norm(who.trim()))).slice(0, 40));
  async function openByName() {
    byName = true;
    try { people = await api.door(id); } catch { people = []; }
  }
  async function mark(d: DoorPerson) {
    if (busy) return;
    busy = true;
    try {
      const r = await api.checkinPerson(id, d.person.id);
      res = r; seq++;
      if (r.result === 'ok' || r.result === 'already') count = { came: r.came, going: r.going };
      if (r.result === 'ok') {
        haptic.ok(); who = '';
        undoFor = d.person.id; clearTimeout(undoTimer); undoTimer = setTimeout(() => (undoFor = null), 8000);
      } else haptic.error();
      people = await api.door(id);
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); } finally { busy = false; }
  }
  async function undo() {
    const uid = undoFor;
    if (uid == null) return;
    try {
      await api.undoCheckin(id, uid);
      undoFor = null; res = null;
      if (count) count = { ...count, came: count.came - 1 };
      haptic.soft(); say(t('door.undone'), 'waving_hand_3d_default');
      people = await api.door(id);
    } catch { say(t('common.error'), 'pleading_face_3d'); }
  }

  onMount(() => {
    panel.animate([{ opacity: 0, transform: 'translate3d(0,40px,0)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'cubic-bezier(.2,.9,.25,1)' });
    if (names) void openByName();
    else if (live !== 'failed') void startCam();
    else if (camera) scan();
    return hideChrome();
  });

  function leave() {
    if (gone) return;
    gone = true;
    closeScanner(); stopCam();
    const a = panel.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="panel" bind:this={panel}>
  <header class="bar">
    {#if !inTelegram}<button class="x" onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={22} /></button>{/if}
  </header>

  <div class="body scroll">
    {#if e}
      <h2 class="t-h3 clamp-2">{e.title}</h2>
      <p class="t-foot">{relDay(e.startsAt)}, {time(e.startsAt)} · {placeOf(e.place)}</p>
      <p class="count">{count ? t('scan.came', count) : tn('event.going', e.taken)}</p>
    {/if}

    {#if !names && live !== 'failed'}
      {#key seq}<div class="cam" class:good={res?.result === 'ok'} class:warn={res?.result === 'already'} class:bad={!!res && res.result !== 'ok' && res.result !== 'already'} class:flash={seq > 0}>
        <video bind:this={video} playsinline muted></video>
        {#if live === 'off'}<span class="wait"><ScanLine size={36} /></span>{/if}
        <span class="aim"></span>
      </div>{/key}
    {/if}

    {#key seq}
      {#if res}
        {#if res.result === 'ok' || res.result === 'already'}
          <div class="res" class:good={res.result === 'ok'} class:warn={res.result === 'already'}>
            <Avatar person={res.person} size={84} />
            <b class="nm">{withNick(res.person.realName, res.person)}</b>
            <span>{res.result === 'ok' ? t('scan.ok') : t('scan.already', { time: time(res.at) })}</span>
            {#if res.walkIn || res.late >= 5 || undoFor === res.person.id}<span class="more">{[undoFor === res.person.id && t('door.byHand'), res.walkIn && t('scan.walkIn'), res.late >= 5 && t('scan.late', { n: res.late })].filter(Boolean).join(' · ')}</span>{/if}
            {#if res.flagged}<span class="flag"><TriangleAlert size={16} />{t('scan.flagged')}</span>{/if}
            {#if undoFor === res.person.id}<button class="undo" onclick={undo}>{t('door.undo')}</button>{/if}
          </div>
        {:else}
          <div class="res bad"><span class="ic"><TriangleAlert size={44} /></span><b class="nm">{t(MSG[res.result])}</b></div>
        {/if}
      {/if}
    {/key}

    {#if !names}
      {#if live !== 'on' && camera}
        <Button kind="primary" size="l" full onclick={scan}>{#snippet icon()}<ScanLine size={20} />{/snippet}{t('scan.open')}</Button>
      {:else if live === 'failed'}
        <p class="t-callout hint">{t('scan.noCamera')}</p>
      {/if}
      <form class="manual" onsubmit={(ev) => { ev.preventDefault(); void check(code); }}>
        <label class="field"><span class="t-cap">{t('scan.code')}</span>
          <input bind:value={code} autocapitalize="characters" autocomplete="off" spellcheck="false" enterkeyhint="done" placeholder="7K4 M2P" /></label>
        <Button kind="secondary" size="l" type="submit" loading={busy} disabled={!code.trim()}>{t('scan.mark')}</Button>
      </form>
    {/if}

    {#if !byName}
      <button class="byname" onclick={openByName}><UserSearch size={18} />{t('door.byName')}</button>
    {:else}
      <section class="door">
        <label class="search"><Search size={18} /><input bind:value={who} placeholder={t('door.search')} type="search" autocomplete="off" /></label>
        {#if people}
          {#each found as d (d.person.id)}
            <div class="dp" class:in={!!d.checkedInAt}>
              <Avatar person={d.person} size={36} tappable={false} />
              <b class="ellipsis">{withNick(d.person.realName, d.person)}</b>
              {#if d.checkedInAt}<i>{t('door.came', { time: time(d.checkedInAt) })}</i>
              {:else}<Button kind="secondary" size="s" disabled={busy} onclick={() => mark(d)}>{t('door.mark')}</Button>{/if}
            </div>
          {:else}
            <p class="t-foot none">{t('door.none')}</p>
          {/each}
        {/if}
      </section>
    {/if}
  </div>
</div>

<style>
  .flag { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: var(--r-full); background: var(--warning-soft); color: var(--warning-text); font: 650 13.5px/1.2 var(--font-text); }
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--glow), var(--bg); }
  .bar { position: absolute; left: 0; right: 0; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); height: 38px; z-index: 1;
    display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .x { position: absolute; left: 12px; width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--surface); color: var(--text); pointer-events: auto; }

  .body { position: absolute; inset: max(48px, var(--top)) 0 0; display: flex; flex-direction: column; gap: 12px; padding: 6px var(--gutter) calc(var(--safe-bottom) + 20px); }
  .body > p.t-foot { margin-top: -8px; }
  .count { font: 760 28px/1.1 var(--font-display); letter-spacing: -0.02em; margin: 6px 0 2px; }

  .res { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 22px 16px; border-radius: var(--r-l); text-align: center;
    animation: pop 360ms cubic-bezier(.2, .9, .25, 1.2); }
  .good { background: var(--success-soft); color: var(--success-text); }
  .warn { background: var(--warning-soft); color: var(--warning-text); }
  .bad { background: var(--danger-soft); color: var(--danger-text); }
  .nm { font: 720 22px/1.2 var(--font-display); color: var(--text); }
  .bad .nm { font-size: 18px; }
  .more { font: 650 14px/1.3 var(--font-text); color: var(--text-2); }
  .ic { display: flex; }
  @keyframes pop { from { opacity: 0; transform: scale(0.92); } }

  .hint { color: var(--text-2); }
  .cam { position: relative; flex: none; width: 100%; aspect-ratio: 1; max-height: 44vh; border-radius: var(--r-l); overflow: hidden; background: #000; }
  .cam video { width: 100%; height: 100%; object-fit: cover; display: block; }
  .wait { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: rgba(255, 255, 255, 0.5); }
  .aim { position: absolute; inset: 18%; border-radius: 22px; box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.75), 0 0 0 999px rgba(0, 0, 0, 0.28); pointer-events: none; }
  .cam.good .aim { box-shadow: 0 0 0 4px var(--success), 0 0 0 999px rgba(0, 0, 0, 0.28); }
  .cam.warn .aim { box-shadow: 0 0 0 4px var(--warning), 0 0 0 999px rgba(0, 0, 0, 0.28); }
  .cam.bad .aim { box-shadow: 0 0 0 4px var(--danger), 0 0 0 999px rgba(0, 0, 0, 0.28); }
  .cam.flash .aim { animation: pulse 420ms cubic-bezier(.2, .9, .25, 1.2); }
  @keyframes pulse { from { transform: scale(1.08); } }
  .undo { margin-top: 2px; padding: 8px 16px; border-radius: var(--r-full); background: rgba(255, 255, 255, 0.16); font: 650 14px/1 var(--font-text); }
  .byname { display: flex; align-items: center; justify-content: center; gap: 8px; height: 46px; border-radius: var(--r-m); color: var(--accent-text);
    background: var(--accent-soft); font: 640 15px/1 var(--font-text); }
  .door { display: flex; flex-direction: column; gap: 6px; }
  .search { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 12px; margin-bottom: 4px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-3); }
  .search input { flex: 1; min-width: 0; font: 500 16px/1 var(--font-text); color: var(--text); background: none; }
  .dp { display: flex; align-items: center; gap: 10px; min-height: 52px; padding: 6px 8px 6px 10px; border-radius: var(--r-m); background: var(--surface); }
  .dp b { flex: 1; min-width: 0; font: 620 15px/1.2 var(--font-text); }
  .dp i { flex: none; font: 600 12.5px/1 var(--font-text); font-style: normal; color: var(--success-text); }
  .dp.in { opacity: 0.6; }
  .none { padding: 6px 2px; }
  .manual { display: flex; gap: 8px; align-items: stretch; }
  .manual .field { flex: 1; min-width: 0; }
  .manual input { letter-spacing: 0.06em; text-transform: uppercase; }
  .manual :global(.btn) { height: auto; }
</style>
