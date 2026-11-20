<script lang="ts">
  // A team event's teams, the organizers' (the "events" right; server evteams.py): every team with its people (the
  // captain first), then those with no team yet; "Form teams" fills the teams looking for people and makes new ones of
  // the rest; a person's ⌃⌄ moves them to another team or to none, after a confirm. All fixed once the event starts.
  // Someone without the teams' own consent waits alone, marked at the row's end, never placed (server evteams.py);
  // its menu: the bot reminds them (a template, once a day). Every menu ends with taking the person (or their whole
  // team) off the event, after a confirm.
  // A paid event: a player whose receipt nobody checked yet is marked too, and Form teams waits for them; a refund is
  // recorded by rejecting the receipt in the attendees list, which takes the player out of the team. A short team says
  // how many it lacks; a paid event's top line counts short teams and paid players with none. Form teams completes the
  // fullest team first; once sign-up closed it fills every short team, before that only those looking (or all, if the
  // organizer says so in a second question).
  import { teamSize } from '../../lib/teams';
  import { onMount } from 'svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { api, ApiErr, staffEvents, type Id, type PersonRef, type TeamsBoard } from '../../lib/api';
  import { errorText, studioChanged } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import type { MenuItem } from '../../ui/menu';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();
  let b = $state<TeamsBoard | null>(null);
  onMount(() => { api.teams(id).then((x) => (b = x)).catch(() => {}); });
  const fail = (e: unknown) => { haptic.error(); say(e instanceof ApiErr ? errorText(e) : t('common.error'), 'pleading_face_3d'); };

  // the move at once (the same rules as the server's: a team that empties goes), the server's list after
  function moved(x: TeamsBoard, p: PersonRef, to: Id | null): TeamsBoard {
    const teams = x.teams.map((tm) => ({ ...tm, members: tm.members.filter((m) => m.id !== p.id) }))
      .map((tm) => (tm.id === to ? { ...tm, members: [...tm.members, p] } : tm))
      .filter((tm) => tm.members.length)
      .map((tm) => ({ ...tm, captain: tm.members[0].id }));
    return { ...x, teams, solo: to === null ? [...x.solo.filter((m) => m.id !== p.id), { ...p, consent: true }] : x.solo.filter((m) => m.id !== p.id) };
  }
  async function move(p: PersonRef, to: Id | null, name: string) {
    if (!b || !(await sheets.ask({ title: to === null ? t('tm.toSoloAsk', { name: p.name }) : t('tm.moveAsk', { name: p.name, team: name }),
      text: to === null ? undefined : t('tm.moveText'), ok: t('tm.move'), cancel: t('common.cancel') }))) return;
    const was = b;
    b = moved(b, p, to); haptic.tap();
    try { b = await api.teamsMove(id, p.id, to); haptic.ok(); } catch (e) { b = was; fail(e); }
  }
  // someone signed up without the teams consent: the bot's template, at most once a day (server evteams.remind)
  async function remind(p: PersonRef) {
    haptic.tap();
    try {
      const r = await api.teamsRemind(id, p.id);
      if (r.consent || r.off) { b = await api.teams(id); return; } // agreed or withdrew meanwhile: the board says which
      haptic.ok(); say(t(r.queued ? 'tm.reminded' : 'tm.remindedToday'), 'speech_balloon_3d');
    } catch (e) { fail(e); }
  }
  // off the event (server seats.remove_seats): one person, or a whole team at once; the bot tells each, the waitlist
  // moves in, a paid one's receipt stays (the refund is the club's, by hand)
  async function out(p: PersonRef | null, tm: { id: Id; name: string; members: PersonRef[] } | null) {
    if (!b || !(await sheets.ask({ title: tm ? t('tm.removeTeamAsk', { team: tm.name }) : t('att.removeAsk', { name: p!.name }),
      text: tm ? t('tm.removeTeamText', { n: tm.members.length }) + (b.paid ? ' ' + t('tm.refund') : '') : t(b.paid ? 'att.removePaid' : 'att.removeText'),
      ok: t(tm ? 'tm.removeTeam' : 'att.remove'), cancel: t('common.cancel'), danger: true }))) return;
    const was = b, gone = new Set(tm ? tm.members.map((m) => m.id) : [p!.id]);
    b = { ...b, teams: b.teams.map((x) => ({ ...x, members: x.members.filter((m) => !gone.has(m.id)) })).filter((x) => x.members.length)
      .map((x) => ({ ...x, captain: x.members[0].id })), solo: b.solo.filter((m) => !gone.has(m.id)) };
    haptic.tap();
    try {
      await (tm ? api.removeTeam(id, tm.id, tm.members.map((m) => m.id)) : api.removePerson(id, p!.id));
      haptic.ok(); say(t(tm ? 'tm.teamRemoved' : 'att.removed'), 'waving_hand_3d_default'); studioChanged();
      b = await api.teams(id);
    } catch (e) {
      b = was;
      if (e instanceof ApiErr && e.message === 'changed') { haptic.error(); say(t('tm.changed'), 'warning_3d'); b = await api.teams(id).catch(() => was); }
      else if (e instanceof ApiErr && e.message === 'checked_in') { haptic.error(); say(t('att.removeCame'), 'warning_3d'); } else fail(e);
    }
  }
  // the app's admin from Admin never on a paid event (money is the club's; server remove_seats)
  const plain = $derived(staffEvents.has(id) && !session.me?.founder);
  const outItems = (p: PersonRef, tm: { id: Id; name: string; members: PersonRef[] } | null): MenuItem[] => plain && b?.paid ? [] : [
    { label: t('att.remove'), destructive: true, onselect: () => out(p, null) },
    ...(tm ? [{ label: t('tm.removeTeam'), destructive: true, onselect: () => out(null, tm) }] : []),
  ];
  // "Write in Telegram", as on the attendees' list (a club lead, Nov 20: "send me the solo players' usernames"):
  // one @username at a time, logged; none: the bot asks them to write instead (server organizing.attendee_contact)
  async function write(p: PersonRef) {
    try {
      const { username, asked } = await api.attendeeContact(id, p.id);
      if (username) { openLink(`https://t.me/${encodeURIComponent(username)}`); return; }
      if (asked) { say(t('att.asked'), 'waving_hand_3d_default'); return; }
      if (!(await sheets.ask({ title: t('att.askTitle'), text: t('att.askText'), ok: t('att.askOk'), cancel: t('common.cancel') }))) return;
      await api.askToWrite(id, p.id);
      haptic.ok(); say(t('att.asked'), 'waving_hand_3d_default');
    } catch (e) {
      haptic.error();
      say(!(e instanceof ApiErr) ? t('common.error') : e.code === 'rate_limited' ? t('att.writeTooMany') : e.message === 'own_username' ? t('att.ownUsername') : t('common.error'), 'warning_3d');
    }
  }
  const some = (m: MenuItem[]) => (m.length ? m : undefined); // an empty menu draws no dots
  const writeItem = (p: PersonRef): MenuItem[] => plain || p.id === session.me?.id ? [] : [{ label: t('person.write'), onselect: () => void write(p) }];
  const menuOf = (p: PersonRef, from: Id | null): MenuItem[] => !b || b.locked ? writeItem(p) : [...writeItem(p),
    ...b.teams.filter((tm) => tm.id !== from).map((tm) => ({ label: t('tm.toTeam', { team: tm.name, n: tm.members.length, max: b!.max }), disabled: tm.members.length >= b!.max, onselect: () => move(p, tm.id, tm.name) })),
    ...(from !== null ? [{ label: t('tm.toSolo'), onselect: () => move(p, null, '') }] : []),
    ...outItems(p, b.teams.find((tm) => tm.id === from) ?? null),
  ];

  let forming = $state(false);
  async function form() {
    if (!b || forming || !(await sheets.ask({ title: t('tm.formAsk'), text: t(b.regShut ? 'tm.formTextAll' : 'tm.formText'), ok: t('tm.form'), cancel: t('common.cancel') }))) return;
    const closedShort = !b.regShut && b.teams.some((x) => !x.open && x.members.length < b!.max);
    const all = closedShort && (await sheets.ask({ title: t('tm.fillAllAsk'), text: t('tm.fillAllText'), ok: t('tm.fillAll'), cancel: t('tm.onlyOpen') }));
    forming = true; haptic.tap();
    try {
      b = await api.teamsForm(id, all);
      const skipped = b.noConsent ? ' · ' + t('tm.skipped', { n: b.noConsent }) : ''; // no consent yet: not placed
      if (!b.placed) { haptic.soft(); say(t('tm.nothing') + skipped, 'thinking_face_3d'); }
      else { haptic.ok(); say((b.left ? t('tm.formedLeft', { n: b.placed, left: b.left }) : t('tm.formed', { n: b.placed })) + skipped, 'party_popper_3d'); }
    } catch (e) { fail(e); }
    finally { forming = false; }
  }
</script>

<Sheet {overlay} icon={UsersRound} full title={t('tm.board')}>
  {#if b}
    <p class="t-foot sub">{b.cap ? t('tm.sizeCap', { size: teamSize(b.min, b.max), cap: b.cap }) : t('tm.size', { size: teamSize(b.min, b.max) })}{b.locked ? ' · ' + t('tm.locked') : ''}</p>
    {#if b.paid}<p class="t-foot sub">{t('tm.summary', { short: b.teams.filter((x) => x.members.length < b!.max).length, solo: b.solo.length })}</p>{/if}
    {#if b.unchecked.length}<p class="t-foot sub">{t('tm.uncheckedNote', { n: b.unchecked.length })}</p>{/if}
    {#if !b.teams.length && !b.solo.length}
      <EmptyState inline text={t('tm.none')} />
    {:else}
      <div class="list">
        {#each b.teams as tm (tm.id)}
          <Group caption="{tm.name} · {tm.members.length}/{b.max}{tm.members.length < b.max ? ' · ' + t('tm.shortBy', { n: b.max - tm.members.length }) : ''}{tm.open && tm.members.length < b.max ? ' · ' + t('tm.looking') : ''}">
            {#each tm.members as p (p.id)}
              <Row dense title={p.name} subtitle={p.id === tm.captain ? t('tm.captain') : undefined} value={b.unchecked.includes(p.id) ? t('tm.unchecked') : undefined} menu={some(menuOf(p, tm.id))}>
                {#snippet lead()}<Avatar person={p} size={32} />{/snippet}
              </Row>
            {/each}
          </Group>
        {/each}
        {#if b.solo.length}
          <Group caption="{t('tm.solo')} · {b.solo.length}">
            {#each b.solo as p (p.id)}
              <Row dense title={p.name} value={p.off ? t('tm.offConsent') : !p.consent ? t('tm.noConsent') : b.unchecked.includes(p.id) ? t('tm.unchecked') : undefined} menu={some(b.locked ? writeItem(p) : p.off ? [...writeItem(p), ...outItems(p, null)] : !p.consent ? [...writeItem(p), { label: t('tm.remind'), onselect: () => remind(p) }, ...outItems(p, null)] : menuOf(p, null))}>
                {#snippet lead()}<Avatar person={p} size={32} />{/snippet}
              </Row>
            {/each}
          </Group>
        {/if}
      </div>
    {/if}
  {/if}
  {#snippet footer()}
    {#if b && !b.locked}<Button kind="primary" size="l" full loading={forming} disabled={!b.solo.length} onclick={form}>{t('tm.form')}</Button>{/if}
  {/snippet}
</Sheet>

<style>
  .sub { margin: 2px var(--s-1) 0; }
  .list { display: flex; flex-direction: column; gap: var(--s-5); margin-top: var(--s-4); }
</style>
