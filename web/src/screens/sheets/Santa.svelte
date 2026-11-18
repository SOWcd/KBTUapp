<script lang="ts">
  // Secret Santa on the event's page (server santa.py), for a participant alone: before the draw one quiet line; after
  // it a wrapped card, and the tap that opens it is the game's moment (the gift lifts away, the name rises: transform
  // and opacity only). Opened once, it stays open on this phone.
  import Gift from '@lucide/svelte/icons/gift';
  import type { EventFull, Id } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Avatar from '../../ui/Avatar.svelte';

  let { id, mine }: { id: Id; mine: NonNullable<EventFull['mySanta']> } = $props();
  // per person: a person changed (theirs stepped out, server santa_changed) wraps up again for its own reveal
  const key = $derived(`kb-santa-${id}-${mine.to?.person.id ?? ''}`);
  const seen = () => { try { return localStorage.getItem(key) === '1'; } catch { return false; } };
  let open = $state(seen());
  let fresh = $state(false); // opened by this tap: the reveal plays
  function reveal() {
    open = fresh = true;
    try { localStorage.setItem(key, '1'); } catch { /* blocked: it wraps itself again next time */ }
    haptic.ok(); burst();
  }
</script>

{#if mine.to === undefined}
  <p class="santa line t-body"><Gift size={18} /><b>{t('santa.title')}</b><span>{t('santa.wait')}</span></p>
{:else if mine.to === null}
  <p class="santa line t-body"><Gift size={18} /><span>{t('santa.left')}</span></p>
{:else if !open}
  <button class="santa wrap t-body" onclick={reveal}><span class="gift"><Gift size={30} strokeWidth={1.8} /></span><b>{t('santa.open')}</b></button>
{:else}
  <section class="santa card" class:fresh>
    <span class="cap t-foot">{t('santa.to')}</span>
    <div class="who"><Avatar person={mine.to.person} size={44} /><b class="fs-t3">{mine.to.person.name}</b></div>
    <p class="wish t-body">{mine.to.wish}</p>
  </section>
{/if}

<style>
  .santa { margin: 0; border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim, var(--shadow-card)); color: var(--text); }
  .line { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-4); }
  .line :global(svg) { flex: none; color: var(--accent); }
  .line span { color: var(--text-2); }
  .line b + span { margin-left: auto; }
  .wrap { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); width: 100%; padding: var(--s-5) var(--s-4); border: 0; cursor: pointer;
    transition: transform 450ms var(--ease-bounce); }
  .wrap:active { transform: scale(0.97); transition-duration: 80ms; }
  .gift { display: grid; place-items: center; width: 64px; height: 64px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent); animation: sway 2.6s ease-in-out infinite; }
  .card { display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-4); }
  .cap { color: var(--text-2); }
  .who { display: flex; align-items: center; gap: var(--s-3); min-width: 0; }
  .who b { min-width: 0; overflow-wrap: anywhere; }
  .wish { margin: 0; color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .fresh { animation: pop 520ms var(--ease-bounce) both; }
  .fresh > * { animation: rise 420ms var(--ease) both; }
  .fresh > .who { animation-delay: 140ms; }
  .fresh > .wish { animation-delay: 260ms; }
  @keyframes sway { 0%, 100% { transform: rotate(-5deg); } 50% { transform: rotate(5deg) translateY(-2px); } }
  @keyframes pop { from { opacity: 0; transform: scale(0.9); } }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } }
  @media (prefers-reduced-motion: reduce) { .gift, .fresh, .fresh > * { animation: none; } }
</style>
