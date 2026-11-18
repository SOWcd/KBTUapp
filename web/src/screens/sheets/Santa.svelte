<script lang="ts">
  // Secret Santa on the event's page (server santa.py), for a participant alone. Before the draw: when it is and how
  // many play. After it a sealed card, and the tap that opens it is the game's moment (SantaReveal, once per person
  // I give to, kept on this phone); then, calmly, whom I give to and their wishlist. My own wishlist under it.
  import { onDestroy } from 'svelte';
  import type { EventCard, EventFull, Id } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { open } from '../../lib/state/ui.svelte';
  import { dayMonthShort, time, nowTs } from '../../lib/time';
  import Avatar from '../../ui/Avatar.svelte';
  import SantaBack from './SantaBack.svelte';
  import SantaReveal from './SantaReveal.svelte';

  let { id, e, mine }: { id: Id; e: EventCard; mine: NonNullable<EventFull['mySanta']> } = $props();
  // per person: a person changed (theirs stepped out, server santa_changed) is sealed again for its own reveal
  const key = $derived(`kb-santa-${id}-${mine.to?.person.id ?? ''}`);
  const kept = (k: string) => { try { return localStorage.getItem(k) === '1'; } catch { return false; } };
  let now = $state(''); // the key opened by this tap: the page turns calm under the dark screen, not before it
  const opened = $derived(now === key || kept(key));
  let lifted = $state(false); // the small card is in the air (the reveal's large one flew out of it)
  let mini = $state<HTMLSpanElement>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  onDestroy(() => clearTimeout(timer));
  function reveal() {
    if (lifted || !mine.to) return;
    const k = key;
    lifted = true;
    try { localStorage.setItem(k, '1'); } catch { /* blocked: it seals itself again next time */ }
    open(SantaReveal, { to: mine.to, from: mini?.getBoundingClientRect() ?? null });
    timer = setTimeout(() => { now = k; lifted = false; }, 600);
  }
  // ponytail: the server says only whom I give to; "two are left" is read off the players' count (the bot says the same
  // from the ring itself). A flag on mySanta if the two ever disagree.
  const two = $derived(!!mine.to && e.taken === 2);
  const drawAt = $derived(e.regUntil && e.regUntil > nowTs() ? `${dayMonthShort(e.regUntil)}, ${time(e.regUntil)}` : '');
</script>

{#if mine.to === undefined}
  <section class="santa row">
    <SantaBack w={42} />
    <span class="txt"><span class="t-foot">{t(drawAt ? 'santa.drawAt' : 'santa.title')}{e.taken > 1 ? ' · ' + tn('santa.playing', e.taken) : ''}</span><b class="fs-row">{drawAt || t('santa.wait')}</b></span>
  </section>
{:else if mine.to === null}
  <section class="santa card">
    <b class="fs-t3">{t('santa.left')}</b>
    <p class="t-body dim">{t('santa.leftSub')}</p>
  </section>
{:else if !opened}
  <button class="santa seal santa-seal" onclick={reveal}>
    <span class="mini" class:lifted bind:this={mini}><SantaBack w={96} /></span>
    <b class="fs-row">{t('santa.open')}</b>
  </button>
{:else}
  <section class="santa card">
    <span class="t-foot">{t('santa.to')}</span>
    <div class="who"><Avatar person={mine.to.person} size={56} /><b class="fs-t3">{mine.to.person.name}</b></div>
    {#if two}<p class="t-foot two">{t('santa.two')}</p>{/if}
    <hr />
    <span class="t-foot">{t('santa.wishOf')}</span>
    <p class="wish t-body">{mine.to.wish}</p>
  </section>
{/if}
{#if mine.to !== null}
  <section class="santa card mine">
    <div class="cap"><span class="t-foot">{t('santa.mine')}</span><span class="t-foot hint">{t('santa.mineHint')}</span></div>
    <p class="wish t-body">{mine.wish}</p>
  </section>
{/if}

<style>
  .santa { margin: 0; border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim, var(--shadow-card)); color: var(--text); text-align: left; }
  .row { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); }
  .txt { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
  .txt b, .seal b { font-weight: 600; }
  .card { display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-4); }
  .dim { margin: 0; color: var(--text-2); }
  .seal { display: flex; flex-direction: column; align-items: center; gap: var(--s-4); width: 100%; padding: var(--s-6) var(--s-4) var(--s-5); border: 0; cursor: pointer; }
  .mini { display: block; border-radius: var(--r-s); box-shadow: 0 10px 22px rgba(120, 10, 30, 0.28); animation: float 3.2s ease-in-out infinite; transition: transform 450ms var(--ease-bounce); }
  .seal:active .mini { transform: scale(0.94); transition-duration: 80ms; }
  .lifted { visibility: hidden; }
  .who { display: flex; align-items: center; gap: var(--s-3); min-width: 0; margin-top: 2px; }
  .who b { min-width: 0; overflow-wrap: anywhere; }
  .two { margin: 0; color: var(--text); }
  hr { width: 100%; height: 0.5px; margin: var(--s-2) 0; border: 0; background: var(--separator, var(--line)); }
  .wish { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
  .cap { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 0 var(--s-3); white-space: nowrap; } /* 320: the hint goes under, whole */
  .hint { color: var(--text-3); }
  @keyframes float { 0%, 100% { translate: 0 0; } 50% { translate: 0 -4px; } }
  @media (prefers-reduced-motion: reduce) { .mini { animation: none; } }
  :global(html.lowfx) .mini { animation: none; }
</style>
