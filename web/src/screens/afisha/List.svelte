<script lang="ts">
  // Events → List (the home page). Title + count, a two-week date strip, the featured post, then the
  // days as timelines: classes from the portal schedule (one slim row each; back-to-back ones of a subject
  // joined into one row with a "×2"/"×3" chip, lib/classes.ts; owner, Oct 13: tall blocks took too much room)
  // and events, in time order, so an event shows in the gap between classes where it really is. Tapping a date shows only that day.
  import { tagName } from '../../lib/posts';
  import MapIcon from '@lucide/svelte/icons/map';
  import { data, skipped, classKey, skipClass } from '../../lib/state/data.svelte';
  import { t, tn, subjectOf } from '../../lib/i18n/index.svelte';
  import { shortSubject, lessonKind } from '../../lib/i18n/subjects';
  import { dayNo, nowTs, parts, weekday, dayMonth, weekdayShort, OFFSET, at } from '../../lib/time';
  import type { ClassItem, EventCard } from '../../lib/api';
  import EventRow from '../../ui/EventRow.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { floorOf, atDorm, DORM_2GIS, atBldg2, bldg2Room, BLDG2_2GIS } from '../../lib/map';
  import { openLink } from '../../lib/tg';
  import TwoGisMark from '../../ui/TwoGisMark.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import { ui } from '../../lib/state/ui.svelte';

  let picked = $state<number | null>(null); // local day number, null = all days
  let openPost = $state(false);

  const today = dayNo(nowTs());
  const strip = Array.from({ length: 14 }, (_, i) => today + i);
  const dayTs = (d: number) => d * 86400 - OFFSET; // start of local day d as a UTC timestamp

  const busyDays = $derived(new Set(data.events.filter((e) => e.status !== 'cancelled').map((e) => dayNo(e.startsAt))));
  const featured = $derived(data.posts.find((p) => p.featured));

  type Item = { key: string; at: number } & ({ c: ClassItem; end: number } | { e: EventCard });
  function classesOn(d: number): Item[] {
    const p = parts(dayTs(d) + 12 * 3600);
    const on = (hm: string) => { const [h, m] = hm.split(':').map(Number); return at(p.y, p.m, p.d, h, m); };
    return data.schedule.filter((c) => c.weekday === (p.wd || 7)) // 1 = Monday … 7 = Sunday
      .map((c) => ({ key: classKey(d, c), at: on(c.begins), end: on(c.ends), c }));
  }

  type Day = { d: number; items: Item[] };
  const days = $derived.by<Day[]>(() => {
    const by = new Map<number, Item[]>();
    for (const e of data.events) { const d = dayNo(e.startsAt); if (!by.has(d)) by.set(d, []); by.get(d)!.push({ key: 'e' + e.id, at: e.startsAt, e }); }
    // all days: the coming week's class days too (the owner missed his Wednesday, Oct 5), later only event days
    const week = strip.slice(0, 7).filter((d) => d === today || data.schedule.some((c) => c.weekday === (parts(dayTs(d) + 12 * 3600).wd || 7)));
    const wanted = picked != null ? [picked] : [...new Set([...week, ...by.keys()])].sort((a, b) => a - b);
    // a class before an event that starts at the same minute: you leave the class for it
    return wanted.map((d) => ({ d, items: [...classesOn(d), ...(by.get(d) ?? [])].sort((a, b) => a.at - b.at || ('c' in a ? -1 : 1)) }));
  });
  const clock = nowTs();

  function head(d: number): string {
    if (d === today) return t('common.today');
    if (d === today + 1) return t('common.tomorrow');
    const w = weekday(dayTs(d) + 12 * 3600);
    return w.charAt(0).toUpperCase() + w.slice(1);
  }
</script>

<div class="page scroll">
  <header class="hd">
    <span><h1 class="t-h1">{t('list.title')}</h1>
    <p class="t-foot">{tn('list.count', data.events.filter((e) => e.status !== 'cancelled').length)}</p></span>
    <button class="map" onclick={() => sheets.map()}><MapIcon size={18} />{t('map.open')}</button>
  </header>

  <div class="strip hscroll" data-noswipe>
    <button class="day all" class:on={picked == null} onclick={() => (picked = null)}>{t('common.all')}</button>
    {#each strip as d, i (d)}
      <button class="day" class:on={picked === d} onclick={() => (picked = picked === d ? null : d)}>
        <i>{i === 0 ? t('list.todayShort') : weekdayShort(dayTs(d) + 12 * 3600)}</i>
        <b class="num">{parts(dayTs(d) + 12 * 3600).d}</b>
        <s class:has={busyDays.has(d)}></s>
      </button>
    {/each}
  </div>

  {#if featured && picked == null}
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
        <p class="empty t-foot">{picked != null ? t('list.nothing') : t('list.freeDay')}</p>
      {:else if picked != null && !day.items.some((x) => 'e' in x)}
        <p class="empty t-foot">{t('list.nothing')}</p>
      {/if}
    </section>
  {/each}
  {#if picked == null && data.eventsReady && data.events.filter((e) => e.status !== 'cancelled').length < 6}
    <!-- the first weeks of the pilot: a short list should read as "more is coming", not as an empty app -->
    <section class="more surface">
      <Emoji name="sparkles_3d" size={36} />
      <b>{t('list.moreSoon')}</b>
      <p class="t-foot">{t('list.moreSoonText')}</p>
      <button onclick={() => (ui.page.afisha = 2)}>{t('list.toClubs')}</button>
    </section>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: calc(var(--top) + 56px) var(--gutter) 0; background: var(--glow), var(--bg); }
  .hd { margin-bottom: 14px; display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }
  .map { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 14px/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .map:active { transform: scale(0.95); }
  .hd p { margin-top: 4px; }

  .more { display: flex; flex-direction: column; align-items: center; gap: 6px; margin-top: 8px; padding: 20px 18px; text-align: center; }
  .more b { font: 700 16px/1.3 var(--font-text); }
  .more p { text-wrap: balance; }
  .more button { margin-top: 8px; height: 38px; padding: 0 16px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 14px/1 var(--font-text); }
  .more button:active { transform: scale(0.96); }
  .strip { gap: 6px; margin: 0 calc(-1 * var(--gutter)) 18px; padding: 0 var(--gutter); }
  .day {
    position: relative; flex: none; width: 46px; height: 62px; border-radius: 15px; background: var(--surface);
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px;
    transition: background-color var(--t-base) var(--ease), color var(--t-base) var(--ease), transform var(--t-fast) var(--ease);
  }
  .day:active { transform: scale(0.95); }
  .day i { font: 650 10.5px/1 var(--font-text); font-style: normal; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-3); }
  .day b { font: 700 18px/1.15 var(--font-text); letter-spacing: -0.02em; }
  .day s { width: 4px; height: 4px; border-radius: 50%; background: transparent; margin-top: 2px; }
  .day s.has { background: var(--accent); }
  .day.all { width: auto; padding: 0 14px; font: 650 13px/1 var(--font-text); }
  .day.on { background: var(--text); color: var(--bg); }
  .day.on i { color: var(--bg); opacity: 0.6; }
  .day.on s.has { background: var(--bg); }

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

  .empty { padding: 4px 2px; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
