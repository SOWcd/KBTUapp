<script lang="ts">
  // Profile → Me (owner, Oct 13: two pages, Friends | Me). Guest: the sign-in card. Student: my badge (the same hero
  // as everyone else sees), then what's coming up for me (tickets and saved; nothing when there's nothing), the
  // academic calendar and the psychological service, the app's channel and group, "still in development". Every setting
  // is behind the gear in the corner (PrefsSheet); the admin's panel is a row here.
  import Settings2 from '@lucide/svelte/icons/settings';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import Crown from '@lucide/svelte/icons/crown';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import CodeXml from '@lucide/svelte/icons/code-xml';
  import { session } from '../../lib/state/session.svelte';
  import { data, loadMyCard } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { say, ui } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api, type PersonCard } from '../../lib/api';
  import { nextUp, nameOf, whenOf, PSYCHOLOGIST } from '../../lib/academic';
  import { inner } from '../../lib/perms';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth, relDay, whenLine } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Hero from './Hero.svelte';
  import Button from '../../ui/Button.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import FeedbackCard from '../../ui/FeedbackCard.svelte';

  const up = nextUp();
  // the psychologist's nearest free hour (server: psych.py, cached; the first ask after a while may come back empty)
  let psych = $state<number | null>(null);
  $effect(() => { if (ui.tab === 'profile') untrack(() => api.psych().then((r) => (psych = r.next), () => {})); });
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
  const asks = $derived(me?.role === 'admin' ? me.counters.reports + me.counters.clubApps : 0);
  // the app's own Telegram (owner, Oct 5): news in the channel, talk in the topics group (BUGS / IDEAS / QUESTIONS)
  const TG_NEWS = 'https://t.me/KBTUappNews', TG_TALK = 'https://t.me/KBTUappTop';

  async function keepAccount() {
    try { session.me = await api.keepMe(); haptic.ok(); say(t('del.kept'), 'raising_hands_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<div class="page scroll">
  <button class="gear" class:in={!me?.student} onclick={() => { haptic.tap(); sheets.prefs(); }} aria-label={t('me.settings')}>
    <Settings2 size={20} /></button>
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
  {#if me?.student?.manual}
    <!-- signed in by hand while the portal was down (owner, Oct 16): the way to a real sign-in, always in sight -->
    <button class="verify surface" onclick={() => { haptic.tap(); sheets.login(); }}><span class="tx"><b>{t('me.verify')}</b><i class="t-foot">{t('me.verifyNote')}</i></span><ChevronRight size={18} /></button>
  {/if}
  {#if me?.deleteAt}
    <!-- the week to change my mind (DeleteSheet), with the way back -->
    <div class="soon surface"><span>{t('del.soon', { date: dayMonth(me.deleteAt) })}</span>
      <Button kind="secondary" size="s" onclick={keepAccount}>{t('del.keep')}</Button></div>
  {/if}

  {#if me?.role === 'admin'}
    <!-- the admin panel on the main screen (owner, Oct 14): the rest of my app looks like anyone's -->
    <div class="rows surface"><button class="r" onclick={() => sheets.admin()}><span class="ic"><Crown size={20} /></span>
      <span class="lb">{t('me.admin')}</span>{#if asks}<b class="cnt num">{asks}</b>{/if}<ChevronRight size={18} /></button></div>
  {/if}

  {#if me?.student && soon.length}
    <h2 class="sec t-h3">{t('me.upcoming')}</h2>
    <div class="list">{#each soon as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} onopen={e.my?.status === 'going' ? () => sheets.ticket(e.id) : undefined} />{/each}</div>
  {/if}

  <!-- the university's: its academic calendar, what's next under it (owner, Oct 7), and the psychological service
       (owner, Oct 5): quiet, but there for whoever needs it -->
  <div class="rows surface">
    <button class="r" onclick={() => sheets.academic()}><span class="ic"><CalendarDays size={20} /></span>
      <span class="lb">{t('acad.title')}<i class="sub">{up ? `${nameOf(up)} · ${whenOf(up)}` : t('acad.sub')}</i></span><ChevronRight size={18} /></button>
    <button class="r" onclick={() => openLink(PSYCHOLOGIST)}><span class="ic"><HeartHandshake size={20} /></span>
      <span class="lb">{t('me.psych')}<i class="sub">{psych ? t('me.psychNext', { when: whenLine(psych) }) : t('me.psychSub')}</i></span><ChevronRight size={18} /></button>
  </div>

  <!-- the app's own channel and group, and "still in development": out of the settings onto the main screen (owner, Oct 14) -->
  <div class="rows surface">
    <button class="r" onclick={() => openLink(TG_NEWS)}><span class="ic"><Megaphone size={20} /></span>
      <span class="lb">{t('me.tgNews')}<i class="sub">{t('me.tgNewsSub')}</i></span><ChevronRight size={18} /></button>
    <button class="r" onclick={() => openLink(TG_TALK)}><span class="ic"><MessagesSquare size={20} /></span>
      <span class="lb">{t('me.tgTalk')}<i class="sub">{t('me.tgTalkSub')}</i></span><ChevronRight size={18} /></button>
    <!-- the open code (owner, Oct 17): anyone can read it and send a change -->
    <button class="r" onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}><span class="ic"><CodeXml size={20} /></span>
      <span class="lb">GitHub<i class="sub">{t('me.githubSub')}</i></span><ChevronRight size={18} /></button>
  </div>
  <FeedbackCard />
  <div class="tail"></div>
</div>

<style>
  .sub { display: block; margin-top: 2px; font: 500 12.5px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .page { position: absolute; inset: 0; padding: calc(var(--top) + 56px) var(--gutter) 0; background: var(--glow), var(--bg); display: flex; flex-direction: column; gap: 12px; }
  .page > :global(*) { flex-shrink: 0; }

  .sec { margin-top: 10px; }
  .soon { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: var(--r-l); box-shadow: inset 0 0 0 1.5px var(--danger-soft); font: 600 14.5px/1.3 var(--font-text); }
  .soon span { flex: 1; }

  .guest { display: flex; flex-direction: column; gap: 12px; padding: 22px 18px 18px; border-radius: var(--r-xl); background: radial-gradient(90% 80% at 20% 0%, rgba(124, 77, 255, 0.55), transparent 60%), linear-gradient(160deg, #2443B8, #101633); color: #fff; }
  .guest p { color: rgba(255, 255, 255, 0.82); }
  .mark { color: #fff; width: 64px; height: 64px; border-radius: 20px; background: rgba(255, 255, 255, 0.14); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); }

  .rows { display: flex; flex-direction: column; padding: 2px 0; overflow: hidden; }
  .r { display: flex; align-items: center; gap: 12px; min-height: 54px; padding: 0 14px; text-align: left; color: var(--text-3); }
  .r + .r { box-shadow: inset 0 1px 0 var(--line); }
  button.r:active { background: var(--surface-2); }
  .ic { display: flex; color: var(--accent-text); }
  .lb { flex: 1; min-width: 0; font: 580 15.5px/1.2 var(--font-text); color: var(--text); }
  .list { display: flex; flex-direction: column; gap: 8px; }
  /* the gear (PrefsSheet): in the lanyard's gap right of its strap; on a guest's card, inside its corner */
  .gear { position: absolute; top: calc(var(--top) + 50px); right: var(--gutter); z-index: 1; width: 36px; height: 36px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; background: var(--surface); box-shadow: var(--shadow-card); color: var(--text-2); }
  .gear:active { transform: scale(0.92); }
  .gear.in { top: calc(var(--top) + 70px); right: calc(var(--gutter) + 14px); background: rgba(255, 255, 255, 0.14); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); color: #fff; }
  .cnt { min-width: 22px; height: 22px; padding: 0 7px; border-radius: 11px; background: var(--danger); color: #fff; font: 700 12.5px/22px var(--font-text); text-align: center; }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
  .verify { display: flex; align-items: center; gap: 12px; width: 100%; padding: 14px 16px; margin-bottom: 12px; border-radius: var(--r-l); text-align: left; box-shadow: inset 0 0 0 1.5px var(--warning); }
  .verify .tx { flex: 1; display: flex; flex-direction: column; gap: 3px; }
  .verify b { font: 650 16px/1.25 var(--font-text); }
  .verify i { font-style: normal; }
</style>
