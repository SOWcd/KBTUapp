<script lang="ts">
  // Events → List (the home page). Title + count, the featured post, then the
  // days as timelines: classes from the portal schedule (one slim row each; back-to-back ones of a subject
  // joined into one row with a "×2"/"×3" chip, lib/classes.ts; owner, Oct 13: tall blocks took too much room)
  // and events, in time order, so an event shows in the gap between classes where it really is. No date strip (owner, Oct 24: people
  // scroll); the headers don't stick either (a slab mid-screen over the rows, owner's screenshot).
  // Mockup v24 (owner, Oct 21): "Today" up top with a stack of live cards you swipe like Wallet passes: the event I'm
  // going to with its countdown and ticket, and the class on now or next with its room, what's left of it and the rest
  // of the day. The class card comes first while a class is on or within the hour, else the event (most students have
  // no timetable yet: PLAN 49, schedules). Neither: no stack.
  import { tagName } from '../../lib/posts';
  import MapIcon from '@lucide/svelte/icons/map';
  import { data, skipped, classKey, skipClass } from '../../lib/state/data.svelte';
  import { t, tn, subjectOf, placeOf } from '../../lib/i18n/index.svelte';
  import { shortSubject, lessonKind } from '../../lib/i18n/subjects';
  import { dayNo, nowTs, parts, weekday, dayMonth, OFFSET, at } from '../../lib/time';
  import type { ClassItem, EventCard } from '../../lib/api';
  import EventRow from '../../ui/EventRow.svelte';
  import StoryRow from './StoryRow.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { classesOn, classesLeft } from '../../lib/classes';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import { onMount } from 'svelte';
  import { soon, time } from '../../lib/time';
  import { floorOf, atDorm, DORM_2GIS, atBldg2, bldg2Room, BLDG2_2GIS } from '../../lib/map';
  import { openLink } from '../../lib/tg';
  import TwoGisMark from '../../ui/TwoGisMark.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import { ui } from '../../lib/state/ui.svelte';

  let openPost = $state(false);

  // the stack's clock: a minute is enough for "21 min left"
  let now = $state(nowTs());
  // moves on at midnight with the stack's clock (the app can stay open overnight)
  const today = $derived(dayNo(now));
  const dayTs = (d: number) => d * 86400 - OFFSET; // start of local day d as a UTC timestamp

  const featured = $derived(data.posts.find((p) => p.featured));

  type Item = { key: string; at: number } & ({ c: ClassItem; end: number } | { e: EventCard });
  const classesOf = (d: number): Item[] => classesOn(data.schedule, d).map((x) => ({ key: classKey(d, x.c), at: x.b, end: x.e, c: x.c }));

  type Day = { d: number; items: Item[] };
  const days = $derived.by<Day[]>(() => {
    const by = new Map<number, Item[]>();
    for (const e of data.events) { const d = dayNo(e.startsAt); if (!by.has(d)) by.set(d, []); by.get(d)!.push({ key: 'e' + e.id, at: e.startsAt, e }); }
    // all days: the coming week's class days too (the owner missed his Wednesday, Oct 5), later only event days
    // today's classes stay here too: their rows are where "I won't go" is tapped (and taken back), and the stack shows
    // only the next three
    const week = Array.from({ length: 7 }, (_, i) => today + i).filter((d) => d === today || data.schedule.some((c) => c.weekday === (parts(dayTs(d) + 12 * 3600).wd || 7)));
    const wanted = [...new Set([...week, ...by.keys()])].sort((a, b) => a - b);
    // a class before an event that starts at the same minute: you leave the class for it
    return wanted.map((d) => ({ d, items: [...classesOf(d), ...(by.get(d) ?? [])].sort((a, b) => a.at - b.at || ('c' in a ? -1 : 1)) }));
  });
  onMount(() => { const id = setInterval(() => (now = nowTs()), 30_000); return () => clearInterval(id); });
  const clock = $derived(now);
  const left = $derived(classesLeft(data.schedule, now).filter((x) => !skipped.has(classKey(today, x.c))));
  const going = $derived(data.events.filter((e) => e.my?.status === 'going' && e.status !== 'cancelled' && (e.endsAt ?? e.startsAt + 3 * 3600) > now && e.startsAt - now < 7 * 86400)
    .sort((a, b) => a.startsAt - b.startsAt)[0]);
  const cur = $derived(left[0]);
  const onNow = $derived(!!cur && cur.b <= now);
  const cards = $derived<('class' | 'event')[]>(cur && going ? (onNow || cur.b - now <= 3600 ? ['class', 'event'] : ['event', 'class']) : cur ? ['class'] : going ? ['event'] : []);
  let stack = $state<HTMLDivElement>();
  let shown = $state(0);
  const onStack = () => { if (stack) shown = Math.round(stack.scrollLeft / stack.clientWidth); };
  // the order flips at the hour mark: back to the first card, so the dots tell the truth
  $effect(() => { void cards.join(); if (stack) { stack.scrollLeft = 0; shown = 0; } });
  const weekCount = $derived(data.events.filter((e) => e.status !== 'cancelled' && (e.endsAt ?? e.startsAt + 3 * 3600) > now && dayNo(e.startsAt) >= today && dayNo(e.startsAt) < today + 7).length);

  function head(d: number): string {
    if (d === today) return t('common.today');
    if (d === today + 1) return t('common.tomorrow');
    const w = weekday(dayTs(d) + 12 * 3600);
    return w.charAt(0).toUpperCase() + w.slice(1);
  }
</script>

<div class="page scroll">
  <header class="hd">
    <span><p class="kick">{weekday(dayTs(today) + 12 * 3600)}, {dayMonth(dayTs(today) + 12 * 3600)}</p><h1 class="ttl">{t('common.today')}</h1></span>
  </header>
  <StoryRow />

  {#if cards.length}
    <!-- data-edge: at the stack's end the swipe moves the pages (Pager) -->
    <div class="stack" bind:this={stack} onscroll={onStack} data-edge>
      {#each cards as k (k)}
        {#if k === 'class' && cur}
          {@const room = cur.c.room}
          {@const lk = lessonKind(cur.c.kind)}
          <!-- the class on now or next: its room big, what's left of it, the rest of today -->
          <section class="card now">
            <div class="now-m" class:pr={!!room && floorOf(room) != null}>
              {#if room}<span class="rm"><small>{t('list.room')}</small><b class="num ellipsis">{atBldg2(room) ? bldg2Room(room) || room : room}</b></span>{/if}
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
                  <div class="up"><time class="num">{x.c.begins}</time><span><b class="ellipsis">{subjectOf(x.c)}</b><small>{soon(x.b, now)}</small></span>{#if x.c.room}<em class="num ellipsis">{x.c.room}</em>{/if}</div>
                {/each}
              </div>
            {/if}
            {#if room && floorOf(room) != null}<button class="go" onclick={() => sheets.map(room)}><MapPin size={15} />{t('route.open')}</button>{/if}
          </section>
        {:else if k === 'event' && going}
          <!-- the event I'm going to: how soon in words, the way there and the ticket -->
          <section class="card ev" style="--c:{going.color ?? going.tint}">
            <button class="open" onclick={() => sheets.event(going.id)} aria-label={going.title}></button>
            <div class="ev-top"><span class="ev-k"><i></i>{t('event.youGo')}</span><span class="ev-ob"><Emoji name={going.emoji ?? going.org.emoji} size={54} /></span></div>
            <b class="ev-t clamp-2">{going.title}</b>
            <span class="ev-m">{placeOf(going.place)} · {going.org.name}</span>
            <div class="ev-cd"><b class="num">{soon(going.startsAt, now)}</b><small class="num">{t('list.at', { time: time(going.startsAt) })}</small></div>
            <div class="ev-act">
              {#if floorOf(going.place) != null}<button onclick={() => sheets.map(going.place)}><MapPin size={16} />{t('route.open')}</button>{/if}
              <button onclick={() => sheets.ticket(going.id)}><QrCode size={16} />{t('event.ticket')}</button>
            </div>
          </section>
        {/if}
      {/each}
    </div>
    {#if cards.length > 1}<div class="dots" aria-hidden="true">{#each cards as k, i (k)}<i class:on={i === shown}></i>{/each}</div>{/if}
  {/if}

  <div class="evh"><h2>{t('list.title')}</h2><span class="num">{tn('list.week', weekCount)}</span></div>

  {#if featured}
    <button class="pin surface press" onclick={() => (openPost = !openPost)}>
      <span class="pin-top"><Chip tone="warning">{tagName(featured.tag) ?? t('common.more')}</Chip><span class="t-foot">{featured.org.name}</span></span>
      <span class="t-title">{featured.title}</span>
      <span class="t-body dim" class:clamp-2={!openPost}>{featured.body}</span>
    </button>
  {/if}

  {#each days as day (day.d)}
    <section class="dayblk">
      <h2 class="dh"><span class:now={day.d === today}>{head(day.d)}</span><span class="t-foot">{dayMonth(dayTs(day.d) + 12 * 3600)}</span></h2>

      {#each day.items as it (it.key)}
        {#if 'c' in it}
          {@const hours = Math.round((it.end - it.at) / 3600)}
          {@const k = lessonKind(it.c.kind)}
          <!-- a tap: "I won't go" (the capsule leaves it out), or back again -->
          <div class="cl" class:past={it.end < clock} class:skip={skipped.has(it.key)} role="button" tabindex="0"
               onclick={(ev) => { if (!(ev.target as HTMLElement).closest('.cl-r')) void skipClass(it.key, it.c); }} onkeydown={(k) => k.key === 'Enter' && skipClass(it.key, it.c)}>
            <!-- a lettered tile, its colour per kind (owner, Oct 14: the icons didn't say "lecture" or "practice") -->
            <span class="cl-k {k ?? ''}" title={it.c.kind ?? undefined}>{k ? t(`list.kind.${k}`) : ''}</span>
            <span class="cl-t num"><b>{it.c.begins}</b>–{it.c.ends}</span>
            <span class="cl-s ellipsis">{shortSubject(subjectOf(it.c))}</span>
            {#if hours > 1}<span class="cl-x num">×{hours}</span>{/if}
            {#if skipped.has(it.key)}<span class="cl-no">{t('skip.tag')}</span>{/if}
            {#if floorOf(it.c.room) != null}<button class="cl-r on" onclick={() => sheets.map(it.c.room!)}><span class="ellipsis">{it.c.room}</span><MapIcon size={13} /></button>
            {:else if atBldg2(it.c.room)}<button class="cl-r on gis" title={it.c.room} onclick={() => openLink(BLDG2_2GIS)}><span class="ellipsis">{[bldg2Room(it.c.room!), t('list.bldg2')].filter(Boolean).join(' · ')}</span><TwoGisMark size={14} /></button>
            {:else if atDorm(it.c.room)}<button class="cl-r on gis" title={it.c.room} onclick={() => openLink(DORM_2GIS)}>{t('list.dorm')}<TwoGisMark size={14} /></button>
            {:else if it.c.room}<span class="cl-r ellipsis">{it.c.room}</span>{/if}
          </div>
        {:else}
          <EventRow e={it.e} />
        {/if}
      {/each}

      {#if !day.items.length}
        <p class="empty t-foot">{t('list.freeDay')}</p>
      {/if}
    </section>
  {/each}
  {#if data.eventsReady && data.events.filter((e) => e.status !== 'cancelled').length < 6}
    <!-- the first weeks of the pilot: a short list should read as "more is coming", not as an empty app -->
    <section class="more surface">
      <Emoji name="sparkles_3d" size={36} />
      <b>{t('list.moreSoon')}</b>
      <p class="t-foot">{t('list.moreSoonText')}</p>
      <button onclick={() => { ui.tab = 'club'; ui.page.club = 0; }}>{t('list.toClubs')}</button>
    </section>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  .hd { margin-bottom: 16px; display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }

  .more { display: flex; flex-direction: column; align-items: center; gap: 6px; margin-top: 8px; padding: 20px 18px; text-align: center; }
  .more b { font: 700 16px/1.3 var(--font-text); }
  .more p { text-wrap: balance; }
  .more button { margin-top: 8px; height: 38px; padding: 0 16px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 14px/1 var(--font-text); }
  .more button:active { transform: scale(0.96); }
  .pin { display: flex; flex-direction: column; gap: 6px; width: 100%; padding: 14px 16px; margin-bottom: 18px; text-align: left; }
  .pin-top { display: flex; align-items: center; gap: 8px; }

  .dayblk { display: flex; flex-direction: column; gap: 8px; margin-bottom: 22px; }
  .dh { display: flex; align-items: baseline; gap: 8px; font: 750 19px/1.2 var(--font-display); letter-spacing: -0.025em; margin-bottom: 2px; }
  .dh .now { color: var(--accent-text); }

  /* a class: one slim row between the event cards, the way a day really goes */
  .cl { display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 8px 12px; border-radius: 14px; background: var(--surface-2); }
  .cl.past { opacity: 0.5; }
  .cl.skip { opacity: 0.55; }
  .cl.skip .cl-s { text-decoration: line-through; }
  .cl-x { flex: none; padding: 3px 6px; border-radius: var(--r-full); background: var(--surface-3); font: 700 11.5px/1 var(--font-text); color: var(--text-2); }
  .cl-no { flex: none; font: 650 12px/1 var(--font-text); color: var(--text-3); }
  .cl-k { flex: none; display: grid; place-items: center; width: 26px; height: 22px; border-radius: 7px; letter-spacing: -0.02em;
    background: var(--surface-3, var(--line)); color: var(--text-2); font: 750 12px/1 var(--font-text); }
  .cl-k.lecture { background: var(--accent-soft); color: var(--accent-text); }
  .cl-k.practice { background: var(--success-soft); color: var(--success-text); }
  .cl-k.lab { background: var(--warning-soft); color: var(--warning-text); }
  .cl-t { font: 500 13px/1 var(--font-text); color: var(--text-2); flex: none; }
  .cl-t b { font-weight: 680; color: var(--text); }
  .cl-s { flex: 1; min-width: 0; font: 560 14px/1.3 var(--font-text); }
  .cl-r { flex: none; max-width: 45%; font: 600 12.5px/1.3 var(--font-text); color: var(--text-2); }
  /* a room in the main building opens the map on its floor */
  .cl-r.on { display: inline-flex; align-items: center; gap: 4px; height: 26px; margin: -4px -6px -4px 0; padding: 0 8px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); }
  .cl-r.on :global(svg) { flex: none; } /* a hall by its name (Kunaev) is long: the name gives way, not the icon */
  /* the dorm opens in 2GIS: their mark and green, as an off-campus place on the event sheet */
  .cl-r.gis { background: rgba(25, 170, 30, 0.14); color: #19AA1E; }
  :global(:root[data-theme='light']) .cl-r.gis { color: #0F7A14; }

  /* "Today": the date small above it (mockup v24) */
  .kick { font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); margin-bottom: 2px; }
  .kick::first-letter { text-transform: uppercase; }
  .ttl { font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .evh { display: flex; align-items: baseline; justify-content: space-between; margin: 28px 4px 12px; }
  .evh h2 { font: 760 var(--fs-sec)/1.1 var(--font-display); letter-spacing: -0.025em; }
  .evh span { font: 550 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }

  /* the live stack: cards side by side, one at a time under the finger */
  .stack { display: flex; gap: 10px; overflow-x: auto; scroll-snap-type: x mandatory; margin: 0 calc(-1 * var(--gutter)); padding: 0 var(--gutter) 2px; scrollbar-width: none; scroll-padding: 0 var(--gutter); }
  .stack::-webkit-scrollbar { display: none; }
  .card { position: relative; flex: none; width: 100%; scroll-snap-align: center; overflow: hidden; border-radius: var(--r-xl); padding: 16px; display: flex; flex-direction: column; text-align: left; }
  .dots { display: flex; justify-content: center; gap: 6px; margin: 10px 0 2px; }
  .dots i { width: 6px; height: 6px; border-radius: 3px; background: var(--line-2); transition: width .4s var(--ease-spring), background-color .3s; }
  .dots i.on { width: 18px; background: var(--text); }

  /* the class card: blue, calm */
  .now { gap: 12px; background: radial-gradient(90% 80% at 0% 0%, rgba(59, 107, 255, 0.28), transparent 60%), var(--surface); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), inset 0 0 0 1px var(--line), var(--shadow-card); }
  .now-m { display: flex; gap: 14px; align-items: flex-start; }
  .now-m.pr { padding-top: 40px; } /* the Route pill sits above the subject, never over it */
  .now-m.pr .rm { margin-top: -40px; }
  .rm { flex: none; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 72px; height: 72px; border-radius: 18px; background: #fff; color: #0B1433; box-shadow: 0 10px 22px -12px rgba(0, 0, 0, 0.6); }
  .rm small { font: 600 var(--fs-micro)/1 var(--font-text); color: #4A5680; }
  .rm b { max-width: 64px; font: 800 26px/1.1 var(--font-display); letter-spacing: -0.03em; }
  .now-t { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .now-t small { display: flex; align-items: center; gap: 6px; font: 650 var(--fs-cap)/1.2 var(--font-text); color: var(--accent-text); }
  .now-t small i { display: none; width: 7px; height: 7px; border-radius: 50%; background: #46D6FF; box-shadow: 0 0 0 3px rgba(70, 214, 255, 0.25); }
  .now-t small.live i { display: block; }
  .now-t b { font: 700 var(--fs-card)/1.2 var(--font-text); }
  .now-t span { font: 500 var(--fs-sub)/1.25 var(--font-text); color: var(--text-3); }
  .bar { height: 5px; border-radius: 3px; background: var(--surface-3); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), #46D6FF); }
  .now-f { display: flex; justify-content: space-between; margin-top: -6px; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-2); }
  .ups { display: flex; flex-direction: column; margin: 0 -16px -16px; border-top: 1px solid var(--line); }
  .up { display: flex; align-items: center; gap: 12px; padding: 10px 16px; }
  .up + .up { border-top: 1px solid var(--line); }
  .up time { flex: none; width: 44px; font: 650 var(--fs-sub)/1 var(--font-text); color: var(--accent-text); }
  .up span { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .up b { font: 620 var(--fs-body)/1.2 var(--font-text); }
  .up small { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .up em { flex: none; max-width: 30%; padding: 4px 8px; border-radius: 8px; background: var(--surface-3); font: 650 var(--fs-cap)/1 var(--font-text); font-style: normal; color: var(--text-2); }
  .go { position: absolute; top: 14px; right: 14px; display: inline-flex; align-items: center; gap: 5px; height: 32px; padding: 0 12px 0 10px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 var(--fs-sub)/1 var(--font-text); }

  /* the event card: the event's own colour, its emoji floating */
  .ev { gap: 4px; color: #fff;
    background: radial-gradient(90% 70% at 85% 10%, color-mix(in srgb, var(--c) 60%, transparent), transparent 65%), radial-gradient(80% 70% at 10% 100%, color-mix(in srgb, var(--c) 35%, transparent), transparent 65%), #0F1328;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.16), inset 0 0 0 1px rgba(255, 255, 255, 0.07), 0 18px 36px -24px var(--c); }
  .ev-top { display: flex; justify-content: space-between; align-items: flex-start; }
  .ev-k { display: flex; align-items: center; gap: 6px; font: 750 var(--fs-cap)/1 var(--font-text); letter-spacing: 0.06em; text-transform: uppercase; color: #8FF0BE; }
  .ev-k i { width: 6px; height: 6px; border-radius: 50%; background: #3FD68A; }
  .ev-ob { margin: -6px -2px -10px 0; filter: drop-shadow(0 14px 16px rgba(0, 0, 0, 0.45)); animation: floaty 4s ease-in-out infinite; }
  @keyframes floaty { 50% { transform: translateY(-6px) rotate(-3deg); } }
  :global(html.lowfx) .ev-ob { animation: none; } /* power saving */
  @media (prefers-reduced-motion: reduce) { .ev-ob { animation: none; } }
  .ev-t { margin-top: 6px; font: 790 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.025em; }
  .ev-m { font: 500 var(--fs-sub)/1.3 var(--font-text); color: rgba(255, 255, 255, 0.7); }
  .ev-cd { display: flex; align-items: baseline; gap: 8px; margin-top: 12px; }
  .ev-cd b { font: 800 var(--fs-sec)/1 var(--font-display); letter-spacing: -0.02em; }
  .ev-cd small { font: 600 var(--fs-sub)/1 var(--font-text); color: rgba(255, 255, 255, 0.7); }
  .ev-act { position: relative; z-index: 1; display: flex; gap: 8px; margin-top: 14px; }
  /* the whole card opens the event; its two buttons sit above it */
  .open { position: absolute; inset: 0; border-radius: inherit; }
  .ev-act button { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 40px; border-radius: var(--r-full);
    background: rgba(255, 255, 255, 0.14); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2); color: #fff; font: 650 var(--fs-body)/1 var(--font-text); }
  .ev-act button:active { transform: scale(0.96); }

  .empty { padding: 4px 2px; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
