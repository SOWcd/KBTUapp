<script lang="ts">
  // Profile → Me (owner, Oct 13: Friends | Me; Oct 21: Friends | Me | Settings, mockup v24). Guest: the sign-in card.
  // Student: my badge (the same hero as everyone else sees), then what's coming up for me (tickets and saved; nothing
  // when there's nothing), the term (a strip of its weeks, the academic calendar behind it) with KBTU's psychologist
  // under it (one row, a small button to their own booking page), and the app's card (AppCard; owner, Oct 25: it stays
  // on Me, not Settings).
  // The admin panel is the shield next to the pencil.
  import Pencil from '@lucide/svelte/icons/pencil';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import MessageCircleHeart from '@lucide/svelte/icons/message-circle-heart';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import { session } from '../../lib/state/session.svelte';
  import { data, loadMyCard } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { say, ui } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api, type PersonCard } from '../../lib/api';
  import { nextUp, nameOf, whenOf, semester, PSYCHOLOGIST } from '../../lib/academic';
  import { inner } from '../../lib/perms';
  import { t, tn, i18n } from '../../lib/i18n/index.svelte';
  import { dateInput, dayMonth, nowTs, relDay } from '../../lib/time';
  import { onMount } from 'svelte';
  import { haptic, on, openLink } from '../../lib/tg';
  import Hero from './Hero.svelte';
  import Invite from './Invite.svelte';
  import AppCard from './AppCard.svelte';
  import Button from '../../ui/Button.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  // today: Me stays mounted and the app can stay open for days, so it moves on when the app comes back
  let today = $state(dateInput(nowTs()));
  onMount(() => on('activated', () => (today = dateInput(nowTs()))));
  const up = $derived(nextUp(today)), sem = $derived(semester(today));
  // the strip's month under its first week, in the app's language
  const semFrom = $derived(sem ? new Intl.DateTimeFormat(i18n.lang, { month: 'short', timeZone: 'UTC' }).format(new Date(sem.start)).replace('.', '') : '');
  const me = $derived(session.me);
  const card = $derived(data.myCard); // loaded with the app (and kept for the next launch); coming into view refreshes it
  $effect(() => { if (ui.tab === 'profile' && ui.page.profile >= 1 && me?.student) void untrack(loadMyCard); });
  // the hero shows at once from what the app already knows; numbers and awards fill in when the card arrives
  const shown = $derived<PersonCard | null>(card ? { ...card, skin: me?.skin } : (me?.student ? {
    id: me.id, name: me.name, avatar: me.avatar, founder: me.founder, no: me.no, course: me.student.course, school: me.student.school, bio: me.bio,
    attended: -1, clubs: me.memberships, past: [], showcase: [], shelf: [], awards: { achievements: [], badges: [] }, friendship: 'none', friendsSince: null, going: [], skin: me.skin,
  } : null));

  // coming up: my tickets (a club's own event has none) and what I saved, soonest first
  const soon = $derived(data.events.filter((e) => (e.my && e.my.status !== 'cancelled' && !inner(e)) || e.saved).sort((a, b) => a.startsAt - b.startsAt));
  const asks = $derived(me?.role === 'admin' || me?.role === 'moderator' ? me.counters.reports + me.counters.clubApps : 0);

  let page = $state<HTMLDivElement>();
  function look() { haptic.tap(); page?.scrollTo({ top: 0, behavior: 'smooth' }); sheets.look(); }

  async function keepAccount() {
    try { session.me = await api.keepMe(); haptic.ok(); say(t('del.kept'), 'raising_hands_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<div class="page scroll" bind:this={page}>
  {#if me?.student}
    <!-- dress my lanyard: the page goes up to it and the panel takes the nav's place below (owner, Oct 17) -->
    <button class="gear" onclick={look} aria-label={t('look.title')}><Pencil size={19} /></button>
    {#if me.role === 'admin' || me.role === 'moderator'}
      <!-- the admin panel (owner, Oct 14), with what waits for it; a moderator's is the content part (Oct 22) -->
      <button class="gear adm" onclick={() => { haptic.tap(); sheets.admin(); }} aria-label={t('me.admin')}><ShieldCheck size={19} />{#if asks}<b class="cnt num">{asks}</b>{/if}</button>
    {/if}
  {/if}
  {#if me?.student}
    {#if shown}<Hero p={shown} qr={me.qr} live={ui.tab === 'profile'} />{/if}
  {:else if session.ready}
    <section class="guest">
      <div class="mark"><KbtuMark /></div>
      <h1 class="t-h1">{t('guest.title')}</h1>
      <p class="t-body">{t('guest.text')}</p>
      <Button kind="primary" size="l" full onclick={() => sheets.login()}>{t('guest.button')}</Button>
    </section>
  {/if}
  {#if me?.student && !me.student.ms}
    <!-- not confirmed with the KBTU account yet: in sight on the profile, not only in the settings (owner, Oct 20) -->
    <button class="confirm surface" onclick={() => { haptic.tap(); sheets.login(); }}>
      <svg viewBox="0 0 21 21" width="26" height="26" aria-hidden="true"><path fill="#f25022" d="M0 0h10v10H0z"/><path fill="#7fba00" d="M11 0h10v10H11z"/><path fill="#00a4ef" d="M0 11h10v10H0z"/><path fill="#ffb900" d="M11 11h10v10H11z"/></svg>
      <span class="lb">{t('me.msTitle')}<i class="sub">{t('me.msText')}</i></span><ChevronRight size={18} /></button>
  {/if}
  {#if me?.deleteAt}
    <!-- the week to change my mind (DeleteSheet), with the way back -->
    <div class="soon surface"><span>{t('del.soon', { date: dayMonth(me.deleteAt) })}</span>
      <Button kind="secondary" size="s" onclick={keepAccount}>{t('del.keep')}</Button></div>
  {/if}

  {#if me?.student && soon.length}
    <h2 class="sec t-h3">{t('me.upcoming')}</h2>
    <div class="list">{#each soon as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} onopen={e.my?.status === 'going' ? () => sheets.ticket(e.id) : undefined} />{/each}</div>
  {/if}

  <!-- the term: a strip of its weeks (mockup v24), the academic calendar behind it (owner, Oct 7); out of term the row
       names what comes next. Under it KBTU's psychologist (owner, Oct 5) -->
  <div class="term surface">
    {#if sem}
      <!-- v25 (owner, Oct 25: "make it beautiful"): one track with the term filled to this week and a glowing dot on it,
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
    <!-- KBTU's psychologist: one quiet row, a small button to their own booking page (owner, Oct 21: nothing else) -->
    <div class="r psy"><span class="pi"><MessageCircleHeart size={18} /></span><span class="lb">{t('psy.kbtu')}</span>
      <button class="book" onclick={() => { haptic.tap(); openLink(PSYCHOLOGIST); }}>{t('me.psychBook')}<ArrowUpRight size={14} strokeWidth={2.4} /></button></div>
  </div>

  {#if me?.referrals}<Invite r={me.referrals} />{/if}
  <AppCard />
  <div class="tail"></div>
</div>

<style>
  .sub { display: block; margin-top: 2px; font: 500 12.5px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: 12px; }
  .page > :global(*) { flex-shrink: 0; }

  .sec { margin-top: 10px; }
  .confirm { display: flex; align-items: center; gap: 14px; padding: 14px; border-radius: var(--r-l); text-align: left; color: var(--text-3);
    box-shadow: inset 0 0 0 1.5px var(--accent-soft), var(--shadow-card); }
  .confirm:active { transform: scale(0.98); }
  .soon { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: var(--r-l); box-shadow: inset 0 0 0 1.5px var(--danger-soft); font: 600 14.5px/1.3 var(--font-text); }
  .soon span { flex: 1; }

  .guest { display: flex; flex-direction: column; gap: 12px; padding: 22px 18px 18px; border-radius: var(--r-xl); background: radial-gradient(90% 80% at 20% 0%, rgba(124, 77, 255, 0.55), transparent 60%), linear-gradient(160deg, #2443B8, #101633); color: #fff; }
  .guest p { color: rgba(255, 255, 255, 0.82); }
  .mark { color: #fff; width: 64px; height: 64px; border-radius: 20px; background: rgba(255, 255, 255, 0.14); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); }

  .r { display: flex; align-items: center; gap: 12px; min-height: 54px; padding: 0 16px; text-align: left; color: var(--text-3); }
  button.r:active { background: var(--surface-2); }
  .lb { flex: 1; min-width: 0; font: 580 15.5px/1.2 var(--font-text); color: var(--text); }
  .list { display: flex; flex-direction: column; gap: 8px; }
  /* the pencil and the shield: in the lanyard's gap right of its strap */
  .gear { position: absolute; top: calc(var(--page-top) - 6px); right: var(--gutter); z-index: 1; width: 36px; height: 36px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; background: var(--surface); box-shadow: var(--shadow-card); color: var(--text-2); }
  .gear::after { content: ''; position: absolute; inset: -4px; border-radius: 50%; } /* a 44 px target, the circle stays 36 */
  .gear:active { transform: scale(0.92); }
  .gear.adm { right: calc(var(--gutter) + 44px); }
  .cnt { position: absolute; top: -4px; right: -6px; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: var(--danger); color: #fff; font: 700 11px/18px var(--font-text); text-align: center; }

  /* the term card: the strip of weeks, then the psychologist (mockup v24) */
  .term { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .sem { display: flex; flex-direction: column; gap: 12px; padding: 16px 16px 14px; text-align: left; }
  .sem-h { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .sem-h b { font: 750 19px/1.15 var(--font-display); letter-spacing: -0.02em; color: var(--text); }
  .left { flex: none; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .track { position: relative; height: 10px; margin: 6px 0 2px; border-radius: 5px; background: var(--surface-3); }
  .track i { position: absolute; top: 0; bottom: 0; border-radius: 5px; }
  .band { background: color-mix(in srgb, var(--gold) 38%, transparent); }
  .exam { right: 0; width: calc(100% / 16); background: color-mix(in srgb, var(--danger) 75%, transparent); }
  .fill { left: 0; background: linear-gradient(90deg, #3B6BFF, #7C5CFF); box-shadow: 0 0 14px -2px color-mix(in srgb, #5B6BFF 70%, transparent); }
  .dot { top: 50% !important; bottom: auto !important; width: 20px; height: 20px; translate: -50% -50%; border-radius: 50% !important;
    background: radial-gradient(circle at 35% 30%, #fff, #DCE3FF); box-shadow: 0 0 0 4px color-mix(in srgb, #6B6BFF 45%, transparent), 0 0 18px 2px color-mix(in srgb, #6B6BFF 60%, transparent); }
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
  /* the psychologist in the app's own blue, its icon on a tile like the calendar row's (owner, Oct 25: no pink accent) */
  .pi { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 10px; flex: none; background: var(--accent-soft); color: var(--accent-text); }

  .tail { flex: none; height: calc(var(--bottom) + 12px); }
</style>
