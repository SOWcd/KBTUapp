<script lang="ts">
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Search from '@lucide/svelte/icons/search';
  import Share from '@lucide/svelte/icons/share';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import RotateCw from '@lucide/svelte/icons/rotate-cw';
  import Settings from '@lucide/svelte/icons/settings';
  import LogOut from '@lucide/svelte/icons/log-out';
  import { api } from '../lib/api';
  import { t } from '../lib/i18n/index.svelte';
  import { tick } from 'svelte';
  import { close, goTab, overlays, say, ui } from '../lib/state/ui.svelte';
  import { backButton, openTelegramLink, telegramAppLink } from '../lib/tg';
  import { copyText } from './copy';
  import { menu } from './menu';

  let { back, start, onsettings }: { back: boolean; start: string; onsettings: () => void } = $props();
  let menuId = $state(0), signingOut = $state(false);
  const expanded = $derived(overlays.some((o) => o.id === menuId && !o.closing));

  async function share(url: string) {
    try {
      if (navigator.share) await navigator.share({ url });
      else if (!(await copyText(url, t('sl.copied')))) say(t('common.error'), 'warning_3d');
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) say(t('common.error'), 'warning_3d');
    }
  }

  async function signOut() {
    if (signingOut) return;
    signingOut = true;
    try {
      await api.webLogout();
      location.reload();
    } catch {
      signingOut = false;
      say(t('common.error'), 'warning_3d');
    }
  }

  // no Back: the left pill opens the tab's pull-down search (Profile has none: the Afisha's), so neither side is ever empty
  async function search() {
    if (ui.tab === 'profile') { goTab('afisha'); await tick(); }
    const field = [...document.querySelectorAll<HTMLElement>('.pull')].find((el) => {
      const tab = el.closest<HTMLElement>('.tab');
      return !tab || getComputedStyle(tab).contentVisibility !== 'hidden'; // App hides the other tabs this way
    });
    if (!field) return;
    field.inert = false; // shut, the field is inert; it fades in with the scroll below
    field.querySelector('input')?.focus({ preventScroll: true }); // first, inside the tap, or iOS shows no keyboard
    field.closest('.scroll')?.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function options(e: MouseEvent) {
    if (expanded) { close(menuId); return; }
    const url = telegramAppLink(start);
    menuId = menu(e.currentTarget as HTMLElement, [
      { label: t('web.share'), icon: Share, onselect: () => void share(url) },
      { label: t('tgo.open'), icon: ExternalLink, onselect: () => openTelegramLink(url) },
      { label: t('web.reload'), icon: RotateCw, onselect: () => location.reload() },
      { label: t('me.settings'), icon: Settings, onselect: onsettings },
      { label: t('web.signOut'), icon: LogOut, destructive: true, disabled: signingOut, onselect: () => void signOut() },
    ], 'end');
  }
</script>

<header class="bar">
  <!-- always there (owner, Nov 22): only its content swaps, Search <-> Back, crossfading like Telegram's Close <-> Back -->
  <button class="glass glass-pill left" class:back type="button" aria-label={back ? t('web.back') : t('web.search')} onclick={() => (back ? backButton.click() : void search())}>
    <span class="face" aria-hidden={back}><Search size={18} /><span>{t('web.search')}</span></span>
    <span class="face" aria-hidden={!back}><ChevronLeft size={20} /><span>{t('web.back')}</span></span>
  </button>
  <button class="glass glass-pill more" type="button" aria-label={t('web.menu')} aria-haspopup="menu" aria-expanded={expanded} onclick={options}><Ellipsis size={20} /></button>
</header>

<style>
  .bar { position: absolute; inset: max(8px, calc(var(--safe-top) + 4px)) 0 auto; z-index: calc(var(--z-sheet) + 7);
    padding-inline: max(12px, env(safe-area-inset-left, 0px)) max(12px, env(safe-area-inset-right, 0px));
    display: flex; align-items: center; justify-content: space-between; pointer-events: none; }
  /* Telegram's own header pills (owner, Nov 22: "identical to Telegram"): 30 px tall, centred on the capsule's line;
     the bar keeps a full tap height (::after belongs to .glass: never a hit-area trick here) */
  .bar { height: var(--tap); }
  button { position: relative; display: flex; align-items: center; justify-content: center; gap: 2px; height: 30px; min-width: 44px;
    padding-inline: 10px; border-radius: var(--r-full); color: var(--text); font: 600 var(--fs-body)/1 var(--font-text); pointer-events: auto; }
  /* both faces share one cell, so the pill keeps one width and never jumps */
  .left { display: grid; padding-inline: 8px 12px; }
  .face { grid-area: 1 / 1; display: flex; align-items: center; justify-content: center; gap: 4px;
    transition: opacity .2s ease, transform .25s var(--ease); }
  .face:last-child, .back .face:first-child { opacity: 0; transform: scale(.8); }
  .back .face:last-child { opacity: 1; transform: none; gap: 2px; }
  @media (prefers-reduced-motion: reduce) { .face { transition: none; } }
  button:active { transform: scale(.94); }
</style>
