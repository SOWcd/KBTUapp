<script lang="ts">
  import { withNick } from '../../lib/perms';
  // Profile → Friends, a sheet from the row under my badge (SPEC §4.7): requests first, then everyone with Add at
  // the list's end (a friend's next event on their row; where friends go shows on the events' own rows), then my own requests
  // still waiting. Adding is the AddFriend
  // sheet: a one-time QR or link (friends at once) or a request by @username. Guests get the sign-in card. The data is
  // already there (loaded with the app, kept for the next launch); coming into view only refreshes it quietly.
  import X from '@lucide/svelte/icons/x';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import { api, ApiErr, type EventCard, type FriendRow, type Suggestion } from '../../lib/api';
  import { asked, offerDue, offerLater, restored, without } from '../../lib/pymk';
  import Sheet from '../../ui/Sheet.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { session, loadMe, saveSwitch } from '../../lib/state/session.svelte';
  import { data, loadFriends, prefetchPerson, forgetPeople, friendsChanged, phrase } from '../../lib/state/data.svelte';
  import { touchAhead } from '../../lib/touch';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { onMount, type Snippet } from 'svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayNo, nowTs, relDay } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { schoolShort } from '../../lib/short';
  import SortChip from '../../ui/SortChip.svelte';
  import { sorted, byName, newest, usual, type Order } from '../../lib/sort.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const me = $derived(session.me);
  const f = $derived(data.friends);
  onMount(() => { if (me?.student) void loadFriends(); });

  const line = (r: Pick<FriendRow, 'course' | 'school'>) => [r.course ? t('person.course', { n: r.course }) : '', schoolShort(r.school)].filter(Boolean).join(' · ');
  /** The next event this friend goes to, if any (the cards are sorted by start). */
  const nextOf = (r: FriendRow): EventCard | undefined => f?.going.find((e) => e.friends.some((p) => p.id === r.person.id));
  const today = $derived(dayNo(nowTs()));
  // the server's order is the closest first (events and clubs we share)
  const ORDERS: Order<FriendRow>[] = [usual('sort.close'), newest((r) => r.at), byName((r) => r.fullName), { id: 'course', label: 'sort.course', by: (r) => r.course }];
  const list = $derived(sorted('friends', ORDERS, f?.friends ?? []));

  // the row moves first (the speed rule); an error puts the list back, the server's copy lands in the background
  async function answer(r: FriendRow, yes: boolean) {
    const was = data.friends; if (!was) return;
    data.friends = { ...was, incoming: was.incoming.filter((x) => x.person.id !== r.person.id), friends: yes ? [{ ...r, at: nowTs() }, ...was.friends] : was.friends };
    if (yes) { haptic.ok(); burst(); say(t('fr.accepted', { name: r.person.name }), 'partying_face_3d'); }
    else { haptic.soft(); say(t('fr.declined'), 'waving_hand_3d_default'); }
    try {
      // only this person's row from the answer: a reply to an earlier tap can land after a later one
      const s = await api.answerFriend(r.person.id, yes), c = data.friends, row = s.friends.find((x) => x.person.id === r.person.id);
      if (c) data.friends = { ...c, going: s.going, friends: row ? c.friends.map((x) => x.person.id === row.person.id ? row : x) : c.friends };
      forgetPeople(); void loadMe(); } // the dot on the Profile tab
    catch { const c = data.friends; if (c) data.friends = { ...c, incoming: was.incoming.some((x) => x.person.id === r.person.id) && !c.incoming.some((x) => x.person.id === r.person.id) ? [r, ...c.incoming] : c.incoming, friends: yes ? c.friends.filter((x) => x.person.id !== r.person.id) : c.friends }; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // People you may know (lib/pymk.ts): the card goes first, the server follows; a no puts it back where it was
  let offer = $state(offerDue(nowTs()));
  async function suggestAdd(s: Suggestion) {
    const was = data.friends; if (!was?.suggest) return;
    const at = was.suggest.findIndex((x) => x.person.id === s.person.id);
    data.friends = asked(was, s, nowTs()); haptic.tap();
    try {
      const r = await api.askFriend(s.person.id);
      if (r.friendship === 'friends') { haptic.ok(); burst(); say(t('fr.accepted', { name: s.person.name }), 'partying_face_3d'); friendsChanged(); }
      else { haptic.ok(); say(t('person.requestSent'), 'raising_hands_3d_default'); forgetPeople(); }
    } catch (e) {
      const c = data.friends; if (c) data.friends = restored(c, s, at);
      haptic.error(); say(e instanceof ApiErr && e.code === 'rate_limited' ? t('fr.tooMany') : e instanceof ApiErr && e.code === 'closed' ? t('fr.closed') : t('common.error'), 'warning_3d');
    }
  }
  async function suggestHide(s: Suggestion) {
    const was = data.friends; if (!was?.suggest) return;
    const at = was.suggest.findIndex((x) => x.person.id === s.person.id);
    data.friends = without(was, s.person.id); haptic.soft(); say(t('pymk.hidden'), 'waving_hand_3d_default');
    try { await api.dismissSuggestion(s.person.id); }
    catch { const c = data.friends; if (c) data.friends = restored(c, s, at); haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function turnOn() {
    const was = data.friends; if (!was) return;
    data.friends = { ...was, suggest: [] }; haptic.ok();
    try { await saveSwitch('suggestMe', true); say(t('pymk.turnedOn'), 'sparkles_3d'); void loadFriends(); }
    catch { const c = data.friends; if (c) data.friends = { ...c, suggest: null }; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  function notNow() { haptic.soft(); offerLater(nowTs()); offer = false; }

  async function takeBack(r: FriendRow) {
    const was = data.friends; if (!was) return;
    data.friends = { ...was, outgoing: was.outgoing.filter((x) => x.person.id !== r.person.id) };
    haptic.soft(); say(phrase('say.takenBack'), 'waving_hand_3d_default');
    try { await api.takeBackRequest(r.person.id); forgetPeople(); }
    catch { const c = data.friends; if (c && !c.outgoing.some((x) => x.person.id === r.person.id)) data.friends = { ...c, outgoing: [r, ...c.outgoing] }; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<!-- a row's person starts loading as the finger lands, unless it's a scroll (lib/touch.ts; the sheet then opens with them): the rows' order is the list's -->
{#snippet people(list: FriendRow[], body: Snippet)}
  <!-- engine: Row has no onpointerdown; the group's pointerdown finds the row's place -->
  <div role="presentation" onpointerdown={(e) => { const row = (e.target as Element).closest('.kb-row'); const i = row ? [...row.parentElement!.children].indexOf(row) : -1;
    if (list[i]) touchAhead(e, () => prefetchPerson(list[i].person.id)); }}>{@render body()}</div>
{/snippet}

<Sheet {overlay} tall title={t('page.friends')} icon={UsersRound}>
<div class="friends">
  {#if session.ready && !me?.student}
    <section class="hello">
      <span class="mark"><KbtuMark /></span>
      <h2 class="t-h2">{t('fr.guestTitle')}</h2>
      <p class="t-callout">{t('fr.guestText')}</p>
      <Button kind="primary" size="l" full onclick={() => sheets.login()}>{t('guest.button')}</Button>
    </section>
  {:else if f}
    {#if f.incoming.length}
      <!-- the one thing on the page that asks for an answer -->
      <Section title={t('fr.requests')} count={f.incoming.length}>
        <Group>
          {#each f.incoming as r (r.person.id)}
            <Row dense title={withNick(r.fullName, r.person)} subtitle={line(r)}>
              {#snippet lead()}<Avatar person={r.person} size={40} ring />{/snippet}
              {#snippet trailing()}<Button kind="primary" size="s" onclick={() => answer(r, true)}>{t('fr.accept')}</Button>
                <IconButton icon={X} label={t('fr.decline')} size="s" onclick={() => answer(r, false)} />{/snippet}
            </Row>
          {/each}
        </Group>
      </Section>
    {/if}

    {#if f.suggest?.length}
      <!-- clubmates who turned it on too: how many clubs we share, never which (server logic/pymk.py) -->
      <Section title={t('pymk.title')}>
        <div class="strip">
          {#each f.suggest as s (s.person.id)}
            <div class="sg">
              <span class="hide"><IconButton icon={X} label={t('pymk.hide')} size="s" onclick={() => suggestHide(s)} /></span>
              <button class="who" onclick={() => sheets.person(s.person.id)} onpointerdown={(e) => touchAhead(e, () => prefetchPerson(s.person.id))}>
                <span class="pic"><Avatar person={s.person} size={64} tappable={false} /></span>
                <span class="nm">{s.person.name}</span>
                <span class="sub">{line(s) || '\u00a0'}</span>
                <span class="why">{tn('pymk.clubs', s.clubs)}</span>
              </button>
              <Button kind="primary" size="s" full onclick={() => suggestAdd(s)}>{t('fr.add')}</Button>
            </div>
          {/each}
        </div>
      </Section>
    {:else if f.suggest === null && offer}
      <!-- the offer, inline (its own consent: the words are the switch's, Settings has it too) -->
      <section class="offer">
        <h3 class="t-h3">{t('pymk.askTitle')}</h3>
        <p class="t-callout">{t('pymk.askText')}</p>
        <div class="acts">
          <Button kind="primary" size="m" onclick={turnOn}>{t('pymk.on')}</Button>
          <Button kind="secondary" size="m" onclick={notNow}>{t('pymk.later')}</Button>
        </div>
      </section>
    {/if}

    {#if f.friends.length}
      {#snippet all()}
        <Group caption={tn('fr.count', list.length)} aside={list.length > 1 ? sort : undefined}>
          {#each list as r (r.person.id)}
            {@const next = nextOf(r)}
            <Row dense title={withNick(r.fullName, r.person)} subtitle={next ? `${t('fr.goesTo', { title: next.title })} · ${relDay(next.startsAt).toLowerCase()}` : line(r)}
              accessory="chevron" onclick={() => sheets.person(r.person.id)}>
              {#snippet lead()}<span class="av" class:live={next && dayNo(next.startsAt) === today}><Avatar person={r.person} size={40} tappable={false} /></span>{/snippet}
            </Row>
          {/each}
          <Row tone="add" title={t('fr.add')} onclick={() => sheets.addFriend()} />
        </Group>
      {/snippet}
      {#snippet sort()}<SortChip list="friends" orders={ORDERS} />{/snippet}
      {@render people(list, all)}
    {:else if !f.incoming.length}
      <div class="empty">
        <EmptyState icon={UsersRound} title={t('fr.emptyTitle')} text={t('fr.emptyText')} action={{ label: t('fr.invite'), onclick: () => sheets.addFriend('share') }} />
        <Button kind="secondary" size="m" onclick={() => sheets.addFriend()}>{#snippet icon()}<QrCode size={18} />{/snippet}{t('fr.showQr')}</Button>
      </div>
    {:else}
      <Group><Row tone="add" title={t('fr.add')} onclick={() => sheets.addFriend()} /></Group>
    {/if}

    {#if f.outgoing.length}
      <Section title={t('fr.waiting')}>
        <Group>
          {#each f.outgoing as r (r.person.id)}
            <Row dense title={withNick(r.fullName, r.person)} subtitle={line(r)}>
              {#snippet lead()}<Avatar person={r.person} size={40} />{/snippet}
              {#snippet trailing()}<Button kind="secondary" size="s" onclick={() => takeBack(r)}>{t('fr.takeBack')}</Button>{/snippet}
            </Row>
          {/each}
        </Group>
      </Section>
    {/if}
  {:else}
    <!-- the very first launch only (afterwards the stored copy shows at once) -->
    <Skeleton kind="rows" n={3} />
  {/if}
</div>
</Sheet>

<style>
  .friends { display: flex; flex-direction: column; gap: var(--s-6); }
  .friends > :global(*) { flex-shrink: 0; }
  .av { position: relative; display: flex; }
  /* going somewhere today: a green ring, like a story */
  .av.live::after { content: ''; position: absolute; inset: -3px; border-radius: 50%; box-shadow: 0 0 0 2px var(--success); }
  .empty { display: flex; flex-direction: column; align-items: center; }

  /* People you may know: a row of cards the width of the page, swiped sideways */
  .strip { display: flex; gap: var(--s-3); overflow-x: auto; margin: 0 calc(-1 * var(--gutter)); padding: 0 var(--gutter);
    scroll-snap-type: x mandatory; scroll-padding: 0 var(--gutter); overscroll-behavior-x: contain; scrollbar-width: none; }
  .strip::-webkit-scrollbar { display: none; }
  .sg { position: relative; flex: none; width: 148px; scroll-snap-align: start; display: flex; flex-direction: column; gap: var(--s-3);
    padding: var(--s-4) var(--s-3) var(--s-3); border-radius: var(--r-group); background: var(--surface); box-shadow: var(--card-rim, none); }
  .hide { position: absolute; top: var(--s-1); right: var(--s-1); }
  .who { display: flex; flex-direction: column; align-items: center; gap: 2px; min-width: 0; text-align: center; }
  .pic { display: flex; margin-bottom: var(--s-2); }
  .nm, .sub, .why { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .nm { font: 600 var(--fs-row)/1.25 var(--font-text); color: var(--text); }
  .sub { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .why { font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--accent-text); }
  .offer { display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-5) var(--s-4) var(--s-4); border-radius: var(--r-group);
    background: var(--surface); box-shadow: var(--card-rim, none); }
  .offer p { color: var(--text-2); }
  .acts { display: flex; gap: var(--s-2); margin-top: var(--s-2); }

  /* a guest: the sign-in card (Me's) */
  .hello { display: flex; flex-direction: column; gap: 12px; padding: 22px 18px 18px; border-radius: var(--r-xl); color: #fff;
    background: radial-gradient(90% 80% at 20% 0%, rgba(124, 77, 255, 0.55), transparent 60%), linear-gradient(160deg, #2443B8, #101633); }
  .hello p { color: rgba(255, 255, 255, 0.82); }
  .mark { color: #fff; width: 64px; height: 64px; border-radius: 20px; background: rgba(255, 255, 255, 0.14); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); }
</style>
