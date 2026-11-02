<script lang="ts">
  // Profile, one screen (Oct 30: Friends and Settings were pages beside it). Guest: the sign-in card.
  // Student: my badge (the same hero as everyone else sees), then two squares: my friends (the Friends sheet: requests,
  // everyone, Add) and my invite (RefSheet); my tickets and saved events are on Afisha's list, not repeated here, the term (a strip of its weeks, the academic calendar behind it) with KBTU's psychologist
  // under it (one row, a small button to their own booking page) and KBTU's anthem, and the app's card (AppCard; it stays
  // on Me, not Settings).
  // Top right: the admin panel's shield and the gear (a guest's too). Settings open in place under the lanyard
  // (settings-spec-final.md): the gear or my photo; the blocks below leave ([data-away]), the list (SettingsList, its own
  // chunk) rises under the badge, the gear turns into a check; the check, Telegram's Back (SettingsMode, an overlay) or
  // Escape take it back.
  import Check from '@lucide/svelte/icons/check';
  import Plus from '@lucide/svelte/icons/plus';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import SettingsIcon from '@lucide/svelte/icons/settings';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import MessageCircleHeart from '@lucide/svelte/icons/message-circle-heart';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Music from '@lucide/svelte/icons/music';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, loadMyCard } from '../../lib/state/data.svelte';
  import { untrack, flushSync, type Component } from 'svelte';
  import { say, ui, open, close, removeOverlay } from '../../lib/state/ui.svelte';
  import { calm } from '../../ui/fold';
  import SettingsMode from './SettingsMode.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import { photosFirst } from '../../lib/faces';
  import { sheets } from '../../lib/state/sheets';
  import { api, type PersonCard } from '../../lib/api';
  import { nextUp, nameOf, whenOf, semester, PSYCHOLOGIST } from '../../lib/academic';
  import { t, tn, i18n } from '../../lib/i18n/index.svelte';
  import { dateInput, dayMonth, nowTs } from '../../lib/time';
  import { onMount } from 'svelte';
  import { haptic, on, openLink } from '../../lib/tg';
  import Hero from './Hero.svelte';
  import Invite from './Invite.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import AppCard from './AppCard.svelte';
  import Button from '../../ui/Button.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  // today: Me stays mounted and the app can stay open for days, so it moves on when the app comes back
  let today = $state(dateInput(nowTs()));
  onMount(() => on('activated', () => (today = dateInput(nowTs()))));
  const up = $derived(nextUp(today)), sem = $derived(semester(today));
  // the strip's month under its first week, in the app's language
  const semFrom = $derived(sem ? new Intl.DateTimeFormat(i18n.lang, { month: 'short', timeZone: 'UTC' }).format(new Date(sem.start)).replace('.', '') : '');
  const me = $derived(session.me);
  const card = $derived(data.myCard); // loaded with the app (and kept for the next launch); coming into view refreshes it
  $effect(() => { if (ui.tab === 'profile' && me?.student) void untrack(loadMyCard); });
  // the hero shows at once from what the app already knows; numbers and awards fill in when the card arrives
  const shown = $derived<PersonCard | null>(card ? { ...card, skin: ui.tryOn?.id ?? me?.skin, frame: me?.frame } : (me?.student ? {
    id: me.id, name: me.name, nick: me.nick, realName: me.nick ? `${me.student.firstName} ${[...me.student.lastName][0] ?? ''}`.trim() : undefined, avatar: me.avatar, founder: me.founder, no: me.no, course: me.student.course, school: me.student.school, bio: me.bio,
    attended: -1, clubs: me.memberships, past: [], showcase: [], shelf: [], awards: { achievements: [], badges: [] }, friendship: 'none', friendsSince: null, going: [], skin: ui.tryOn?.id ?? me.skin, frame: me.frame,
  } : null));

  // the Friends row: a few faces, how many, and the requests waiting (the tab's dot too)
  const friends = $derived(data.friends?.friends ?? []);
  const asked = $derived(me?.counters.friendRequests ?? 0);
  // the faces' cluster: [width, left, top] in % of its box (132 × 104; ~130 px wide on a phone, so a face is ~1.3 × width px), the first face the biggest, the rest around it
  // packed so seventeen faces fill the box without holes (owner, Nov 2: as many faces as fit, the whole tile above its name); fewer friends take the biggest
  const SPOTS = [[36, 2, 27], [29, 39, 32], [26, 27, 1], [23, 28, 66], [21, 53, 68], [20, 6, 75], [18, 7, 2], [17, 55, 10], [17, 68, 50], [16, 68, 28], [15, 73, 8], [14, 76, 72], [14, 84, 38], [13, 86, 57], [12, 88, 21], [11, 88, 1], [11, 88, 86]];
  // which friends: shuffled once per app open (owner, Nov 2: not always the same A-names first), the ones with a photo first
  const faces = $derived(photosFirst(friends));
  const asks = $derived(me?.role === 'admin' || me?.role === 'moderator' ? me.counters.reports + me.counters.clubApps : 0);

  let page = $state<HTMLDivElement>();

  // ---- settings in place (the motion: settings-spec-final.md). Phases run on timers, never on onfinish (a hidden
  // webview stalls it); WAAPI with transform and opacity only (iOS 15) ----
  const listChunk = () => import('./SettingsList.svelte'); // warmed with the app (App.svelte warmPages)
  let phase = $state<'idle' | 'entering' | 'on' | 'leaving'>('idle');
  let set = $state(false);   // after the swap: the away blocks gone, the list in
  let hold = $state(false);  // a fade runs: the page takes no taps
  let List = $state<Component<Record<string, never>, { photoMenu: (at: Element) => void }> | null>(null);
  let list = $state<{ photoMenu: (at: Element) => void }>();
  let lift = $state<HTMLDivElement>(), gear = $state<HTMLButtonElement>(), shield = $state<HTMLButtonElement>();
  let tok = 0, run = 0, pending = false, liftA: Animation | undefined, fades: Animation[] = [];
  const SPRING = 'cubic-bezier(.32,.72,0,1)', EASE = 'cubic-bezier(.2,.9,.22,1)', IN = 'cubic-bezier(.4,0,1,1)', BOUNCE = 'cubic-bezier(.34,1.45,.5,1)';
  const all = (q: string) => [...(page?.querySelectorAll<HTMLElement>(q) ?? [])];
  const clamp = (d: number) => Math.max(-240, Math.min(240, d));
  const top = () => lift?.getBoundingClientRect().top ?? 0;
  const ty = (el: Element) => { const m = getComputedStyle(el).transform; return m && m !== 'none' ? new DOMMatrixReadOnly(m).m42 : 0; };
  const fade = (el: Element, show: boolean, opts: KeyframeAnimationOptions) => el.animate([{ opacity: show ? 0 : 1 }, { opacity: show ? 1 : 0 }], opts);

  // the gear's circle: the gear turns away and the check springs in, or back (their rest is CSS: .gear.done)
  function icons(check: boolean, q: boolean) {
    const [g, c] = gear ? [...gear.children] : [];
    if (!g || !c) return;
    if (q) { fade(check ? g : c, false, { duration: 150 }); fade(check ? c : g, true, { duration: 150 }); return; }
    if (check) {
      g.animate([{ transform: 'none', opacity: 1 }, { transform: 'rotate(60deg)', opacity: 0 }], { duration: 140, easing: IN });
      c.animate([{ transform: 'scale(.6)', opacity: 0 }, { transform: 'none', opacity: 1 }], { duration: 260, delay: 60, easing: BOUNCE, fill: 'backwards' });
    } else {
      c.animate([{ transform: 'none', opacity: 1 }, { transform: 'scale(.6)', opacity: 0 }], { duration: 140, easing: IN });
      g.animate([{ transform: 'rotate(60deg)', opacity: 0 }, { transform: 'none', opacity: 1 }], { duration: 200, delay: 40, easing: EASE, fill: 'backwards' });
    }
  }

  function enter() {
    if (phase !== 'idle' || !page) return;
    const r = ++run, q = calm();
    haptic.tap();
    phase = 'entering'; hold = true; pending = false;
    tok = open(SettingsMode, { onclose: leave });
    icons(true, q);
    if (shield) fade(shield, false, { duration: 120 });
    fades = all('[data-away]').map((el, i) => el.animate(q ? [{ opacity: 1 }, { opacity: 0 }] : [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(16px)' }],
      { duration: 150, delay: q ? 0 : Math.min(i, 3) * 20, easing: IN, fill: 'forwards' }));
    if (lift && !q) liftA = lift.animate([{ transform: 'none' }, { transform: 'translateY(-6px)' }], { duration: 320, easing: SPRING, fill: 'forwards' });
    // the swap waits for the fade and for the list's chunk, whichever is later; a chunk that can't come undoes it all
    let time = false;
    const go = () => { if (r === run && time && List && !set) swapIn(r); };
    if (!List) listChunk().then((m) => { List = m.default; go(); }).catch(() => { if (r === run) { reset(); say(t('common.offline'), 'pleading_face_3d'); } });
    setTimeout(() => { time = true; go(); }, 150);
  }
  // one frame: the blocks go, the list comes, the page goes to the top; the lanyard slides from where it was (FLIP)
  function swapIn(r: number) {
    const q = calm(), y0 = top();
    set = true; hold = false;
    flushSync();
    if (page) page.scrollTop = 0;
    fades.forEach((a) => a.cancel()); fades = [];
    const d = y0 - top();
    if (lift && !q && d) {
      const cur = ty(lift);
      liftA?.cancel();
      liftA = lift.animate([{ transform: `translateY(${cur + clamp(d)}px)` }, { transform: 'translateY(-6px)' }], { duration: 380, easing: SPRING, fill: 'forwards' });
    }
    all('[data-unit]').forEach((u, i) => u.animate(q ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 0, transform: 'translateY(18px)' }, { opacity: 1, transform: 'none' }],
      { duration: q ? 150 : 380, delay: q ? 0 : 45 * i, easing: EASE, fill: 'backwards' }));
    page?.querySelector<HTMLElement>('.set-h')?.focus({ preventScroll: true });
    if (pending) { out(); return; }
    setTimeout(() => { if (r === run) phase = 'on'; }, q ? 150 : 515);
  }
  // the check, Back or Escape (SettingsMode's onclose); Back in the enter's fade waits for its swap, never reverses mid-fade
  function leave() {
    if (phase === 'entering' && !set) pending = true;
    else if (phase === 'entering' || phase === 'on') out();
  }
  function out() {
    const r = ++run, q = calm();
    phase = 'leaving'; hold = true; pending = false;
    haptic.soft();
    // a lanyard tried on but not mine to wear (owner, Oct 31): said so, and mine turns back
    if (ui.tryOn) { say(t('look.locked', { name: ui.tryOn.name }), 'locked_3d'); ui.tryOn = null; }
    icons(false, q);
    fades = all('[data-unit]').map((u) => u.animate(q ? [{ opacity: 1 }, { opacity: 0 }] : [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(8px)' }],
      { duration: q ? 150 : 140, easing: IN, fill: 'forwards' }));
    setTimeout(() => { if (r === run) swapOut(); }, q ? 150 : 140);
  }
  // always back at the top: the lanyard stays put, or slides down from under the capsule when the list was scrolled
  function swapOut() {
    const q = calm(), y0 = top();
    set = false; fades = [];
    flushSync();
    if (page) page.scrollTop = 0;
    const d = y0 - top(); // measured with the -6 lift still on: the layout's shift alone
    liftA?.cancel(); liftA = undefined;
    if (lift && !q) lift.animate([{ transform: `translateY(${-6 + clamp(d)}px)` }, { transform: 'none' }], { duration: 380, easing: SPRING });
    // the page's own blocks replay their stagger by themselves (display back on); the badge's bio and shelf aren't its
    // children, so they rise here. Calm: kb-stagger is off (lowfx) or 1 ms, so every block fades back here
    for (const el of all(q ? '[data-away]' : '.lift [data-away]')) {
      el.animate(q ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }],
        { duration: q ? 150 : 460, delay: q ? 0 : 40, easing: EASE, fill: 'backwards' });
    }
    if (shield) fade(shield, true, { duration: q ? 150 : 200 });
    removeOverlay(tok); tok = 0;
    phase = 'idle'; hold = false;
    gear?.focus({ preventScroll: true });
  }
  // at once, no motion: another tab took the screen (only code can: the nav is hidden), or the chunk failed
  function reset() {
    run++;
    fades.forEach((a) => a.cancel()); fades = []; liftA?.cancel(); liftA = undefined;
    set = false; hold = false; pending = false; phase = 'idle';
    if (tok) { removeOverlay(tok); tok = 0; }
  }
  $effect(() => { if (ui.tab !== 'profile') untrack(() => { if (phase !== 'idle') reset(); }); });

  async function keepAccount() {
    try { session.me = await api.keepMe(); haptic.ok(); say(t('del.kept'), 'raising_hands_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<div class="page scroll stagger" class:set class:mode={phase !== 'idle'} class:hold bind:this={page}>
  <div class="gears" class:out={!me?.student && !set}>
    {#if me?.student && (me.role === 'admin' || me.role === 'moderator')}
      <!-- the admin panel, with what waits for it; a moderator's is the content part -->
      <button class="gear shield" bind:this={shield} onclick={() => { haptic.tap(); sheets.admin(); }} aria-label={t('me.admin')}><ShieldCheck size={19} />{#if asks}<b class="cnt num">{asks}</b>{/if}</button>
    {/if}
    <!-- settings in place; in them, the check that ends them (a tap while the motion runs is ignored) -->
    <button class="gear" class:done={phase === 'entering' || phase === 'on'} bind:this={gear} aria-label={t(phase === 'entering' || phase === 'on' ? 'me.done' : 'me.settings')}
      onclick={() => { if (phase === 'idle') enter(); else if (phase === 'on') close(tok, true); }}>
      <span class="gi"><SettingsIcon size={19} /></span><span class="gi c"><Check size={20} strokeWidth={2.4} /></span></button>
  </div>
  {#if me?.student}
    <!-- my photo: settings, or in them the photo's menu at it -->
    {#if shown}<div class="lift" bind:this={lift}><Hero p={shown} qr={me.qr} live={ui.tab === 'profile'}
      onphoto={(el) => { if (phase === 'idle') enter(); else if (phase === 'on') list?.photoMenu(el); }} /></div>{/if}
    <!-- two squares (owner, Nov 1): my friends as a cluster of faces, and my invite -->
    <div class="duo" data-away>
      <button class="sq fr surface" onclick={() => { haptic.tap(); sheets.friends(); }} aria-label={asked ? `${t('page.friends')}, ${t('fr.requests')}: ${asked}` : t('page.friends')}>
        {#if friends.length}
          <span class="cluster" aria-hidden="true">{#each faces.slice(0, SPOTS.length) as r, i (r.person.id)}
            {@const [w, x, y] = SPOTS[i]}<span class="spot" style="--i:{i};width:{w}%;left:{x}%;top:{y}%"><Avatar person={r.person} size={Math.round(w * 1.3)} tappable={false} /></span>{/each}</span>
        {:else}<span class="cluster ghost" aria-hidden="true">{#each SPOTS.slice(0, 9) as [w, x, y], i}<span class="spot" style="--i:{i};width:{w}%;left:{x}%;top:{y}%">{#if !i}<Plus size={22} strokeWidth={2.4} />{/if}</span>{/each}</span>{/if}
        {#if asked}<b class="req num">{asked}</b>{/if}
        <span class="ft"><b>{t('page.friends')}</b>{#if friends.length}<span class="num fn">{friends.length}</span>{:else}<i>{t('fr.add')}</i>{/if}</span>
      </button>
      {#if me.referrals}<Invite r={me.referrals} />{/if}
    </div>
  {:else if session.failed}
    <!-- the app couldn't reach us (a bad network at start): not the guest card, which reads as being signed out -->
    <section class="failed surface" data-away>
      <p class="t-body">{t('common.offline')}</p>
      <Button kind="secondary" size="m" onclick={() => { haptic.tap(); void loadMe(); }}>{t('me.retry')}</Button>
    </section>
  {:else if session.ready}
    <section class="guest" data-away>
      <div class="mark"><KbtuMark /></div>
      <h1 class="t-h1">{t('guest.title')}</h1>
      <p class="t-body">{t('guest.text')}</p>
      <Button kind="primary" size="l" full onclick={() => sheets.login()}>{t('guest.button')}</Button>
    </section>
  {/if}
  {#if me?.student && !me.student.ms}
    <!-- not confirmed with the KBTU account yet: in sight on the profile, not only in the settings -->
    <button class="confirm surface" data-away onclick={() => { haptic.tap(); sheets.login(); }}>
      <svg viewBox="0 0 21 21" width="26" height="26" aria-hidden="true"><path fill="#f25022" d="M0 0h10v10H0z"/><path fill="#7fba00" d="M11 0h10v10H11z"/><path fill="#00a4ef" d="M0 11h10v10H0z"/><path fill="#ffb900" d="M11 11h10v10H11z"/></svg>
      <span class="lb">{t('me.msTitle')}<i class="sub">{t('me.msText')}</i></span><ChevronRight size={18} /></button>
  {/if}
  {#if me?.deleteAt}
    <!-- the week to change my mind (DeleteSheet), with the way back -->
    <div class="soon surface" data-away><span>{t('del.soon', { date: dayMonth(me.deleteAt) })}</span>
      <Button kind="secondary" size="s" onclick={keepAccount}>{t('del.keep')}</Button></div>
  {/if}

  <!-- the term: a strip of its weeks (mockup v24), the academic calendar behind it; out of term the row
       names what comes next. Under it KBTU's psychologist -->
  <div class="term surface" data-away>
    {#if sem}
      <!-- v25: one track with the term filled to this week and a glowing dot on it,
           the midterm a gold band, the exams red at the end; the next calendar day its own row, never cut -->
      {@const at = (w: number) => `${((w - 0.5) / (sem.weeks + 1)) * 100}%`}
      <button class="sem" onclick={() => sheets.academic()}>
        <span class="sem-h"><b>{sem.over ? t('sem.over') : t('sem.week', { n: sem.week, of: sem.weeks })}</b>
          <span class="left">{sem.toExams ? tn('sem.toExams', sem.toExams) : t('sem.examsNow')}</span></span>
        <span class="track" aria-hidden="true">
          <i class="band" style="left:{((sem.mid[0] - 1) / (sem.weeks + 1)) * 100}%;width:{((sem.mid[1] - sem.mid[0] + 1) / (sem.weeks + 1)) * 100}%"></i>
          <i class="exam"></i>
          <i class="fill" style="width:{sem.over ? '100%' : at(sem.week)}"></i>
          {#if !sem.over}<i class="dot" style="left:{at(sem.week)}"></i>{/if}
        </span>
        <span class="sem-l"><span>{semFrom}</span><span style="left:{at((sem.mid[0] + sem.mid[1]) / 2)}">{t('sem.mid')}</span><span>{t('sem.exams')}</span></span>
      </button>
      {#if up}<button class="r nx" onclick={() => sheets.academic()}><span class="ni"><CalendarDays size={18} /></span>
        <span class="lb ellipsis">{nameOf(up)}</span><span class="nw">{whenOf(up)}</span><ChevronRight size={16} /></button>{/if}
    {:else}
      <button class="r" onclick={() => sheets.academic()}>
        <span class="lb">{t('acad.title')}<i class="sub">{up ? `${nameOf(up)} · ${whenOf(up)}` : t('acad.sub')}</i></span><ChevronRight size={18} /></button>
    {/if}
    <!-- KBTU's psychologist: one quiet row, a small button to their own booking page (nothing else) -->
    <div class="r psy"><span class="pi"><MessageCircleHeart size={18} /></span><span class="lb">{t('psy.kbtu')}</span>
      <button class="book" onclick={() => { haptic.tap(); openLink(PSYCHOLOGIST); }}>{t('me.psychBook')}<ArrowUpRight size={14} strokeWidth={2.4} /></button></div>
    <!-- KBTU's anthem: the words and the song (the Oct 31 initiation's card on Afisha, here for good) -->
    <button class="r psy" onclick={() => sheets.anthem()}><span class="pi"><Music size={18} /></span><span class="lb">{t('anthem.title')}</span><ChevronRight size={18} /></button>
  </div>

  <AppCard />
  <!-- last before the tail, so no block's stagger delay shifts -->
  <!-- a failure inside the list shows itself instead of a blank page (Nov 2: Settings came up empty on phones) -->
  {#if set && List}<svelte:boundary onerror={(e) => console.error(e)}><List bind:this={list} />
    {#snippet failed(error, retry)}<p class="t-foot crash">{String((error as Error)?.message ?? error).slice(0, 300)} <button class="t-foot" onclick={retry}>↻</button></p>{/snippet}
  </svelte:boundary>{/if}
  <div class="tail"></div>
</div>

<style>
  .sub { display: block; margin-top: 2px; font: 500 12.5px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: 12px; }
  .page > :global(*) { flex-shrink: 0; }
  /* settings in place: what leaves is gone after the swap; the shield steps aside; no taps while a fade runs */
  .page.set :global([data-away]) { display: none; }
  .mode .shield { opacity: 0; pointer-events: none; }
  .hold { pointer-events: none; }

  .confirm { display: flex; align-items: center; gap: 14px; padding: 14px; border-radius: var(--r-l); text-align: left; color: var(--text-3);
    box-shadow: inset 0 0 0 1.5px var(--accent-soft), var(--shadow-card); }
  .confirm:active { transform: scale(0.98); }
  .soon { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: var(--r-l); box-shadow: inset 0 0 0 1.5px var(--danger-soft); font: 600 14.5px/1.3 var(--font-text); }
  .soon span { flex: 1; }

  .guest { display: flex; flex-direction: column; gap: 12px; padding: 22px 18px 18px; border-radius: var(--r-xl); background: radial-gradient(90% 80% at 20% 0%, rgba(124, 77, 255, 0.55), transparent 60%), linear-gradient(160deg, #2443B8, #101633); color: #fff; }
  .guest p { color: rgba(255, 255, 255, 0.82); }
  .failed { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 24px 18px; text-align: center; }
  .failed p { color: var(--text-2); }
  .mark { color: #fff; width: 64px; height: 64px; border-radius: 20px; background: rgba(255, 255, 255, 0.14); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); }

  .r { display: flex; align-items: center; gap: 12px; min-height: 54px; padding: 0 16px; text-align: left; color: var(--text-3); }
  button.r:active { background: var(--surface-2); }
  .lb { flex: 1; min-width: 0; font: 580 15.5px/1.2 var(--font-text); color: var(--text); }
  /* my friends and my invite: two squares under the badge (Invite.svelte is the right one) */
  .duo { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .sq { position: relative; overflow: hidden; aspect-ratio: 1; display: flex; flex-direction: column; justify-content: space-between; padding: 14px; border-radius: var(--r-l); text-align: left; }
  .sq:active { transform: scale(0.97); }
  .fr { background: radial-gradient(90% 70% at 15% 0%, var(--accent-soft), transparent 70%), var(--surface); }
  .cluster { position: relative; display: block; width: 100%; aspect-ratio: 132 / 104; }
  .spot { position: absolute; aspect-ratio: 1; display: flex; border-radius: 50%; box-shadow: 0 0 0 2px var(--surface-solid), 0 6px 14px -8px rgba(0, 0, 0, 0.45);
    z-index: calc(10 - var(--i)); animation: pop 520ms cubic-bezier(.2, .9, .25, 1.2) backwards; animation-delay: calc(120ms + var(--i) * 55ms); }
  .spot :global(.av) { width: 100% !important; height: 100% !important; }
  .spot :global(.seal) { display: none; }
  :global(html.lowfx) .spot { animation: none; }
  @keyframes pop { from { opacity: 0; transform: scale(0.6); } }
  /* no friends yet: the places waiting for them, the biggest with a plus (owner, Nov 2: not a waving hand) */
  .ghost .spot { align-items: center; justify-content: center; background: var(--fill); box-shadow: none; color: var(--accent); }
  .ghost .spot:not(:first-child) { opacity: 0.55; }
  .ft { display: flex; align-items: baseline; gap: 8px; }
  .ft b { font: 700 var(--fs-body)/1.2 var(--font-text); }
  .ft i { font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .fn { font: 700 var(--fs-body)/1 var(--font-text); color: var(--text-3); }
  .sq .req { position: absolute; top: 12px; right: 12px; z-index: 11; }
  .req { min-width: 22px; height: 22px; padding: 0 7px; border-radius: 11px; background: var(--danger); color: #fff; font: 700 12px/22px var(--font-text); text-align: center; }
  /* the shield and the gear: in the lanyard's gap right of its strap */
  .gears { position: absolute; top: calc(var(--page-top) - 6px); right: var(--gutter); z-index: 1; display: flex; gap: 8px; }
  /* a guest's gear sits over the sign-in card's corner: in it, on its glass */
  .gears.out { top: calc(var(--page-top) + 12px); right: calc(var(--gutter) + 12px); }
  .gears.out .gear { background: rgba(255, 255, 255, 0.14); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); color: #fff; }
  .gear { position: relative; width: 36px; height: 36px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; background: var(--surface); box-shadow: var(--shadow-card); color: var(--text-2); }
  .gear::after { content: ''; position: absolute; inset: -4px; border-radius: 50%; } /* a 44 px target, the circle stays 36 */
  .gear:active { transform: scale(0.92); }
  /* the gear and the check stacked in one circle, crossfading (icons()) */
  .gi { position: absolute; inset: 0; display: grid; place-items: center; }
  .gi.c, .done .gi:not(.c) { opacity: 0; }
  .done .gi.c { opacity: 1; color: var(--accent-text); }
  .cnt { position: absolute; top: -4px; right: -6px; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: var(--danger); color: #fff; font: 700 11px/18px var(--font-text); text-align: center; }

  /* the term card: the strip of weeks, then the psychologist (mockup v24) */
  .term { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .sem { display: flex; flex-direction: column; gap: 12px; padding: 16px 16px 14px; text-align: left; }
  /* a <button> doesn't stretch its flex children on older iOS WebKit: the track had no width and every label sat on the
     left ("3midterms", Oct 31) */
  .sem > * { width: 100%; }
  .sem-h { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .sem-h b { font: 750 19px/1.15 var(--font-display); letter-spacing: -0.02em; color: var(--text); }
  .left { flex: none; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .track { position: relative; height: 10px; margin: 6px 0 2px; border-radius: 5px; background: var(--surface-3); }
  .track i { position: absolute; top: 0; bottom: 0; border-radius: 5px; }
  .band { background: rgba(245, 177, 61, 0.38); }
  .exam { right: 0; width: calc(100% / 16); background: rgba(240, 82, 74, 0.75); }
  .fill { left: 0; background: linear-gradient(90deg, #3B6BFF, #7C5CFF); box-shadow: 0 0 14px -2px rgba(91, 107, 255, 0.7); }
  .dot { top: 50% !important; bottom: auto !important; width: 20px; height: 20px; translate: -50% -50%; border-radius: 50% !important;
    background: radial-gradient(circle at 35% 30%, #fff, #DCE3FF); box-shadow: 0 0 0 4px rgba(107, 107, 255, 0.45), 0 0 18px 2px rgba(107, 107, 255, 0.6); }
  .sem-l { position: relative; display: flex; justify-content: space-between; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .sem-l span:nth-child(2) { position: absolute; translate: -50% 0; color: var(--warning-text); }
  .sem-l span:last-child { color: var(--danger-text); }
  .nx { min-height: 52px; gap: 10px; }
  .ni { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 10px; background: var(--warning-soft); color: var(--warning-text); flex: none; }
  .nx .lb { font-size: var(--fs-body); }
  .nw { flex: none; font: 600 var(--fs-sub)/1 var(--font-text); color: var(--warning-text); }
  .term .r { box-shadow: inset 0 1px 0 var(--line); }
  .psy { min-height: 56px; }
  .book { position: relative; z-index: 1; flex: none; display: inline-flex; align-items: center; gap: 3px; height: 30px; padding: 0 10px 0 12px; border-radius: var(--r-full);
    background: var(--surface-2); color: var(--text); font: 650 var(--fs-sub)/1 var(--font-text); }
  .book:active { transform: scale(0.94); }
  /* the psychologist in the app's own blue, its icon on a tile like the calendar row's (no pink accent) */
  .pi { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 10px; flex: none; background: var(--accent-soft); color: var(--accent-text); }

  .tail { flex: none; height: calc(var(--bottom) + 12px); }
  .crash { padding: 16px; color: var(--danger-text); word-break: break-word; }
</style>
