<script lang="ts">
  // Afisha, one screen, in Luma's manner (owner, Nov 2: mock A with B's covers on top). The date and Today with a quiet
  // pill (the assistant, "In a row"), the news circles; "Your events": big covers swiped sideways, the next one peeking
  // in (the events I'm going to this week, their Ticket and Route on the cover), the class on now or next among them
  // as a card of its own; then "Events" over its grey count, the featured post, and the days ("Tomorrow / Tuesday"):
  // rows with a square cover, the club, a bold title, time and place with thin icons, classes as slim rows in time
  // order between them (one row per subject block, lib/classes.ts), hairlines inset to the text. No date strip
  // (owner, Oct 24: people scroll); the headers don't stick (a slab mid-screen over the rows).
  import Clock from '@lucide/svelte/icons/clock';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import MapIcon from '@lucide/svelte/icons/map';
  import Play from '@lucide/svelte/icons/play';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import CalendarCheck from '@lucide/svelte/icons/calendar-check';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { onMount } from 'svelte';
  import type { ClassItem, EventCard } from '../../lib/api';
  import { data, skipped, classKey, skipClass, prefetchEvent } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { ui } from '../../lib/state/ui.svelte';
  import { t, tn, money, placeOf, subjectOf, friendsLine } from '../../lib/i18n/index.svelte';
  import { shortSubject, lessonKind } from '../../lib/i18n/subjects';
  import { dayNo, nowTs, parts, weekday, dayMonth, OFFSET, soon, time, dateInput } from '../../lib/time';
  import { classesOn, classesLeft } from '../../lib/classes';
  import { noClasses } from '../../lib/academic';
  import { floorOf, atDorm, DORM_2GIS, atBldg2, bldg2Room, BLDG2_2GIS } from '../../lib/map';
  import { openLink } from '../../lib/tg';
  import { tagName } from '../../lib/posts';
  import { nameOf, shortOf } from '../../lib/short';
  import { inner } from '../../lib/perms';
  import Poster from '../../ui/Poster.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Tag from '../../ui/Tag.svelte';
  import TwoGisMark from '../../ui/TwoGisMark.svelte';
  import { fitTitle, largeTitle } from '../../ui/title';
  import StoryRow from './StoryRow.svelte';

  let openPost = $state(false);

  // the clock: a minute is enough for "21 min left"; moves on at midnight (the app can stay open overnight)
  let now = $state(nowTs());
  onMount(() => { const id = setInterval(() => (now = nowTs()), 30_000); return () => clearInterval(id); });
  const today = $derived(dayNo(now));
  const dayTs = (d: number) => d * 86400 - OFFSET; // start of local day d as a UTC timestamp
  const endOf = (e: EventCard) => e.endsAt ?? e.startsAt + 3 * 3600;

  const featured = $derived(data.posts.find((p) => p.featured));
  const shown = $derived(data.events.filter((e) => e.status !== 'cancelled'));

  type Item = { key: string; at: number } & ({ c: ClassItem; end: number } | { e: EventCard });
  const classesOf = (d: number): Item[] => classesOn(data.schedule, d).map((x) => ({ key: classKey(d, x.c), at: x.b, end: x.e, c: x.c }));
  const days = $derived.by(() => {
    const by = new Map<number, Item[]>();
    for (const e of data.events) { const d = dayNo(e.startsAt); if (d < today) continue; if (!by.has(d)) by.set(d, []); by.get(d)!.push({ key: 'e' + e.id, at: e.startsAt, e }); }
    // the coming week's class days too (the owner missed his Wednesday), later only event days; today's classes stay
    // here too: their rows are where "I won't go" is tapped (and taken back)
    const week = Array.from({ length: 7 }, (_, i) => today + i).filter((d) => d === today || data.schedule.some((c) => c.weekday === (parts(dayTs(d) + 12 * 3600).wd || 7)));
    const wanted = [...new Set([...week, ...by.keys()])].sort((a, b) => a - b);
    // a class before an event that starts at the same minute: you leave the class for it
    return wanted.map((d) => ({ d, items: [...classesOf(d), ...(by.get(d) ?? [])].sort((a, b) => a.at - b.at || ('c' in a ? -1 : 1)) }));
  });
  const weekCount = $derived(shown.filter((e) => endOf(e) > now && dayNo(e.startsAt) < today + 7).length);
  // a day off by the academic calendar on a class day: say why the classes are gone
  const offToday = $derived(noClasses(dateInput(now)) && data.schedule.some((c) => c.weekday === (parts(now).wd || 7)));

  // "Your events": the events I'm going to this week, and the class on now or next; the class goes first while it's on
  // or within the hour, else after the nearest event (most students have no timetable yet: PLAN 49)
  const going = $derived(shown.filter((e) => e.my?.status === 'going' && endOf(e) > now && e.startsAt - now < 7 * 86400).sort((a, b) => a.startsAt - b.startsAt));
  const left = $derived(classesLeft(data.schedule, now).filter((x) => !skipped.has(classKey(today, x.c))));
  const cur = $derived(left[0]);
  const onNow = $derived(!!cur && cur.b <= now);
  const classAt = $derived(!cur ? -1 : onNow || cur.b - now <= 3600 || !going.length ? 0 : 1);
  const cards = $derived.by<(EventCard | null)[]>(() => { const l: (EventCard | null)[] = [...going]; if (classAt >= 0) l.splice(classAt, 0, null); return l; });

  function head(d: number): [string, string] {
    const w = weekday(dayTs(d) + 12 * 3600);
    if (d === today) return [t('common.today'), w];
    if (d === today + 1) return [t('common.tomorrow'), w];
    return [w.charAt(0).toUpperCase() + w.slice(1), dayMonth(dayTs(d) + 12 * 3600)];
  }
</script>

{#snippet status(e: EventCard)}
  {@const st = e.my?.status}
  {@const cancelled = e.status === 'cancelled'}
  {@const over = !cancelled && endOf(e) <= now}
  {@const live = !cancelled && !over && e.startsAt <= now}
  {@const full = e.seats != null && e.taken >= e.seats && st !== 'going' && st !== 'hold'}
  {#if e.toCheck && !cancelled}<Tag tone="warning">{t('studio.chipCheck', { n: e.toCheck })}</Tag>{/if}
  {#if cancelled}<Tag tone="danger">{t('event.cancelled')}</Tag>
  {:else if e.status === 'draft'}<Tag>{t('studio.draft')}</Tag>
  {:else if over}{#if e.my?.checkedInAt}<Tag tone="success">{t('event.attended')}</Tag>{/if}
  {:else if live}<Tag tone="success">{t('event.live')}</Tag>
  {:else if st === 'going'}<Tag tone="accent">{t('event.youGo')}</Tag>
  {:else if st === 'hold'}<Tag tone="warning">{t('event.pay', { price: money(e.price ?? 0) })}</Tag>
  {:else if st === 'waitlist'}<Tag tone="neutral">{t('event.notifyOn')}</Tag>
  {:else if full}<Tag tone="neutral">{t('event.full')}</Tag>
  {:else if e.guestHost}<Tag tone="neutral">{t('event.partner')}</Tag>
  {:else if e.visibility === 'members'}<Tag tone="accent">{t('event.teamOnly')}</Tag>
  {:else if e.firstYear}<Tag tone="warning">{t('event.firstYear')}</Tag>{/if}
  {#if e.friends.length && !cancelled}
    <span class="fr"><span class="av">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={18} tappable={false} />{/each}</span>
      <span class="ellipsis">{friendsLine(e.friends.map((f) => f.name), over)}</span></span>
  {/if}
{/snippet}

<div class="page scroll">
  <header class="hd">
    <span><p class="kick">{weekday(dayTs(today) + 12 * 3600)}, {dayMonth(dayTs(today) + 12 * 3600)}</p>
      <h1 class="ttl" use:fitTitle use:largeTitle={'afisha'}>{t('common.today')}</h1></span>
    <!-- Luma's "+ / bell" pill: the assistant (with the forum's switch) and the Feed full screen -->
    {#if session.board || shown.length}
      <span class="pill">
        {#if session.board}<button onclick={() => sheets.assistant()} aria-label={t('as.ask')}><Sparkles size={19} strokeWidth={1.9} /></button>{/if}
        {#if shown.length}<button onclick={() => sheets.feed()} aria-label={t('list.inRow')}><Play size={17} strokeWidth={2} fill="currentColor" /></button>{/if}
      </span>
    {/if}
  </header>
  <StoryRow />
  {#if offToday}<p class="off t-foot">{t('list.dayOff')}</p>{/if}

  <h2 class="sec">{t('list.yours')}</h2>
  {#if cards.length}
    <div class="heroes" class:one={cards.length === 1}>
      {#each cards as e (e?.id ?? 'class')}
        {#if e}
          <!-- an event I'm going to: its cover, how soon, the way there and the ticket -->
          <section class="hero" style="--c:{e.color ?? e.tint}">
            <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
            <Poster item={e} big radius={0} />
            <div class="shade"></div>
            <div class="hero-tx">
              <span class="when num">{soon(e.startsAt, now)} · {time(e.startsAt)}</span>
              <b class="clamp-2">{e.title}</b>
              <span class="where ellipsis">{placeOf(e.place)} · {shortOf(e.org)}</span>
              <!-- solid tinted, not glass: base.css keeps glass for what floats over the page (as the Feed's posters) -->
              <span class="acts">
                <button onclick={() => sheets.ticket(e.id)}><QrCode size={17} />{t('event.ticket')}</button>
                {#if floorOf(e.place) != null}<button onclick={() => sheets.map(e.place)}><MapPin size={17} />{t('route.open')}</button>{/if}
              </span>
            </div>
          </section>
        {:else if cur}
          {@const room = cur.c.room}
          {@const lk = lessonKind(cur.c.kind)}
          <!-- the class on now or next: its room big, what's left of it, the rest of today -->
          <section class="hero now">
            <button class="hit" onclick={() => sheets.week()} aria-label={t('sched.weekTitle')}></button>
            <div class="now-m">
              {#if room}{@const rl = atDorm(room) ? t('list.dorm') : atBldg2(room) ? bldg2Room(room) || room : room}<span class="rm"><small>{t('list.room')}</small><b class="num ellipsis" class:sm={rl.length > 4}>{rl}</b></span>{/if}
              <span class="now-t"><small class:live={onNow}><i></i>{onNow ? t('list.nowUntil', { time: cur.c.ends }) : soon(cur.b, now)}</small>
                <b class="clamp-2">{subjectOf(cur.c)}</b>
                <span>{[lk ? t(`list.kind.${lk}Long`) : cur.c.kind, cur.c.teacher].filter(Boolean).join(' · ')}</span></span>
            </div>
            {#if onNow}
              <div class="bar"><i style="width:{Math.min(100, ((now - cur.b) / Math.max(60, cur.e - cur.b)) * 100)}%"></i></div>
              <div class="now-f num"><span>{t('list.minLeft', { n: Math.max(1, Math.ceil((cur.e - now) / 60)) })}</span><span>{cur.c.begins}–{cur.c.ends}</span></div>
            {/if}
            {#if left.length > 1}
              <div class="ups">
                {#each left.slice(1, 3) as x (classKey(today, x.c))}
                  <div class="up"><time class="num">{x.c.begins}</time><span class="ellipsis">{subjectOf(x.c)}</span>{#if x.c.room}<em class="num ellipsis">{x.c.room}</em>{/if}</div>
                {/each}
              </div>
            {/if}
            {#if room && floorOf(room) != null}<span class="acts"><button class="soft" onclick={() => sheets.map(room)}><MapPin size={17} />{t('route.open')}</button></span>{/if}
          </section>
        {/if}
      {/each}
    </div>
  {:else}
    <!-- Luma's empty state: a soft tile, one sentence that names the way on -->
    <div class="empty"><span class="ic"><CalendarCheck size={26} strokeWidth={1.75} /></span><p>{t('list.yoursNone')}</p></div>
  {/if}

  <h2 class="sec two">{t('list.title')}<span class="num">{tn('list.week', weekCount)}</span></h2>

  {#if featured}
    <button class="pin" onclick={() => (openPost = !openPost)}>
      <span class="pin-top"><Tag tone="warning">{tagName(featured.tag) ?? t('common.more')}</Tag><span class="ellipsis">{nameOf(featured.org)}</span></span>
      <b>{featured.title}</b>
      <span class="pin-b" class:clamp-2={!openPost}>{featured.body}</span>
    </button>
  {/if}

  {#each days as day (day.d)}
    <!-- no timetable yet: today's place asks for it (PLAN 26) instead of a "free day" we can't know (onboarding plan) -->
    {@const ask = day.d === today && !!session.me?.student && !data.schedule.length}
    {#if day.items.length || ask || data.schedule.length}
      {@const [a, b] = head(day.d)}
      <h3 class="dh">{a}<span>&nbsp;/ {b}</span></h3>
      {#if ask}
        <button class="tile" onclick={() => sheets.schedHowTo()}>
          <span class="ic sm"><CalendarPlus size={20} strokeWidth={1.75} /></span>
          <span class="tt"><b>{t('sched.cardTitle')}</b><small>{t('sched.cardSub')}</small></span>
          <ChevronRight size={18} />
        </button>
      {/if}
      <div class="list">
        {#each day.items as it (it.key)}
          {#if 'c' in it}
            {@const hours = Math.round((it.end - it.at) / 3600)}
            {@const k = lessonKind(it.c.kind)}
            <!-- a class: a slim row, its times where the covers are; a tap: "I won't go" (the capsule leaves it out), or back -->
            <div class="row cl" class:past={it.end < now} class:skip={skipped.has(it.key)} role="button" tabindex="0"
                 onclick={(ev) => { if (!(ev.target as HTMLElement).closest('.cl-r')) void skipClass(it.key, it.c); }} onkeydown={(ev) => ev.key === 'Enter' && skipClass(it.key, it.c)}>
              <span class="cl-t num"><b>{it.c.begins}</b>{it.c.ends}</span>
              <span class="cl-s"><b class="ellipsis">{shortSubject(subjectOf(it.c))}</b>
                <small class="ellipsis">{#if k}<i class="cl-k {k}">{t(`list.kind.${k}Long`)}</i>{:else if it.c.kind}{it.c.kind}{/if}{#if hours > 1}<span class="num"> · ×{hours}</span>{/if}{#if skipped.has(it.key)} · {t('skip.tag')}{/if}</small></span>
              {#if floorOf(it.c.room) != null}<button class="cl-r on" onclick={() => sheets.map(it.c.room!)}><span class="ellipsis">{it.c.room}</span><MapIcon size={13} /></button>
              {:else if atBldg2(it.c.room)}<button class="cl-r on gis" title={it.c.room} onclick={() => openLink(BLDG2_2GIS)}><span class="ellipsis">{[bldg2Room(it.c.room!), t('list.bldg2')].filter(Boolean).join(' · ')}</span><TwoGisMark size={14} /></button>
              {:else if atDorm(it.c.room)}<button class="cl-r on gis" title={it.c.room} onclick={() => openLink(DORM_2GIS)}>{t('list.dorm')}<TwoGisMark size={14} /></button>
              {:else if it.c.room}<span class="cl-r ellipsis">{it.c.room}</span>{/if}
            </div>
          {:else}
            {@const e = it.e}
            <!-- an event: Luma's row; a club's own event shows its team mark by the club -->
            <div class="row" class:cancelled={e.status === 'cancelled'}>
              <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
              <Poster item={e} size={76} radius={16} dim={e.status === 'cancelled'} />
              <span class="tx">
                <span class="org"><OrgLogo org={e.org} size={16} /><span class="ellipsis">{nameOf(e.org)}</span>{#if inner(e)}<UsersRound size={13} strokeWidth={2.2} />{/if}{#if e.saved && e.status !== 'cancelled'}<Bookmark class="sv" size={13} strokeWidth={2.4} fill="currentColor" aria-label={t('event.saved')} />{/if}</span>
                <b class="clamp-2 title">{e.title}</b>
                <span class="meta num">
                  <span><Clock size={14} strokeWidth={1.75} />{time(e.startsAt)}</span>
                  <span class="ellipsis"><MapPin size={14} strokeWidth={1.75} />{placeOf(e.place)}</span>
                  {#if e.price}<span>{money(e.price)}</span>{/if}
                </span>
                <span class="sub">{@render status(e)}</span>
              </span>
            </div>
          {/if}
        {/each}
      </div>
      {#if !day.items.length && !ask}<p class="free t-foot">{t('list.freeDay')}</p>{/if}
    {/if}
  {/each}

  {#if data.eventsReady && shown.length < 6}
    <!-- the first weeks of the pilot: a short list should read as "more is coming", not as an empty app -->
    <div class="empty more">
      <span class="ic"><Sparkles size={26} strokeWidth={1.75} /></span>
      <span class="tt"><b>{t('list.moreSoon')}</b><p>{t('list.moreSoonText')}</p>
        <button onclick={() => { ui.tab = 'club'; ui.allClubs = true; }}>{t('list.toClubs')}<ChevronRight size={16} /></button></span>
    </div>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
  .kick { font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); margin-bottom: 2px; }
  .kick::first-letter { text-transform: uppercase; }
  .ttl { font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .pill { flex: none; display: flex; height: var(--ctl-m); padding: 0 4px; border-radius: var(--r-full); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); }
  .pill button { width: 42px; display: grid; place-items: center; color: var(--text); transition: transform var(--t-fast) var(--ease); }
  .pill button:active { transform: scale(0.88); }
  .off { margin: 12px 4px 0; color: var(--text-2); }

  /* Luma's section titles: bold, the second line grey at the same size */
  .sec { margin: 26px 0 12px; font: 780 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.03em; }
  .sec.two { display: flex; flex-direction: column; margin-top: 34px; }
  .sec.two span { color: var(--text-3); font-weight: 720; }
  .dh { margin: 22px 0 6px; font: 720 var(--fs-row)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .dh span { color: var(--text-3); font-weight: 600; }
  .dh span::first-letter { text-transform: none; }
  .hit { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }

  /* "Your events": covers side by side, the next one peeks in */
  .heroes { display: flex; gap: 10px; overflow-x: auto; scroll-snap-type: x mandatory; margin: 0 calc(-1 * var(--gutter)); padding: 0 var(--gutter); scroll-padding: 0 var(--gutter); scrollbar-width: none; }
  .heroes::-webkit-scrollbar { display: none; }
  .hero { position: relative; flex: none; width: calc(100% - 28px); min-height: 300px; scroll-snap-align: start; overflow: hidden; border-radius: var(--r-xl);
    box-shadow: inset 0 0 0 1px var(--line), 0 18px 36px -24px var(--c, transparent); transition: transform var(--t-fast) var(--ease); }
  .hero:has(> .hit:active) { transform: scale(0.985); }
  .heroes.one .hero { width: 100%; }
  .hero :global(.poster) { position: absolute; inset: 0; }
  .hero :global(.poster .emoji) { width: 104px; height: 104px; margin-bottom: 38%; filter: drop-shadow(0 16px 18px rgba(0, 0, 0, 0.4)); }
  .shade { position: absolute; inset: 35% 0 0; background: linear-gradient(transparent, rgba(0, 0, 0, 0.64)); pointer-events: none; }
  .hero-tx { position: absolute; left: 0; right: 0; bottom: 0; display: flex; flex-direction: column; gap: 3px; padding: 16px; color: var(--on-accent); pointer-events: none; }
  .when { font: 650 var(--fs-sub)/1.2 var(--font-text); opacity: 0.85; }
  .hero-tx b { font: 780 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.025em; }
  .where { font: 520 var(--fs-sub)/1.3 var(--font-text); opacity: 0.75; }
  .acts { position: relative; z-index: 2; display: flex; gap: 8px; margin-top: 12px; pointer-events: auto; }
  .acts button { display: inline-flex; align-items: center; gap: 6px; height: var(--btn-m); padding: 0 16px; border-radius: var(--r-full); color: var(--on-accent);
    background: rgba(20, 22, 32, 0.42); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16); font: 650 var(--fs-body)/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .acts button:active { transform: scale(0.95); }
  .acts button.soft { background: var(--accent-soft); box-shadow: none; color: var(--accent-text); }

  /* the class card: calm, the accent's glow in its corner */
  .now { display: flex; flex-direction: column; gap: 12px; padding: 16px; background: radial-gradient(90% 80% at 0% 0%, var(--accent-soft), transparent 60%), var(--surface); }
  .now > :not(.hit) { position: relative; pointer-events: none; }
  .now > .acts { pointer-events: auto; margin-top: auto; }
  .now-m { display: flex; gap: 14px; align-items: flex-start; }
  .rm { flex: none; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 72px; height: 72px; border-radius: var(--r-l); background: var(--text); color: var(--bg); }
  .rm small { font: 600 var(--fs-micro)/1 var(--font-text); opacity: 0.6; }
  .rm b { max-width: 64px; font: 800 var(--fs-t3)/1.1 var(--font-display); letter-spacing: -0.03em; }
  .rm b.sm { font-size: var(--fs-body); } /* the dorm, a long room: whole, not cut to one letter */
  .now-t { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .now-t small { display: flex; align-items: center; gap: 6px; font: 650 var(--fs-cap)/1.2 var(--font-text); color: var(--accent-text); }
  .now-t small i { display: none; width: 7px; height: 7px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .now-t small.live i { display: block; }
  .now-t b { font: 750 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.02em; }
  .now-t span { font: 500 var(--fs-sub)/1.25 var(--font-text); color: var(--text-3); }
  .bar { height: 5px; border-radius: 3px; background: var(--surface-3); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: inherit; background: var(--grad-accent); }
  .now-f { display: flex; justify-content: space-between; margin-top: -6px; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-2); }
  .ups { display: flex; flex-direction: column; }
  .up { display: flex; align-items: center; gap: 12px; min-height: 36px; font: 600 var(--fs-body)/1.2 var(--font-text); }
  .up + .up { border-top: 0.5px solid var(--separator); }
  .up time { flex: none; width: 44px; font: 650 var(--fs-sub)/1 var(--font-text); color: var(--accent-text); }
  .up span { flex: 1; min-width: 0; }
  .up em { flex: none; max-width: 30%; font: 600 var(--fs-sub)/1 var(--font-text); font-style: normal; color: var(--text-3); }

  /* the featured post: its own card, the body folded to two lines */
  .pin { display: flex; flex-direction: column; gap: 6px; width: 100%; padding: 14px 16px; margin-bottom: 4px; border-radius: var(--r-l); background: var(--surface); text-align: left; }
  .pin-top { display: flex; align-items: center; gap: 8px; min-width: 0; font: 560 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .pin b { font: 700 var(--fs-card)/1.25 var(--font-text); }
  .pin-b { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); }

  /* the rows of a day: a hairline between them, inset to the text (Luma) */
  .list { display: flex; flex-direction: column; }
  .row { position: relative; display: flex; align-items: center; gap: 14px; padding: 12px 0; }
  .row + .row::before { content: ''; position: absolute; top: 0; left: 90px; right: 0; height: 0.5px; background: var(--separator); }
  .row :global(.poster) { box-shadow: inset 0 0 0 1px var(--line); transition: transform var(--t-fast) var(--ease); }
  .row:has(> .hit:active) :global(.poster) { transform: scale(0.96); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; pointer-events: none; }
  .tx :global(button), .tx :global(a) { pointer-events: auto; }
  .org { display: flex; align-items: center; gap: 6px; min-width: 0; font: 560 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .org :global(.logo) { box-shadow: 0 0 0 1px var(--line); }
  .org :global(svg) { flex: none; color: var(--accent-text); }
  .org :global(.sv) { color: var(--warning-text); } /* saved: the themed amber */
  .title { font: 700 var(--fs-card)/1.22 var(--font-text); letter-spacing: -0.01em; }
  .cancelled .title { text-decoration: line-through; color: var(--text-2); }
  .meta { display: flex; flex-wrap: wrap; gap: 2px 12px; min-width: 0; font: 520 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .meta span { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
  .meta :global(svg) { flex: none; color: var(--text-3); }
  .sub { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .sub:empty { display: none; }
  .fr { display: flex; align-items: center; gap: 6px; min-width: 0; font: 520 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .av { flex: none; display: flex; }
  .av :global(.av + .av) { margin-left: -5px; }
  .av :global(.av) { box-shadow: 0 0 0 1.5px var(--bg); }

  /* a class: its times in the covers' column, the room at the row's end */
  .cl { min-height: 56px; padding: 8px 0; cursor: pointer; }
  .cl.past, .cl.skip { opacity: 0.5; }
  .cl.skip .cl-s b { text-decoration: line-through; }
  .cl-t { flex: none; width: 76px; display: flex; flex-direction: column; align-items: center; gap: 3px; font: 500 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .cl-t b { font: 680 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .cl-s { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .cl-s b { font: 620 var(--fs-body)/1.25 var(--font-text); }
  .cl-s small { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .cl-k { font-style: normal; }
  .cl-k.lecture { color: var(--accent-text); }
  .cl-k.practice { color: var(--success-text); }
  .cl-k.lab { color: var(--warning-text); }
  .cl-r { flex: none; max-width: 42%; font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  /* a room in the main building opens the map on its floor; the dorm and the second building open 2GIS */
  .cl-r.on { display: inline-flex; align-items: center; gap: 4px; height: 28px; padding: 0 10px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); }
  .cl-r.on :global(svg) { flex: none; }
  .cl-r.gis { background: var(--success-soft); color: var(--success-text); }
  .free { padding: 6px 0 0 90px; }

  /* Luma's soft tiles: an icon, a sentence */
  .empty { display: flex; align-items: center; gap: 16px; }
  .ic { flex: none; display: grid; place-items: center; width: 76px; height: 76px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-3); }
  .ic.sm { width: 44px; height: 44px; border-radius: var(--r-s); }
  .empty p { font: 540 var(--fs-body)/1.35 var(--font-text); color: var(--text-2); text-wrap: pretty; }
  .more { align-items: flex-start; margin-top: 30px; }
  .more .tt { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .more b { font: 700 var(--fs-body)/1.3 var(--font-text); }
  .more p { font-size: var(--fs-sub); }
  .more button { align-self: flex-start; display: inline-flex; align-items: center; gap: 2px; margin-top: 4px; font: 650 var(--fs-sub)/1.6 var(--font-text); color: var(--accent-text); }
  .tile { display: flex; align-items: center; gap: 14px; width: 100%; margin: 6px 0; padding: 12px 14px; border-radius: var(--r-l); background: var(--surface); text-align: left; color: var(--text-3); }
  .tile .tt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tile b { font: 650 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  .tile small { font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
