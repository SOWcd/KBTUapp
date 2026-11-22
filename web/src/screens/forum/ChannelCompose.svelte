<script module lang="ts">
  import { calm } from '../../ui/fold';
  import { flushSync } from 'svelte';
  import { open } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { touched, updateChannelPosts } from '../../lib/state/channel.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { nowTs } from '../../lib/time';
  import { count } from '../../lib/stats';
  import type { ChannelFeedPost, ForumWhy, Id, Media } from '../../lib/api';
  import Self from './ChannelCompose.svelte';

  /** a photo picked for the post: the server's once uploaded (id), till then the phone's own preview; failed: its
   *  upload didn't go (the file kept for another try) */
  export type Pic = Media & { id?: Id; file?: Blob; failed?: boolean };
  /** why: a refusal by the rules, said above the words until I change them; tip: the AI's reason and advice from a
   *  refusal (Edit), kept the same way */
  export type Draft = { body: string; anon: boolean; photos?: Pic[]; why?: string; tip?: ForumWhy | null };
  // the words (and photos) not posted yet: closing the window keeps them, posting clears them. ponytail: in memory
  // only, as the feed (the posts' words stay out of storage): a relaunch starts empty; localStorage if students ask.
  // next: when the pace lets me post again (the server's word, from the last refusal or the window's open)
  const kept: { body: string; anon: boolean; photos: Pic[]; next: number | null } = { body: '', anon: false, photos: [], next: null };

  /** The writing window, out of the Forum tab's "Share with KBTU…" pill. Called in a tap: the field takes the focus in
   *  that same tap (flushSync mounts the window first), or iOS won't bring the keyboard up. */
  export function compose(draft?: Draft): void {
    open(Self, { draft }, 'sheet.compose');
    flushSync();
    const fields = document.querySelectorAll<HTMLTextAreaElement>('.cw-text'), f = fields[fields.length - 1]; // the last: an old one may still be leaving
    f?.focus({ preventScroll: true });
    f?.setSelectionRange(f.value.length, f.value.length);
  }

  // the bot's signature, as the server makes it (fchannel.signature): the real first name and the last initial, a nick or
  // not (the nick rule; the app's feed shows the nick)
  export function signOf(): string {
    const s = session.me?.student;
    return s ? `${s.firstName} ${s.lastName ? [...s.lastName][0] : ''}`.trim() : session.me?.name ?? '';
  }

  /** A stand-in on top of the feed while the server answers (a tap answers in the same frame) */
  export function stand(text: string, was: boolean, human = false, photos: Media[] = []): ChannelFeedPost {
    const me = session.me;
    const temp: ChannelFeedPost = { id: -Date.now(), body: text, status: 'held', human, at: nowTs(), msg: null, anon: was, nick: null, sign: was ? t('fc.nickSoon') : signOf(), mine: true,
      person: !was && me ? { id: me.id, name: me.name, avatar: me.avatar, founder: false } : null, comments: 0, thread: null, faces: [], reactions: [], hearts: 0, hearted: false, hot: false, photos };
    updateChannelPosts((posts) => [temp, ...posts]);
    return temp;
  }
  // the feed's key for a post that was my stand-in: the stand-in's own, so the card stays the same card when the
  // server's id comes (a new key swapped it for a twin, a blink at the top). ponytail: grows by one per post I send
  // in this session
  const born = new Map<Id, Id>();
  export const keyOf = (p: ChannelFeedPost): Id => born.get(p.id) ?? p.id;
  /** The stand-in becomes the real one (or just goes, if a refresh brought the real one already: no twin keys) */
  export function land(temp: ChannelFeedPost, p: { id: Id; status: ChannelFeedPost['status']; at: number; nick: ChannelFeedPost['nick'] }, human = false,
    review?: ChannelFeedPost['review']): void {
    touched();
    born.set(p.id, temp.id);
    updateChannelPosts((posts) => posts.some((x) => x.id === p.id) ? posts.filter((x) => x.id !== temp.id)
      : posts.map((x) => x.id === temp.id ? { ...x, id: p.id, status: p.status, at: p.at, nick: p.nick, human, review } : x));
  }
  export const unstand = (temp: ChannelFeedPost): void => updateChannelPosts((posts) => posts.filter((x) => x.id !== temp.id));
</script>

<script lang="ts">
  // The writing window grows from the Forum card; its header keeps the card's geometry.
  // Focus stays in the opening tap for iOS. The editor and guidance scroll above the attachment control.
  import { onMount, untrack } from 'svelte';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import RotateCw from '@lucide/svelte/icons/rotate-cw';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import X from '@lucide/svelte/icons/x';
  import { shrink } from '../../lib/photo';
  import { api, ApiErr } from '../../lib/api';
  import { channel, updateChannelPosts as updatePosts } from '../../lib/state/channel.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { close, hideChrome, removeOverlay, say, type Overlay } from '../../lib/state/ui.svelte';
  import { type Key } from '../../lib/i18n/index.svelte';
  import { brokenAll, meaningful, type Rule } from '../../lib/forumRules';
  import { haptic } from '../../lib/tg';
  import { keyboard } from '../../lib/state/keyboard.svelte';
  import { burst } from '../../ui/burst';
  import { grow } from '../../ui/grow';
  import { glass } from '../../ui/glass';
  import Avatar from '../../ui/Avatar.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import ChannelRefused from './ChannelRefused.svelte';

  let { overlay, draft }: { overlay: Overlay; draft?: Draft } = $props();
  let body = $state(untrack(() => draft?.body ?? kept.body)), anon = $state(untrack(() => draft?.anon ?? kept.anon));
  // the photos (up to 4): each uploads as it's picked, its preview at once (the phone's own) till the server's comes
  let pics = $state<Pic[]>(untrack(() => draft?.photos ?? kept.photos));
  const PICS = 4;
  let revealed = $state<number | null>(null), next = $state<number | null>(kept.next), clock = $state(nowTs());
  onMount(() => {
    api.channelRevealed().then((r) => { revealed = r.revealed; next = kept.next = r.next; }).catch(() => {});
    const tick = setInterval(() => { clock = nowTs(); }, 10_000);
    return () => clearInterval(tick);
  });
  $effect(() => { kept.body = body; kept.anon = anon; kept.photos = pics; });
  $effect(() => { overlay.title = t('fc.new'); overlay.icon = SquarePen; });
  const why = $derived(draft?.why && body === draft.body ? draft.why : null);  // gone once I change the words
  const tip = $derived(draft?.tip && body === draft.body ? draft.tip : null);
  const MAX = $derived(pics.length ? 900 : 1000);  // under photos: a caption (the server's CAPTION_MAX)
  const HINT: Record<Rule, Key> = { link: 'fc.noLink', mention: 'fc.noMention', phone: 'fc.noPhone', signature: 'fc.signature' };
  const rules = $derived(brokenAll(body));
  const wait = $derived(next && next > clock ? Math.ceil((next - clock) / 60) : 0);
  // what holds Send, the first said on a tap: the words' rules (said as I type), too long, empty, too short, a photo
  // still uploading, the pace. short is said only once I tap (a first word is not a mistake yet)
  const hold = $derived<Key | null>(rules.length ? HINT[rules[0]] : body.length > MAX ? 'fc.long' : !body.trim() ? 'fc.empty'
    : !meaningful(body) ? 'fc.short' : pics.some((p) => !p.id) ? 'fc.uploading' : null);
  const ready = $derived(!hold && !wait);
  // the reason a tap on Send got, shown until the words or the photos change
  let tapped = $state<{ key: Key; body: string; n: number } | null>(null);
  const nudged = $derived(tapped && tapped.body === body && tapped.n === pics.length ? tapped.key : null);
  const hints = $derived([...new Set([...rules.map((r) => HINT[r]), ...(body.length > MAX ? ['fc.long' as Key] : []), ...(nudged && !rules.length ? [nudged] : [])])]);
  const sign = $derived(session.me ? signOf() : '');
  let more = $state(false);  // the anonymity's details, a tap deeper

  async function upload(url: string, file: Blob) {
    try {
      const got = await api.uploadChannelPhoto(await shrink(file));
      pics = pics.map((p) => (p.url === url ? got : p));
      URL.revokeObjectURL(url);
    } catch {
      haptic.error();
      pics = pics.map((p) => (p.url === url ? { ...p, failed: true } : p));  // stays, with a retry: the text and the others too
    }
  }
  function pick(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, files = [...(el.files ?? [])].slice(0, PICS - pics.length);
    el.value = '';
    for (const file of files) {
      if (file.size > 30 * 1024 * 1024) { say(t('ed.photoBig'), 'pleading_face_3d'); continue; }
      const url = URL.createObjectURL(file);
      pics = [...pics, { url, thumb: url, w: 1, h: 1, blur: '', file }];  // in the order picked
      void upload(url, file);
    }
    field?.focus({ preventScroll: true });
  }
  function retry(p: Pic) {
    if (!p.file) return;
    haptic.tap(); pics = pics.map((x) => (x.url === p.url ? { ...x, failed: false } : x)); void upload(p.url, p.file);
  }
  const unpick = (p: Pic) => { haptic.select(); pics = pics.filter((x) => x.url !== p.url); };
  const view = (i: number) => sheets.photos(pics.filter((p) => p.id).map((p, j) => ({ ...p, id: j + 1, by: null, mine: true, canDelete: false })), i);

  // the mode switch keeps the caret where it was (a tap on it would take the keyboard away)
  let field = $state<HTMLTextAreaElement>(), caret: [number, number] | null = null;
  const keep = () => { caret = document.activeElement === field && field ? [field.selectionStart, field.selectionEnd] : null; };
  function mode(v: 'name' | 'anon') {
    anon = v === 'anon'; haptic.select();
    if (caret && field) { field.focus({ preventScroll: true }); field.setSelectionRange(...caret); }
    caret = null;
  }

  // Done on the keyboard (the field gives the focus to nothing) with nothing written folds the window back into the
  // pill, as Apple's own fields do when left empty; words or a photo keep it open (Back, the dim or a swipe on it
  // close it, the draft kept). A tap on the window's own controls takes the focus from the field too: never that.
  let touchAt = -1e9;
  const touch = () => { touchAt = performance.now(); };
  const empty = () => !body.trim() && !pics.length;
  function left() {
    if (!empty() || performance.now() - touchAt < 500) return;
    setTimeout(() => { if (!gone && empty() && !win.contains(document.activeElement)) close(overlay.id); });  // a tick on: where the focus went
  }

  // One morph, transforms and opacity only (an animated clip-path repainted the whole window every frame on iPhone):
  // win, the frame, rounds and clips; pane, the surface, slides down out of the pill's row; inner slides back by as
  // much, so the words never move inside the window while its lower edge sweeps open. The pill itself stays under
  // it at the folded end (Channel .compose.away) and the window fades over it, so the capsule's glass and rounding
  // never swap for the window's in one frame. The dim and the nav move on this one clock.
  let win: HTMLDivElement, pane: HTMLDivElement, inner: HTMLDivElement;
  let motion: Animation[] = [];
  let out = $state(true);  // folded into the pill: the state it opens from and closes back to (CSS transitions in between)
  let gone = false, sent = false;
  let restore = () => {};  // the pill and the nav come back as the fold starts, not after it
  const OPEN = 460, SHUT = 360;  // the scrim's times in CSS are these
  const ease = () => getComputedStyle(win).getPropertyValue('--ease-spring').trim();

  // where the pill is, against the window's resting place (its layout box: read with no motion on it)
  function pill(): { dy: number; h: number } | null {
    const p = document.querySelector('[data-compose]')?.getBoundingClientRect();
    if (!p?.width || p.left < -1 || p.right > innerWidth + 1 || p.bottom < 0 || p.top > innerHeight) return null;
    return { dy: p.top - win.getBoundingClientRect().top, h: Math.min(p.height, win.offsetHeight) };
  }
  // the pill's row and the window, one morph either way; from: the frame on screen (Back mid-growth folds from there)
  function morph(f: { dy: number; h: number }, from?: string[], shown = '1'): Animation[] {
    const H = win.offsetHeight, ends = [`translateY(${f.dy}px)`, `translateY(${f.h - H}px)`, `translateY(${H - f.h}px)`];
    return [...[win, pane, inner].map((el, i) => el.animate(from ? [{ transform: from[i] }, { transform: ends[i] }] : [{ transform: ends[i] }, { transform: 'none' }],
      { duration: from ? SHUT : OPEN, easing: ease(), fill: from ? 'forwards' : 'none' })),
      // the hand-over: the window comes over the pill in its first moments (Channel hides the pill after these 90 ms)
      // and thins out over it in its last
      win.animate(from ? [{ opacity: shown }, { opacity: 0 }] : [{ opacity: 0 }, { opacity: 1 }],
        from ? { duration: 140, delay: SHUT - 140, easing: 'ease-in', fill: 'both' } : { duration: 90, easing: 'ease-out' })];
  }

  function leave() {
    if (gone) return;
    gone = true; out = true;
    const from = [win, pane, inner].map((el) => getComputedStyle(el).transform), shown = getComputedStyle(win).opacity;
    // the keyboard going down must not grow the window under the exit: its last frame still matches the pill
    win.style.height = win.style.maxHeight = `${win.offsetHeight}px`;
    for (const a of motion) a.cancel();
    const f = calm() ? null : pill();
    (document.activeElement as HTMLElement | null)?.blur?.(); // the keyboard goes with it
    restore();
    motion = f ? morph(f, from, shown) : [win.animate([{ opacity: shown }, { opacity: 0 }], { duration: calm() ? 1 : 200, easing: ease(), fill: 'forwards' })];
    motion[0].onfinish = () => {
      flushSync(() => removeOverlay(overlay.id));
      document.querySelector<HTMLElement>('[data-compose]')?.focus({ preventScroll: true });
    };
  }
  $effect(() => { if (overlay.closing) untrack(leave); });  // Back, the scrim, a send: the draft stays, nothing to ask

  onMount(() => {
    channel.writing++;
    const chrome = hideChrome();
    restore = () => { restore = () => {}; channel.writing--; chrome(); };
    // the feed behind is out of reach while I write: no focus, no screen reader (the dialog is modal)
    const bg = document.querySelector('section.tab.on'), was = bg?.hasAttribute('inert');
    bg?.setAttribute('inert', '');
    // The opening starts a frame on: by then the tap's focus has told the keyboard (keyboard.h, guessed on iOS at once,
    // lib/state/keyboard), so the window is measured at the size it keeps, never relaid out under the motion.
    const frame = requestAnimationFrame(() => {
      if (gone) return;
      const f = calm() ? null : pill();
      motion = f ? morph(f) : [win.animate([{ opacity: 0 }, { opacity: 1 }], { duration: calm() ? 1 : 200, easing: ease() })];
      out = false;
    });
    return () => {
      cancelAnimationFrame(frame); for (const a of motion) a.cancel();
      restore();
      if (!was) bg?.removeAttribute('inert');
    };
  });

  function reason(e: unknown): string {
    const why: Key = e instanceof ApiErr ? (e.code === 'rate_limited' ? 'fc.slow' : e.message === 'long' ? 'fc.long' : e.message === 'links' ? 'fc.links' : e.message === 'signature' ? 'fc.signature' : e.message === 'short' ? 'fc.short' : e.message === 'duplicate' ? 'fc.dup' : 'common.error') : 'common.error';
    return t(why);
  }

  async function post() {
    if (!ready) { haptic.error(); tapped = hold ? { key: hold, body, n: pics.length } : null; return; }  // stays in place and says why (the wait is on the bar already)
    if (sent) return;  // once: a second tap while it closes sends nothing
    sent = true;
    const text = body.trim(), was = anon, photos = $state.snapshot(pics) as Pic[];
    const temp = stand(text, was, false, photos); haptic.select(); kept.body = ''; kept.photos = []; close(overlay.id);
    try {
      const p = await api.newChannelPost(text, was, photos.map((x) => x.id!));
      count('do.forum');
      const photo = p.status === 'held' && was && photos.length > 0;
      land(temp, p, p.status === 'held' && (!!p.ai || photo), photo ? { kind: 'photo', explain: null } : undefined);
      haptic.ok();
      // out: the card at the top says it (Publishing…, then the channel's link); no toast over it
      if (p.status === 'live') {
        burst();
        setTimeout(() => { void api.channelPost(p.id).then((next) => updatePosts((posts) => posts.map((row) => row.id === p.id ? next : row))).catch(() => {}); }, 5000);
      }
      else {
        say(t('fc.heldSay'), 'thinking_face_3d');
        if (p.ai) api.channelPostWhy(p.id, text).then((x) => { if (x.explain) channel.why[p.id] = x.explain; }).catch(() => {});
      }
    } catch (e) {
      unstand(temp); haptic.error(); kept.body = text; kept.anon = was; kept.photos = photos;  // not gone: the words wait in the window
      const d = e instanceof ApiErr ? e.data : {};
      if (e instanceof ApiErr && e.code === 'rate_limited' && typeof d.retry === 'number') kept.next = d.retry;
      if (e instanceof ApiErr && (e.message === 'noise' || e.message === 'ad') && typeof d.post === 'number')
        open(ChannelRefused, { body: text, anon: was, photos, refused: { post: d.post, kind: e.message === 'ad' ? 'ad' : 'noise', appeal: d.appeal === true } });
      else compose({ body: text, anon: was, photos, why: e instanceof ApiErr && e.code === 'rate_limited' && kept.next ? undefined : reason(e) });
    }
  }
  // Ctrl/Cmd+Enter sends (a computer); a plain Enter is a new line
  const key = (e: KeyboardEvent) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); post(); } };
</script>

<div class="scrim" class:out onclick={() => close(overlay.id, true)} ontouchmove={() => close(overlay.id, true)} role="presentation"></div>
<!-- the window ends above the keyboard (keyboard.h: the app's one number for it); its scroller keeps its own room
     (data-kb-own): a spacer the keyboard code put under the words slid them down and back while it came up -->
<div class="cw" class:out bind:this={win} style:--kb="{keyboard.h}px" onpointerdowncapture={touch} onpointerupcapture={touch} role="dialog" aria-modal="true" aria-label={t('fc.new')}>
<div class="pane glass glass-sheet" use:glass bind:this={pane}>
<div class="in" bind:this={inner}>
  <!-- the pill's own row, the same places: my face, then who it goes out as (the pill's words fade into it), Send -->
  <div class="top">
    {#key anon || !session.me}<span class="face">{#if anon || !session.me}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
    {:else}<Avatar person={session.me} size={36} tappable={false} />{/if}</span>{/key}
    <span class="who" aria-live="polite"><b class="ellipsis">{anon ? t('fc.nickNew') : sign}</b><span class="sub">{t('fc.toChannel')}</span></span>
    <span class="ghost ellipsis" aria-hidden="true">{t('fc.share')}</span>
    <button class="send" class:ready aria-disabled={!ready} onclick={post} aria-label={t('fc.post')} aria-describedby="cw-hold">
      <span class="ic pen" aria-hidden="true"><SquarePen size={18} strokeWidth={2} /></span>
      <span class="ic go" aria-hidden="true"><ArrowUp size={20} strokeWidth={2.4} /></span>
    </button>
  </div>
  <div class="body">
  <div class="rest scroll" data-kb-own>
    <!-- who it goes out as, said outright; the tap keeps the keyboard and the caret -->
    <div class="mode" onpointerdown={keep} onmousedown={(e) => e.preventDefault()} role="presentation">
      <Segmented label={t('fc.anon')} value={anon ? 'anon' : 'name'} onchange={mode}
        items={[{ value: 'name', label: t('fc.named') }, { value: 'anon', label: t('fc.anon') }]} />
    </div>
    {#if why}<div class="why"><Notice tone="warning" text={why} /></div>{/if}
    <!-- the AI's reason and advice from a refusal (Edit), until I change the words -->
    {#if tip}<div class="tip"><p>{tip.reason}</p>{#if tip.fix}<p class="fix"><Lightbulb size={15} strokeWidth={2} aria-hidden="true" /><span>{tip.fix}</span></p>{/if}</div>{/if}
    <textarea class="cw-text" class:bad={rules.length > 0} bind:this={field} bind:value={body} maxlength={MAX} rows="4" placeholder={t('fc.share')} aria-label={t('fc.ph')}
      aria-invalid={rules.length > 0} aria-describedby="cw-hold" onkeydown={key} onblur={left} use:grow></textarea>
    <!-- every rule broken, at once, in plain words; a tap on Send adds why it held -->
    <div class="hints" id="cw-hold" role="status">{#each hints as h (h)}<p>{t(h)}</p>{/each}</div>
    <!-- the photos, in the order picked: each its own state (uploading, failed: tap to try again), its x; a tap views it -->
    {#if pics.length}<div class="pics">
      {#each pics as p, i (p.url)}<span class="pic" class:up={!p.id && !p.failed} class:failed={p.failed}>
        {#if p.failed}<button class="img" onclick={() => retry(p)} aria-label={t('fc.retry')}><img src={p.thumb} alt="" /><span class="re"><RotateCw size={20} strokeWidth={2.2} /></span></button>
        {:else}<button class="img" onclick={() => p.id && view(pics.filter((x) => x.id).indexOf(p))} aria-label="{t('fc.photo')} {i + 1}" disabled={!p.id}><img src={p.thumb} alt="" /></button>{/if}
        <button class="off" onclick={() => unpick(p)} aria-label={t('fc.photoOff')}><X size={14} strokeWidth={2.6} /></button></span>{/each}
    </div>{/if}
    {#if anon && pics.length}<p class="note warn">{t('fc.photoAnon')}</p>{/if}
    <!-- the rules in both modes; with the mask, the honest line and the rest a tap deeper -->
    <div class="notes">
      <p class="note">{t('fc.rules')}</p>
      {#if anon}
        <p class="note">{t('fc.anonHidden')} <button class="link" aria-expanded={more} onclick={() => { haptic.tap(); more = !more; }}>{t('fc.about')}</button></p>
        {#if more}<p class="note">{t('fc.asAnon')}{#if revealed !== null}<br />{t('fc.revealed', { n: revealed })}{/if}</p>{/if}
      {/if}
    </div>
  </div>
  <div class="footer">
    <!-- A named attachment control belongs to the editor, without a separate empty toolbar. -->
    <div class="tools">
      <label class="photo-tool" class:disabled={pics.length >= PICS}>
        <ImagePlus size={20} strokeWidth={2} aria-hidden="true" /><span>{t('fc.addPhoto')}</span>
        {#if pics.length}<span class="n">{pics.length}/{PICS}</span>{/if}
        <input type="file" accept="image/*" multiple aria-label={t('fc.addPhoto')} onchange={pick} disabled={pics.length >= PICS} />
      </label>
      {#if wait}<span class="wait" role="status">{t('fc.wait', { n: wait })}</span>{/if}
      {#if body.length > MAX - 100}<span class="count" class:full={body.length >= MAX}>{MAX - body.length}</span>{/if}
    </div>
  </div>
  </div>
</div>
</div>
</div>

<style>
  /* the dim, on the morph's clock (OPEN and SHUT in the script). No blur under it: it came as a second step once the
     window stood, and went in one frame as the dim began to fade (WebKit drops a backdrop-filter under an animated
     opacity) */
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--scrim); transition: opacity 460ms var(--ease-spring); }
  .scrim.out { opacity: 0; transition-duration: 360ms; }
  /* the frame: where the window rests, its rounding and its clip (nothing painted of its own); the ground ends 12 px
     above the keyboard */
  .cw { position: absolute; z-index: var(--z-sheet); top: calc(var(--head-bottom) + var(--s-2)); left: var(--gutter); right: var(--gutter);
    max-width: 560px; margin: 0 auto; max-height: calc(100% - var(--head-bottom) - var(--s-2) - max(var(--kb, 0px) + 12px, var(--s-4) + var(--safe-bottom)));
    display: flex; flex-direction: column; overflow: hidden; border-radius: var(--r-l); }
  /* the surface and the words, each a layer of its own while they slide (morph in the script) */
  .pane { position: relative; min-height: 0; display: flex; flex-direction: column; overflow: hidden; border-radius: inherit; background: var(--surface-solid); box-shadow: none;
    -webkit-backdrop-filter: none; backdrop-filter: none; }
  .in { flex: 0 1 auto; min-height: 0; display: flex; flex-direction: column; }

  /* the top row: the pill's sizes, so its pen stays put; my face and the words sit a step further in than the pill's
     (the window's own margin) and glide that step with the morph */
  .top { position: relative; flex: none; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-3) var(--s-3) var(--s-4); }
  .face { flex: none; display: flex; }
  .face, .ghost { transition: transform 460ms var(--ease-spring), opacity 100ms var(--ease); }
  .out .face, .out .ghost { transform: translateX(calc(var(--s-3) - var(--s-4))); transition-duration: 360ms, 160ms; }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--fill-2); color: var(--text); }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; transition: opacity var(--t-base) var(--ease) 60ms; }
  .who b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); letter-spacing: -0.01em; }
  .sub { font: 450 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  /* the pill's words, where they were. One line goes before the other comes: the two never read through each other */
  .ghost { position: absolute; left: calc(var(--s-4) + 36px + var(--s-3)); right: calc(36px + var(--s-3) * 2); top: 50%; translate: 0 -50%; opacity: 0; pointer-events: none;
    font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-3); }
  .out .who { opacity: 0; transition-duration: var(--t-fast); transition-delay: 0s; }
  .out .ghost { opacity: 1; transition-delay: 0s, 80ms; }

  /* the pen turns into Send: one round button, the accent while it can send (held: grey, a tap says why) */
  .send { position: relative; flex: none; width: 36px; height: 36px; border-radius: 50%; background: var(--fill-2); color: var(--text-3);
    transition: background var(--t-base) var(--ease), color var(--t-base) var(--ease), box-shadow var(--t-base) var(--ease), transform var(--t-base) var(--ease); }
  .send.ready { background: var(--accent); color: var(--on-accent); box-shadow: 0 4px 12px -4px var(--accent); }
  /* folded: the pill's own quiet pen lens (Channel .pen), so the hand-over at either end changes nothing */
  .out .send { background: var(--fill); color: var(--text); box-shadow: inset 0 1px 0.5px var(--lg-rim-lo), inset 0 0 0 0.5px var(--line-2); }
  .send::after { content: ''; position: absolute; inset: -4px; } /* 44 to the finger */
  .ic { position: absolute; inset: 0; display: grid; place-items: center; transition: opacity 200ms var(--ease), transform var(--t-base) var(--ease); }
  .pen { opacity: 0; transform: rotate(24deg) scale(0.8); }
  .out .pen { opacity: 1; transform: none; }
  .out .go { opacity: 0; transform: rotate(-24deg) scale(0.8); }

  /* One opaque writing surface: no feed text or buttons bleed through its lower edge. */
  .body { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .rest { position: relative; flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
  .rest, .footer { transition: opacity var(--t-base) var(--ease); }
  .out .rest, .out .footer { opacity: 0; transition-duration: var(--t-fast); }
  .mode { padding: var(--s-1) var(--s-4) var(--s-2); }
  .why { margin: var(--s-3) var(--s-4) 0; }
  .tip { margin: var(--s-3) var(--s-4) 0; display: flex; flex-direction: column; gap: var(--s-1); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-2); }
  .tip .fix { display: flex; gap: var(--s-2); align-items: flex-start; color: var(--text); }
  .tip .fix :global(svg) { flex: none; margin-top: 2px; color: var(--warning-text); }
  /* the words: no box of their own, the window is the field */
  .cw-text { display: block; width: 100%; min-height: calc(var(--s-10) * 3); padding: var(--s-3) var(--s-4); border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.42 var(--font-text); letter-spacing: -0.012em; caret-color: var(--accent); }
  .cw-text.bad { caret-color: var(--danger); }
  .cw-text::placeholder { color: var(--text-3); }
  .cw-text:focus { outline: none; }
  .hints { padding: 0 var(--s-4); font: 500 var(--fs-sub)/1.35 var(--font-text); color: var(--danger-text); }
  .hints p { padding-bottom: var(--s-2); }
  .pics { display: flex; flex-wrap: wrap; gap: var(--s-2); padding: 0 var(--s-4) var(--s-3); }
  .pic { position: relative; width: 64px; height: 64px; border-radius: var(--r-m); overflow: hidden; background: var(--fill-2); flex: none; }
  .img { display: block; width: 100%; height: 100%; }
  .img img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .pic.up img { opacity: 0.5; animation: up 1s var(--ease) infinite alternate; }
  @keyframes up { to { opacity: 0.8; } }
  .pic.failed img { opacity: 0.35; }
  .re { position: absolute; inset: 0; display: grid; place-items: center; color: var(--danger-text); }
  .off { position: absolute; top: 3px; right: 3px; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center;
    background: rgb(0 0 0 / 0.55); color: white; }
  .off::after { content: ''; position: absolute; inset: -8px; } /* a bigger target */
  .note { font: 450 var(--fs-cap)/1.4 var(--font-text); color: var(--text-3); }
  .rest > .note { padding: 0 var(--s-4) var(--s-2); }
  .note.warn { color: var(--warning-text); font-weight: 500; }
  .link { display: inline; padding: 0; color: var(--accent-text); font: inherit; font-weight: 500; position: relative; }
  .link::after { content: ''; position: absolute; inset: -12px -6px; } /* 44 to the finger */

  /* Only the attachment control stays pinned: the editor keeps room for words when the keyboard is open. */
  .footer { flex: none; padding: 0 var(--s-4) var(--s-3); }
  .tools { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2) var(--s-3); padding: var(--s-1) 0 var(--s-2); }
  .photo-tool { position: relative; display: inline-flex; align-items: center; justify-content: center; gap: var(--s-2);
    min-height: var(--tap); max-width: 100%; padding: 0 var(--s-3); border-radius: var(--r-full); background: var(--fill); color: var(--text-2);
    font: 600 var(--fs-sub)/1.2 var(--font-text); cursor: pointer; transition: background var(--t-fast) var(--ease); }
  .photo-tool:active { background: var(--fill-2); }
  .photo-tool:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  .photo-tool.disabled { opacity: 0.5; cursor: default; }
  .photo-tool :global(svg) { flex: none; }
  .photo-tool input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: inherit; }
  .notes { display: grid; gap: var(--s-1); padding: 0 var(--s-4) var(--s-2); }
  .n, .wait, .count { font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); font-variant-numeric: tabular-nums; }
  .wait { flex: 1; color: var(--warning-text); }
  .count { margin-left: auto; }
  .count.full { color: var(--warning-text); }

  @media (prefers-reduced-motion: reduce) {
    .pic.up img { animation: none; }
    .scrim, .who, .face, .ghost, .send, .ic, .rest, .footer, .photo-tool { transition-duration: 1ms !important; transition-delay: 0s !important; }
  }
</style>
