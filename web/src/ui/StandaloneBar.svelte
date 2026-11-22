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
  import { glass } from './glass';
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
  <!-- always there (owner, Nov 22): the capsule's own glass and height; only the content changes, Search <-> Back, the way
       Telegram's Close <-> Back does: the icon turns into the other in place, the word slides through the pill -->
  <button class="glass glass-pill side left" class:back type="button" aria-label={back ? t('web.back') : t('web.search')} onclick={() => (back ? backButton.click() : void search())} use:glass={{ bloom: true }}>
    <span class="tone-base" aria-hidden="true"></span>
    <span class="ico" aria-hidden="true"><i class="a"><Search size={17} strokeWidth={2.4} /></i><i class="b"><ChevronLeft size={20} strokeWidth={2.4} /></i></span>
    <span class="txt" aria-hidden="true"><i class="a">{t('web.search')}</i><i class="b">{t('web.back')}</i></span>
  </button>
  <button class="glass glass-pill side more" type="button" aria-label={t('web.menu')} aria-haspopup="menu" aria-expanded={expanded} onclick={options} use:glass={{ bloom: true }}>
    <span class="tone-base" aria-hidden="true"></span><Ellipsis size={20} strokeWidth={2.4} />
  </button>
</header>

<style>
  /* the capsule's own line: its top and 38 px height (ui/Capsule.svelte); both pills one width (--pill, tokens.css),
     the capsule centred between them with the same gap each side */
  .bar { position: absolute; inset: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)) 0 auto; height: 38px;
    z-index: calc(var(--z-sheet) + 7); padding-inline: 12px; display: flex; align-items: center; justify-content: space-between; pointer-events: none; }
  .side { position: relative; display: flex; align-items: center; justify-content: center; gap: 3px; width: var(--pill); height: 38px;
    padding-inline: 7px; border-radius: var(--r-full); background: none; color: var(--text); font: 600 var(--fs-body)/1 var(--font-text);
    letter-spacing: -0.01em; pointer-events: auto; transition: transform 200ms var(--ease); }
  .side > .tone-base { background: var(--glass-clear); }
  :global(html[data-theme='light'][data-sheet]) .side > .tone-base { background: var(--glass-solid); }
  .side:active { transform: scale(.94); }
  .side :global(svg) { flex: none; }

  .ico, .txt { display: grid; place-items: center; }
  .txt { overflow: hidden; min-width: 0; }
  .ico > i, .txt > i { grid-area: 1 / 1; font-style: normal; white-space: nowrap;
    transition: opacity 220ms var(--ease), transform 380ms var(--ease-spring), filter 220ms var(--ease); }
  .ico > i { display: flex; }
  /* what is not shown waits: the icon turned and small, the word just past the pill's edge */
  .ico > .b, .back .ico > .a { opacity: 0; transform: scale(.5) rotate(-60deg); }
  .back .ico > .a { transform: scale(.5) rotate(60deg); }
  .txt > .b { opacity: 0; transform: translateX(70%); filter: blur(2px); }
  .back .txt > .a { opacity: 0; transform: translateX(-70%); filter: blur(2px); }
  .back .ico > .b, .back .txt > .b { opacity: 1; transform: none; filter: none; }
  @media (prefers-reduced-motion: reduce) { .ico > i, .txt > i { transition: opacity 120ms linear; transform: none !important; filter: none !important; } }
</style>
