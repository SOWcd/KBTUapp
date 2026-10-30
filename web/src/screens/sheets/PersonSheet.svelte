<script lang="ts">
  // The universal profile card (SPEC §4.12): the same sheet from any avatar or name in the app, with the same
  // hero as Me. Shows only what the viewer may see (§3) — the server filters.
  import { roleName, titleOf } from '../../lib/perms';
  import { achName, tierName } from '../../lib/awards';
  import Sheet from '../../ui/Sheet.svelte';
  import Hero from '../profile/Hero.svelte';
  import Medal from '../../ui/Medal.svelte';
  import Pin from '../../ui/Pin.svelte';
  import Button from '../../ui/Button.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import { api, ApiErr, type Id, type PersonCard } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase, personCard, keepPerson } from '../../lib/state/data.svelte';
  import { data, friendsChanged } from '../../lib/state/data.svelte';
  import { burst } from '../../ui/burst';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth, monthYear } from '../../lib/time';
  import { ROLE_NAME } from '../../lib/perms';
  import { haptic, openLink } from '../../lib/tg';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { nameOf } from '../../lib/short';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  // svelte-ignore state_referenced_locally
  const pre = personCard(id); // a sheet is one person for its life
  // svelte-ignore state_referenced_locally
  let p = $state<PersonCard | null>(session.me?.id === id ? null : pre.card ?? null); // mine: data.myCard is fresher
  let failed = $state<string | null>(null);  // the error's text: the day's limit of strangers' profiles (audit M2) says so
  $effect(() => { pre.p.then((x) => (p = x)).catch((e) => {
    const limit = e instanceof ApiErr && e.code === 'rate_limited';
    if (limit && p) asStranger(); else failed = t(limit ? 'person.tooMany' : 'common.error'); // the server refuses it now
  }); });
  // the plain card from what we know waits a moment: the real one usually lands first, and the plain one jumped into it
  let late = $state(false);
  $effect(() => { const k = setTimeout(() => (late = true), 300); return () => clearTimeout(k); });
  // what the app already knows opens the card at once (me; a friend or a request: name, face, course); the rest fills in
  const known = $derived.by((): PersonCard | null => {
    if (session.me?.id === id && data.myCard) return data.myCard;
    const f = data.friends;
    const row = f && ([...f.friends, ...f.incoming, ...f.outgoing].find((r) => r.person.id === id));
    if (!f || !row) return null;
    const friendship = f.friends.includes(row) ? 'friends' : f.incoming.includes(row) ? 'incoming' : 'requested';
    return { ...row.person, no: null, course: row.course, school: row.school, bio: '', attended: -1, clubs: [], past: [], showcase: [], shelf: [],
      awards: { achievements: [], badges: [] }, friendship, friendsSince: friendship === 'friends' ? row.at : null, going: [] };
  });
  const me = $derived(session.me?.id === id);
  // what they picked for their showcase leads, in their order; the rest after it as the server lists them
  function showcaseFirst<T>(list: T[], key: (x: T) => string): T[] {
    const pick = shown?.shelf ?? [];
    const at = (x: T) => { const i = pick.indexOf(key(x)); return i < 0 ? pick.length : i; };
    return [...list].sort((a, b) => at(a) - at(b));
  }
  const shown = $derived(p ?? (late || me ? known : null));

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
  async function act(job: () => Promise<unknown>, done: () => void, stranger = false) {
    acting = true;
    try { await job(); done(); friendsChanged(); await reload(stranger); }
    catch (e) { haptic.error(); say(e instanceof ApiErr && e.code === 'rate_limited' ? t('fr.tooMany') : t('common.error'), 'pleading_face_3d'); }
    finally { acting = false; }
  }
  const welcome = () => { haptic.ok(); burst(); say(t('fr.accepted', { name: shown!.name }), 'partying_face_3d'); };
  async function ask() {
    acting = true;
    try {
      const r = await api.askFriend(id);
      if (r.friendship === 'friends') welcome(); else { haptic.ok(); say(t('person.requestSent'), 'raising_hands_3d_default'); }
      friendsChanged(); await reload();
    } catch (e) { haptic.error(); say(e instanceof ApiErr && e.code === 'rate_limited' ? t('fr.tooMany') : t('common.error'), 'pleading_face_3d'); }
    finally { acting = false; }
  }
  const accept = () => act(() => api.answerFriend(id, true), welcome);
  const decline = () => act(() => api.answerFriend(id, false), () => { haptic.soft(); say(t('fr.declined'), 'waving_hand_3d_default'); }, true);
  const takeBack = () => act(() => api.takeBackRequest(id), () => { haptic.soft(); say(phrase('say.takenBack'), 'waving_hand_3d_default'); }, true);
  async function unfriend() {
    if (!shown || !(await sheets.ask({ title: t('fr.removeAsk', { name: shown.name }), text: t('fr.removeText'), ok: t('fr.remove'), cancel: t('common.cancel'), danger: true }))) return;
    await act(() => api.unfriend(id), () => { haptic.soft(); say(t('fr.removed'), 'waving_hand_3d_default'); }, true);
  }
</script>

<Sheet {overlay} title={shown?.name ?? ''}>
  {#if shown}
    <!-- no award shelf on the card here: the sheet lists every award below it, the showcase first (PLAN 89: "Awards"
         showed twice) -->
    <Hero p={shown} shelf={false} />

    {#if !me && session.me?.student}
      <div class="act">
        {#if shown.friendship === 'friends'}
          <p class="t-foot friends">{t('person.friendsSince', { date: shown.friendsSince ? dayMonth(shown.friendsSince) : '' })}</p>
          <div class="two">
            {#if shown.username}<Button kind="secondary" size="l" full onclick={() => openLink(`https://t.me/${encodeURIComponent(shown!.username!)}`)}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('person.writeShort')}</Button>{/if}
            <Button kind="primary" size="l" full onclick={() => sheets.inviteTo(id, shown!.name)}>{t('inv.toButton')}</Button>
          </div>
        {:else if shown.username}<!-- a teammate: straight to their Telegram chat -->
          <Button kind="secondary" size="l" full onclick={() => openLink(`https://t.me/${encodeURIComponent(shown!.username!)}`)}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('person.write')}</Button>
        {/if}
        {#if shown.friendship === 'requested'}
          <Button kind="neutral" size="l" full disabled>{t('person.requestSent')}</Button>
          <button class="quiet" disabled={acting} onclick={takeBack}>{t('fr.takeBackReq')}</button>
        {:else if shown.friendship === 'incoming'}
          <div class="two">
            <Button kind="neutral" size="l" full disabled={acting} onclick={decline}>{t('fr.decline')}</Button>
            <Button kind="primary" size="l" full loading={acting} onclick={accept}>{t('fr.acceptReq')}</Button>
          </div>
        {:else if shown.friendship !== 'friends'}
          <Button kind="primary" size="l" full loading={acting} onclick={ask}>{t('person.addFriend')}</Button>
        {/if}
      </div>
    {/if}

    {#if !p && failed}
      <p class="t-body dim pad">{failed}</p>
    {:else if !p}
      <div class="skel" aria-hidden="true"><span class="s2"></span><span class="s3"></span></div>
    {:else}
    <!-- everything they have earned, right under the card: achievements with their level, then badges; what they haven't earned yet stays on their own Awards page -->
    {@const earned = showcaseFirst(p.awards.achievements.filter((a) => a.level > 0), (a) => a.code)}
    {@const badges = showcaseFirst(p.awards.badges, (b) => 'b' + b.eventId)}
    {#if p.going.length}
      <h3 class="sec">{t('person.goes')}</h3>
      <div class="going">{#each p.going as e (e.id)}<EventRow {e} />{/each}</div>
    {/if}
    <h3 class="sec">{t('person.awards')}{earned.length + badges.length ? ' · ' + (earned.length + badges.length) : ''}</h3>
    {#if earned.length + badges.length}
      <div class="grid">
        {#each earned as a (a.code)}
          <button class="cell" onclick={() => sheets.award({ key: 'a' + a.code, ach: a, name: achName(a), sub: tierName(a) }, me)}><Medal {a} size={52} /><i>{achName(a)}{#if tierName(a)}<br />{tierName(a)}{/if}</i></button>
        {/each}
        {#each badges as b (b.eventId)}
          <button class="cell" onclick={() => sheets.award({ key: 'b' + b.eventId, badge: b, name: b.title, sub: dayMonth(b.at) })}><Pin emoji={b.emoji} color={b.color} size={52} /><i>{b.title}</i></button>
        {/each}
      </div>
    {:else}
      <p class="t-foot none">{t('person.noAwards')}</p>
    {/if}
    {#if p.clubs.length}
      <h3 class="sec">{t('person.clubs')}</h3>
      <div class="clubs">
        {#each p.clubs as m (m.org.id)}
          <span class="club"><OrgLogo org={m.org} size={20} /><b>{nameOf(m.org)}</b>{#if m.role}<i>{roleName(m.role, titleOf(m))}</i>{/if}</span>
        {/each}
      </div>
    {/if}
    {#if p.limited}<p class="t-foot none lim">{t('person.limited')}</p>{/if}
    {#if p.past?.length}
      <!-- where they were before, written down by itself -->
      <h3 class="sec">{t('person.past')}</h3>
      <div class="past">
        {#each p.past as h, i (i)}
          <div class="was"><OrgLogo org={h.org} size={28} /><span class="tx"><b class="ellipsis">{nameOf(h.org)}</b>
            <i>{h.role ? ROLE_NAME[h.role] + ' · ' : ''}{monthYear(h.since)}{monthYear(h.since) === monthYear(h.until) ? '' : ' – ' + monthYear(h.until)}</i></span></div>
        {/each}
      </div>
    {/if}

    {#if p.forum?.skills.length}
      <h3 class="sec">{t('fo.skillsOf')}</h3>
      <div class="skills">{#each p.forum.skills as s (s.id)}<span class="chip">{s.name}</span>{/each}{#if p.forum.open}<span class="chip open">{t('fo.open')}</span>{/if}</div>
    {/if}

    {#if !me && session.me?.student}
      <!-- a nick, an own photo or "about me" that shouldn't be there: to the admin's queue -->
      <div class="rep">
        <button class="quiet" onclick={() => sheets.report('user', id, shown.name)}>{t('person.report')}</button>
        {#if shown.friendship === 'friends'}<button class="quiet" disabled={acting} onclick={unfriend}>{t('fr.remove')}</button>{/if}
      </div>
    {/if}
    {/if}
  {:else if failed}
    <p class="t-body dim pad">{failed}</p>
  {:else}
    <div class="skel"><span class="s1"></span><span class="s2"></span><span class="s3"></span></div>
  {/if}
</Sheet>

<style>



  .act { margin: 14px 0 4px; display: flex; flex-direction: column; align-items: center; gap: 4px; }
  .act > :global(.btn) { width: 100%; }
  .two { display: flex; gap: 8px; width: 100%; }
  .two :global(.btn.full) { flex: 1 1 auto; width: auto; min-width: 0; }
  .two :global(.btn.full:first-child:not(:last-child)) { flex: 0 0 auto; }
  .quiet { padding: 8px 10px; font: 600 13.5px/1 var(--font-text); color: var(--text-3); }
  .rep { display: flex; flex-direction: column; align-items: center; gap: 8px; margin-top: 22px; text-align: center; }
  .friends { text-align: center; color: var(--text-2); }
  /* section titles in the type scale of mockup v24 (sentence case, not the old caps caption) */
  .skills { display: flex; flex-wrap: wrap; gap: 6px; }
  .skills .chip { display: inline-flex; align-items: center; height: 28px; padding: 0 10px; border-radius: var(--r-full); background: var(--surface-2); font: 600 13px/1 var(--font-text); }
  .skills .open { background: var(--success-soft); color: var(--success-text); }
  .sec { margin: 26px 2px 12px; font: 760 var(--fs-sec)/1.1 var(--font-display); letter-spacing: -0.025em; text-transform: none; color: var(--text); }
  .clubs { display: flex; flex-wrap: wrap; gap: 6px; }
  .club { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px 6px 6px; border-radius: var(--r-full); background: var(--surface-2); }
  .club b { font: 620 13px/1 var(--font-text); }
  .club i { font: 600 11px/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .going { display: flex; flex-direction: column; gap: 8px; }
  .past { display: flex; flex-direction: column; gap: 10px; }
  .was { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .was .tx { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .was b { font: 620 14px/1.2 var(--font-text); }
  .was i { font: 550 12px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }

  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px 6px; }
  .cell { display: flex; flex-direction: column; align-items: center; gap: 6px; transition: transform var(--t-fast) var(--ease); }
  .cell:active { transform: scale(0.94); }
  .none { margin: 0 4px; }
  .lim { margin-top: 18px; }
  .cell i { font: 550 10.5px/1.2 var(--font-text); font-style: normal; color: var(--text-2); text-align: center; }


  .pad { padding: 20px 0; }
  .skel { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 24px 0 40px; }
  .skel span { display: block; border-radius: 12px; background: var(--surface-2); animation: pulse 1.2s ease-in-out infinite; }
  .s1 { width: 92px; height: 92px; border-radius: 50% !important; }
  .s2 { width: 160px; height: 22px; }
  .s3 { width: 110px; height: 14px; }
  @keyframes pulse { 50% { opacity: 0.5; } }
</style>
