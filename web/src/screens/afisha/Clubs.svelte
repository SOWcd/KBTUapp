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


  let q = $state('');
  // the chats directory (§4.11): mine first (my school and course, then everyone's); the rest a tap away
  const chats = $derived(data.chats);
  $effect(() => { if ((session.me?.id ?? null) !== chatsFor) loadChats(); });
  function tapChat(c: Chat) {
    void openChat(c);
  }
  // clubs come first; KBTU's eleven schools after them under their own heading, no tab of their own (owner, Oct 14:
  // "schools matter less than clubs"; Oct 20: "there, but not up front")
  let view = $state<'all' | 'mine'>('all');
  const norm = (s: string) => s.toLowerCase().replace(/\u0451/g, '\u0435'); // Russian yo → ye, so both spellings match
  const hit = (o: (typeof data.orgs)[number]) => [o.name, o.abbr ?? ''].some((x) => norm(x).includes(norm(q.trim())));
  const list = $derived(data.orgs.filter((o) => (view !== 'mine' || o.subscribed) && (!q.trim() || hit(o))));
  const clubs = $derived(list.filter((o) => o.kind !== 'school'));
  const schools = $derived(list.filter((o) => o.kind === 'school'));
  const subsCount = $derived(data.orgs.filter((o) => o.subscribed).length);
  // what's next at each club: its soonest event, else "recruiting" when it takes applications
  const next = $derived.by(() => {
    const m = new Map<number, string>(), now = nowTs();
    for (const e of [...data.events].sort((a, b) => a.startsAt - b.startsAt))
      if (e.status !== 'cancelled' && e.startsAt > now && !m.has(e.org.id)) m.set(e.org.id, `${e.startsAt - now < 6 * 86400 ? weekdayShort(e.startsAt) : dayMonthShort(e.startsAt)} ${time(e.startsAt)} · ${e.title}`);
    return m;
  });
  // recruiting now (was the Join page): a round first (soonest deadline), then one-tap applications; not my own clubs
  const recruit = $derived(session.me?.student ? data.orgs.filter((o) => (o.round || o.recruiting) && !o.myRole)
    .sort((a, b) => +(a.kind === 'school') - +(b.kind === 'school') || (a.round ? a.round.closesAt : Infinity) - (b.round ? b.round.closesAt : Infinity)) : []);
  // a chat without a picture: its letters on a colour of its own
  const tint = (title: string) => COVERS[[...title].reduce((h, c) => h + c.charCodeAt(0), 0) % COVERS.length];
</script>

<div class="page scroll">
  <header class="hd">
    <h1 class="t-h1">{t('clubs.title')}</h1>
    <div class="seg" role="tablist">
      <button class:on={view === 'all'} onclick={() => (view = 'all')}>{t('clubs.all')}</button>
      <button class:on={view === 'mine'} onclick={() => (view = 'mine')}>{t('clubs.mineShort')}{subsCount ? ' · ' + subsCount : ''}</button>
    </div>
  </header>

  <label class="search">
    <Search size={18} />
    <input bind:value={q} placeholder={t('clubs.search')} type="search" enterkeyhint="search" autocomplete="off" />
    {#if q}<button onclick={() => (q = '')} aria-label={t('common.close')}><X size={16} /></button>{/if}
  </label>

  {#if recruit.length && !q.trim()}
    <div class="sec"><h2>{t('clubs.openNow')}</h2><span class="num">{recruit.length}</span></div>
    <div class="recruit surface">
      {#each recruit as o (o.id)}
        <div class="rc">
          <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
          <OrgLogo org={o} size={44} />
          <span class="txt"><b class="ellipsis">{o.name}</b><small class="ellipsis">{o.round ? t('cast.recruiting', { when: dayMonth(o.round.closesAt) }) : tn('club.members', o.members)}</small></span>
          <span class="go">
            {#if o.round}<Button kind={o.round.applied ? 'neutral' : 'primary'} size="s" onclick={() => sheets.roundApply(o.id, 'join')}>{o.round.applied ? t('cast.applied') : t('join.apply')}</Button>
            {:else if o.myRequest === 'rejected'}<Button kind="neutral" size="s" disabled>{t('join.notNow')}</Button>
            {:else}<Button kind={o.myRequest ? 'neutral' : 'primary'} size="s" onclick={() => toggleJoin(o.id)}>{o.myRequest ? t('join.sent') : t('join.apply')}</Button>{/if}
          </span>
        </div>
      {/each}
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

  <!-- the clubs as tiles, then KBTU's schools as a list (owner, Oct 14 and 20: there, but not up front) -->
  {#if clubs.length || !schools.length}
    <div class="sec"><h2>{t('clubs.clubs')}</h2><span class="num">{clubs.length}</span></div>
    <div class="grid">
      {#each clubs as o (o.id)}
        {@const nx = next.get(o.id) ?? (o.recruiting ? t('clubs.recruiting') : '')}
        <div class="club surface">
          <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
          <span class="ghost" aria-hidden="true"><OrgLogo org={{ ...o, logo: null }} size={88} /></span>
          <button class="bell" class:on={o.subscribed} onclick={() => toggleSub(o.id)} aria-label={t(o.subscribed ? 'clubs.subscribed' : 'clubs.subscribe')} aria-pressed={o.subscribed}>
            {#if o.subscribed}<BellCheck size={17} />{:else}<Bell size={17} />{/if}</button>
          <OrgLogo org={o} size={52} />
          <span class="txt">
            <span class="nm"><b class="clamp-2">{o.name}</b>{#if o.official}<span class="ok" title={t('clubs.official')}><BadgeCheck size={15} /></span>{/if}</span>
            <small>{tn('clubs.subscribers', o.subscribers)}</small>
            {#if nx}<em class="cnx"><i></i><span>{nx}</span></em>{/if}
          </span>
        </div>
      {:else}
        <p class="t-foot empty">{t('clubs.nothing')}</p>
      {/each}
    </div>
  {/if}
  {#if schools.length}
    <div class="sec"><h2>{t('clubs.schools')}</h2></div>
    <div class="schools surface">
      {#each schools as o (o.id)}
        <div class="school">
          <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
          <OrgLogo org={o} size={40} />
          <span class="txt"><b>{o.abbr ?? o.name}</b>{#if o.abbr}<small class="ellipsis">{o.name}</small>{/if}</span>
          <button class="bell" class:on={o.subscribed} onclick={() => toggleSub(o.id)} aria-label={t(o.subscribed ? 'clubs.subscribed' : 'clubs.subscribe')} aria-pressed={o.subscribed}>
            {#if o.subscribed}<BellCheck size={17} />{:else}<Bell size={17} />{/if}</button>
        </div>
      {/each}
    </div>
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

  /* recruiting now: one list, the button its own target */
  .recruit { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .rc { position: relative; display: flex; align-items: center; gap: 12px; min-height: 64px; padding: 8px 12px 8px 10px; }
  .rc + .rc { box-shadow: inset 0 1px 0 var(--line); }
  .rc:active:not(:has(.go :active)) { background: var(--surface-2); }
  .rc .txt { flex: 1; pointer-events: none; }
  .rc .txt b { font: 650 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .go { position: relative; z-index: 2; flex: none; }
  /* schools: one list */
  .schools { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .school { position: relative; display: flex; align-items: center; gap: 12px; min-height: 60px; padding: 8px 12px 8px 10px; text-align: left; color: var(--text-3); }
  .school .bell { position: relative; top: auto; right: auto; z-index: 2; flex: none; }
  .school .txt { pointer-events: none; }
  .school + .school { box-shadow: inset 0 1px 0 var(--line); }
  .school:active { background: var(--surface-2); }
  .school .txt b { font: 650 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .school .txt { flex: 1; }
  .cta { margin-top: 24px; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
