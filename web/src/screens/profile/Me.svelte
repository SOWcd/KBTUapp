<script lang="ts">
  // Profile, one screen (Oct 30: Friends and Settings were pages beside it). Guest: the sign-in card.
  // Student: my badge (the same hero as everyone else sees), then groups of rows, the phone's own way (owner, Nov 15:
  // redone from scratch): what needs me (the KBTU sign-in, a deletion on its way), my people (friends: the Friends sheet;
  // my invite: RefSheet); my tickets and saved events are on Afisha's list, not repeated here, the term (a strip of its weeks, the academic calendar behind it) with KBTU's psychologist
  // under it (one row, a small button to their own booking page) and KBTU's anthem, and the app's card (AppCard; it stays
  // on Me, not Settings).
  // Top right: the admin panel's shield, the Student Government's panel and the gear (a guest's too). Settings open in place under the lanyard
  // (settings-spec-final.md): the gear or my photo; the blocks below leave ([data-away]), the list (SettingsList, its own
  // chunk) rises under the badge, the gear turns into a check; the check, Telegram's Back (SettingsMode, an overlay) or
  // Escape take it back.
  import Check from '@lucide/svelte/icons/check';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import SettingsIcon from '@lucide/svelte/icons/settings';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import MessageCircleHeart from '@lucide/svelte/icons/message-circle-heart';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Music from '@lucide/svelte/icons/music';
  import MonitorUp from '@lucide/svelte/icons/monitor-up';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import Landmark from '@lucide/svelte/icons/landmark';
  import MessageCircleQuestion from '@lucide/svelte/icons/message-circle-question-mark';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, loadMyCard } from '../../lib/state/data.svelte';
  import { untrack, flushSync, type Component } from 'svelte';
  import { say, ui, open, close, removeOverlay, overlays } from '../../lib/state/ui.svelte';
  import { calm } from '../../ui/fold';
  import SettingsMode from './SettingsMode.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import { photosFirst } from '../../lib/faces';
  import { sheets } from '../../lib/state/sheets';
  import { api, type PersonCard } from '../../lib/api';
  import { nextUp, nameOf, whenOf, semester, termsOf, MASTER, PSYCHOLOGIST } from '../../lib/academic';
  import { t, tn, i18n } from '../../lib/i18n/index.svelte';
  import { dateInput, dayMonth, nowTs } from '../../lib/time';
  import { onMount } from 'svelte';
  import { haptic, on, openLink } from '../../lib/tg';
  import { may } from '../../lib/perms';
  import Hero from './Hero.svelte';
  import { myShown } from '../../lib/state/looks.svelte';
  import Invite from './Invite.svelte';
  import AppCard from './AppCard.svelte';
  import Button from '../../ui/Button.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Notice from '../../ui/Notice.svelte';

  // today: Me stays mounted and the app can stay open for days, so it moves on when the app comes back
  let today = $state(dateInput(nowTs()));
  onMount(() => on('activated', () => (today = dateInput(nowTs()))));
  // my calendar by my student ID's letter (master's: M)
  const terms = $derived(termsOf(session.me?.student?.studentId));
  const up = $derived(nextUp(today, terms)), sem = $derived(semester(today, terms));
  // the strip's month under its first week, in the app's language
  const semFrom = $derived(sem ? new Intl.DateTimeFormat(i18n.lang, { month: 'short', timeZone: 'UTC' }).format(new Date(sem.start)).replace('.', '') : '');
  const me = $derived(session.me);
  const card = $derived(data.myCard); // loaded with the app (and kept for the next launch); coming into view refreshes it
  $effect(() => { if (ui.tab === 'profile' && me?.student) void untrack(loadMyCard); });
  const shown = $derived(myShown()); // at once from what the app knows (looks.svelte.ts)

  // the Friends row: a few faces, how many, and the requests waiting (the tab's dot too)
  const friends = $derived(data.friends?.friends ?? []);
  const asked = $derived(me?.counters.friendRequests ?? 0);
  // whose faces: shuffled once per app open (owner, Nov 2: not always the same A-names first), the ones with a photo first
  const faces = $derived(photosFirst(friends));
  const staff = $derived(me?.role === 'admin' || me?.role === 'moderator');
  const asks = $derived(staff ? me!.counters.inbox : 0);
  // the Student Government's people (appeals.sg): their own panel, with the appeals nobody took yet
  const sg = $derived(!!me?.appeals?.sg), sgNew = $derived(sg ? data.sg?.items.filter((a) => a.status === 'new').length ?? 0 : 0);
  const hd = $derived(!!me?.ask?.staff), hdNew = $derived(hd ? data.helpq?.items.filter((a) => a.status === 'new').length ?? 0 : 0);

  let page = $state<HTMLDivElement>();

  // built in two steps: the badge (and the gears) in the first task, the blocks under it in the next one, or, built
  // while the tab is away, in the next idle moment. Unseen either way: those blocks fade in on the page's stagger, from
  // 80 ms after the badge.
  let rest = $state(false);
  onMount(() => {
    if (ui.tab !== 'profile' && 'requestIdleCallback' in window) { const h = requestIdleCallback(() => (rest = true), { timeout: 1000 }); return () => cancelIdleCallback(h); }
    let k = 0;
    const f = requestAnimationFrame(() => (k = setTimeout(() => (rest = true)) as unknown as number));
    return () => { cancelAnimationFrame(f); clearTimeout(k); };
  });

  // ---- settings in place (the motion: settings-spec-final.md). Phases run on timers, never on onfinish (a hidden
  // webview stalls it); WAAPI with transform and opacity only (iOS 15) ----
  const listChunk = () => import('./SettingsList.svelte'); // warmed with the app (App.svelte warmPages)
  let phase = $state<'idle' | 'entering' | 'on' | 'leaving'>('idle');
  let set = $state(false);   // after the swap: the away blocks gone, the list in
  let hold = $state(false);  // a fade runs: the page takes no taps
  let List = $state<Component<{ editing: boolean; onlanyard: () => void }, { photoMenu: (at: Element) => void }> | null>(null);
  // the lanyard's editor in place of the list (its first row), under the same badge: a second overlay over the
  // settings' (etok), so Back returns to the list; the check saves and leaves the settings (owner, Nov 8)
  let edit = $state(false), etok = 0;
  let list = $state<{ photoMenu: (at: Element) => void }>();
  let lift = $state<HTMLDivElement>(), gear = $state<HTMLButtonElement>(), shield = $state<HTMLSpanElement>();
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
    if (!rest) { rest = true; flushSync(); } // the blocks under the badge, if still to come, are there to fade out with the rest
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
    rise(q);
    page?.querySelector<HTMLElement>('.set-list')?.focus({ preventScroll: true });
    if (pending) { out(); return; }
    setTimeout(() => { if (r === run) phase = 'on'; }, q ? 150 : 515);
  }
  const rise = (q: boolean) => all('[data-unit]').forEach((u, i) => u.animate(q ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 0, transform: 'translateY(18px)' }, { opacity: 1, transform: 'none' }],
    { duration: q ? 150 : 380, delay: q ? 0 : 45 * i, easing: EASE, fill: 'backwards' }));
  // the list and the editor swap in one frame, the new one rising as the list did
  function swapEdit(on: boolean) {
    edit = on;
    flushSync();
    if (page) page.scrollTop = 0;
    rise(calm());
  }
  function lanyard() {
    if (phase !== 'on' || edit || !me) return;
    ui.look = { skin: me.skin, frame: me.frame ?? null };
    etok = open(SettingsMode, { title: 'look.lanyard', onclose: unedit });
    swapEdit(true);
  }
  const dirty = () => !!ui.look && !!me && (ui.look.skin !== me.skin || ui.look.frame !== (me.frame ?? null));
  // a locked lanyard tried on (owner, Oct 31): said it isn't mine, and mine turns back
  function untry() {
    if (ui.tryOn) { say(t(ui.tryOn.school ? (session.me?.student?.school ? 'look.lockedSchool' : 'look.noSchoolYet') : 'look.locked', { name: ui.tryOn.name }), 'locked_3d'); ui.tryOn = null; }
  }
  // Back (or Escape) in the editor: to the list; a change not saved asks first (iOS's "Discard changes?")
  async function unedit() {
    if (dirty()) {
      const o = overlays.find((x) => x.id === etok);
      if (o) o.closing = false;
      if (!(await sheets.ask({ title: t('look.discard'), ok: t('look.discardGo'), cancel: t('common.cancel'), danger: true })) || !edit) return;
    }
    haptic.soft();
    ui.tryOn = null; ui.look = null;
    removeOverlay(etok); etok = 0;
    swapEdit(false);
  }
  // the check in the editor: saved at once (back on a failure), and the settings close onto the profile
  function save() {
    const was = session.me, next = ui.look;
    if (was && next && dirty()) {
      session.me = { ...was, ...next };
      api.updateMe(next).then((m) => (session.me = m), () => { session.me = was; haptic.error(); say(t('common.error'), 'warning_3d'); });
    }
    ui.look = null;
    removeOverlay(etok); etok = 0;
    close(tok, true);
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
    untry();
    icons(false, q);
    fades = all('[data-unit]').map((u) => u.animate(q ? [{ opacity: 1 }, { opacity: 0 }] : [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(8px)' }],
      { duration: q ? 150 : 140, easing: IN, fill: 'forwards' }));
    setTimeout(() => { if (r === run) swapOut(); }, q ? 150 : 140);
  }
  // always back at the top: the lanyard stays put, or slides down from under the capsule when the list was scrolled
  function swapOut() {
    const q = calm(), y0 = top();
    set = false; edit = false; fades = [];
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
    edit = false; ui.look = null; ui.tryOn = null;
    if (etok) { removeOverlay(etok); etok = 0; }
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
    {#if me?.student && (staff || sg || hd)}
      <!-- the panels (the only staff things on a normal tab), each with what waits for it: the admin's (a moderator's
        is the content part) and the Student Government's (its queue of appeals) -->
      <span class="shield" bind:this={shield}>
        {#if staff}<button class="gear" onclick={() => { haptic.tap(); sheets.admin(); }} aria-label={t('me.admin')}><ShieldCheck size={19} />{#if asks}<b class="cnt num">{asks}</b>{/if}</button>{/if}
        {#if sg}<button class="gear" onclick={() => { haptic.tap(); sheets.sgQueue(); }} aria-label={t('apl.sg')}><Landmark size={19} />{#if sgNew}<b class="cnt num">{sgNew}</b>{/if}</button>{/if}
        {#if hd}<button class="gear" onclick={() => { haptic.tap(); sheets.helpQueue(); }} aria-label={t('ask.queue')}><MessageCircleQuestion size={19} />{#if hdNew}<b class="cnt num">{hdNew}</b>{/if}</button>{/if}
      </span>
    {/if}
    <!-- settings in place; in them, the check that ends them (a tap while the motion runs is ignored) -->
    <button class="gear" class:done={phase === 'entering' || phase === 'on'} bind:this={gear} aria-label={t(phase === 'entering' || phase === 'on' ? 'me.done' : 'me.settings')}
      onclick={() => { if (phase === 'idle') enter(); else if (phase === 'on') { if (edit) save(); else close(tok, true); } }}>
      <span class="gi"><SettingsIcon size={19} /></span><span class="gi c"><Check size={20} strokeWidth={2.4} /></span></button>
  </div>
  {#if me?.student}
    <!-- my photo: settings, or in them the photo's menu at it -->
    {#if shown}<div class="lift" bind:this={lift}><Hero p={shown} qr={me.qr} live={ui.tab === 'profile'}
      onphoto={(el) => { if (phase === 'idle') enter(); else if (phase === 'on' && !edit) list?.photoMenu(el); }} /></div>{/if}
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
  {#if rest}
  {#if me?.student && !me.student.ms}
    <!-- not confirmed with the KBTU account yet: in sight on the profile, not only in the settings -->
    <div data-away><Group footnote={t('me.msText')}>
      <Row title={t('me.msTitle')} accessory="chevron" onclick={() => { haptic.tap(); sheets.login(); }}>{#snippet lead()}
        <svg viewBox="0 0 21 21" width="24" height="24" aria-hidden="true"><path fill="#f25022" d="M0 0h10v10H0z"/><path fill="#7fba00" d="M11 0h10v10H11z"/><path fill="#00a4ef" d="M0 11h10v10H0z"/><path fill="#ffb900" d="M11 11h10v10H11z"/></svg>{/snippet}</Row>
    </Group></div>
  {/if}
  {#if me?.deleteAt}
    <!-- the week to change my mind (DeleteSheet), with the way back -->
    <div data-away><Notice tone="danger" text={t('del.soon', { date: dayMonth(me.deleteAt) })} action={{ label: t('del.keep'), onclick: keepAccount }} /></div>
  {/if}

  {#if me?.student}
    <!-- my people: friends (a few faces, how many, the requests waiting) and my invite -->
    <div data-away><Group>
      <Row title={t('page.friends')} subtitle={friends.length ? tn('fr.count', friends.length) : t('fr.add')} count={asked} accessory="chevron" onclick={() => { haptic.tap(); sheets.friends(); }}>
        {#snippet lead()}<span class="ppl"><UsersRound size={20} strokeWidth={2} /></span>{/snippet}
        {#snippet detail()}<span class="faces" aria-hidden="true">{#each faces.slice(0, 3) as r (r.person.id)}<span class="face"><Avatar person={r.person} size={26} tappable={false} /></span>{/each}</span>{/snippet}
      </Row>
      {#if me.referrals}<Invite r={me.referrals} ach={card?.awards.achievements.find((a) => a.code === 'referral')} />{/if}
    </Group></div>
  {/if}

  <!-- the term: a strip of its weeks (mockup v24), the academic calendar behind it; out of term the row
       names what comes next. Under it KBTU's psychologist and the anthem -->
  <div data-away><Group>
    {#if sem}
      <!-- v25: one track with the term filled to this week and a glowing dot on it,
           the midterm a gold band, the exams red at the end; the next calendar day its own row, never cut -->
      {@const at = (w: number) => `${((w - 0.5) / (sem.weeks + 1)) * 100}%`}
      <!-- engine: Group takes Rows alone; kb-row (Row's own mark) gives the strip the line under it -->
      <button class="sem kb-row" onclick={() => sheets.academic()}>
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
      {#if up}<Row icon={CalendarDays} title={nameOf(up)} subtitle={whenOf(up)} accessory="chevron" onclick={() => sheets.academic()} />{/if}
    {:else}
      <Row icon={CalendarDays} title={t('acad.title')} subtitle={up ? `${nameOf(up)} · ${whenOf(up)}` : t(terms === MASTER ? 'acad.subM' : 'acad.sub')} accessory="chevron" onclick={() => sheets.academic()} />
    {/if}
    <!-- KBTU's psychologist: one quiet row, a small button to their own booking page (nothing else) -->
    <Row icon={MessageCircleHeart} title={t('psy.kbtu')}>{#snippet trailing()}
      <Button kind="secondary" size="s" onclick={() => openLink(PSYCHOLOGIST)}><span class="bk">{t('me.psychBook')}<ArrowUpRight size={14} strokeWidth={2.4} /></span></Button>{/snippet}</Row>
    <!-- the check-in page lives in Studio; here only for whom Studio doesn't lead there (a door handed over, the app's
         admin, while a session is open: server account.me) and a helper's own QR -->
    {#if session.me?.bigScreen === 'qr' || (session.me?.bigScreen === 'pair' && !session.me.memberships.some((m) => may(m, 'events')))}<Row icon={MonitorUp} title={t('scr.page')} accessory="chevron" onclick={() => sheets.bigScreen()} />{/if}
    <!-- KBTU's anthem: the words and the song (the Oct 31 initiation's card on Afisha, here for good) -->
    <Row icon={Music} title={t('anthem.title')} accessory="chevron" onclick={() => sheets.anthem()} />
    <!-- appeals to the Student Government (APPEALS): their entry is the Forum tab's card under the composer (owner, Nov 11);
         here only for a person without that tab, so nobody loses it (SG's queue is its panel, top right) -->
    {#if session.me?.appeals && !session.channel}<Row icon={Megaphone} title={t('apl.row')} accessory="chevron" onclick={() => { haptic.tap(); sheets.appeals(); }} />{/if}
  </Group></div>

  <AppCard />
  {/if}
  <!-- last before the tail, so no block's stagger delay shifts -->
  <!-- a failure inside the list shows itself instead of a blank page (Nov 2: Settings came up empty on phones) -->
  {#if set && List}<svelte:boundary onerror={(e) => console.error(e)}><List bind:this={list} editing={edit} onlanyard={lanyard} />
    {#snippet failed(error, retry)}<p class="t-foot crash">{String((error as Error)?.message ?? error).slice(0, 300)} <button class="t-foot" onclick={retry}>↻</button></p>{/snippet}
  </svelte:boundary>{/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: 16px; }
  .page > :global(*) { flex-shrink: 0; }
  /* settings in place: what leaves is gone after the swap; the panels' buttons step aside; no taps while a fade runs */
  .page.set :global([data-away]) { display: none; }
  .shield { display: flex; gap: 8px; }
  .mode .shield { opacity: 0; pointer-events: none; }
  .hold { pointer-events: none; }


  .guest { display: flex; flex-direction: column; gap: 12px; padding: 22px 18px 18px; border-radius: var(--r-xl); background: radial-gradient(90% 80% at 20% 0%, rgba(124, 77, 255, 0.55), transparent 60%), linear-gradient(160deg, #2443B8, #101633); color: #fff; }
  .guest p { color: rgba(255, 255, 255, 0.82); }
  .failed { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 24px 18px; text-align: center; }
  .failed p { color: var(--text-2); }
  .mark { color: #fff; width: 64px; height: 64px; border-radius: 20px; background: rgba(255, 255, 255, 0.14); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); }

  /* my friends: a quiet accent mark the medal's size, a few faces overlapping before the row's end */
  .ppl { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 50%; color: var(--accent-text); background: var(--accent-soft); }
  .faces { display: flex; padding-left: 8px; }
  .face { display: flex; margin-left: -8px; border-radius: 50%; box-shadow: 0 0 0 2px var(--surface-solid); }
  .face :global(.seal) { display: none; }
  /* the shield and the gear: in the lanyard's gap right of its strap */
  .gears { position: absolute; top: calc(var(--page-top) - 6px); right: var(--gutter); z-index: 1; display: flex; gap: 8px; }
  /* a guest's gear sits over the sign-in card's corner: in it, on its glass */
  /* 320 px with all three (shield, SG, gear): clear of the strap */
  @media (max-width: 340px) { .gears, .shield { gap: 6px; } }
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

  /* the term's strip of weeks, the first block of its group (mockup v24) */
  .sem { display: flex; flex-direction: column; gap: 12px; padding: 16px 16px 14px; text-align: left; }
  /* a <button> doesn't stretch its flex children on older iOS WebKit: the track had no width and every label sat on the
     left ("3midterms", Oct 31) */
  .sem > * { width: 100%; }
  .sem-h { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .sem-h b { font: 700 var(--fs-t3)/1.15 var(--font-display); letter-spacing: -0.02em; color: var(--text); }
  @media (max-width: 359px) { .sem-h b { font-size: 17px; white-space: nowrap; } } /* 320 px: the week on one line beside what's left */
  .left { flex: none; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .track { position: relative; height: 10px; margin: 6px 0 2px; border-radius: 5px; background: var(--surface-3); }
  .track i { position: absolute; top: 0; bottom: 0; border-radius: 5px; }
  .band { background: rgba(245, 177, 61, 0.38); }
  .exam { right: 0; width: calc(100% / 16); background: rgba(240, 82, 74, 0.75); }
  .fill { left: 0; background: var(--accent); }
  .dot { top: 50% !important; bottom: auto !important; width: 16px; height: 16px; translate: -50% -50%; border-radius: 50% !important;
    background: #fff; box-shadow: 0 0 0 3px var(--accent), 0 2px 6px rgba(0, 0, 0, 0.25); }
  .sem-l { position: relative; display: flex; justify-content: space-between; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .sem-l span:nth-child(2) { position: absolute; translate: -50% 0; color: var(--warning-text); }
  .sem-l span:last-child { color: var(--danger-text); }
  .bk { display: inline-flex; align-items: center; gap: 3px; } /* the word and its ↗ on one line */

  .tail { flex: none; height: calc(var(--bottom) + 12px); }
  .crash { padding: 16px; color: var(--danger-text); word-break: break-word; }
</style>
