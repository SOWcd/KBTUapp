// KBTU's anthem as it plays: its one audio element and the rule of its award, outside the sheet, so the song goes on
// when the sheet is sent to the background (`bg`: the capsule shows it, App.svelte's live status) and across tabs.
// The element is made on the first tap (iOS plays only from a tap; nothing loads before it).
import { say } from './ui.svelte';
import { sheets } from './sheets';
import { api } from '../api';
import { session } from './session.svelte';
import { data, loadMyCard } from './data.svelte';
import { t } from '../i18n/index.svelte';

/** fair: this play is followed from its start with nothing skipped (the award's rule); done: it ended and stands at
 *  its end (repeat off) until played again; won: the award was given in this session; bg: playing with the sheet closed */
export const anthem = $state({ on: false, waiting: false, repeat: false, cur: 0, dur: 211, bg: false, fair: false, done: false, won: false }); // 211: the file's length, shown before it loads

let audio: HTMLAudioElement | null = null;
const ms = typeof navigator !== 'undefined' && 'mediaSession' in navigator ? navigator.mediaSession : null;

/** the audio's own clock, for a frame loop (the state's `cur` moves ~4 times a second) */
export const anthemTime = () => (audio ? audio.currentTime : anthem.cur);
/** I have the award already: nothing to lose by skipping */
export const anthemOwned = () => anthem.won || !!data.myCard?.awards.achievements.some((x) => x.code === 'anthem' && x.level > 0);

// the award for the whole anthem without skipping: a play is followed from its first 2 s; a jump forward
// past what was heard (the scrubber, the arrows, a line tapped ahead) loses it, once with a word why; back and pause
// are fine. At the end (or as `loop` wraps it round) the server gives it, once a student, and its moment shows over
// whatever is open (the sheet or, in the background, the tab)
let run = -1, runAt = 0, told = false, sent = false; // run: how far the followed play has got (s), -1: none; runAt: when (ms)
function follow(to: number) { run = to; if (anthem.fair !== to >= 0) anthem.fair = to >= 0; }
function heard(a: HTMLAudioElement) {
  // a locked phone sends timeupdate rarely: the time played since the last one counts (paused: none; at most 5 s)
  const at = a.currentTime, gone = a.paused ? 0 : Math.min(5, (performance.now() - runAt) / 1000);
  runAt = performance.now();
  if (run < 0) { if (at < 2 && !a.paused) follow(at); return; }
  if (a.loop && at < 1 && run >= anthem.dur - 3) { award(); follow(at); return; }
  if (at <= run + 2 + gone) { run = Math.max(run, at); return; }
  follow(-1);
  if (!told && !sent && session.me?.student && !anthemOwned()) { told = true; say(t('anthem.skipNote'), 'headphone_3d'); }
}
function award() {
  if (sent || !session.me?.student) return;
  sent = anthem.won = true;
  api.anthemHeard().then((r) => { if (session.me) session.me = { ...session.me, unlocked: r.unlocked }; sheets.celebrate(); void loadMyCard(); }).catch(() => (sent = anthem.won = false));
}

function make(): HTMLAudioElement {
  const a = new Audio();
  a.preload = 'none';
  a.loop = anthem.repeat;
  a.src = 'anthem/kbtu-anthem.m4a';
  const from = anthem.cur; // scrubbed or a line tapped before the first play: it starts there
  if (from) a.addEventListener('loadedmetadata', () => (a.currentTime = from), { once: true });
  a.onplay = () => { anthem.on = true; anthem.done = false; if (ms) ms.playbackState = 'playing'; };
  a.onpause = () => { anthem.on = anthem.waiting = false; if (ms) ms.playbackState = 'paused'; };
  a.onwaiting = () => (anthem.waiting = true);
  a.onplaying = () => (anthem.waiting = false);
  a.ontimeupdate = a.onseeked = () => { heard(a); if (!anthem.done) anthem.cur = a.currentTime; };
  a.ondurationchange = () => { if (isFinite(a.duration)) anthem.dur = a.duration; };
  // repeat off (on, `loop` starts it over by itself): it stands at its end, the next play starts over; nothing left to
  // show in the capsule
  a.onended = () => { if (run >= anthem.dur - 3) award(); follow(-1); anthem.done = true; anthem.bg = false; anthem.cur = anthem.dur; };
  a.onerror = () => { anthem.on = anthem.waiting = false; say(t('common.offline'), 'pleading_face_3d'); };
  if (ms) {
    try { // the lock screen and the headphones' buttons
      ms.metadata = new MediaMetadata({ title: t('anthem.title'), artist: 'KBTU', artwork: [{ src: 'apple-touch-icon.png', sizes: '180x180', type: 'image/png' }] });
      ms.setActionHandler('play', () => void a.play().catch(() => {}));
      ms.setActionHandler('pause', () => a.pause());
    } catch { /* an old WebView without it */ }
  }
  return a;
}

export function anthemToggle() {
  const a = (audio ??= make());
  if (!a.paused) { a.pause(); return; }
  if (a.error) a.load(); // a failed load (offline) tries again
  if (anthem.done) { anthem.done = false; anthem.cur = a.currentTime = 0; }
  anthem.on = true; anthem.waiting = a.readyState < 3; // the tap answers at once; a ring while it buffers
  a.play().catch((e) => { if (e?.name !== 'AbortError') anthem.on = anthem.waiting = false; });
}
export const anthemPause = () => audio?.pause();
export function anthemLoop() { anthem.repeat = !anthem.repeat; if (audio) audio.loop = anthem.repeat; }
export function anthemSeek(s: number) {
  anthem.done = false;
  anthem.cur = Math.min(anthem.dur, Math.max(0, s));
  if (audio) audio.currentTime = anthem.cur;
}
/** the sheet left and the song is not kept in the background: it stops, its download too */
export function anthemStop() {
  anthem.on = anthem.waiting = anthem.bg = anthem.done = false; anthem.cur = 0; follow(-1);
  if (!audio) return;
  const a = audio; audio = null;
  a.onerror = a.onpause = a.ontimeupdate = a.onseeked = a.onended = null;
  a.pause(); a.removeAttribute('src'); a.load();
  if (ms) { try { ms.metadata = null; ms.setActionHandler('play', null); ms.setActionHandler('pause', null); } catch { /* as above */ } }
}
