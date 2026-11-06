<script module lang="ts">
  import { flushSync } from 'svelte';
  import { open } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { channel, touched } from '../../lib/state/channel.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { nowTs } from '../../lib/time';
  import type { ChannelFeedPost, Id } from '../../lib/api';
  import Self from './ChannelCompose.svelte';

  export type Draft = { body: string; anon: boolean; why?: string };
  // the words not posted yet: closing the window keeps them, posting clears them. ponytail: in memory only, as the
  // feed (the posts' words stay out of storage): a relaunch starts empty; localStorage if students ask for more
  const kept = { body: '', anon: false };

  /** The writing window, out of the Forum tab's "Share with KBTU…" pill. Called in a tap: the field takes the focus in
   *  that same tap (flushSync mounts the window first), or iOS won't bring the keyboard up. */
  export function compose(draft?: Draft): void {
    open(Self, { draft });
    flushSync();
    const fields = document.querySelectorAll<HTMLTextAreaElement>('.cw-text'), f = fields[fields.length - 1]; // the last: an old one may still be leaving
    f?.focus({ preventScroll: true });
    f?.setSelectionRange(f.value.length, f.value.length);
  }

  // the bot's signature, as the server makes it (fchannel.signature): the real first name and the last initial, a nick or
  // not (owner, Nov 2: the nick rule; the app's feed shows the nick)
  export function signOf(): string {
    const s = session.me?.student;
    return s ? `${s.firstName} ${s.lastName ? [...s.lastName][0] : ''}`.trim() : session.me?.name ?? '';
  }

  /** A stand-in on top of the feed while the server answers (a tap answers in the same frame) */
  export function stand(text: string, was: boolean, human = false): ChannelFeedPost {
    const me = session.me;
    const temp: ChannelFeedPost = { id: -Date.now(), body: text, status: 'held', human, at: nowTs(), msg: null, anon: was, nick: null, sign: was ? t('fc.nickSoon') : signOf(), mine: true,
      person: !was && me ? { id: me.id, name: me.name, avatar: me.avatar, founder: false } : null, comments: 0, thread: null, faces: [], reactions: [], hot: false };
    channel.feed = [temp, ...(channel.feed ?? [])];
    return temp;
  }
  /** The stand-in becomes the real one (or just goes, if a refresh brought the real one already: no twin keys) */
  export function land(temp: ChannelFeedPost, p: { id: Id; status: ChannelFeedPost['status']; at: number; nick: ChannelFeedPost['nick'] }, human = false): void {
    const feed = channel.feed ?? []; touched();
    channel.feed = feed.some((x) => x.id === p.id) ? feed.filter((x) => x.id !== temp.id)
      : feed.map((x) => (x.id === temp.id ? { ...x, id: p.id, status: p.status, at: p.at, nick: p.nick, human } : x));
  }
  export const unstand = (temp: ChannelFeedPost): void => { channel.feed = (channel.feed ?? []).filter((x) => x.id !== temp.id); };
</script>

<script lang="ts">
  // A new post to the forum channel: a glass window at the top that grows out of the Forum tab's pill (owner, Nov 6:
  // the sheet was ugly; iOS 26's Liquid Glass morph). The pill's glass stretches down into the window: my face stays
  // where it was, its words fade into the name the post goes out under, the pen turns into Send, and the field and the
  // Anonymous switch flow in under them; closing folds it back into the pill. Send sits in the top row, so the keyboard
  // never covers it. The rules are checked as I type (lib/forumRules, the server's own), said at the spot, holding
  // Send; the count only near the limit. Send closes the window at once and the post stands at the top of the feed,
  // "checking" while the AI looks. Refused by the AI: the verdict sheet (ChannelRefused). A refusal by the rules (a
  // link, the pace) brings the window back with the words and why above them until I edit.
  import { onMount, untrack } from 'svelte';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import { api, ApiErr } from '../../lib/api';
  import { loadChannel } from '../../lib/state/channel.svelte';
  import { close, hideChrome, removeOverlay, say, type Overlay } from '../../lib/state/ui.svelte';
  import { type Key } from '../../lib/i18n/index.svelte';
  import { broken, type Rule } from '../../lib/forumRules';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import { grow } from '../../ui/grow';
  import { glass } from '../../ui/glass';
  import Avatar from '../../ui/Avatar.svelte';
  import Notice from '../../ui/Notice.svelte';
  import ChannelRefused from './ChannelRefused.svelte';

  let { overlay, draft }: { overlay: Overlay; draft?: Draft } = $props();
  let body = $state(untrack(() => draft?.body ?? kept.body)), anon = $state(untrack(() => draft?.anon ?? kept.anon));
  let revealed = $state<number | null>(null);
  onMount(() => { api.channelRevealed().then((r) => (revealed = r.revealed)).catch(() => {}); });
  $effect(() => { kept.body = body; kept.anon = anon; });
  $effect(() => { overlay.title = t('fc.new'); overlay.icon = SquarePen; });
  const why = $derived(draft?.why && body === draft.body ? draft.why : null);  // gone once I change the words
  const MAX = 1000;
  const rule = $derived(broken(body));
  const ready = $derived(body.trim().length >= 2 && !rule);
  const HINT: Record<Rule, Key> = { link: 'fc.noLink', mention: 'fc.noMention', phone: 'fc.noPhone', signature: 'fc.signature' };
  const sign = $derived(session.me ? signOf() : '');

  let win: HTMLDivElement;
  let out = $state(true);  // folded into the pill: the state it opens from and closes back to (CSS transitions in between)
  let gone = false, sent = false;
  const R = 22;  // var(--r-l): the pill's and the window's corners
  const FULL = `inset(0px 0px 0px 0px round ${R}px)`;
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  // the pill as a frame of the window: moved to its place and clipped to its size. null: no pill on screen (scrolled
  // away, another tab), the window just fades
  function pill(): Keyframe | null {
    const p = document.querySelector('[data-compose]')?.getBoundingClientRect(), r = win.getBoundingClientRect();
    if (!p?.width || p.left < -1 || p.right > innerWidth + 1 || p.bottom < 0 || p.top > innerHeight) return null;
    return { translate: `0 ${p.top - r.top}px`, clipPath: `inset(0px ${r.right - p.right}px ${Math.max(0, r.height - p.height)}px ${p.left - r.left}px round ${R}px)` };
  }

  function leave() {
    if (gone) return;
    gone = true; out = true;
    (document.activeElement as HTMLElement | null)?.blur?.(); // the keyboard goes with it
    const from = still() ? null : pill();
    const a = from ? win.animate([{ translate: '0 0', clipPath: FULL }, from], { duration: 380, easing: 'cubic-bezier(.32,.72,0,1)', fill: 'forwards' })
      : win.animate([{ opacity: 1 }, { opacity: 0, scale: '0.97' }], { duration: 180, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) untrack(leave); });  // Back, the scrim, a send: the draft stays, nothing to ask

  onMount(() => {
    channel.writing++;
    const chrome = hideChrome();
    // the room down to the keyboard (iOS lays it over the page): the window stops above it
    const vv = window.visualViewport;
    const fit = () => { if (vv) win.style.setProperty('--room', `${vv.offsetTop + vv.height - win.getBoundingClientRect().top - 12}px`); };
    fit(); vv?.addEventListener('resize', fit); vv?.addEventListener('scroll', fit);
    const from = still() ? null : pill();
    if (from) {
      // the glass stretches down out of the pill on a spring that overshoots a hair, narrowing a touch as it flows
      win.animate([from, { translate: '0 0', clipPath: FULL }], { duration: 560, easing: 'cubic-bezier(.3,1.12,.4,1)' });
      win.animate([{ scale: '1 1' }, { scale: '0.985 1.012', offset: 0.35 }, { scale: '1 1' }], { duration: 560, easing: 'ease-out' });
    } else win.animate([{ opacity: 0, scale: '0.97' }, { opacity: 1, scale: '1' }], { duration: still() ? 1 : 220, easing: 'ease-out' });
    requestAnimationFrame(() => { out = false; });
    return () => { channel.writing--; chrome(); vv?.removeEventListener('resize', fit); vv?.removeEventListener('scroll', fit); };
  });

  function reason(e: unknown): string {
    const why: Key = e instanceof ApiErr ? (e.code === 'rate_limited' ? 'fc.slow' : e.message === 'links' ? 'fc.links' : e.message === 'signature' ? 'fc.signature' : e.message === 'short' ? 'fc.short' : e.message === 'duplicate' ? 'fc.dup' : 'common.error') : 'common.error';
    return t(why);
  }

  async function post() {
    if (!ready || sent) return;  // once: a second tap while it closes sends nothing
    sent = true;
    const text = body.trim(), was = anon;
    const temp = stand(text, was); haptic.select(); kept.body = ''; close(overlay.id);
    try {
      const p = await api.newChannelPost(text, was);
      land(temp, p, p.status === 'held' && !!p.ai);
      haptic.ok();
      if (p.status === 'live') { burst(); say(t('fc.postedSay'), 'party_popper_3d'); setTimeout(loadChannel, 5000); } // the bot sends it within seconds: its link then
      else {
        say(t('fc.heldSay'), 'thinking_face_3d');
        if (p.ai) api.channelPostWhy(p.id, text).then((x) => { if (x.explain) channel.why[p.id] = x.explain; }).catch(() => {});
      }
    } catch (e) {
      unstand(temp); haptic.error(); kept.body = text; kept.anon = was;  // not gone: the words wait in the window
      const d = e instanceof ApiErr ? e.data : {};
      if (e instanceof ApiErr && (e.message === 'noise' || e.message === 'ad') && typeof d.post === 'number')
        open(ChannelRefused, { body: text, anon: was, refused: { post: d.post, kind: e.message === 'ad' ? 'ad' : 'noise', appeal: d.appeal === true } });
      else compose({ body: text, anon: was, why: reason(e) });
    }
  }
  // Ctrl/Cmd+Enter sends (a computer); a plain Enter is a new line
  const key = (e: KeyboardEvent) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); post(); } };
</script>

<div class="scrim" class:out onclick={() => close(overlay.id, true)} role="presentation"></div>
<div class="cw glass glass-sheet" class:out use:glass bind:this={win} role="dialog" aria-modal="true" aria-label={t('fc.new')}>
  <!-- the pill's own row, the same places: my face, then who it goes out as (the pill's words fade into it), Send -->
  <div class="top">
    {#key anon || !session.me}<span class="face">{#if anon || !session.me}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
    {:else}<Avatar person={session.me} size={36} tappable={false} />{/if}</span>{/key}
    <span class="who"><b class="ellipsis">{anon ? t('fc.nickSoon') : sign}</b><span class="sub">{t('fc.toChannel')}</span></span>
    <span class="ghost ellipsis" aria-hidden="true">{t('fc.share')}</span>
    <button class="send" class:ready disabled={!ready} onclick={post} aria-label={t('fc.post')}>
      <span class="ic pen" aria-hidden="true"><SquarePen size={18} strokeWidth={2} /></span>
      <span class="ic go" aria-hidden="true"><ArrowUp size={20} strokeWidth={2.4} /></span>
    </button>
  </div>
  <div class="rest scroll">
    <label class="as sw-on">
      <span class="asi" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
      <span class="asl">{t('fc.anon')}</span>
      <input type="checkbox" role="switch" bind:checked={anon} onchange={() => haptic.select()} />
    </label>
    {#if why}<div class="why"><Notice tone="danger" text={why} /></div>{/if}
    <textarea class="cw-text" class:bad={!!rule} bind:value={body} maxlength={MAX} rows="5" placeholder={t('fc.share')} aria-label={t('fc.ph')} aria-invalid={!!rule}
      onkeydown={key} use:grow></textarea>
    <!-- the rule broken, at the spot (the server's words for it); the count once it's near the limit -->
    {#if rule || body.length > MAX - 100}<div class="foot">
      {#if rule}<span class="hint" role="status">{t(HINT[rule])}</span>{/if}
      {#if body.length > MAX - 100}<span class="count" class:full={body.length >= MAX}>{MAX - body.length}</span>{/if}
    </div>{/if}
    <p class="note">{anon ? t('fc.asAnon') : t('fc.rules')}</p>
    {#if anon && revealed !== null}<p class="note">{t('fc.revealed', { n: revealed })}</p>{/if}
  </div>
</div>

<style>
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--scrim); transition: opacity 320ms var(--ease); }
  .scrim.out { opacity: 0; transition-duration: 260ms; }
  /* the window: the pill's width, under the capsule, as tall as its words up to the keyboard */
  .cw { position: absolute; z-index: var(--z-sheet); top: calc(var(--head-bottom) + var(--s-2)); left: var(--gutter); right: var(--gutter);
    max-width: 560px; margin: 0 auto; max-height: min(var(--room, 100%), calc(100% - var(--head-bottom) - var(--s-2) - var(--s-4) - var(--safe-bottom)));
    display: flex; flex-direction: column; overflow: hidden; border-radius: var(--r-l); transform-origin: 50% 0; will-change: transform; }

  /* the top row: the pill's paddings and sizes, so its face and its pen stay put */
  .top { position: relative; flex: none; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-3) var(--s-3) var(--s-4); }
  .face { flex: none; display: flex; animation: swap 320ms var(--ease-bounce); }
  @keyframes swap { from { transform: scale(0.6) rotate(-12deg); opacity: 0; } }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--fill-2); color: var(--text); }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; transition: opacity 260ms var(--ease) 80ms, translate 420ms var(--ease); }
  .who b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); letter-spacing: -0.01em; }
  .sub { font: 450 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  /* the pill's words, where they were: they fade as the name comes */
  .ghost { position: absolute; left: calc(var(--s-4) + 36px + var(--s-3)); right: calc(36px + var(--s-3) * 2); top: 50%; translate: 0 -50%; opacity: 0; pointer-events: none;
    font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-3); transition: opacity 160ms var(--ease); }
  .out .who { opacity: 0; translate: 0 4px; transition-delay: 0s; transition-duration: 140ms; }
  .out .ghost { opacity: 1; transition-delay: 80ms; }

  /* the pen turns into Send: one round button, the accent while it can send */
  .send { position: relative; flex: none; width: 36px; height: 36px; border-radius: 50%; background: var(--fill-2); color: var(--text-3);
    transition: background var(--t-base) var(--ease), color var(--t-base) var(--ease), box-shadow var(--t-base) var(--ease), transform 450ms var(--ease-bounce); }
  .send.ready, .out .send { background: var(--accent); color: var(--on-accent); box-shadow: 0 4px 12px -4px var(--accent); }
  .send:disabled { opacity: 1; }
  .send::after { content: ''; position: absolute; inset: -4px; } /* 44 to the finger */
  .ic { position: absolute; inset: 0; display: grid; place-items: center; transition: opacity 200ms var(--ease), transform 460ms var(--ease-bounce); }
  .pen { opacity: 0; transform: rotate(80deg) scale(0.4); }
  .out .pen { opacity: 1; transform: none; }
  .out .go { opacity: 0; transform: rotate(-80deg) scale(0.4); }

  /* under the top row: the switch, the words, the rules; they flow in after the glass */
  .rest { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; transition: opacity 280ms var(--ease) 100ms, translate 420ms var(--ease) 60ms; }
  .out .rest { opacity: 0; translate: 0 -8px; transition-delay: 0s; transition-duration: 140ms; }
  .as { position: relative; display: flex; align-items: center; gap: var(--s-3); min-height: 44px; padding: var(--s-1) var(--s-3) var(--s-1) var(--s-4); cursor: pointer; }
  .as::before, .as::after { content: ''; position: absolute; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .as::before { top: 0; } .as::after { bottom: 0; }
  .asi { flex: none; width: 36px; display: grid; place-items: center; color: var(--text-2); }
  .asl { flex: 1; font: 500 var(--fs-body)/1.3 var(--font-text); color: var(--text); }
  .why { margin: var(--s-3) var(--s-4) 0; }
  /* the words: no box of their own, the window is the field */
  .cw-text { display: block; width: 100%; min-height: 132px; padding: var(--s-3) var(--s-4); border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.42 var(--font-text); letter-spacing: -0.012em; caret-color: var(--accent); }
  .cw-text.bad { caret-color: var(--danger); }
  .cw-text::placeholder { color: var(--text-3); }
  .cw-text:focus { outline: none; }
  .foot { display: flex; align-items: baseline; gap: var(--s-2); padding: 0 var(--s-4) var(--s-2); font: 500 var(--fs-sub)/1.3 var(--font-text); }
  .hint { flex: 1; color: var(--danger-text); }
  .count { margin-left: auto; color: var(--text-3); font-variant-numeric: tabular-nums; }
  .count.full { color: var(--warning-text); }
  .note { position: relative; padding: var(--s-3) var(--s-4) var(--s-4); font: 450 var(--fs-cap)/1.4 var(--font-text); color: var(--text-3); }
  .note::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }

  @media (prefers-reduced-motion: reduce) {
    .face { animation: none; }
    .scrim, .who, .ghost, .send, .ic, .rest { transition-duration: 1ms !important; transition-delay: 0s !important; }
  }
</style>
