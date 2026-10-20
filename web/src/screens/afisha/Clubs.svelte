<script lang="ts">
  import Plus from '@lucide/svelte/icons/plus';
  // Events → Clubs: subscribe to a club to hear about its new events (the bell; the Feed and List show
  // everything anyway). Search on top (a catalog of 50–100 clubs is unusable by scrolling), then what's
  // coming up from subscriptions, then the catalog with a "my subscriptions" filter.
  import Search from '@lucide/svelte/icons/search';
  import BadgeCheck from '@lucide/svelte/icons/badge-check';
  import X from '@lucide/svelte/icons/x';
  import Bell from '@lucide/svelte/icons/bell';
  import BellCheck from '@lucide/svelte/icons/bell-check';
  import { data, toggleSub } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { relDay, nowTs } from '../../lib/time';
  import EventRow from '../../ui/EventRow.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Button from '../../ui/Button.svelte';
  import CreateClubCard from '../../ui/CreateClubCard.svelte';
  import Check from '@lucide/svelte/icons/check';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { api, type Chat, type Chats } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { openChat, compact, suggestChat } from '../../lib/chats';


  let q = $state('');
  // the chats directory (§4.11): mine first (my school and course, then everyone's); the rest a tap away
  let chats = $state<Chats | null>(null);
  $effect(() => { void session.me?.id; api.chats().then((c) => (chats = c)).catch(() => {}); });
  function tapChat(c: Chat) {
    void openChat(c).then(() => { if (chats) chats = { forYou: chats.forYou.map((x) => (x.id === c.id ? { ...x, opened: true } : x)), all: chats.all.map((x) => (x.id === c.id ? { ...x, opened: true } : x)) }; });
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
  const soon = $derived.by(() => {
    const subs = new Set(data.orgs.filter((o) => o.subscribed).map((o) => o.id));
    return data.events.filter((e) => subs.has(e.org.id) && e.status !== 'cancelled' && e.startsAt > nowTs()).sort((a, b) => a.startsAt - b.startsAt).slice(0, 3);
  });
</script>

<div class="page scroll">
  <header class="hd"><h1 class="t-h1">{t('clubs.title')}</h1></header>

  <label class="search">
    <Search size={18} />
    <input bind:value={q} placeholder={t('clubs.search')} type="search" enterkeyhint="search" autocomplete="off" />
    {#if q}<button onclick={() => (q = '')} aria-label={t('common.close')}><X size={16} /></button>{/if}
  </label>

  {#if soon.length && !q.trim()}
    <section class="soon">
      <h2 class="t-h3">{t('clubs.soon')}</h2>
      {#each soon as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} />{/each}
    </section>
  {/if}

  {#if chats && (chats.all.length || session.me?.student) && !q.trim()}
    <section class="chats">
      <div class="ch-h"><h2 class="t-h3">{t('chats.title')}</h2>{#if chats.all.length}<button class="ch-all" onclick={() => sheets.chats(chats!.all)}>{t('chats.all', { n: chats.all.length })}</button>{/if}</div>
      <div class="ch-row hscroll" data-noswipe>
        {#each chats.forYou as c (c.id)}
          <button class="chat surface" onclick={() => tapChat(c)}>
            <span class="ci" class:ch={c.kind === 'channel'} class:sq={c.kind === 'forum'}>{#if c.photo}<img src={c.photo} alt="" />{:else if c.kind === 'channel'}<Megaphone size={18} />{:else}<UsersRound size={18} />{/if}
              {#if c.opened}<span class="tick"><Check size={11} strokeWidth={3} /></span>{/if}</span>
            <b class="clamp-2">{c.title}</b>
            <i>{c.members ? compact(c.members) + ' · ' : ''}{t(`chats.${c.kind}`)}</i>
          </button>
        {/each}
        <!-- any student brings a chat in: the bot opens Telegram's own chat picker (owner, Oct 20) -->
        <button class="chat surface add" onclick={suggestChat}>
          <span class="ci"><Plus size={20} /></span><b class="clamp-2">{t('chats.suggest')}</b><i>{t('chats.suggestSub')}</i>
        </button>
      </div>
    </section>
  {/if}

  <div class="seg" role="tablist">
    <button class:on={view === 'all'} onclick={() => (view = 'all')}>{t('clubs.clubs')}</button>
    <button class:on={view === 'mine'} onclick={() => (view = 'mine')}>{t('clubs.mine')}{subsCount ? ' · ' + subsCount : ''}</button>
  </div>

  <!-- the clubs, then KBTU's schools under a heading (only when both show) -->
  {#each [clubs, schools] as group, gi (gi)}
  {#if group.length && clubs.length && schools.length}<h2 class="grp t-h3">{t(gi ? 'clubs.schools' : 'clubs.clubs')}</h2>{/if}
  {#if group.length || (gi && !clubs.length && !schools.length)}
  <div class="list">
    {#each group as o (o.id)}
      <div class="club surface">
        <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
        <OrgLogo org={o} size={52} />
        <span class="txt">
          <!-- a school by its short name (SITE, ISE), the full one under it -->
          <span class="nm"><b class="t-title ellipsis">{o.abbr ?? o.name}</b>{#if o.official}<span class="ok" title={t('clubs.official')}><BadgeCheck size={16} /></span>{/if}</span>
          <span class="t-foot" class:ellipsis={!!o.abbr}>{o.abbr ? o.name : tn('clubs.subscribers', o.subscribers) + (o.upcoming ? ' · ' + tn('clubs.events', o.upcoming) : '')}</span>
        </span>
        {#if o.subscribed}
          <Button kind="neutral" size="s" label={t('clubs.subscribed')} onclick={() => toggleSub(o.id)}>{#snippet icon()}<BellCheck size={17} />{/snippet}</Button>
        {:else}
          <Button kind="secondary" size="s" label={t('clubs.subscribe')} onclick={() => toggleSub(o.id)}>{#snippet icon()}<Bell size={15} />{/snippet}<span class="wd">{t('clubs.subscribe')}</span></Button>
        {/if}
      </div>
    {:else}
      <p class="t-foot empty">{t('clubs.nothing')}</p>
    {/each}
  </div>
  {/if}
  {/each}
  <div class="cta"><CreateClubCard /></div>
  <div class="tail"></div>
</div>

<style>
  .grp { margin: 18px 2px 10px; }
  .page { position: absolute; inset: 0; padding: calc(var(--top) + 56px) var(--gutter) 0; background: var(--glow), var(--bg); }
  .hd { margin-bottom: 14px; }
  .search { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface); color: var(--text-3); box-shadow: var(--shadow-card); }
  .search input { flex: 1; min-width: 0; font: 500 15px/1 var(--font-text); color: var(--text); }
  .search input::placeholder { color: var(--text-3); }
  .search input::-webkit-search-cancel-button { display: none; }
  .search button { display: flex; color: var(--text-3); padding: 4px; }
  .soon { display: flex; flex-direction: column; gap: 8px; margin-top: 18px; }
  .seg { margin: 12px 0 14px; }
  .chats { margin-top: 18px; }
  .ch-h { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 8px; }
  .ch-all { font: 620 14px/1 var(--font-text); color: var(--accent-text); }
  .ch-row { gap: 8px; margin: 0 calc(-1 * var(--gutter)); padding: 2px var(--gutter) 6px; }
  .chat { flex: none; width: 148px; display: flex; flex-direction: column; align-items: flex-start; gap: 6px; padding: 12px; text-align: left; }
  .chat:active { transform: scale(0.97); }
  .chat.add { background: none; box-shadow: inset 0 0 0 1.5px var(--line); }
  .chat b { font: 640 14px/1.25 var(--font-text); min-height: 2.5em; }
  .chat i { font: 500 12px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  .ci { position: relative; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent-text); }
  .ci.ch { background: color-mix(in srgb, #2AABEE 18%, transparent); color: #2AABEE; }
  /* the chat's own avatar; a topics group is a squircle, as Telegram draws it */
  .ci.sq { border-radius: 30%; }
  .ci img { width: 100%; height: 100%; border-radius: inherit; object-fit: cover; }
  .tick { position: absolute; right: -3px; bottom: -3px; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--success); color: #fff; box-shadow: 0 0 0 2px var(--surface); }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .club { position: relative; display: flex; align-items: center; gap: 12px; padding: 10px 12px 10px 10px; }
  /* the whole row opens the club; the bell sits above it as its own button */
  .open { position: absolute; inset: 0; border-radius: inherit; }
  .club > :global(.btn) { position: relative; z-index: 1; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .nm { display: flex; align-items: center; gap: 5px; min-width: 0; }
  .ok { display: inline-flex; color: var(--accent-text); flex: none; }
  .empty { padding: 20px 4px; }
  .cta { margin-top: 14px; }
  .tail { height: calc(var(--bottom) + 24px); }
  @media (max-width: 379px) { .wd { display: none; } } /* phones under 380 px (360 Android, 375 iPhone): the bell alone, the name gets the room */
</style>
