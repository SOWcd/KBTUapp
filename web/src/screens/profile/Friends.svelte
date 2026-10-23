<script lang="ts">
  import { withNick } from '../../lib/perms';
  // Profile → Friends (SPEC §4.7): requests first, then where friends are going (the reason to open the app again:
  // magazine cards, the cover full-bleed) on top, away from the thumb (owner, Oct 11: the cards mid-screen caught the swipe
  // back to Me), then the title with Add and everyone, then my own requests still waiting. Adding is the AddFriend
  // sheet: a one-time QR or link (friends at once) or a request by @username. Guests get the sign-in card. The data is
  // already there (loaded with the app, kept for the next launch); coming into view only refreshes it quietly.
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import X from '@lucide/svelte/icons/x';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { api, type EventCard, type FriendRow } from '../../lib/api';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, loadFriends, prefetchEvent, prefetchPerson, forgetPeople, phrase } from '../../lib/state/data.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn, friendsLine } from '../../lib/i18n/index.svelte';
  import { dayNo, nowTs, relDay, time } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import Poster from '../../ui/Poster.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  const me = $derived(session.me);
  const f = $derived(data.friends);
  const here = $derived(ui.tab === 'profile' && ui.page.profile === 0);
  $effect(() => { if (here && me?.student) void loadFriends(); });

  const line = (r: FriendRow) => [r.course ? t('person.course', { n: r.course }) : '', r.school].filter(Boolean).join(' · ');
  /** The next event this friend goes to, if any (the cards are sorted by start). */
  const nextOf = (r: FriendRow): EventCard | undefined => f?.going.find((e) => e.friends.some((p) => p.id === r.person.id));
  const firstNames = (e: EventCard) => e.friends.map((p) => p.name.split(' ')[0]);
  const today = $derived(dayNo(nowTs()));

  let busy = $state<number | null>(null);
  async function answer(r: FriendRow, yes: boolean) {
    busy = r.person.id;
    try {
      data.friends = await api.answerFriend(r.person.id, yes);
      forgetPeople(); // their card changed
      if (yes) { haptic.ok(); burst(); say(t('fr.accepted', { name: r.person.name }), 'partying_face_3d'); }
      else { haptic.soft(); say(t('fr.declined'), 'waving_hand_3d_default'); }
      void loadMe(); // the dot on the Profile tab
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = null; }
  }
  async function takeBack(r: FriendRow) {
    busy = r.person.id;
    try { await api.takeBackRequest(r.person.id); forgetPeople(); if (data.friends) data.friends = { ...data.friends, outgoing: data.friends.outgoing.filter((x) => x.person.id !== r.person.id) }; haptic.soft(); say(phrase('say.takenBack'), 'waving_hand_3d_default'); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = null; }
  }
</script>

<div class="page scroll">
  {#if session.ready && !me?.student}
    <section class="hello">
      <span class="mark"><KbtuMark /></span>
      <h2 class="t-h2">{t('fr.guestTitle')}</h2>
      <p class="t-callout">{t('fr.guestText')}</p>
      <Button kind="primary" size="l" full onclick={() => sheets.login()}>{t('guest.button')}</Button>
    </section>
  {:else}
    {#if f}
      {#if f.incoming.length}
        <section class="blk">
          <h2 class="sh">{t('fr.requests')}<span class="n">{f.incoming.length}</span></h2>
          {#each f.incoming as r, i (r.person.id)}
            <div class="req" style="--i:{i}">
              <Avatar person={r.person} size={46} ring />
              <button class="tx" onpointerdown={() => prefetchPerson(r.person.id)} onclick={() => sheets.person(r.person.id)}><b class="ellipsis">{withNick(r.fullName, r.person)}</b><i class="ellipsis">{line(r)}</i></button>
              <Button kind="primary" size="s" loading={busy === r.person.id} onclick={() => answer(r, true)}>{t('fr.accept')}</Button>
              <button class="no" aria-label={t('fr.decline')} disabled={busy === r.person.id} onclick={() => answer(r, false)}><X size={18} /></button>
            </div>
          {/each}
        </section>
      {/if}

      {#if f.going.length}
        <section class="blk">
          <h2 class="sh">{t('fr.going')}</h2>
          <div class="cards hscroll" data-noswipe>
            {#each f.going as e, i (e.id)}
              <button class="card" style="--i:{i};--c:{e.tint}" onpointerdown={() => prefetchEvent(e.id)} onclick={() => sheets.event(e.id)}>
                <span class="art"><Poster item={e} big radius={0} /></span>
                <span class="veil"></span>
                <span class="when" class:now={dayNo(e.startsAt) === today}>{relDay(e.startsAt)} · {time(e.startsAt)}</span>
                <span class="foot">
                  <b class="title">{e.title}</b>
                  <span class="who">
                    <span class="stack">{#each e.friends.slice(0, 3) as p (p.id)}<Avatar person={p} size={24} tappable={false} />{/each}</span>
                    <i class="ellipsis">{friendsLine(firstNames(e))}</i>
                  </span>
                </span>
              </button>
            {/each}
          </div>
        </section>
      {/if}

      <header class="hd">
        <span><h1 class="t-h1">{t('page.friends')}</h1><p class="t-foot">{tn('fr.count', f.friends.length)}</p></span>
        <button class="add" onclick={() => sheets.addFriend()}><UserPlus size={18} />{t('fr.add')}</button>
      </header>

      {#if f.friends.length}
        <section class="blk">
          <div class="rows surface">
            {#each f.friends as r (r.person.id)}
              {@const next = nextOf(r)}
              <button class="row" onpointerdown={() => prefetchPerson(r.person.id)} onclick={() => sheets.person(r.person.id)}>
                <span class="av" class:live={next && dayNo(next.startsAt) === today}><Avatar person={r.person} size={44} tappable={false} /></span>
                <span class="tx">
                  <b class="ellipsis">{withNick(r.fullName, r.person)}</b>
                  {#if next}<i class="go ellipsis">{t('fr.goesTo', { title: next.title })} · {relDay(next.startsAt).toLowerCase()}</i>
                  {:else}<i class="ellipsis">{line(r)}</i>{/if}
                </span>
                <span class="chev"><ChevronRight size={18} /></span>
              </button>
            {/each}
          </div>
        </section>
      {:else if !f.incoming.length}
        <section class="empty">
          <span class="wave"><Emoji name="waving_hand_3d_default" size={72} /></span>
          <h2 class="t-h2">{t('fr.emptyTitle')}</h2>
          <p class="t-callout">{t('fr.emptyText')}</p>
          <div class="two">
            <Button kind="primary" size="l" full onclick={() => sheets.addFriend('share')}>{#snippet icon()}<UserPlus size={18} />{/snippet}{t('fr.invite')}</Button>
            <Button kind="secondary" size="l" full onclick={() => sheets.addFriend()}>{#snippet icon()}<QrCode size={18} />{/snippet}{t('fr.showQr')}</Button>
          </div>
        </section>
      {/if}

      {#if f.outgoing.length}
        <section class="blk">
          <h2 class="sh">{t('fr.waiting')}</h2>
          <div class="rows surface">
            {#each f.outgoing as r (r.person.id)}
              <div class="row">
                <Avatar person={r.person} size={36} />
                <span class="tx"><b class="ellipsis">{withNick(r.fullName, r.person)}</b><i class="ellipsis">{line(r)}</i></span>
                <button class="tb" disabled={busy === r.person.id} onclick={() => takeBack(r)}>{t('fr.takeBack')}</button>
              </div>
            {/each}
          </div>
        </section>
      {/if}
    {:else}
      <!-- the very first launch only (afterwards the stored copy shows at once): the page's own shapes, so nothing jumps -->
      <div class="skel" aria-hidden="true">
        <span class="bar"></span>
        <span class="strip"><span class="c"></span><span class="c"></span></span>
        <span class="bar"></span>
        <span class="list">{#each [0, 1, 2] as i (i)}<span class="r"><span class="ava"></span><span class="ln"><span></span><span></span></span></span>{/each}</span>
      </div>
    {/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: calc(var(--top) + 56px) var(--gutter) 0; background: var(--glow), var(--bg); display: flex; flex-direction: column; gap: 14px; }
  .page > :global(*) { flex-shrink: 0; }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }
  .hd p { margin-top: 4px; }
  .add { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 14px/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .add:active { transform: scale(0.95); }

  .blk { display: flex; flex-direction: column; gap: 8px; }
  .sh { display: flex; align-items: center; gap: 8px; font: 750 19px/1.2 var(--font-display); letter-spacing: -0.025em; margin-top: 4px; }
  .n { min-width: 22px; height: 22px; padding: 0 7px; border-radius: var(--r-full); background: var(--danger); color: #fff; font: 700 12px/22px var(--font-text); text-align: center; letter-spacing: 0; }

  /* a request: the one thing on the page that asks for an answer */
  .req { display: flex; align-items: center; gap: 10px; padding: 10px 10px 10px 12px; border-radius: var(--r-l);
    background: linear-gradient(120deg, var(--accent-soft), transparent 90%), var(--surface); box-shadow: inset 0 0 0 1px var(--line);
    animation: rise 420ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 60ms); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; text-align: left; }
  .tx b { font: 650 15px/1.25 var(--font-text); }
  .tx i { font: 500 12.5px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .no { flex: none; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface-2); color: var(--text-2); }
  .no:active { transform: scale(0.92); }

  /* where friends are going: portrait cards, the cover full-bleed, the words on the photo */
  .cards { gap: 10px; margin: 0 calc(-1 * var(--gutter)); padding: 2px var(--gutter) 8px; scroll-snap-type: x mandatory; scroll-padding: 0 var(--gutter); }
  .card { position: relative; flex: none; width: 212px; height: 270px; border-radius: 24px; overflow: hidden; scroll-snap-align: start; text-align: left; color: #fff;
    background: var(--c); box-shadow: 0 18px 34px -22px color-mix(in srgb, var(--c) 80%, #000), inset 0 0 0 1px rgba(255, 255, 255, 0.08);
    transition: transform var(--t-fast) var(--ease); animation: rise 480ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 70ms); }
  .card:active { transform: scale(0.97); }
  .art { position: absolute; inset: 0; }
  .veil { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0, 0, 0, 0.28), transparent 26%, transparent 42%, rgba(6, 8, 18, 0.88)); }
  .when { position: absolute; left: 10px; top: 10px; padding: 6px 10px; border-radius: var(--r-full); font: 650 12px/1 var(--font-text);
    background: rgba(10, 12, 24, 0.42); -webkit-backdrop-filter: blur(12px) saturate(160%); backdrop-filter: blur(12px) saturate(160%); }
  .when.now { background: rgba(47, 191, 113, 0.88); }
  .foot { position: absolute; left: 0; right: 0; bottom: 0; padding: 12px 12px 12px 14px; display: flex; flex-direction: column; gap: 8px; }
  .title { font: 760 17px/1.2 var(--font-display); letter-spacing: -0.02em; display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; text-shadow: 0 1px 12px rgba(0, 0, 0, 0.35); }
  .who { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .who i { font: 600 12.5px/1.2 var(--font-text); font-style: normal; color: rgba(255, 255, 255, 0.86); min-width: 0; }
  .stack { display: flex; flex: none; }
  .stack > :global(*) { box-shadow: 0 0 0 2px rgba(10, 12, 24, 0.85); border-radius: 50%; }
  .stack > :global(* + *) { margin-left: -8px; }

  .rows { display: flex; flex-direction: column; padding: 2px 0; }
  .row { display: flex; align-items: center; gap: 12px; min-height: 64px; padding: 8px 12px 8px 14px; text-align: left; }
  .row + .row { box-shadow: inset 0 1px 0 var(--line); }
  button.row:active { background: var(--surface-2); }
  .av { position: relative; display: flex; flex: none; }
  /* going somewhere today: a green ring, like a story */
  .av.live::after { content: ''; position: absolute; inset: -3px; border-radius: 50%; box-shadow: 0 0 0 2px var(--success); }
  .go { color: var(--accent-text) !important; font-weight: 600 !important; }
  .chev { display: flex; color: var(--text-3); }
  .tb { flex: none; padding: 8px 4px; font: 620 13.5px/1 var(--font-text); color: var(--text-2); }

  .empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 26px 18px 18px; margin-top: 6px; text-align: center; border-radius: var(--r-xl);
    background: radial-gradient(80% 60% at 50% 0%, var(--accent-soft), transparent 70%), var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
  .empty p { color: var(--text-2); max-width: 32ch; }
  .wave { display: flex; animation: wave 2.4s ease-in-out 600ms infinite; transform-origin: 70% 80%; }
  :global(html.lowfx) .wave { animation: none; } /* power saving */
  @keyframes wave { 0%, 60%, 100% { transform: rotate(0); } 10%, 30% { transform: rotate(14deg); } 20%, 40% { transform: rotate(-8deg); } }
  .two { display: flex; flex-direction: column; gap: 8px; width: 100%; margin-top: 8px; }

  .hello { display: flex; flex-direction: column; gap: 12px; padding: 22px 18px 18px; border-radius: var(--r-xl); color: #fff;
    background: radial-gradient(90% 80% at 20% 0%, rgba(124, 77, 255, 0.55), transparent 60%), linear-gradient(160deg, #2443B8, #101633); }
  .hello p { color: rgba(255, 255, 255, 0.82); }
  .mark { color: #fff; width: 64px; height: 64px; border-radius: 20px; background: rgba(255, 255, 255, 0.14); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); }

  .skel { display: flex; flex-direction: column; gap: 8px; animation: pulse 1.2s ease-in-out infinite; }
  .skel .bar { width: 46%; height: 20px; margin-top: 6px; border-radius: 8px; background: var(--surface-2); }
  .skel .strip { display: flex; gap: 10px; margin-right: calc(-1 * var(--gutter)); padding-bottom: 8px; overflow: hidden; }
  .skel .c { flex: none; width: 212px; height: 270px; border-radius: 24px; background: var(--surface-2); }
  .skel .list { display: flex; flex-direction: column; border-radius: var(--r-l); background: var(--surface); overflow: hidden; }
  .skel .r { display: flex; align-items: center; gap: 12px; min-height: 64px; padding: 8px 14px; }
  .skel .r + .r { box-shadow: inset 0 1px 0 var(--line); }
  .skel .ava { flex: none; width: 44px; height: 44px; border-radius: 50%; background: var(--surface-2); }
  .skel .ln { flex: 1; display: flex; flex-direction: column; gap: 7px; }
  .skel .ln span { height: 12px; width: 62%; border-radius: 6px; background: var(--surface-2); }
  .skel .ln span + span { width: 38%; height: 10px; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  @keyframes rise { from { opacity: 0; transform: translateY(14px) scale(0.98); } }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
</style>
