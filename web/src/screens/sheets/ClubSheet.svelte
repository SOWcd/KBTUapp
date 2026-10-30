<script lang="ts">
  // A club, from anywhere its name or logo shows (SPEC §8.3: one sheet for "Subscribe" and "Join"): who they
  // are, their socials, what's coming up. Subscribe and Apply answer at once (optimistic, data.svelte.ts); a
  // club that closed applications can still be written to: its Telegram, else its first link (§4.5). Its Vice+ change
  // the logo and the rest by tapping the logo (testers looked for it here, not in Studio).
  import BadgeCheck from '@lucide/svelte/icons/badge-check';
  import Bell from '@lucide/svelte/icons/bell';
  import BellCheck from '@lucide/svelte/icons/bell-check';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Camera from '@lucide/svelte/icons/camera';
  import Users from '@lucide/svelte/icons/users';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Lock from '@lucide/svelte/icons/lock';
  import FolderPlus from '@lucide/svelte/icons/folder-plus';
  import ChatAvatar from '../../ui/ChatAvatar.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import AiBadge from '../../ui/AiBadge.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import Button from '../../ui/Button.svelte';
  import SocialIcon from '../../ui/SocialIcon.svelte';
  import { api, translated, type EventCard, type Id, type Org, type Post } from '../../lib/api';
  import { ago } from '../../lib/time';
  import { focusPos } from '../../lib/photo';
  import { data, toggleJoin, toggleSub } from '../../lib/state/data.svelte';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { inLang, roleName, titleOf } from '../../lib/perms';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { social } from '../../lib/social';
  import { dayMonth, relDay } from '../../lib/time';
  import { openLink, haptic } from '../../lib/tg';
  import { compact, APP_FOLDER } from '../../lib/chats';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  let fetched = $state<Org | null>(null);
  let fetchedEvents = $state<EventCard[] | null>(null);
  // the club's news, every post (the circles on Afisha keep 30 days): newest first here, played oldest first
  let posts = $state<Post[] | null>(null);
  function play(p: Post) {
    if (!o || !posts) return;
    const list = [...posts].sort((a, b) => a.createdAt - b.createdAt);
    sheets.stories([{ org: posts[0].org, items: list.map((post) => ({ post })), unread: list.some((x) => !x.read), cast: false }], 0, list.indexOf(p));
  }
  // the afisha already holds the club's upcoming events (the server's list is the same filter): they show at once
  const events = $derived(fetchedEvents ?? (data.eventsReady ? data.events.filter((e) => e.org.id === id) : null));
  // the catalog's copy when there is one, so the bell here and in Clubs is the same state
  const o = $derived(data.orgs.find((x) => x.id === id) ?? fetched);
  const leaders = $derived(fetched?.leaders ?? []); // the catalog's copy has none
  // its Telegram chats (PLAN 86): the main channel as a card with Subscribe, the rest as rows; a closed one has no way in
  const chats = $derived(fetched?.chats ?? []);
  const main = $derived(chats.find((c) => c.main && c.url));
  const rest = $derived(chats.filter((c) => c !== main));
  const tap = (url: string) => { haptic.tap(); openLink(url); };
  let raw = $state(false); // the description as typed, not the AI's translation (PLAN 9)
  $effect(() => {
    api.org(id).then((x) => (fetched = x)).catch(() => {});
    api.events({ org: id }).then((x) => (fetchedEvents = x)).catch(() => {}); // the afisha's copy stays
    api.posts({ org: id }).then((x) => (posts = x)).catch(() => {});
  });
  const joinable = $derived(o?.kind === 'club' || o?.kind === 'school' || o?.kind === 'council'); // a school is joined like a club
  const contact = $derived(o?.links.find((u) => social(u).kind === 'telegram') ?? o?.links[0]);
  // the second button: apply, the pending application, or "write to the club" once it's closed
  const join = $derived(!!o && joinable && !!(o.round || o.myRequest || o.recruiting || contact));
</script>

{#snippet bell()}{#if o?.subscribed}<BellCheck size={19} />{:else}<Bell size={19} />{/if}{/snippet}
{#snippet send()}<TelegramMark size={18} />{/snippet}

<Sheet {overlay} title={o?.name ?? ''}>
  {#if o}
    <div class="hero">
      {#if o.myRights?.includes('profile')}
        <button class="lg" onclick={() => sheets.clubEdit(o.id)} aria-label={t('ce.title')}><OrgLogo org={o} size={84} /><span class="cam"><Camera size={16} /></span></button>
      {:else}<OrgLogo org={o} size={84} />{/if}
      <h2 class="t-h2 name">{o.name}{#if o.official}<span class="ok"><BadgeCheck size={20} /></span>{/if}</h2>
      <p class="t-foot">{o.official ? t('clubs.official') : t('club.initiative')}</p>
      <p class="t-foot stats">{[tn('clubs.subscribers', o.subscribers), tn('club.members', o.members)].join(' · ')}</p>
    </div>

    {#if o.myRole}<p class="role">{t('club.myRole', { role: roleName(o.myRole, inLang(o.myTitle, o.myTitleKk, o.myTitleEn)) })}</p>{/if}
    {#if o.description}<p class="t-body about selectable">{raw ? o.orig?.description ?? o.description : o.description}</p>
      {#if translated(o, 'description')}<button class="trn" onclick={() => (raw = !raw)}><AiBadge /> {raw ? t('ai.showTr') : t('ai.showOrig')}</button>{/if}{/if}
    {#if o.round && !o.myRole}<p class="rnd">{t('cast.recruiting', { when: dayMonth(o.round.closesAt) })}</p>
    {:else if joinable && !o.myRole && !o.recruiting && !o.myRequest}<p class="t-foot closed">{t('join.closed')}</p>{/if}

    {#if o.links.length}
      <div class="links">
        {#each o.links as url (url)}
          {@const s = social(url)}
          <button class="link" onclick={() => openLink(url)}><SocialIcon kind={s.kind} size={19} /><span class="ellipsis">{s.label}</span></button>
        {/each}
      </div>
    {/if}

    {#if chats.length || o.kind === 'app'}
      <h3 class="t-cap sec">{t('oc.title')}</h3>
      {#if main}
        <div class="mc surface">
          <div class="mh"><ChatAvatar title={main.title} photo={main.photo} kind={main.kind} size={52} />
            <span><b class="ellipsis">{main.title}</b><small>{main.members ? tn('clubs.subscribers', main.members).replace(String(main.members), compact(main.members)) : t('chats.channel')}</small></span></div>
          {#if main.about}<p class="t-foot ab clamp-2">{main.about}</p>{/if}
          <Button kind="primary" size="m" full icon={send} onclick={() => tap(main.url!)}>{t('oc.subscribe')}</Button>
        </div>
      {/if}
      {#if rest.length || o.kind === 'app'}
        <div class="posts" class:gap={!!main}>
          {#each rest as c (c.id)}
            {@const line = [c.closed ? t('oc.closed') : t(`chats.${c.kind}`), c.members ? tn('chats.members', c.members).replace(String(c.members), compact(c.members)) : ''].filter(Boolean).join(' · ')}
            {#if c.url}
              <button class="pst" onclick={() => tap(c.url!)}><ChatAvatar title={c.title} photo={c.photo} kind={c.kind} />
                <span><b class="ellipsis">{c.title}</b><small>{line}</small></span></button>
            {:else}
              <!-- closed: shown, but nobody gets in from here -->
              <div class="pst shut"><ChatAvatar title={c.title} photo={c.photo} kind={c.kind} />
                <span><b class="ellipsis">{c.title}</b><small>{line}</small></span><Lock size={17} /></div>
            {/if}
          {/each}
          {#if o.kind === 'app'}
            <button class="pst fold" onclick={() => tap(APP_FOLDER)}><span class="fi"><FolderPlus size={20} /></span><span><b>{t('oc.folder')}</b></span><ChevronRight size={18} /></button>
          {/if}
        </div>
      {/if}
    {:else if fetched && (o.myRights?.includes('profile') || session.me?.role === 'admin')}
      <!-- none yet: shown to who can link them (even the app's creator couldn't find how) -->
      <h3 class="t-cap sec">{t('oc.title')}</h3>
      <div class="nochat surface"><p class="t-foot">{t('oc.emptyHint')}</p>
        <Button kind="secondary" size="m" full onclick={() => sheets.clubEdit(o.id, 'chats')}>{t('oc.linkChat')}</Button></div>
    {/if}

    {#if leaders.length}
      <h3 class="t-cap sec">{t('club.lead')}</h3>
      <div class="posts">
        {#each leaders as m (m.person.id)}
          <button class="pst" onclick={() => sheets.person(m.person.id)}>
            <Avatar person={m.person} size={44} tappable={false} />
            <span><b class="ellipsis">{m.person.name}</b><small>{roleName(m.role, titleOf(m))}</small></span>
          </button>
        {/each}
        {#if (fetched?.members ?? o.members) > leaders.length && (!o.membersHidden || o.myRole)}
          <button class="pst all" onclick={() => sheets.people(o.id, o.name)}><Users size={20} /><span><b>{t('club.everyone')}</b></span><small>{fetched?.members ?? o.members}</small><ChevronRight size={18} /></button>
        {/if}
      </div>
    {/if}

    <h3 class="t-cap sec">{t('club.upcoming')}</h3>
    {#if events?.length}
      <div class="list">{#each events as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} />{/each}</div>
    {:else if events}
      <p class="t-foot none">{t('club.noEvents')}</p>
    {/if}
    {#if posts?.length}
      <h3 class="t-cap sec">{t('page.news')}</h3>
      <div class="posts">
        {#each posts.slice(0, 6) as p (p.id)}
          <button class="pst" onclick={() => play(p)}>
            {#if p.photo}<img src={p.photo.url} alt="" loading="lazy" decoding="async" style:object-position={focusPos(p.photo)} />{/if}
            <span><b class="clamp-2">{p.title}</b><small>{ago(p.createdAt)}</small></span>
          </button>
        {/each}
      </div>
    {/if}
  {/if}

  {#snippet footer()}
    {#if o && !o.myRole}
      {@const sub = o.subscribed ? t('clubs.subscribed') : t('clubs.subscribe')}
      <div class="acts btns">
        {#if join}
          <!-- next to a join action the bell needs no words -->
          <Button kind={o.subscribed ? 'neutral' : 'secondary'} size="l" label={sub} icon={bell} onclick={() => toggleSub(id)} />
          {#if o.round}
            <Button kind={o.round.applied ? 'neutral' : 'primary'} size="l" full onclick={() => sheets.roundApply(o.id)}>{o.round.applied ? t('cast.applied') : t('join.apply')}</Button>
          {:else if o.myRequest === 'rejected'}
            <Button kind="neutral" size="l" full disabled>{t('join.notNow')}</Button>
          {:else if o.myRequest || o.recruiting}
            <Button kind={o.myRequest ? 'neutral' : 'primary'} size="l" full onclick={() => toggleJoin(id)}>{o.myRequest ? t('join.sent') : t('join.apply')}</Button>
          {:else}
            <Button kind="primary" size="l" full icon={social(contact!).kind === 'telegram' ? send : undefined} onclick={() => openLink(contact!)}>{t('join.write')}</Button>
          {/if}
        {:else}
          <Button kind={o.subscribed ? 'neutral' : 'primary'} size="l" full icon={bell} onclick={() => toggleSub(id)}>{sub}</Button>
        {/if}
      </div>
    {/if}
  {/snippet}
</Sheet>

<style>
  .trn { margin-top: 6px; padding: 2px 0; font: 600 12.5px/1.2 var(--font-text); color: var(--text-3); }
  .hero { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6px; padding: 8px 0 4px; }
  .lg { position: relative; transition: transform var(--t-fast) var(--ease); }
  .lg:active { transform: scale(0.95); }
  .cam { position: absolute; right: -4px; bottom: -4px; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--accent); color: #fff; box-shadow: 0 0 0 3px var(--bg-raised); }
  .name { display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; }
  .ok { color: var(--accent); display: inline-flex; }
  .stats { color: var(--text-2); }
  .role { align-self: center; margin: 10px auto 0; width: fit-content; padding: 6px 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 630 13px/1.2 var(--font-text); }
  .about { margin-top: 14px; color: var(--text); }
  .closed { margin-top: 8px; }
  .rnd { align-self: center; margin: 10px auto 0; width: fit-content; padding: 7px 12px; border-radius: var(--r-full); background: var(--success-soft);
    color: var(--success-text); font: 650 13.5px/1.2 var(--font-text); }
  .acts { display: flex; gap: 8px; }
  .acts :global(.btn:not(.full)) { width: var(--ctl-l); padding: 0; }
  .acts :global(.btn:not(.full) .ic) { margin: 0; }
  .links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .link { display: inline-flex; align-items: center; gap: 8px; height: 40px; max-width: 100%; padding: 0 14px 0 12px; border-radius: var(--r-full);
    background: var(--surface-2); color: var(--text); font: 620 14px/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .link:active { transform: scale(0.96); }
  .sec { margin: 22px 2px 8px; }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .none { padding: 4px 2px; }
  .posts { display: flex; flex-direction: column; border-radius: var(--r-l); background: var(--surface); overflow: hidden; }
  .pst { display: flex; align-items: center; gap: 12px; min-height: 60px; padding: 10px 14px; text-align: left; }
  .pst + .pst { box-shadow: inset 0 1px 0 var(--line); }
  .pst:active { background: var(--surface-2); }
  .pst img { width: 44px; height: 44px; flex: none; border-radius: 10px; object-fit: cover; }
  .pst span { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .pst b { font: 620 15px/1.25 var(--font-text); color: var(--text); }
  .pst small { font: 500 12.5px/1 var(--font-text); color: var(--text-3); }
  .all { color: var(--accent-text); }
  .mc { display: flex; flex-direction: column; gap: 12px; padding: 14px; border-radius: var(--r-l); }
  .mh { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .mh > span { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .mh b { font: 680 16px/1.25 var(--font-text); }
  .mh small { font: 500 12.5px/1 var(--font-text); color: var(--text-3); }
  .ab { margin: -2px 2px 0; color: var(--text-2); }
  .gap { margin-top: 10px; }
  .pst > span { flex: 1; }
  .shut :global(svg) { flex: none; color: var(--text-3); }
  .shut:active { background: none; }
  .fold, .fold b { color: var(--text-2); font-weight: 560; }
  .fi { flex: none !important; width: 44px; height: 44px; display: grid !important; place-items: center; border-radius: 50%; background: var(--surface-2); }
  .fold :global(svg) { flex: none; }
  .all span { flex: 1; }
  .all b { color: var(--accent-text); }
  .all :global(svg) { flex: none; }
  .nochat { display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: var(--r-l); }
</style>
