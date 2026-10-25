<script lang="ts">
  import Plus from '@lucide/svelte/icons/plus';
  // Tab 2 → Clubs, the catalogue for everyone (owner, Oct 24: it moved here from Events; the Join page folded in as
  // "Recruiting now" up top). Mockup v24, owner Oct 21: subscribe to a club to hear about its new events (the bell; the Feed
  // and List show everything anyway). All / mine up top, search (a catalog of 50–100 clubs is unusable by scrolling),
  // KBTU's chats as avatars with a mark for what each is, the clubs as tiles with what's next at each, the schools
  // as a list. Categories wait for the server (orgs have no category yet).
  import Search from '@lucide/svelte/icons/search';
  import BadgeCheck from '@lucide/svelte/icons/badge-check';
  import X from '@lucide/svelte/icons/x';
  import Bell from '@lucide/svelte/icons/bell';
  import BellCheck from '@lucide/svelte/icons/bell-check';
  import { data, toggleSub, toggleJoin, loadChats, chatsFor } from '../../lib/state/data.svelte';
  import Button from '../../ui/Button.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth, dayMonthShort, nowTs, time, weekdayShort } from '../../lib/time';
  import OrgLogo, { COVERS, initials } from '../../ui/OrgLogo.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import ChatKind from '../../ui/ChatKind.svelte';
  import CreateClubCard from '../../ui/CreateClubCard.svelte';
  import { type Chat } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { openChat, compact, suggestChat } from '../../lib/chats';
  import { byWeight, hit, weight } from '../../lib/clubs';
  import type { Org } from '../../lib/api';
  import ClubRow from '../../ui/ClubRow.svelte';
  import GovMark from '../../ui/GovMark.svelte';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { slide } from 'svelte/transition';


  let q = $state('');
  // the chats directory (§4.11): mine first (my school and course, then everyone's); the rest a tap away
  const chats = $derived(data.chats);
  $effect(() => { if ((session.me?.id ?? null) !== chatsFor) loadChats(); });
  function tapChat(c: Chat) {
    void openChat(c);
  }
  // Owner, Oct 25 (video IMG_6648: 44 tiles, most empty, then 11 schools in full): priorities, not a catalogue. Mine (I'm
  // in it or follow it), Soon (an event coming, or taking applications), Popular (the six biggest by members and
  // followers), then "All clubs · N" for the rest (AllClubs.svelte) and the schools folded into one row. The Student
  // Government first wherever it shows. A search goes over everything as plain rows.
  const clubsOnly = $derived(data.orgs.filter((o) => o.kind !== 'school'));
  const schools = $derived(data.orgs.filter((o) => o.kind === 'school'));
  const found = $derived(q.trim() ? [...data.orgs].filter((o) => hit(o, q)).sort(byWeight) : []);
  const mine = $derived(clubsOnly.filter((o) => o.myRole || o.subscribed).sort(byWeight));
  const mineIds = $derived(new Set(mine.map((o) => o.id)));
  // what's next at each club: its soonest event (and when, for Soon's order)
  const next = $derived.by(() => {
    const m = new Map<number, { at: number; text: string }>(), now = nowTs();
    for (const e of [...data.events].sort((a, b) => a.startsAt - b.startsAt))
      if (e.status !== 'cancelled' && e.startsAt > now && !m.has(e.org.id))
        m.set(e.org.id, { at: e.startsAt, text: `${e.startsAt - now < 6 * 86400 ? weekdayShort(e.startsAt) : dayMonthShort(e.startsAt)} ${time(e.startsAt)} · ${e.title}` });
    return m;
  });
  // Soon: not mine (their tiles show what's next), an event first by its time, then recruiting (a round by its deadline)
  const SOON = 6;
  const soon = $derived(data.orgs.filter((o) => !mineIds.has(o.id) && !o.myRole && (next.has(o.id) || o.round || o.recruiting))
    .map((o) => ({ o, at: next.get(o.id)?.at ?? o.round?.closesAt ?? Infinity }))
    .sort((a, b) => +!a.o.gov - +!b.o.gov || a.at - b.at).slice(0, SOON).map((x) => x.o));
  const soonLine = (o: Org) => next.get(o.id)?.text ?? (o.round ? t('cast.recruiting', { when: dayMonth(o.round.closesAt) }) : t('clubs.openNow'));
  const canApply = (o: Org) => !!session.me?.student && !o.myRole && (!!o.round || o.recruiting);
  // Popular: the six biggest that aren't mine, with someone in them or following
  const popular = $derived(clubsOnly.filter((o) => !mineIds.has(o.id) && (o.gov || weight(o) > 0)).sort(byWeight).slice(0, 6));
  let schoolsOpen = $state(false);
  // a chat without a picture: its letters on a colour of its own
  const tint = (title: string) => COVERS[[...title].reduce((h, c) => h + c.charCodeAt(0), 0) % COVERS.length];
</script>

<div class="page scroll">
  <header class="hd">
    <h1 class="t-h1">{t('clubs.title')}</h1>
  </header>

  <label class="search">
    <Search size={18} />
    <input bind:value={q} placeholder={t('clubs.search')} type="search" enterkeyhint="search" autocomplete="off" />
    {#if q}<button onclick={() => (q = '')} aria-label={t('common.close')}><X size={16} /></button>{/if}
  </label>

  {#if q.trim()}
    <div class="sec"><h2>{t('clubs.found')}</h2><span class="num">{found.length}</span></div>
    <div class="rows surface">
      {#each found as o (o.id)}<ClubRow org={o} name={o.kind === 'school' ? o.abbr ?? o.name : o.name} sub={o.kind === 'school' && o.abbr ? o.name : tn('clubs.subscribers', o.subscribers)} />
      {:else}<p class="t-foot empty">{t('clubs.nothing')}</p>{/each}
    </div>
  {/if}

  {#if chats && (chats.all.length || session.me?.student) && !q.trim()}
    <section class="chats">
      <div class="sec"><h2>{t('chats.title')}</h2>{#if chats.all.length}<button class="all" onclick={() => sheets.chats(chats!.all)}>{t('chats.all', { n: chats.all.length })}</button>{/if}</div>
      <div class="ch-row hscroll" data-noswipe>
        <!-- any student brings a chat in: the bot opens Telegram's own chat picker (owner, Oct 20) -->
        <button class="chat add" onclick={suggestChat}><span class="cav"><Plus size={26} /></span><b>{t('chats.suggestShort')}</b></button>
        {#each chats.forYou as c (c.id)}
          <button class="chat" onclick={() => tapChat(c)}>
            <span class="cav" class:sq={c.kind === 'forum'} style={c.photo ? '' : `background:${tint(c.title)}`}>
              {#if c.photo}<img src={c.photo} alt="" />{:else}<em>{initials(c.title)}</em>{/if}
              <!-- what it is, Telegram's way: a channel, a group, a group with topics -->
              <span class="kind"><ChatKind kind={c.kind} /></span>
            </span>
            <b>{c.title}</b>
            {#if c.members}<small><TelegramMark size={10} />{compact(c.members)}</small>{/if}
          </button>
        {/each}
      </div>
    </section>
  {/if}

  {#snippet tile(o: Org)}
    {@const nx = next.get(o.id)?.text ?? (o.recruiting ? t('clubs.recruiting') : '')}
    <div class="club surface">
      <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
      <span class="ghost" aria-hidden="true"><OrgLogo org={{ ...o, logo: null }} size={88} /></span>
      <button class="bell" class:on={o.subscribed} onclick={() => toggleSub(o.id)} aria-label={t(o.subscribed ? 'clubs.subscribed' : 'clubs.subscribe')} aria-pressed={o.subscribed}>
        {#if o.subscribed}<BellCheck size={17} />{:else}<Bell size={17} />{/if}</button>
      <OrgLogo org={o} size={52} />
      <span class="txt">
        <span class="nm"><b class="clamp-2">{o.name}</b>{#if o.official}<span class="ok" title={t('clubs.official')}><BadgeCheck size={15} /></span>{/if}</span>
        {#if o.gov}<GovMark />{/if}
        <small>{o.members ? tn('club.members', o.members) : tn('clubs.subscribers', o.subscribers)}</small>
        {#if nx}<em class="cnx"><i></i><span>{nx}</span></em>{/if}
      </span>
    </div>
  {/snippet}

  {#if !q.trim()}
    {#if mine.length}
      <div class="sec"><h2>{t('clubs.mineShort')}</h2><span class="num">{mine.length}</span></div>
      <div class="grid">{#each mine as o (o.id)}{@render tile(o)}{/each}</div>
    {/if}

    {#if soon.length}
      <div class="sec"><h2>{t('clubs.soon')}</h2></div>
      <div class="rows surface">
        {#each soon as o (o.id)}
          <ClubRow org={o} sub={soonLine(o)} hot={next.has(o.id)}>
            {#snippet end()}
              {#if canApply(o) && o.round}<Button kind={o.round.applied ? 'neutral' : 'primary'} size="s" onclick={() => sheets.roundApply(o.id, 'join')}>{o.round.applied ? t('cast.applied') : t('join.apply')}</Button>
              {:else if canApply(o) && o.myRequest === 'rejected'}<Button kind="neutral" size="s" disabled>{t('join.notNow')}</Button>
              {:else if canApply(o)}<Button kind={o.myRequest ? 'neutral' : 'primary'} size="s" onclick={() => toggleJoin(o.id)}>{o.myRequest ? t('join.sent') : t('join.apply')}</Button>
              {:else}<button class="bell" class:on={o.subscribed} onclick={() => toggleSub(o.id)} aria-label={t(o.subscribed ? 'clubs.subscribed' : 'clubs.subscribe')} aria-pressed={o.subscribed}>
                {#if o.subscribed}<BellCheck size={17} />{:else}<Bell size={17} />{/if}</button>{/if}
            {/snippet}
          </ClubRow>
        {/each}
      </div>
    {/if}

    {#if popular.length}
      <div class="sec"><h2>{t('clubs.popular')}</h2></div>
      <div class="grid">{#each popular as o (o.id)}{@render tile(o)}{/each}</div>
    {/if}

    <button class="allb surface" onclick={() => sheets.allClubs()}><span>{t('clubs.allBtn', { n: clubsOnly.length })}</span><ChevronRight size={18} /></button>

    {#if schools.length}
      <div class="rows surface fold">
        <button class="srow" class:shown={schoolsOpen} onclick={() => (schoolsOpen = !schoolsOpen)} aria-expanded={schoolsOpen}>
          <span class="stack" aria-hidden="true">{#each schools.slice(0, 3) as o (o.id)}<OrgLogo org={o} size={30} />{/each}</span>
          <b>{t('clubs.schools')} · {schools.length}</b>
          <span class="chev"><ChevronDown size={18} /></span>
        </button>
        {#if schoolsOpen}
          <div transition:slide={{ duration: 260 }}>
            {#each schools as o (o.id)}<ClubRow org={o} name={o.abbr ?? o.name} sub={o.abbr ? o.name : ''} />{/each}
          </div>
        {/if}
      </div>
    {/if}
  {/if}
  <div class="cta"><CreateClubCard /></div>
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  .hd { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
  .search { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface); color: var(--text-3); box-shadow: var(--shadow-card); }
  .search input { flex: 1; min-width: 0; font: 500 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .search input::placeholder { color: var(--text-3); }
  .search input::-webkit-search-cancel-button { display: none; }
  .search button { display: flex; color: var(--text-3); padding: 4px; }
  .sec { display: flex; align-items: baseline; justify-content: space-between; margin: 28px 4px 12px; }
  .sec h2 { font: 760 var(--fs-sec)/1.1 var(--font-display); letter-spacing: -0.025em; }
  .sec > span, .sec .all { font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  .sec .all { color: var(--accent-text); }

  /* chats: the chat's own picture (or its letters), a small mark for what it is (mockup v16) */
  .ch-row { gap: 10px; margin: 0 calc(-1 * var(--gutter)); padding: 2px var(--gutter) 6px; }
  .chat { flex: none; width: 82px; display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; }
  .chat > b { width: 100%; font: 620 var(--fs-cap)/1.2 var(--font-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .chat small { display: flex; align-items: center; gap: 3px; margin-top: -3px; font: 600 var(--fs-micro)/1 var(--font-text); color: var(--text-3); }
  .cav { position: relative; width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; color: #fff; background: var(--surface-2);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), 0 10px 20px -12px rgba(0, 0, 0, 0.7); }
  .cav.sq { border-radius: 30%; } /* a topics group is a squircle, as Telegram draws it */
  .cav img { width: 100%; height: 100%; border-radius: inherit; object-fit: cover; }
  .cav em { font: 800 21px/1 var(--font-display); font-style: normal; letter-spacing: -0.02em; }
  .add .cav { background: none; color: var(--text-2); box-shadow: inset 0 0 0 1.5px var(--line-2); }
  .kind { position: absolute; right: -3px; bottom: -3px; display: flex; border-radius: 50%; box-shadow: 0 0 0 2.5px var(--bg); }
  .sq .kind { border-radius: 32%; }

  /* clubs: tiles, two a row; the club's emoji as a faint ghost in the corner; the bell its own button */
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .club { position: relative; display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 14px; border-radius: var(--r-l); overflow: hidden; }
  .club:active:not(:has(.bell:active)) { transform: scale(0.98); }
  .open { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .ghost { position: absolute; right: -18px; bottom: -22px; opacity: 0.1; transform: rotate(-12deg); pointer-events: none; }
  .bell { position: absolute; top: 12px; right: 12px; z-index: 2; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-2); }
  .bell.on { background: var(--success-soft); color: var(--success-text); }
  .txt { position: relative; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .nm { display: flex; align-items: flex-start; gap: 4px; min-width: 0; }
  .nm b { font: 680 var(--fs-body)/1.2 var(--font-text); }
  .ok { display: inline-flex; color: var(--accent-text); flex: none; margin-top: 1px; }
  .txt small { font: 500 var(--fs-sub)/1.25 var(--font-text); color: var(--text-3); }
  .cnx { display: flex; align-items: center; gap: 6px; margin-top: 6px; font: 650 var(--fs-cap)/1.2 var(--font-text); font-style: normal; color: var(--accent-text); min-width: 0; }
  .cnx i { flex: none; width: 6px; height: 6px; border-radius: 50%; background: #46D6FF; }
  .cnx span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .empty { grid-column: 1 / -1; padding: 20px 4px; }

  /* plain rows (Soon, a search, the schools): ClubRow */
  .rows { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .rows .empty { padding: 20px 14px; }
  .rows .bell { position: relative; top: auto; right: auto; }
  /* everything else a tap away */
  .allb { display: flex; align-items: center; justify-content: space-between; width: 100%; height: 52px; margin-top: 16px; padding: 0 14px 0 16px;
    border-radius: var(--r-l); color: var(--accent-text); font: 650 var(--fs-body)/1 var(--font-text); }
  .allb:active { transform: scale(0.98); }
  /* the schools, folded into one row (owner, Oct 25) */
  .fold { margin-top: 10px; }
  .srow { display: flex; align-items: center; gap: 12px; width: 100%; min-height: 56px; padding: 8px 14px 8px 12px; text-align: left; color: var(--text-3); }
  .srow b { flex: 1; font: 650 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .chev { display: flex; transition: transform 0.26s ease; }
  .srow.shown .chev { transform: rotate(180deg); }
  .srow:active { background: var(--surface-2); }
  .fold > div { box-shadow: inset 0 1px 0 var(--line); }
  .stack { display: flex; }
  .stack > :global(*) { box-shadow: 0 0 0 2px var(--surface); border-radius: 50%; }
  .stack > :global(* + *) { margin-left: -10px; }
  .cta { margin-top: 24px; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
