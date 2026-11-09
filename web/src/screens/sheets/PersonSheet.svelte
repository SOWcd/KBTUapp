<script lang="ts">
  // The universal profile card (SPEC §4.12): the same sheet from any avatar or name in the app, with the same
  // hero as Me. Shows only what the viewer may see (§3) — the server filters.
  import { roleName, titleOf } from '../../lib/perms';
  import { achKey, achName, tierName } from '../../lib/awards';
  import Sheet from '../../ui/Sheet.svelte';
  import UserRound from '@lucide/svelte/icons/user-round';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import Hero from '../profile/Hero.svelte';
  import Medal from '../../ui/Medal.svelte';
  import Pin from '../../ui/Pin.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Tag from '../../ui/Tag.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import { api, ApiErr, type Friendship, type Id, type LinkCard, type PersonCard } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase, personCard, keepPerson } from '../../lib/state/data.svelte';
  import { data, friendsChanged } from '../../lib/state/data.svelte';
  import { burst } from '../../ui/burst';
  import { sheets } from '../../lib/state/sheets';
  import { asStudent, session } from '../../lib/state/session.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth, monthYear } from '../../lib/time';
  import { ROLE_NAME } from '../../lib/perms';
  import { haptic, openLink } from '../../lib/tg';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { nameOf } from '../../lib/short';

  // invite: opened by their invite link (r_<code>, the one link, Nov 2): the landing. A big "Add as a friend" makes
  // friends in one tap, no request (sharing the link was their yes); guests see the card too and sign in at the tap
  let { overlay, id, invite }: { overlay: Overlay; id: Id; invite?: { code: string; card: LinkCard } } = $props();

  // svelte-ignore state_referenced_locally
  const pre = personCard(id); // a sheet is one person for its life
  // svelte-ignore state_referenced_locally
  let p = $state<PersonCard | null>(session.me?.id === id ? null : pre.card ?? null); // mine: data.myCard is fresher
  let failed = $state<string | null>(null);  // the error's text: the day's limit of strangers' profiles (audit M2) says so
  $effect(() => { pre.p.then((x) => (p = x)).catch((e) => {
    const limit = e instanceof ApiErr && e.code === 'rate_limited';
    if (limit && p) asStranger(); else if (!invite || session.me?.student) failed = t(limit ? 'person.tooMany' : 'common.error'); // the server refuses it now
  }); });
  // the plain card from what we know waits a moment: the real one usually lands first, and the plain one jumped into it
  let late = $state(false);
  $effect(() => { const k = setTimeout(() => (late = true), 300); return () => clearTimeout(k); });
  // what the app already knows opens the card at once (me; a friend or a request: name, face, course); the rest fills in
  const known = $derived.by((): PersonCard | null => {
    if (session.me?.id === id && data.myCard) return data.myCard;
    const f = data.friends;
    const row = f && ([...f.friends, ...f.incoming, ...f.outgoing].find((r) => r.person.id === id));
    if ((!f || !row) && invite) return { ...invite.card.person, no: null, course: null, school: null, bio: '', attended: -1, clubs: [], past: [], showcase: [], shelf: [],
      awards: { achievements: [], badges: [] }, friendship: invite.card.friendship === 'self' ? 'none' : invite.card.friendship, friendsSince: null, going: [] };
    if (!f || !row) return null;
    const friendship = f.friends.includes(row) ? 'friends' : f.incoming.includes(row) ? 'incoming' : 'requested';
    return { ...row.person, no: null, course: row.course, school: row.school, bio: '', attended: -1, clubs: [], past: [], showcase: [], shelf: [],
      awards: { achievements: [], badges: [] }, friendship, friendsSince: friendship === 'friends' ? row.at : null, going: [] };
  });
  const me = $derived(session.me?.id === id);
  // the card lands in two steps: the badge, then (a task later, the skeleton under it meanwhile) the lists below it;
  // both at once were one long task in the middle of the sheet's rise
  let below = $state(false);
  $effect(() => {
    if (!p || below) return;
    let k = 0;
    const f = requestAnimationFrame(() => (k = setTimeout(() => (below = true)) as unknown as number));
    return () => { cancelAnimationFrame(f); clearTimeout(k); };
  });
  // what they picked for their showcase leads, in their order; the rest after it as the server lists them
  function showcaseFirst<T>(list: T[], key: (x: T) => string): T[] {
    const pick = shown?.shelf ?? [];
    const at = (x: T) => { const i = pick.indexOf(key(x)); return i < 0 ? pick.length : i; };
    return [...list].sort((a, b) => at(a) - at(b));
  }
  // a friend tap moves the card at once (the speed rule): its answer-to-be until the server's card replaces it
  let next = $state<Friendship | null>(null);
  const shown = $derived.by(() => { const c = p ?? (late || me ? known : null); return c && next ? { ...c, friendship: next } : c; });

  // friendship (§4.7): ask, answer, take back, or end it quietly; the card reloads after a change (where they go)
  let acting = $state(false);

  // the card again after a change. Now a stranger (unfriended, declined, taken back) past the day's limit of strangers,
  // the server refuses it: the stranger's view of what we have then (no card yet: the limit's message); else as before
  const reload = async (stranger = false) => {
    try { p = await api.person(id); keepPerson(p); }
    catch (e) {
      if (!stranger || !(e instanceof ApiErr && e.code === 'rate_limited')) throw e;
      if (!p) { failed = t('person.tooMany'); return; }
      asStranger();
    }
  };
  function asStranger() {
    p = { ...p!, friendship: 'none', friendsSince: null, clubs: [], past: [], going: [], awards: { ...p!.awards, badges: [] },
          shelf: p!.shelf.filter((k) => !k.startsWith('b')), username: null, limited: true };
    keepPerson(p);
  }
  // the card moves first; the server's answer settles it (rolled back on an error) and the card refetches quietly
  async function act<R>(job: () => Promise<R>, done: (r: R) => void, to: Friendship, stranger = false) {
    if (acting) return;
    acting = true; next = to; haptic.tap();
    try { done(await job()); }
    catch (e) {
      next = null; haptic.error();
      const closed = e instanceof ApiErr && e.code === 'closed';  // they switched requests off just now
      if (closed && p) p = { ...p, closed };
      say(e instanceof ApiErr && e.code === 'rate_limited' ? t('fr.tooMany') : closed ? t('fr.closed') : t('common.error'), 'warning_3d');
      return;
    } finally { acting = false; }
    friendsChanged();
    reload(stranger).catch(() => {}).finally(() => (next = null));
  }
  const welcome = () => { haptic.ok(); burst(); say(t('fr.accepted', { name: shown!.name }), 'partying_face_3d'); };
  const asked = (r: { friendship: Friendship }) => { if (r.friendship === 'friends') welcome(); else { haptic.ok(); say(t('person.requestSent'), 'raising_hands_3d_default'); } };
  const ask = () => act(() => api.askFriend(id), asked, 'requested');
  // the invite's tap: a guest signs in first (a Microsoft round trip comes back to this landing: `again`); one tap, friends
  function addByLink() {
    if (!invite) return;
    const { code } = invite;
    asStudent(() => act(() => api.addByLink(code), asked, 'friends'), 'r_' + code);
  }
  const accept = () => act(() => api.answerFriend(id, true), welcome, 'friends');
  const decline = () => act(() => api.answerFriend(id, false), () => { haptic.soft(); say(t('fr.declined'), 'waving_hand_3d_default'); }, 'none', true);
  const takeBack = () => act(() => api.takeBackRequest(id), () => { haptic.soft(); say(phrase('say.takenBack'), 'waving_hand_3d_default'); }, 'none', true);
  async function unfriend() {
    if (!shown || !(await sheets.ask({ title: t('fr.removeAsk', { name: shown.name }), text: t('fr.removeText'), ok: t('fr.remove'), cancel: t('common.cancel'), danger: true }))) return;
    await act(() => api.unfriend(id), () => { haptic.soft(); say(t('fr.removed'), 'waving_hand_3d_default'); }, 'none', true);
  }
</script>

<Sheet {overlay} icon={UserRound} title={t('cap.person')}>
  {#if shown}
    <!-- no award shelf on the card here: the sheet lists every award below it, the showcase first (PLAN 89: "Awards"
         showed twice) -->
    <Hero p={shown} shelf={false} />

    {#if invite && !me && !session.me?.student}<!-- a guest on the landing: the button signs in, then adds -->
      <div class="act">
        <p class="t-foot friends">{t('fr.invitesYou')}</p>
        <Button kind="primary" size="l" full loading={acting} onclick={addByLink}>{t('person.addFriend')}</Button>
      </div>
    {:else if !me && session.me?.student}
      <div class="act">
        {#if shown.friendship === 'friends'}
          <p class="t-foot friends">{t('person.friendsSince', { date: shown.friendsSince ? dayMonth(shown.friendsSince) : '' })}</p>
          <div class="two">
            {#if shown.username}<Button kind="secondary" size="l" full onclick={() => openLink(`https://t.me/${encodeURIComponent(shown!.username!)}`)}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('person.writeShort')}</Button>{/if}
            <Button kind="secondary" size="l" full onclick={() => sheets.inviteTo(id, shown!.name)}>{#snippet icon()}<CalendarPlus size={18} />{/snippet}{t('inv.toButton')}</Button>
          </div>
        {:else if shown.username}<!-- a teammate: straight to their Telegram chat -->
          <Button kind="secondary" size="l" full onclick={() => openLink(`https://t.me/${encodeURIComponent(shown!.username!)}`)}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('person.write')}</Button>
        {/if}
        {#if invite && shown.friendship !== 'friends' && shown.friendship !== 'incoming'}<!-- the landing: one tap, friends (my waiting request too) -->
          <p class="t-foot friends">{t('fr.invitesYou')}</p>
          <Button kind="primary" size="l" full loading={acting} onclick={addByLink}>{t('person.addFriend')}</Button>
        {:else if shown.friendship === 'requested'}
          <Button kind="neutral" size="l" full disabled>{t('person.requestSent')}</Button>
          <span class="quiet"><Button kind="plain" size="s" disabled={acting} onclick={takeBack}>{t('fr.takeBackReq')}</Button></span>
        {:else if shown.friendship === 'incoming'}
          <div class="two">
            <Button kind="neutral" size="l" full disabled={acting} onclick={decline}>{t('fr.decline')}</Button>
            <Button kind="primary" size="l" full loading={acting} onclick={accept}>{t('fr.acceptReq')}</Button>
          </div>
        {:else if shown.friendship !== 'friends' && shown.closed}<!-- they take no requests: the place stays, quiet -->
          <Button kind="neutral" size="l" full disabled>{t('fr.closed')}</Button>
        {:else if shown.friendship !== 'friends'}
          <Button kind="primary" size="l" full loading={acting} onclick={ask}>{t('person.addFriend')}</Button>
        {/if}
      </div>
    {/if}

    {#if !p && failed}
      <p class="t-body dim pad">{failed}</p>
    {:else if !p || !below}
      <div class="below"><Skeleton kind="rows" n={2} /></div>
    {:else}
    <!-- everything they have earned, right under the card: achievements with their level, then badges; what they haven't earned yet stays on their own Awards page -->
    {@const earned = showcaseFirst(p.awards.achievements.filter((a) => a.level > 0), (a) => a.code)}
    {@const badges = showcaseFirst(p.awards.badges, (b) => 'b' + b.eventId)}
    <div class="below">
      {#if p.going.length}
        <Section title={t('person.goes')}>
          <div class="going">{#each p.going as e (e.id)}<EventRow {e} />{/each}</div>
        </Section>
      {/if}
      <Section title={t('person.awards')} count={earned.length + badges.length}>
        {#if earned.length + badges.length}
          <div class="grid">
            {#each earned as a (achKey(a))}
              <button class="cell" onclick={() => sheets.award({ key: 'a' + a.code, ach: a, name: achName(a), sub: tierName(a) }, me)}><Medal {a} size={52} /><i>{achName(a)}{#if tierName(a)}<br />{tierName(a)}{/if}</i></button>
            {/each}
            {#each badges as b (b.eventId)}
              <button class="cell" onclick={() => sheets.award({ key: 'b' + b.eventId, badge: b, name: b.title, sub: dayMonth(b.at) })}><Pin emoji={b.emoji} color={b.color} size={52} /><i>{b.title}</i></button>
            {/each}
          </div>
        {:else}
          <Group><EmptyState inline text={t('person.noAwards')} /></Group>
        {/if}
      </Section>
      {#if p.clubs.length}
        <Section title={t('person.clubs')}>
          <Group>
            {#each p.clubs as m (m.org.id)}
              <Row dense title={nameOf(m.org)} value={m.role ? roleName(m.role, titleOf(m)) : undefined}>{#snippet lead()}<OrgLogo org={m.org} size={28} />{/snippet}</Row>
            {/each}
          </Group>
        </Section>
      {/if}
      {#if p.limited}<p class="t-foot lim">{t('person.limited')}</p>{/if}
      {#if p.past?.length}
        <!-- where they were before, written down by itself -->
        <Section title={t('person.past')}>
          <Group>
            {#each p.past as h, i (i)}
              <Row dense title={nameOf(h.org)} subtitle={(h.role ? ROLE_NAME[h.role] + ' · ' : '') + monthYear(h.since) + (monthYear(h.since) === monthYear(h.until) ? '' : ' – ' + monthYear(h.until))}>
                {#snippet lead()}<OrgLogo org={h.org} size={28} />{/snippet}
              </Row>
            {/each}
          </Group>
        </Section>
      {/if}

      {#if p.forum?.skills.length}
        <Section title={t('fo.skillsOf')}>
          <div class="skills">{#each p.forum.skills as s (s.id)}<Tag>{s.name}</Tag>{/each}{#if p.forum.open}<Tag tone="success">{t('fo.open')}</Tag>{/if}</div>
        </Section>
      {/if}

      {#if !me && session.me?.student}
        <!-- a nick, an own photo or "about me" that shouldn't be there: to the admin's queue -->
        <div class="rep quiet">
          <Button kind="plain" size="s" onclick={() => sheets.report('user', id, shown.name)}>{t('person.report')}</Button>
          {#if shown.friendship === 'friends'}<Button kind="plain" size="s" destructive disabled={acting} onclick={unfriend}>{t('fr.remove')}</Button>{/if}
        </div>
      {/if}
    </div>
    {/if}
  {:else if failed}
    <p class="t-body dim pad">{failed}</p>
  {:else}
    <div class="skel"><span class="s1"></span><span class="s2"></span><span class="s3"></span></div>
  {/if}
</Sheet>

<style>
  /* a sheet's buttons stand apart (owner, Nov 3: "Write" over "Decline / Accept" looked cramped, as if overlapping) */
  .act { margin: var(--s-5) 0 var(--s-1); display: flex; flex-direction: column; align-items: center; gap: var(--s-3); }
  .act > :global(.btn) { width: 100%; }
  .two { display: flex; gap: var(--s-3); width: 100%; }
  .two :global(.btn.full) { flex: 1 1 auto; width: auto; min-width: 0; }
  .two :global(.btn.neutral.full) { flex: 0 0 auto; }
  .quiet { --plain-ink: var(--text-3); }
  .rep { display: flex; flex-direction: column; align-items: center; gap: var(--s-1); text-align: center; }
  .friends { text-align: center; color: var(--text-2); }
  .below { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-6); }
  .skills { display: flex; flex-wrap: wrap; gap: 6px; }
  .going { display: flex; flex-direction: column; gap: var(--s-2); }
  .lim { margin: 0 var(--s-1); }

  /* the medals and pins: their art, in a grid of four */
  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--s-3) 6px; }
  .cell { display: flex; flex-direction: column; align-items: center; gap: 6px; transition: transform var(--t-fast) var(--ease); }
  .cell:active { transform: scale(0.94); }
  .cell i { font: 500 var(--fs-micro)/1.2 var(--font-text); font-style: normal; color: var(--text-2); text-align: center; }

  .pad { padding: var(--s-5) 0; }
  /* the hero's shape while the card loads (ui/Skeleton has no avatar-and-name shape) */
  .skel { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--s-6) 0 var(--s-10); }
  .skel span { display: block; border-radius: var(--r-full); background: var(--fill); animation: pulse 1.4s ease-in-out infinite alternate; }
  .s1 { width: 92px; height: 92px; }
  .s2 { width: 160px; height: 22px; }
  .s3 { width: 110px; height: 14px; }
  @keyframes pulse { to { opacity: 0.45; } }
</style>
