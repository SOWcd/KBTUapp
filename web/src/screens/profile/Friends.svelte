<script lang="ts">
  import { withNick } from '../../lib/perms';
  // Profile → Friends, a sheet from the row under my badge (SPEC §4.7): requests first, then everyone with Add at
  // the list's end (a friend's next event on their row; where friends go shows on the events' own rows), then my own requests
  // still waiting. Adding is the AddFriend
  // sheet: a one-time QR or link (friends at once) or a request by @username. Guests get the sign-in card. The data is
  // already there (loaded with the app, kept for the next launch); coming into view only refreshes it quietly.
  import X from '@lucide/svelte/icons/x';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import { api, type EventCard, type FriendRow } from '../../lib/api';
  import Sheet from '../../ui/Sheet.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, loadFriends, prefetchPerson, forgetPeople, phrase } from '../../lib/state/data.svelte';
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

  let { overlay }: { overlay: Overlay } = $props();
  const me = $derived(session.me);
  const f = $derived(data.friends);
  onMount(() => { if (me?.student) void loadFriends(); });

  const line = (r: FriendRow) => [r.course ? t('person.course', { n: r.course }) : '', schoolShort(r.school)].filter(Boolean).join(' · ');
  /** The next event this friend goes to, if any (the cards are sorted by start). */
  const nextOf = (r: FriendRow): EventCard | undefined => f?.going.find((e) => e.friends.some((p) => p.id === r.person.id));
  const today = $derived(dayNo(nowTs()));

  // the row moves first (the speed rule); an error puts the list back, the server's copy lands in the background
  async function answer(r: FriendRow, yes: boolean) {
    const was = data.friends; if (!was) return;
    data.friends = { ...was, incoming: was.incoming.filter((x) => x.person.id !== r.person.id), friends: yes ? [{ ...r, at: nowTs() }, ...was.friends] : was.friends };
    if (yes) { haptic.ok(); burst(); say(t('fr.accepted', { name: r.person.name }), 'partying_face_3d'); }
    else { haptic.soft(); say(t('fr.declined'), 'waving_hand_3d_default'); }
    try { data.friends = await api.answerFriend(r.person.id, yes); forgetPeople(); void loadMe(); } // the dot on the Profile tab
    catch { data.friends = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function takeBack(r: FriendRow) {
    const was = data.friends; if (!was) return;
    data.friends = { ...was, outgoing: was.outgoing.filter((x) => x.person.id !== r.person.id) };
    haptic.soft(); say(phrase('say.takenBack'), 'waving_hand_3d_default');
    try { await api.takeBackRequest(r.person.id); forgetPeople(); }
    catch { data.friends = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<!-- a row's person starts loading as the finger lands (the sheet then opens with them): the rows' order is the list's -->
{#snippet people(list: FriendRow[], body: Snippet)}
  <!-- engine: Row has no onpointerdown; the group's pointerdown finds the row's place -->
  <div role="presentation" onpointerdown={(e) => { const row = (e.target as Element).closest('.kb-row'); const i = row ? [...row.parentElement!.children].indexOf(row) : -1;
    if (list[i]) prefetchPerson(list[i].person.id); }}>{@render body()}</div>
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

    {#if f.friends.length}
      {#snippet all()}
        <Group caption={tn('fr.count', f!.friends.length)}>
          {#each f!.friends as r (r.person.id)}
            {@const next = nextOf(r)}
            <Row dense title={withNick(r.fullName, r.person)} subtitle={next ? `${t('fr.goesTo', { title: next.title })} · ${relDay(next.startsAt).toLowerCase()}` : line(r)}
              accessory="chevron" onclick={() => sheets.person(r.person.id)}>
              {#snippet lead()}<span class="av" class:live={next && dayNo(next.startsAt) === today}><Avatar person={r.person} size={40} tappable={false} /></span>{/snippet}
            </Row>
          {/each}
          <Row tone="add" title={t('fr.add')} onclick={() => sheets.addFriend()} />
        </Group>
      {/snippet}
      {@render people(f.friends, all)}
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

  /* a guest: the sign-in card (Me's) */
  .hello { display: flex; flex-direction: column; gap: 12px; padding: 22px 18px 18px; border-radius: var(--r-xl); color: #fff;
    background: radial-gradient(90% 80% at 20% 0%, rgba(124, 77, 255, 0.55), transparent 60%), linear-gradient(160deg, #2443B8, #101633); }
  .hello p { color: rgba(255, 255, 255, 0.82); }
  .mark { color: #fff; width: 64px; height: 64px; border-radius: 20px; background: rgba(255, 255, 255, 0.14); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); }
</style>
