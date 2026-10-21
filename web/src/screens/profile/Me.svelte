<script lang="ts">
  // Profile → Me (owner, Oct 13: Friends | Me; Oct 21: Friends | Me | Settings, mockup v24). Guest: the sign-in card.
  // Student: my badge (the same hero as everyone else sees), then what's coming up for me (tickets and saved; nothing
  // when there's nothing), the term (a strip of its weeks, the academic calendar behind it) with KBTU's psychologist
  // under it (their own booking page, the nearest free hour from psych.py; the crisis lines always in sight), and the
  // app's card: channel, group, code, a word to the creator. The admin panel is the shield next to the pencil.
  import Pencil from '@lucide/svelte/icons/pencil';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import MessageCircleHeart from '@lucide/svelte/icons/message-circle-heart';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { data, loadMyCard } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { say, ui } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api, type PersonCard } from '../../lib/api';
  import { nextUp, nameOf, whenOf, semester, PSYCHOLOGIST } from '../../lib/academic';
  import { inner } from '../../lib/perms';
  import { t, tn, i18n } from '../../lib/i18n/index.svelte';
  import { dateInput, dayMonth, nowTs, relDay, whenLine } from '../../lib/time';
  import { onMount } from 'svelte';
  import { writeOwner } from '../../lib/feedback';
  import { haptic, on, openLink } from '../../lib/tg';
  import Hero from './Hero.svelte';
  import Button from '../../ui/Button.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  // today: Me stays mounted and the app can stay open for days, so it moves on when the app comes back
  let today = $state(dateInput(nowTs()));
  onMount(() => on('activated', () => (today = dateInput(nowTs()))));
  const up = $derived(nextUp(today)), sem = $derived(semester(today));
  // the strip's month under its first week, in the app's language
  const semFrom = $derived(sem ? new Intl.DateTimeFormat(i18n.lang, { month: 'short', timeZone: 'UTC' }).format(new Date(sem.start)).replace('.', '') : '');
  // the psychologist's nearest free hour (server: psych.py, cached; the first ask after a while may come back empty)
  let psych = $state<number | null>(null), full = $state(false);
  $effect(() => { if (ui.tab === 'profile') untrack(() => api.psych().then((r) => { psych = r.next; full = !!r.full; }, () => {})); });
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
    {#if me.role === 'admin'}
      <!-- the admin panel (owner, Oct 14), with what waits for it -->
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
       names what comes next. Under it KBTU's psychologist (owner, Oct 5; Oct 21: their own booking page, no page of
       ours) and the crisis lines, never behind a tap -->
  <div class="term surface">
    {#if sem}
      <button class="sem" onclick={() => sheets.academic()}>
        <span class="sem-h"><span><b>{t('sem.week', { n: sem.week, of: sem.weeks })}</b><i class="sub">{sem.toExams ? tn('sem.toExams', sem.toExams) : t('sem.examsNow')}</i></span>
          {#if up}<span class="chip">{nameOf(up)} · {whenOf(up)}</span>{/if}</span>
        <span class="strip" style="--n:{sem.weeks}" aria-hidden="true">
          {#each { length: sem.weeks } as _, i (i)}<i class:past={i + 1 < sem.week} class:mid={i + 1 >= sem.mid[0] && i + 1 <= sem.mid[1]} class:now={!sem.exams && i + 1 === sem.week}>{#if !sem.exams && i + 1 === sem.week}<b class="num">{sem.week}</b>{/if}</i>{/each}
          <i class="ex" class:now={sem.exams}></i>
        </span>
        <span class="sem-l"><span>{semFrom}</span><span style="left:calc(({sem.mid[0]} - 0.5) / ({sem.weeks} + 1) * 100%)">{t('sem.mid')}</span><span>{t('sem.exams')}</span></span>
      </button>
    {:else}
      <button class="r" onclick={() => sheets.academic()}>
        <span class="lb">{t('acad.title')}<i class="sub">{up ? `${nameOf(up)} · ${whenOf(up)}` : t('acad.sub')}</i></span><ChevronRight size={18} /></button>
    {/if}
    <button class="r psy" onclick={() => { haptic.tap(); openLink(PSYCHOLOGIST); }}>
      <span class="pi"><MessageCircleHeart size={22} /></span>
      <span class="lb">{t('psy.kbtu')}<i class="sub">{t(full && !psych ? 'me.psychFull' : 'me.psychSub')}</i></span>
      {#if psych}<span class="pt"><i class="sub">{t('me.psychSoon')}</i><b class="num">{whenLine(psych)}</b></span>{/if}
      <ArrowUpRight size={18} /></button>
    <!-- 150 the youth line, 1303 Almaty's mental-health centre, 111 the family line, 112 emergencies (checked at their
         sources Oct 20: telephone150.kz, cpzalmaty.kz, adilet.zan.kz) -->
    <p class="sos">{t('psy.now')}: {#each ['150', '1303', '111', '112'] as n, i (n)}{#if i}<span class="sep">·</span>{/if}<a href="tel:{n}" onclick={() => haptic.tap()}><b class="num">{n}</b>{#if n === '150' || n === '112'} {t(`sos.${n}`)}{/if}</a>{/each}</p>
  </div>

  <!-- the app itself (mockup v24: three tiles, small actions): its channel, its group, the open code (owner, Oct 17),
       and a word straight to the creator (owner, Oct 5) -->
  <div class="appc surface">
    <div class="ap-h"><span class="mk"><KbtuMark size={22} /></span><span><b>KBTU App</b><i class="sub">{t('fb.text')}</i></span></div>
    <div class="ap-t">
      <button class="apt" onclick={() => openLink(TG_NEWS)}><Megaphone size={22} /><b>{t('app.channel')}</b><small>{t('app.channelSub')}</small><span class="go">{t('app.subscribe')}</span></button>
      <button class="apt" onclick={() => openLink(TG_TALK)}><UsersRound size={22} /><b>{t('app.group')}</b><small>{t('app.groupSub')}</small><span class="go">{t('app.join')}</span></button>
      <button class="apt" onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}><GitHubMark size={22} /><b>GitHub</b><small>{t('app.codeSub')}</small><span class="go">{t('app.look')}</span></button>
    </div>
    <button class="write" onclick={writeOwner}>{t('fb.write')}</button>
  </div>
  <div class="tail"></div>
</div>

<style>
  .sub { display: block; margin-top: 2px; font: 500 12.5px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .page { position: absolute; inset: 0; padding: calc(var(--top) + 56px) var(--gutter) 0; background: var(--glow), var(--bg); display: flex; flex-direction: column; gap: 12px; }
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
  .gear { position: absolute; top: calc(var(--top) + 50px); right: var(--gutter); z-index: 1; width: 36px; height: 36px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; background: var(--surface); box-shadow: var(--shadow-card); color: var(--text-2); }
  .gear:active { transform: scale(0.92); }
  .gear.adm { right: calc(var(--gutter) + 44px); }
  .cnt { position: absolute; top: -4px; right: -6px; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: var(--danger); color: #fff; font: 700 11px/18px var(--font-text); text-align: center; }

  /* the term card: the strip of weeks, then the psychologist (mockup v24) */
  .term { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .sem { display: flex; flex-direction: column; gap: 10px; padding: 16px 16px 12px; text-align: left; }
  .sem-h { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
  .sem-h b { font: 700 var(--fs-card)/1.2 var(--font-text); color: var(--text); }
  .chip { flex: none; display: inline-flex; align-items: center; height: 26px; padding: 0 10px; border-radius: var(--r-full); background: var(--warning-soft); color: var(--warning-text); font: 650 var(--fs-cap)/1 var(--font-text); white-space: nowrap; }
  .strip { position: relative; display: grid; grid-template-columns: repeat(calc(var(--n) + 1), 1fr); gap: 3px; height: 30px; align-items: center; }
  .strip i { height: 8px; border-radius: 3px; background: var(--surface-3); }
  .strip i.past { background: linear-gradient(90deg, var(--accent), #6E8FFF); }
  .strip i.mid { background: color-mix(in srgb, var(--gold) 40%, var(--surface-3)); }
  .strip i.mid.past { background: linear-gradient(90deg, #6E8FFF, var(--gold)); }
  .strip i.ex { background: color-mix(in srgb, var(--danger) 70%, var(--surface-3)); }
  /* this week: a lens with its number, sitting on the strip */
  .strip i.now { position: relative; background: var(--accent); }
  .strip i.now b { position: absolute; left: 50%; top: 50%; translate: -50% -50%; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(circle at 35% 30%, #fff, #E6ECFF); color: #1A2C80; font: 800 13px/1 var(--font-text); font-style: italic;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 55%, transparent), 0 6px 14px -4px rgba(0, 0, 0, 0.5); }
  .sem-l { position: relative; display: flex; justify-content: space-between; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .sem-l span:nth-child(2) { position: absolute; translate: -10% 0; color: var(--warning-text); }
  .sem-l span:last-child { color: var(--danger-text); }
  .term .r { box-shadow: inset 0 1px 0 var(--line); }
  .psy { min-height: 64px; }
  .pi { display: flex; color: #FF8FB8; }
  .pt { display: flex; flex-direction: column; align-items: flex-end; gap: 1px; }
  .pt b { font: 750 var(--fs-body)/1.1 var(--font-text); color: #FF8FB8; white-space: nowrap; }
  .sos { margin: 0; padding: 0 16px 14px 50px; font: 500 var(--fs-cap)/1.4 var(--font-text); color: var(--text-3); }
  .sos a { color: var(--text-2); white-space: nowrap; }
  .sos b { font-weight: 700; }
  .sep { margin: 0 6px; }

  /* the app's card: three tiles, small actions (mockup v14/v24) */
  .appc { display: flex; flex-direction: column; gap: 12px; padding: 14px; border-radius: var(--r-l); }
  .ap-h { display: flex; gap: 12px; align-items: center; }
  .ap-h b { font: 700 var(--fs-card)/1.2 var(--font-text); }
  .mk { flex: none; display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: 13px; color: #fff; background: linear-gradient(135deg, #2A4FD6, #5B2BC0); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25); }
  .ap-t { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .apt { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 12px 10px 10px; border-radius: 14px; text-align: left; color: var(--accent-text);
    background: linear-gradient(180deg, color-mix(in srgb, var(--surface-2) 100%, transparent), var(--surface-2)); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.09), inset 0 0 0 1px var(--line); }
  .apt b { margin-top: 8px; font: 650 var(--fs-body)/1.15 var(--font-text); color: var(--text); }
  .apt small { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .apt .go { margin-top: 8px; font: 650 var(--fs-cap)/1 var(--font-text); color: var(--accent-text); }
  .write { align-self: flex-start; padding: 2px 4px; font: 620 var(--fs-sub)/1.2 var(--font-text); color: var(--accent-text); }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
</style>
