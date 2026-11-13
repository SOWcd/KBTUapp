<script lang="ts">
  // A club, from anywhere its name or logo shows (SPEC §8.3: one sheet for "Subscribe" and "Join"): who they
  // are, their socials, what's coming up. Subscribe and Apply answer at once (optimistic, data.svelte.ts); a
  // club can be written to: a DM to its President (lib/clubdm; in the footer once applications are closed). Its Vice+ change
  // the logo and the rest by tapping the logo (testers looked for it here, not in Studio).
  import OfficialMark from '../../ui/OfficialMark.svelte';
  import Bell from '@lucide/svelte/icons/bell';
  import BellCheck from '@lucide/svelte/icons/bell-check';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Camera from '@lucide/svelte/icons/camera';
  import Users from '@lucide/svelte/icons/users';
  import Lock from '@lucide/svelte/icons/lock';
  import FolderPlus from '@lucide/svelte/icons/folder-plus';
  import ChatAvatar from '../../ui/ChatAvatar.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import AiBadge from '../../ui/AiBadge.svelte';
  import AskAi from '../../ui/AskAi.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import { TAB_ICON } from '../../ui/icons';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Notice from '../../ui/Notice.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import SocialIcon from '../../ui/SocialIcon.svelte';
  import { castingStatus, castingWhen } from '../../lib/posts';
  import { api, translated, type EventCard, type Id, type Org, type Post } from '../../lib/api';
  import { ago } from '../../lib/time';
  import { focusPos } from '../../lib/photo';
  import { data, toggleJoin, toggleSub } from '../../lib/state/data.svelte';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { roleLabel } from '../../lib/perms';
  import { sheets } from '../../lib/state/sheets';
  import { social } from '../../lib/social';
  import { dayMonth, relDay } from '../../lib/time';
  import { openLink, haptic } from '../../lib/tg';
  import { compact, APP_FOLDER } from '../../lib/chats';
  import { clubDm } from '../../lib/clubdm';
  import { session } from '../../lib/state/session.svelte';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  let fetched = $state<Org | null>(null);
  let fetchedEvents = $state<EventCard[] | null>(null);
  let past = $state<EventCard[] | null>(null); // its latest few that are over (Recent), asked with the page
  // the club's news, every post (the circles on Afisha keep 30 days): newest first here, played oldest first
  let posts = $state<Post[] | null>(null);
  function play(p: Post) {
    if (!o || !posts) return;
    const list = posts.filter((x) => x.title).sort((a, b) => a.createdAt - b.createdAt); // a deleted casting has nothing to open
    sheets.stories([{ org: posts[0].org, items: list.map((post) => ({ post })), unread: list.some((x) => !x.read), cast: false }], 0, list.indexOf(p));
  }
  // the afisha already holds the club's upcoming events (the server's list is the same filter): they show at once
  const events = $derived(fetchedEvents ?? (data.eventsReady ? data.events.filter((e) => e.org.id === id || e.coHost?.id === id) : null)); // and the ones it co-hosts
  // the catalog's copy when there is one, so the bell here and in Clubs is the same state
  const o = $derived(data.orgs.find((x) => x.id === id) ?? fetched);
  const leaders = $derived(fetched?.leaders ?? []); // the catalog's copy has none
  // its Telegram chats (PLAN 86), the main channel first (the server's order), all the same rows; a closed one has no way in
  const chats = $derived(fetched?.chats ?? []);
  const tap = (url: string) => { haptic.tap(); openLink(url); };
  let raw = $state(false); // the description as typed, not the AI's translation (PLAN 9)
  $effect(() => {
    api.org(id).then((x) => (fetched = x)).catch(() => {});
    api.events({ org: id }).then((x) => (fetchedEvents = x)).catch(() => {}); // the afisha's copy stays
    api.pastEvents(id).then((x) => (past = x)).catch(() => (past = []));
    api.posts({ org: id }).then((x) => (posts = x)).catch(() => {});
  });
  const joinable = $derived(o?.kind === 'club' || o?.kind === 'school' || o?.kind === 'council'); // a school is joined like a club
  // "Message the club": a DM to its President (or the next with a @username), the draft naming the club (lib/clubdm)
  const contact = $derived(fetched?.contact ?? null);
  const write = () => { if (o && contact) { haptic.tap(); openLink(clubDm(contact, o, session.me?.memberships ?? [])); } };
  // in the footer while the club takes no applications; otherwise a row under its links (collabs, questions)
  // the second button: apply, the pending application, or "write to the club" once it's closed
  const join = $derived(!!o && joinable && !!(o.round || o.myRequest || o.recruiting || contact));
  const rowWrite = $derived(!!o && !!contact && !o.myRole && (!join || !!(o.round || o.myRequest || o.recruiting)));
  const shut = $derived(!!o && joinable && !o.myRole && !o.round && !o.recruiting && !o.myRequest); // takes no applications
</script>

{#snippet bell()}{#if o?.subscribed}<BellCheck size={19} />{:else}<Bell size={19} />{/if}{/snippet}
{#snippet send()}<TelegramMark size={18} />{/snippet}

<Sheet {overlay} icon={TAB_ICON.club} title={t('cap.club')}>
  {#if o}
    <div class="hero">
      {#if o.myRights?.includes('profile')}
        <button class="lg" onclick={() => sheets.clubEdit(o.id)} aria-label={t('ce.title')}><OrgLogo org={o} size={84} /><span class="cam"><Camera size={16} /></span></button>
      {:else}<OrgLogo org={o} size={84} />{/if}
      <h2 class="t-h2 name">{o.name}{#if o.official && o.kind === 'club'}<span class="ok"><OfficialMark size={21} explain /></span>{/if}</h2>
      <p class="t-foot">{o.official ? t('clubs.official') : t('club.initiative')}</p>
      <p class="t-foot stats">{[tn('clubs.subscribers', o.subscribers), tn('club.members', o.members)].join(' · ')}</p>
      {#if o.myRole}<span class="tag"><Tag tone="accent">{t('club.myRole', { role: roleLabel({ role: o.myRole, title: o.myTitle, titleKk: o.myTitleKk, titleEn: o.myTitleEn }) })}</Tag></span>
      {:else if o.round}<span class="tag"><Tag tone="success">{t('cast.recruiting', { when: dayMonth(o.round.closesAt) })}</Tag></span>
      {:else if shut && o.members}<span class="tag"><Tag>{t('club.closedTag')}</Tag></span>{/if}
    </div>

    <div class="body">
      {#if session.me?.memberships.some((m) => m.org.id === id)}
        <Group><Row icon={Users} title={t('club.workspace')} accessory="chevron" onclick={() => sheets.studio(id)} /></Group>
      {/if}
      {#if o.description || (shut && !o.members)}
        <div>
          {#if o.description}<p class="t-body selectable">{raw ? o.orig?.description ?? o.description : o.description}</p>
            {#if translated(o, 'description')}<span class="trn"><Button kind="plain" size="s" onclick={() => (raw = !raw)}><AiBadge /> {raw ? t('ai.showTr') : t('ai.showOrig')}</Button></span>{/if}{/if}
          {#if shut && !o.members}<p class="t-foot closed">{t('join.noTeam')}</p>{/if}
        </div>
      {/if}

      {#if o.links.length || rowWrite}
        <Group>
          {#if rowWrite}<Row title={t('join.write')} accessory="external" onclick={write}>{#snippet lead()}<span class="si"><TelegramMark size={20} /></span>{/snippet}</Row>{/if}
          {#each o.links as url (url)}
            {@const s = social(url)}
            <Row title={s.label} accessory="external" onclick={() => openLink(url)}>{#snippet lead()}<span class="si"><SocialIcon kind={s.kind} size={20} /></span>{/snippet}</Row>
          {/each}
        </Group>
      {/if}
      <div class="ask"><AskAi ctx={{ kind: 'club', id: o.id, title: o.name }} hint={t('as.askClub')} /></div>

      {#if chats.length || o.kind === 'app'}
        <Section title={t('oc.title')}>
          <Group>
            {#each chats as c (c.id)}
              {@const line = [c.closed ? t('oc.closed') : t(`chats.${c.kind}`), c.members ? tn(c.kind === 'channel' ? 'clubs.subscribers' : 'chats.members', c.members).replace(String(c.members), compact(c.members)) : ''].filter(Boolean).join(' · ')}
              <!-- closed (no url): shown, but nobody gets in from here -->
              <Row dense title={c.title} subtitle={line} accessory={c.url ? 'external' : 'none'} onclick={c.url ? () => tap(c.url!) : undefined}>
                {#snippet lead()}<ChatAvatar title={c.title} photo={c.photo} kind={c.kind} size={36} />{/snippet}
                {#snippet detail()}{#if !c.url}<span class="lock"><Lock size={17} /></span>{/if}{/snippet}
              </Row>
            {/each}
            {#if o.kind === 'app'}<Row icon={FolderPlus} title={t('oc.folder')} accessory="external" onclick={() => tap(APP_FOLDER)} />{/if}
          </Group>
        </Section>
      {:else if fetched && o.myRights?.includes('profile')}
        <!-- none yet: shown to the club's own team, who can link them (the app's admin does it in Admin) -->
        <Section title={t('oc.title')}>
          <Notice stack text={t('oc.emptyHint')} action={{ label: t('oc.linkChat'), onclick: () => sheets.clubEdit(o.id, 'chats') }} />
        </Section>
      {/if}

      {#if leaders.length}
        <Section title={t('club.lead')}>
          <Group>
            {#each leaders as m (m.person.id)}
              <Row dense title={m.person.name} subtitle={roleLabel(m)} accessory="chevron" onclick={() => sheets.person(m.person.id)}>
                {#snippet lead()}<Avatar person={m.person} size={36} tappable={false} />{/snippet}
              </Row>
            {/each}
            {#if (fetched?.members ?? o.members) > leaders.length && (!o.membersHidden || o.myRole)}
              <Row icon={Users} title={t('club.everyone')} value={String(fetched?.members ?? o.members)} accessory="chevron" onclick={() => sheets.people(o.id, o.name)} />
            {/if}
          </Group>
        </Section>
      {/if}

      <!-- nothing coming but something recent: Recent alone, no empty Coming up above it -->
      {#if events?.length || (events && past && !past.length)}
        <Section title={t('club.upcoming')}>
          {#if events.length}
            <div class="list">{#each events as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} />{/each}</div>
          {:else}
            <Group><EmptyState inline text={t('club.noEvents')} /></Group>
          {/if}
        </Section>
      {/if}
      {#if past?.length}
        <Section title={t('club.recent')}>
          <div class="list">{#each past as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} />{/each}</div>
        </Section>
      {/if}
      {#if posts?.length}
        <Section title={t('page.news')}>
          <Group>
            {#each posts.slice(0, 6) as p (p.id)}
              {@const sub = !p.casting ? ago(p.createdAt) : p.title ? `${t('casting.mark')} · ${castingStatus(p.casting)}` : `${castingWhen(p.casting)} · ${p.casting.place}`}
              {#if !p.title}<Row dense title={t('casting.gone')} subtitle={sub} />
              {:else if p.photo}
                {@const ph = p.photo}
                <Row dense title={p.title} subtitle={sub} onclick={() => play(p)}>
                  {#snippet lead()}<img class="ph" src={ph.url} alt="" loading="lazy" decoding="async" style:object-position={focusPos(ph)} />{/snippet}
                </Row>
              {:else}<Row dense title={p.title} subtitle={sub} onclick={() => play(p)} />{/if}
            {/each}
          </Group>
        </Section>
      {/if}
    </div>
  {/if}

  {#snippet footer()}
    {#if o && !o.myRole}
      {@const sub = t(o.subscribed ? 'club.following' : 'club.follow')}
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
            <Button kind="primary" size="l" full icon={send} onclick={write}>{t('join.write')}</Button>
          {/if}
        {:else}
          <Button kind={o.subscribed ? 'neutral' : 'primary'} size="l" full icon={bell} onclick={() => toggleSub(id)}>{sub}</Button>
        {/if}
      </div>
    {:else if o && fetched?.groupLink}
      <!-- a member the club took through a round: its group, one tap (the bot's "you're in" leads here) -->
      {@const link = fetched.groupLink}
      <Button kind="primary" size="l" full icon={send} onclick={() => tap(link)}>{t('cast.joinGroup')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .hero { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6px; padding: var(--s-2) 0 var(--s-1); }
  .lg { position: relative; transition: transform var(--t-fast) var(--ease); }
  .lg:active { transform: scale(0.95); }
  .cam { position: absolute; right: -4px; bottom: -4px; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--accent); color: var(--on-accent); box-shadow: 0 0 0 3px var(--bg-raised); }
  .name { display: inline-flex; align-items: center; gap: 6px; margin-top: var(--s-2); }
  .ok { color: var(--accent); display: inline-flex; }
  .stats { color: var(--text-2); }
  .tag { margin-top: var(--s-2); max-width: 100%; }
  .tag :global(.chip) { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
  .body { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-4); }
  .trn { display: block; margin: var(--s-1) 0 0 calc(-1 * var(--s-2)); --plain-ink: var(--text-3); }
  .closed { margin-top: var(--s-2); }
  .acts { display: flex; gap: var(--s-2); }
  .acts :global(.btn:not(.full)) { width: var(--ctl-l); padding: 0; }
  .acts :global(.btn:not(.full) .ic) { margin: 0; }
  .ask :global(.ai) { margin: 0; } /* the column's gap spaces it */
  .si { width: 24px; display: grid; place-items: center; }
  .list { display: flex; flex-direction: column; gap: var(--s-2); }
  .ph { width: 40px; height: 40px; border-radius: var(--r-xs); object-fit: cover; }
  .lock { display: inline-flex; color: var(--text-3); }
</style>
