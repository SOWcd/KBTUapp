<script lang="ts">
  // The Clubs tab: one feed for everyone, an App Store-like showcase (round 5, Nov 2: the "My club | All clubs" switch
  // went, segmented controls inside screens are out app-wide). No large title (the capsule names the tab). Top down:
  //   Mine      my clubs in a row, what's next at each; a club I'm in opens its Studio pushed from the right, one I
  //             follow its page (each of my clubs its own Studio: no picker); 3+ of them: the ones I run as rows,
  //             the rest as circles with "All" at the end (owner, Nov 3)
  //   search    sticks under the capsule once Mine scrolls away (a catalogue of 50-100 clubs needs it); typing turns
  //             the feed into the results
  //   Recommended  clubs with an open recruitment round (or taking applications), Apply at the row's end
  //   chats     KBTU's Telegram chats as avatars with a mark for what each is (§4.11)
  //   All clubs one list A-Z, what's next at each in its line, the bell at its end
  //   Schools and offices  their own list at the bottom; then "Create a club"
  // The Student Government first wherever it shows.
  import Plus from '@lucide/svelte/icons/plus';
  import Bell from '@lucide/svelte/icons/bell';
  import BellCheck from '@lucide/svelte/icons/bell-check';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import SearchField from '../../ui/SearchField.svelte';
  import { data, toggleSub, toggleJoin, loadChats, chatsFor } from '../../lib/state/data.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Section from '../../ui/Section.svelte';
  import Group from '../../ui/Group.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth, dayMonthShort, nowTs, time, weekdayShort } from '../../lib/time';
  import OrgLogo, { COVERS, initials } from '../../ui/OrgLogo.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import ChatKind from '../../ui/ChatKind.svelte';
  import CreateClubCard from '../../ui/CreateClubCard.svelte';
  import { type Org, type OrgRef } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { openChat, compact, suggestChat } from '../../lib/chats';
  import { byWeight, hit } from '../../lib/clubs';
  import { byRank, roleLabel } from '../../lib/perms';
  import { SvelteSet } from 'svelte/reactivity';
  import Row from '../../ui/Row.svelte';
  import { nameOf, shortOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import ClubRow from '../../ui/ClubRow.svelte';
  import GovMark from '../../ui/GovMark.svelte';

  let q = $state('');
  const searching = $derived(!!q.trim());
  // the chats directory (§4.11): mine first (my school and course, then everyone's); the rest a tap away
  const chats = $derived(data.chats);
  $effect(() => { if ((session.me?.id ?? null) !== chatsFor) loadChats(); });

  const SCHOOLISH = new Set(['school', 'office']);
  const clubsOnly = $derived(data.orgs.filter((o) => !SCHOOLISH.has(o.kind)));
  // official clubs, then the schools, then the unofficial ones (owner, Nov 3: the clubs made yesterday for fun topped the
  // list; they stay, below, to grow). Each by its people: the biggest first (the student government before all)
  const bySize = (a: Org, b: Org) => +!a.gov - +!b.gov || b.members - a.members || b.subscribers - a.subscribers || a.name.localeCompare(b.name, 'ru');
  const all = $derived(clubsOnly.filter((o) => o.official).sort(bySize));
  const top = $derived(clubsOnly.filter((o) => !o.official && o.top).sort(bySize)); // the Ascent's top (server clubs.py): own block, before the ✓
  const unofficial = $derived(clubsOnly.filter((o) => !o.official && !o.top).sort(bySize));
  const schools = $derived(data.orgs.filter((o) => SCHOOLISH.has(o.kind)).sort((a, b) => a.kind.localeCompare(b.kind) || nameOf(a).localeCompare(nameOf(b), 'ru')));
  const found = $derived(searching ? [...data.orgs].filter((o) => hit(o, q)).sort(byWeight) : []);

  // what's next at each club: its soonest event
  const next = $derived.by(() => {
    const m = new Map<number, string>(), now = nowTs();
    for (const e of [...data.events].sort((a, b) => a.startsAt - b.startsAt))
      if (e.status !== 'cancelled' && e.startsAt > now && !m.has(e.org.id))
        m.set(e.org.id, `${e.startsAt - now < 6 * 86400 ? weekdayShort(e.startsAt) : dayMonthShort(e.startsAt)} ${time(e.startsAt)} · ${e.title}`);
    return m;
  });

  // Mine: the clubs I'm in (by my rank, each opens its Studio), then the ones I follow (their page)
  // lead: President or Vice there
  type Mine = { org: OrgRef; full: Org | undefined; role: string | null; lead: boolean };
  const byId = $derived(new Map(data.orgs.map((o) => [o.id, o])));
  const mine = $derived.by<Mine[]>(() => {
    const ms = [...(session.me?.memberships ?? [])].sort(byRank);
    const inIds = new Set(ms.map((m) => m.org.id));
    return [...ms.map((m) => ({ org: m.org, full: byId.get(m.org.id), role: roleLabel(m), lead: m.role === 'president' || m.role === 'vice' })),
      ...clubsOnly.filter((o) => o.subscribed && !inIds.has(o.id)).sort(byWeight).map((o) => ({ org: o, full: o, role: null, lead: false }))];
  });
  const openMine = (x: { org: OrgRef; role: string | null }) => { haptic.tap(); if (x.role) sheets.studio(x.org.id); else sheets.club(x.org.id); };
  // 3+ (owner, Nov 3: a carousel of cards lost the ones past the edge): the clubs I run as rows, the rest as circles
  const inMine = $derived(mine.filter((x) => x.role)); // the clubs I follow stay in the lists below, bell on
  const led = $derived(inMine.filter((x) => x.lead));
  const rest = $derived(inMine.filter((x) => !x.lead));
  const mineLine = (x: Mine) => [x.role, next.get(x.org.id) ?? t('clubs.nothingSoon')].filter(Boolean).join(' · ');
  const allMine = () => { haptic.tap(); sheets.myClubs(inMine.map((x) => ({ org: x.org, role: x.role, sub: mineLine(x) }))); };
  // a circle's name: the short one when the full one runs past the circle (StoryRow's rule), measured once each
  const tight = new SvelteSet<number>();
  let pen: CanvasRenderingContext2D | null = null;
  function fit(node: HTMLElement, o: OrgRef) {
    if (!o.abbr) return;
    pen ??= document.createElement('canvas').getContext('2d');
    if (!pen) return;
    pen.font = getComputedStyle(node).font;
    if (pen.measureText(nameOf(o)).width > (matchMedia('(max-width: 360px)').matches ? 58 : 66)) tight.add(o.id);
  }

  // Recommended: open recruitment only, not my own clubs: official clubs and schools first, then student initiatives;
  // in each the student government first, then a round by its deadline, then any-time applications
  const mineIds = $derived(new Set(mine.map((x) => x.org.id)));
  const recruit = $derived(data.orgs.filter((o) => !mineIds.has(o.id) && !o.myRole && (o.round || o.recruiting))
    .sort((a, b) => +!(a.official || a.kind !== 'club') - +!(b.official || b.kind !== 'club') || +!a.gov - +!b.gov || (a.round?.closesAt ?? Infinity) - (b.round?.closesAt ?? Infinity) || byWeight(a, b)));
  const recruitLine = (o: Org) => (o.round ? t('cast.recruiting', { when: dayMonth(o.round.closesAt) }) : t('clubs.openNow'));
  const canApply = (o: Org) => !!session.me?.student && !o.myRole;
  const sub = (o: Org) => next.get(o.id) ?? (o.members ? tn('club.members', o.members) : tn('clubs.subscribers', o.subscribers));

  // stuck under the capsule: the bar's ground reaches up to the capsule, so no row shows between them (a sentinel just
  // above the bar: once it's under the capsule's line, the bar is stuck)
  let stuck = $state(false);
  function sentinel(el: HTMLElement) {
    const top = Math.round((document.querySelector('.cap.glass')?.getBoundingClientRect().bottom ?? 46) + 8);
    const io = new IntersectionObserver(([e]) => { stuck = !e.isIntersecting && e.boundingClientRect.top < top; }, { rootMargin: `-${top}px 0px 0px 0px` });
    io.observe(el);
    return { destroy: () => io.disconnect() };
  }

  // a chat without a picture: its letters on a colour of its own
  const tint = (title: string) => COVERS[[...title].reduce((h, c) => h + c.charCodeAt(0), 0) % COVERS.length];
</script>

<!-- follow / following: the S round button at a card's or a row's end -->
{#snippet bell(o: Org)}
  <IconButton icon={o.subscribed ? BellCheck : Bell} size="s" on={o.subscribed} onclick={() => toggleSub(o.id)} label={t(o.subscribed ? 'clubs.subscribed' : 'clubs.subscribe')} />
{/snippet}

<div class="page scroll stagger">
  {#if inMine.length > 2 && !searching}
    {#if led.length}
      <Section title={t('clubs.lead')}>
        <div class="led"><Group>
          {#each led as x (x.org.id)}
            <Row dense title={shortOf(x.org)} subtitle={mineLine(x)} accessory="chevron" onclick={() => openMine(x)}>
              {#snippet lead()}<OrgLogo org={x.org} size={40} />{/snippet}
            </Row>
          {/each}
        </Group></div>
      </Section>
    {/if}
    {#if rest.length}
      <Section title={t('clubs.memberOf')}>
        <div class="circles hscroll">
          {#each rest as x (x.org.id)}
            <button class="s" onclick={() => openMine(x)}>
              <span class="ring"><span class="in"><OrgLogo org={x.org} size={54} /></span></span>
              <b class="ellipsis" use:fit={x.org}>{tight.has(x.org.id) ? x.org.abbr : nameOf(x.org)}</b>
            </button>
          {/each}
          <button class="s" onclick={allMine}>
            <span class="ring"><span class="in all"><ChevronRight size={26} strokeWidth={2.2} /></span></span>
            <b class="ellipsis">{t('common.all')}</b>
          </button>
        </div>
      </Section>
    {/if}
  {:else if mine.length && !searching}
    <Section title={t('clubs.mineShort')}>
      <div class="mine hscroll">
        {#each mine as x (x.org.id)}
          {@const nx = next.get(x.org.id)}
          <div class="card surface">
            <button class="open" onclick={() => openMine(x)} aria-label={x.org.name}></button>
            <span class="top">
              <OrgLogo org={x.org} size={44} />
              {#if x.full && !x.role}
                <span class="bell">{@render bell(x.full)}</span>
              {:else if x.role}<span class="go" aria-hidden="true"><ChevronRight size={18} /></span>{/if}
            </span>
            <span class="nm"><b class="clamp-2">{nameOf(x.org)}</b>{#if x.full?.gov}<GovMark size={14} />{/if}</span>
            <small class="ellipsis">{x.role ?? (x.full ? tn('clubs.subscribers', x.full.subscribers) : '')}</small>
            <em class="nx" class:none={!nx}>{#if nx}<i></i><span>{nx}</span>{:else}<span>{t('clubs.nothingSoon')}</span>{/if}</em>
          </div>
        {/each}
      </div>
    </Section>
  {/if}

  <!-- the search sticks under the capsule: the catalogue is long -->
  <i class="sent" use:sentinel aria-hidden="true"></i>
  <div class="find" class:stuck><SearchField bind:value={q} placeholder={t('clubs.search')} /></div>

  {#if searching}
    <Section title={t('clubs.found')} count={found.length}>
      <Group>
        {#each found as o (o.id)}<ClubRow org={o} name={nameOf(o)} sub={o.kind === 'school' && o.abbr ? o.name : sub(o)} hot={next.has(o.id)} />
        {:else}<EmptyState inline text={t('clubs.nothing')} />{/each}
      </Group>
    </Section>
  {:else}
    {#if recruit.length}
      <Section title={t('clubs.recommend')}>
      <Group>
        {#each recruit as o (o.id)}
          <ClubRow org={o} sub={recruitLine(o)}>
            {#snippet end()}
              {#if canApply(o) && o.round}<Button kind={o.round.applied ? 'neutral' : 'primary'} size="s" onclick={() => sheets.roundApply(o.id, 'join')}>{o.round.applied ? t('cast.applied') : t('join.apply')}</Button>
              {:else if canApply(o) && o.myRequest === 'rejected'}<Button kind="neutral" size="s" disabled>{t('join.notNow')}</Button>
              {:else if canApply(o)}<Button kind={o.myRequest ? 'neutral' : 'primary'} size="s" onclick={() => toggleJoin(o.id)}>{o.myRequest ? t('join.sent') : t('join.apply')}</Button>
              {:else}{@render bell(o)}{/if}
            {/snippet}
          </ClubRow>
        {/each}
      </Group>
      </Section>
    {/if}

    {#if chats && (chats.all.length || session.me?.student)}
      <Section title={t('chats.title')} onmore={chats.all.length ? () => sheets.chats(chats!.all) : undefined} moreLabel={t('chats.all', { n: chats.all.length })}>
        <div class="ch-row hscroll">
          <!-- any student brings a chat in: the bot opens Telegram's own chat picker -->
          <button class="chat add" onclick={suggestChat}><span class="cav"><Plus size={26} /></span><b>{t('chats.suggestShort')}</b></button>
          {#each chats.forYou as c (c.id)}
            <button class="chat" onclick={() => void openChat(c)}>
              <span class="cav" class:sq={c.kind === 'forum'} style={c.photo ? '' : `background:${tint(c.title)}`}>
                {#if c.photo}<img src={c.photo} alt="" />{:else}<em>{initials(c.title)}</em>{/if}
                <!-- what it is, Telegram's way: a channel, a group, a group with topics -->
                <span class="kind"><ChatKind kind={c.kind} /></span>
              </span>
              <b>{c.title}</b>
              {#if c.org}<em class="who">{shortOf(c.org)}</em>{:else if c.members}<small><TelegramMark size={10} />{compact(c.members)}</small>{/if}
            </button>
          {/each}
        </div>
      </Section>
    {/if}

    {#if all.length}
      <Section title={t('clubs.allTitle')} count={all.length}><Group>{#each all as o (o.id)}<ClubRow org={o} sub={sub(o)} hot={next.has(o.id)} />{/each}</Group></Section>
    {/if}

    {#if schools.length}
      <Section title={t('clubs.schoolsOffices')} count={schools.length}><Group>{#each schools as o (o.id)}<ClubRow org={o} name={nameOf(o)} sub={o.abbr && o.abbr !== nameOf(o) ? o.name : sub(o)} />{/each}</Group></Section>
    {/if}

    {#if top.length}
      <Section title={t('clubs.top')} count={top.length}><Group>{#each top as o (o.id)}<ClubRow org={o} sub={sub(o)} hot={next.has(o.id)} />{/each}</Group></Section>
    {/if}
    {#if unofficial.length}
      <Section title={t('clubs.studentMade')} count={unofficial.length}><Group>{#each unofficial as o (o.id)}<ClubRow org={o} sub={sub(o)} hot={next.has(o.id)} />{/each}</Group></Section>
    {/if}
  {/if}
  <div class="cta"><CreateClubCard /></div>
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  /* the sections a screen's section apart (28), the first right under the capsule */
  .page > :global(.sec) { margin-top: var(--s-7); }
  .page > :global(.sec:first-child) { margin-top: var(--s-1); }

  /* Mine: cards in a row, the page's edges bled; the club, who I am there (or its followers), what's next */
  .mine { gap: 10px; margin: 0 calc(-1 * var(--gutter)); padding: 2px var(--gutter) var(--s-2); scroll-snap-type: x mandatory; scroll-padding: 0 var(--gutter); }
  .card { position: relative; flex: none; width: 164px; display: flex; flex-direction: column; gap: 3px; padding: var(--s-3); border-radius: var(--r-l);
    scroll-snap-align: start; transition: transform 420ms var(--ease-bounce); }
  .card:active:not(:has(.bell :active)) { transform: scale(0.97); transition-duration: 80ms; }
  .open { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: var(--s-2); }
  .go { display: grid; place-items: center; width: 28px; height: 28px; color: var(--text-3); }
  .nm { display: flex; align-items: flex-start; gap: 4px; min-width: 0; min-height: 2.4em; }
  .nm b { font: 600 var(--fs-body)/1.2 var(--font-text); letter-spacing: -0.01em; }
  .card small { font: 500 var(--fs-cap)/1.25 var(--font-text); color: var(--text-3); }
  .nx { display: flex; align-items: center; gap: 6px; margin-top: var(--s-2); padding-top: var(--s-2); box-shadow: inset 0 0.5px 0 var(--line-2);
    font: 600 var(--fs-cap)/1.25 var(--font-text); font-style: normal; color: var(--accent-text); min-width: 0; }
  .nx.none { color: var(--text-3); font-weight: 500; }
  .nx i { flex: none; width: 6px; height: 6px; border-radius: 50%; background: var(--accent-text); }
  .nx span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bell { position: relative; z-index: 2; display: flex; }

  /* 3+: the clubs I run, one line under each ("Vice · Sat 17:00 · Nightm…"); the rest as circles (StoryRow's) */
  .led :global(.st) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .circles { gap: var(--s-3); margin: 0 calc(-1 * var(--gutter)); padding: 2px var(--gutter); }
  .s { flex: none; width: 66px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .s:active .ring { transform: scale(0.94); }
  .ring { display: block; box-sizing: border-box; width: 64px; height: 64px; padding: 2px; border-radius: 50%; background: var(--line-2); transition: transform var(--t-fast) var(--ease); }
  .in { box-sizing: border-box; display: grid; place-items: center; width: 100%; height: 100%; border-radius: 50%; border: 2.5px solid var(--bg); overflow: hidden; }
  .all { background: var(--surface-2); color: var(--text-2); }
  /* a narrow phone: the fifth circle peeks at the edge, so the row reads as one that scrolls */
  @media (max-width: 360px) {
    .circles { gap: var(--s-2); }
    .s { width: 58px; }
    .ring { width: 56px; height: 56px; }
  }
  .s b { max-width: 100%; font: 600 var(--fs-micro)/1.2 var(--font-text); color: var(--text-2); }

  /* the search: sticks under the capsule on the page's own ground (a sticky top counts from the page's padding edge) */
  .find { position: sticky; top: calc(var(--head-bottom) + var(--s-2) - var(--page-top)); z-index: var(--z-sticky); margin: var(--s-3) calc(-1 * var(--gutter)) 0;
    padding: 0 var(--gutter) var(--s-2); background: var(--bg); }
  .page > .sent:first-child + .find { margin-top: 0; }
  .sent { display: block; height: 0; }
  .find::before { content: ''; position: absolute; left: 0; right: 0; bottom: 100%; height: calc(var(--head-bottom) + var(--s-2)); background: var(--bg);
    opacity: 0; transition: opacity var(--t-fast) var(--ease); pointer-events: none; }
  .find.stuck::before { opacity: 1; }
  .find.stuck { box-shadow: 0 0.5px 0 var(--separator); }

  /* chats: the chat's own picture (or its letters), a small mark for what it is (mockup v16) */
  .ch-row { gap: 10px; margin: 0 calc(-1 * var(--gutter)); padding: 2px var(--gutter) 6px; }
  .chat { flex: none; width: 82px; display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; }
  .chat > b { width: 100%; font: 600 var(--fs-cap)/1.2 var(--font-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .chat .who { max-width: 100%; margin-top: -3px; padding: 1px 6px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 600 var(--fs-micro)/1.4 var(--font-text); font-style: normal; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .chat small { display: flex; align-items: center; gap: 3px; margin-top: -3px; font: 600 var(--fs-micro)/1 var(--font-text); color: var(--text-3); }
  .cav { position: relative; width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; color: var(--on-accent); background: var(--surface-2);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), 0 10px 20px -12px rgba(0, 0, 0, 0.7); }
  .cav.sq { border-radius: 30%; } /* a topics group is a squircle, as Telegram draws it */
  .cav img { width: 100%; height: 100%; border-radius: inherit; object-fit: cover; }
  .cav em { font: 800 var(--fs-t3)/1 var(--font-display); font-style: normal; letter-spacing: -0.02em; }
  .add .cav { background: none; color: var(--text-2); box-shadow: inset 0 0 0 1.5px var(--line-2); }
  .kind { position: absolute; right: -3px; bottom: -3px; display: flex; border-radius: 50%; box-shadow: 0 0 0 2.5px var(--bg); }
  .sq .kind { border-radius: 32%; }

  .cta { margin-top: var(--s-6); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
