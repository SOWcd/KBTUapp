<script lang="ts">
  // The campus map's card for the room or place found (CampusMap.svelte): its name and floor (a tap there finds
  // another), when it is free by the timetable, and the way to it. It covers the map's bottom (data-cover: the
  // map frames what it finds above it).
  import X from '@lucide/svelte/icons/x';
  import Search from '@lucide/svelte/icons/search';
  import RouteIcon from '@lucide/svelte/icons/route';
  import { t } from '../../lib/i18n/index.svelte';

  let { title, floor, line, busy, onfind, onclose, onroute }: {
    title: string; floor: string; line: string; busy: boolean; onfind: () => void; onclose: () => void; onroute: () => void;
  } = $props();
</script>

<div class="rcard" data-cover>
  <span class="grab" aria-hidden="true"></span>
  <!-- the place itself is the way to another one (an "Other" button beside the route looked wrong) -->
  <div class="rhead"><button class="rfind" onclick={onfind} aria-label={t('map.other')}>
      <span class="ptb" aria-hidden="true">{t('pad.b')}</span><span class="rt"><b>{title}</b><small>{floor}</small></span>
      <Search size={18} /></button>
    <button class="xb" onclick={onclose} aria-label={t('common.close')}><X size={18} /></button></div>
  {#if line}<p class="fl">{line}</p>{/if}
  <button class="go" disabled={busy} aria-busy={busy} onclick={onroute}><RouteIcon size={20} />{t('map.routeHere')}</button>
</div>

<style>
  /* the room found: a short panel with the way to it */
  .rcard { position: absolute; z-index: 4; left: 0; right: 0; bottom: 0; padding: 8px 16px calc(var(--safe-bottom) + 16px); border-radius: 36px 36px 0 0; background: var(--surface-solid); color: var(--text);
    box-shadow: 0 -20px 60px -20px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.08); animation: rise 0.6s var(--ease-spring); }
  @keyframes rise { from { transform: translate3d(0, 105%, 0); } }
  .grab { display: block; width: 38px; height: 5px; border-radius: 3px; background: var(--line-2); margin: 0 auto 10px; }
  .rhead { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .ptb { width: 28px; height: 28px; border-radius: 50%; display: inline-grid; place-items: center; margin-right: 10px; vertical-align: 2px; background: var(--accent); color: #fff;
    font: 800 15px/1 var(--font-display); box-shadow: 0 0 0 4px rgba(59, 107, 255, 0.25); }
  .rfind { flex: 1; min-width: 0; display: flex; align-items: center; gap: 12px; padding: 10px 14px 10px 10px; border-radius: 22px; background: var(--surface-2); color: var(--text-2); text-align: left; }
  .rfind:active { transform: scale(0.98); }
  .rfind .rt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .rfind b { font: 800 22px/1.15 var(--font-display); letter-spacing: -0.01em; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rfind small { font: 550 14px/1.2 var(--font-text); color: var(--text-2); }
  .rfind .ptb { margin: 0; vertical-align: 0; flex: none; }
  .xb { width: 36px; height: 36px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; color: var(--text-2); flex: none; }
  .go { width: 100%; margin-top: 12px; height: 56px; border-radius: 28px; display: flex; align-items: center; justify-content: center; gap: 8px; font: 750 17px/1 var(--font-text); color: #fff;
    background: linear-gradient(180deg, #5c85ff, #3b6bff 55%, #3457e0); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 10px 24px -8px rgba(59, 107, 255, 0.8); }
  .go:disabled { opacity: 0.65; }
  .fl { margin: 10px 4px 0; font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  @media (prefers-reduced-motion: reduce) { .rcard { animation: none; } }
</style>
