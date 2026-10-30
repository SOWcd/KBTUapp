<script lang="ts">
  // Profile → Settings, the third page, the phone's own way (owner, Oct 30: "like Apple"; the page of hints, tiles and
  // red bins under each row read as clutter): one short row each, its value in grey, a chevron; the choices and the
  // explanations are a tap deeper (SettingsSheet). My phone, my city and deleting the account live under Privacy.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Languages from '@lucide/svelte/icons/languages';
  import SunMoon from '@lucide/svelte/icons/sun-moon';
  import Bell from '@lucide/svelte/icons/bell';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import Smartphone from '@lucide/svelte/icons/smartphone';
  import Lock from '@lucide/svelte/icons/lock';
  import { session } from '../../lib/state/session.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api } from '../../lib/api';
  import { t, i18n, LANG_FULL } from '../../lib/i18n/index.svelte';
  import { theme } from '../../lib/state/theme.svelte';
  import { power } from '../../lib/state/power.svelte';
  import { haptic, openLink, tg, homeScreen, on } from '../../lib/tg';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  const me = $derived(session.me);
  const s = $derived(me?.settings);
  const bells = $derived(s ? [s.nRemind, s.nNewEvents, s.nForum].filter(Boolean).length : 0);

  // my events in the phone's calendar: Apple through our page that hands webcal:// over, the rest through Google. Asked
  // for on the tap: the page mounts unseen next to Me, and the address makes a feed token on the server
  let cal: { page: string; feed: string } | null = null;
  async function subscribe() {
    try { cal ??= await api.calendarFeed(); } catch { say(t('common.error'), 'pleading_face_3d'); return; }
    openLink(/^(ios|macos)$/.test(tg.platform) ? cal.page : 'https://calendar.google.com/calendar/render?cid=' + encodeURIComponent(cal.feed));
  }

  // the app's icon on the home screen: the row only while it can be added and isn't yet
  let home = $state('unsupported');
  void homeScreen.status().then((x) => (home = x));
  $effect(() => on('homeScreenAdded', () => { home = 'added'; say(t('set.homeDone'), 'rocket_3d'); }));
</script>

{#snippet row(Icon: typeof Bell, label: string, value: string, go: () => void)}
  <button class="set-row" onclick={() => { haptic.tap(); go(); }}><span class="ico"><Icon size={21} strokeWidth={1.9} /></span><span class="lb">{label}</span>
    {#if value}<span class="val">{value}</span>{/if}<ChevronRight class="chev" size={18} /></button>
{/snippet}

<div class="page scroll stagger">
  <h1 class="ttl">{t('me.settings')}</h1>

  <div class="set-group">
    {@render row(Languages, t('me.guestLang'), LANG_FULL[i18n.lang], () => sheets.settings('lang'))}
    {@render row(SunMoon, t('me.guestTheme'), t(theme.current === 'dark' ? 'theme.dark' : 'theme.light'), () => sheets.settings('look'))}
  </div>

  {#if me?.student}
    <div class="set-group">
      {@render row(Bell, t('me.notifications'), bells === 3 ? t('set.on') : bells ? `${bells}/3` : t('set.off'), () => sheets.settings('notify'))}
      {@render row(CalendarDays, t('set.calShort'), '', subscribe)}
    </div>
  {/if}

  <div class="set-group">
    {@render row(BatteryMedium, t('power.title'), t(`power.${power.mode}`), () => sheets.settings('power'))}
    {#if home === 'unknown' || home === 'missed'}{@render row(Smartphone, t('set.homeShort'), '', () => homeScreen.add())}{/if}
  </div>

  <div class="set-group">
    {@render row(Lock, t('set.privacy'), '', () => sheets.settings('privacy'))}
    <button class="set-row" onclick={() => { haptic.tap(); sheets.settings('about'); }}><span class="ico"><KbtuMark size={20} /></span><span class="lb">{t('set.about')}</span><ChevronRight class="chev" size={18} /></button>
  </div>
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: 22px; }
  .page > :global(*) { flex-shrink: 0; }
  .ttl { margin: 6px 4px -6px; font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
</style>
