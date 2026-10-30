<script lang="ts">
  // Profile → Settings, full screen from the gear (SettingsPage), the phone's own way (owner, Oct 30: "like Apple"; the page of hints, tiles and
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
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import { session } from '../../lib/state/session.svelte';
  import { say, close } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api } from '../../lib/api';
  import { t, i18n, LANG_FULL } from '../../lib/i18n/index.svelte';
  import { theme } from '../../lib/state/theme.svelte';
  import { power } from '../../lib/state/power.svelte';
  import { haptic, openLink, homeScreen, on } from '../../lib/tg';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import Avatar from '../../ui/Avatar.svelte';

  const me = $derived(session.me);
  const s = $derived(me?.settings);
  const bells = $derived(s ? [s.nRemind, s.nNewEvents, s.nForum].filter(Boolean).length : 0);

  // my events in the phone's calendar, through our page (server/kbtu/calpage.py): it hands webcal:// to Apple's calendar,
  // leads the rest to Google and has the address to copy for any other app. Asked for on the tap, not when Settings
  // opens: the address makes a feed token on the server
  async function subscribe() {
    let cal: { page: string; feed: string };
    try { cal = await api.calendarFeed(); } catch { say(t('common.error'), 'pleading_face_3d'); return; } // asked each time: a reset kills the old link
    openLink(cal.page);
  }

  // the app's icon on the home screen: the row only while it can be added and isn't yet
  let home = $state('unsupported');
  void homeScreen.status().then((x) => (home = x));
  $effect(() => on('homeScreenAdded', () => { home = 'added'; say(t('set.homeDone'), 'rocket_3d'); }));
</script>

<!-- a row: its mark on a flat tile of the phone's own colours (no gloss: owner, Oct 30), the label, its value in grey;
     › stays in the app, ↗ leaves it (the calendar), nothing after an action (Home Screen) -->
{#snippet row(Icon: typeof Bell, c: string, label: string, value: string, go: () => void, end: 'in' | 'out' | 'act' = 'in')}
  <button class="set-row" onclick={() => { haptic.tap(); go(); }}><span class="tile" style:--c={c}><Icon size={18} strokeWidth={2.2} /></span><span class="lb">{label}</span>
    {#if value}<span class="val">{value}</span>{/if}{#if end === 'in'}<ChevronRight class="chev" size={18} />{:else if end === 'out'}<ArrowUpRight class="chev" size={18} />{/if}</button>
{/snippet}

<div class="page scroll stagger settings-root">
  <h1 class="ttl">{t('me.settings')}</h1>

  <!-- who I am, the phone's account row: my face and name; Settings opens over Profile (its gear), so a tap closes it -->
  {#if me}
    <div class="set-group">
      <button class="set-row acct" onclick={() => { haptic.tap(); close(); }}>
        <Avatar person={{ id: me.id, name: me.name, avatar: me.avatar }} size={54} tappable={false} />
        <span class="lb"><b>{me.name}</b><i>{me.student ? [me.student.studentId, me.student.school].filter(Boolean).join(' · ') : '@' + (me.tg.username ?? '')}</i></span>
        <ChevronRight class="chev" size={18} /></button>
    </div>
  {/if}

  <div class="set-group">
    {@render row(Languages, '#8E8E93', t('me.guestLang'), LANG_FULL[i18n.lang], () => sheets.settings('lang'))}
    {@render row(SunMoon, '#5856D6', t('me.guestTheme'), t(theme.current === 'dark' ? 'theme.dark' : 'theme.light'), () => sheets.settings('look'))}
  </div>

  {#if me?.student}
    <div class="set-group">
      {@render row(Bell, '#FF3B30', t('me.notifications'), bells === 3 ? t('set.on') : bells ? `${bells}/3` : t('set.off'), () => sheets.settings('notify'))}
      {@render row(CalendarDays, '#FF9500', t('set.calShort'), '', subscribe, 'out')}
    </div>
  {/if}

  <div class="set-group">
    {@render row(BatteryMedium, '#34C759', t('power.title'), t(`power.${power.mode}`), () => sheets.settings('power'))}
    {#if home === 'unknown' || home === 'missed'}{@render row(Smartphone, '#30B0C7', t('set.homeShort'), '', () => homeScreen.add(), 'act')}{/if}
  </div>

  <div class="set-group">
    {@render row(Lock, '#007AFF', t('set.privacy'), '', () => sheets.settings('privacy'))}
    <button class="set-row" onclick={() => { haptic.tap(); sheets.settings('about'); }}><span class="tile" style:--c="#3B6BFF"><KbtuMark size={18} /></span><span class="lb">{t('set.about')}</span><ChevronRight class="chev" size={18} /></button>
  </div>
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: 22px; }
  .page > :global(*) { flex-shrink: 0; }
  .ttl { margin: 6px 4px -6px; font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
  .acct { gap: 14px; min-height: 76px; }
  .acct b { display: block; font: 650 19px/1.2 var(--font-text); }
  .acct i { display: block; margin-top: 3px; font: 450 14px/1.3 var(--font-text); font-style: normal; color: var(--text-3); }
</style>
