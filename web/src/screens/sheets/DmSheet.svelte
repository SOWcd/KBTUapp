<script lang="ts">
  // The bot can't write to this person (App dmHint, every launch until it can): a plain question was closed by reflex,
  // so this one shows what they miss. A lock screen's notifications from the app land one by one (the ticket, "in
  // 2 hours", a reply), newest on top, then the pile clears and it starts over. Drawn in CSS: transform and opacity
  // only, no files to fetch. "Turn on" is Telegram's own allow-messages dialog (askDm).
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { askDm } from '../../lib/state/data.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import BellRing from '@lucide/svelte/icons/bell-ring';

  let { overlay }: { overlay: Overlay } = $props();

  function on() {
    close(overlay.id);
    void askDm(undefined, true);
  }
</script>

<Sheet {overlay} icon={BellRing} title={t('dm.offTitle')}>
  <div class="dm">
    <!-- decoration: the words under it say the same -->
    <div class="pile" aria-hidden="true">
      {#each ['dm.nTicket', 'dm.nSoon', 'dm.nReply'] as const as key, i (key)}
        <div class="note n{i}">
          <span class="app"><KbtuMark size={20} /></span>
          <span class="words">
            <span class="top"><b>KBTU App</b><span>{t('dm.now')}</span></span>
            <span class="msg">{t(key)}</span>
          </span>
        </div>
      {/each}
    </div>
    <h2 class="t-h2">{t('dm.offTitle')}</h2>
    <p class="t-callout">{t('dm.offText')}</p>
  </div>
  {#snippet footer()}
    <div class="acts">
      <Button size="l" full lit onclick={on}>{t('dm.offOk')}</Button>
      <Button kind="plain" full onclick={() => close(overlay.id)}>{t('dm.offLater')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .dm { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--s-1) var(--s-1) var(--s-2); text-align: center; }
  .dm p { color: var(--text-2); text-wrap: pretty; }
  /* three slots, one under another; every note lies at the top and is moved to its slot (--step = a note and its gap) */
  .pile { --h: 56px; --step: calc(var(--h) + var(--s-2)); position: relative; width: 100%; max-width: 320px; height: calc(var(--step) * 3 - var(--s-2)); margin: var(--s-2) 0 var(--s-3); }
  .note { position: absolute; inset: 0 0 auto; height: var(--h); display: flex; align-items: center; gap: var(--s-3); padding: 0 var(--s-3); border-radius: var(--r-m); background: var(--surface-2); box-shadow: 0 0 0 0.5px var(--line), var(--lg-lift); text-align: start;
    animation: 9s var(--ease-spring) 250ms infinite backwards; will-change: transform, opacity; }
  /* where each rests (and stands under reduced motion): the ticket came first, so it is the lowest */
  .n0 { transform: translate3d(0, calc(var(--step) * 2), 0); animation-name: first; }
  .n1 { transform: translate3d(0, var(--step), 0); animation-name: second; }
  .n2 { animation-name: third; }
  .app { flex: none; display: grid; place-items: center; width: 36px; height: 36px; border-radius: var(--r-xs); background: linear-gradient(145deg, var(--accent-2), var(--accent)); color: white; }
  .words { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 1px; }
  .top { display: flex; justify-content: space-between; gap: var(--s-2); font: 450 var(--fs-cap)/1.25 var(--font-text); color: var(--text-3); }
  .top b { font-weight: 600; color: var(--text); }
  .msg { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text); }
  /* a short screen: lower notes, so the words and both buttons still show without a scroll */
  @media (max-height: 640px) { .pile { --h: 48px; margin: 0 0 var(--s-1); } .app { width: 30px; height: 30px; } }
  .acts { display: flex; flex-direction: column; gap: var(--s-1); }
  /* one 9 s round: a note drops in at the top, steps down as the next lands, all three rest, the pile clears */
  @keyframes first {
    0% { opacity: 0; transform: translate3d(0, -18px, 0) scale(0.94); }
    7%, 16% { opacity: 1; transform: none; }
    23%, 32% { opacity: 1; transform: translate3d(0, var(--step), 0); }
    39%, 90% { opacity: 1; transform: translate3d(0, calc(var(--step) * 2), 0); }
    96%, 100% { opacity: 0; transform: translate3d(0, calc(var(--step) * 2), 0) scale(0.97); }
  }
  @keyframes second {
    0%, 16% { opacity: 0; transform: translate3d(0, -18px, 0) scale(0.94); }
    23%, 32% { opacity: 1; transform: none; }
    39%, 90% { opacity: 1; transform: translate3d(0, var(--step), 0); }
    96%, 100% { opacity: 0; transform: translate3d(0, var(--step), 0) scale(0.97); }
  }
  @keyframes third {
    0%, 32% { opacity: 0; transform: translate3d(0, -18px, 0) scale(0.94); }
    39%, 90% { opacity: 1; transform: none; }
    96%, 100% { opacity: 0; transform: scale(0.97); }
  }
  @media (prefers-reduced-motion: reduce) { .note { animation: none; } }
</style>
