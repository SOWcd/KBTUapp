<script lang="ts">
  // Profile's gear (owner, Oct 13: Me shows me, the settings live behind one button): every setting in one sheet,
  // deleting the account last (the app's Telegram, "still in development" and the admin panel moved to Me, Oct 14).
  import Globe from '@lucide/svelte/icons/globe';
  import SunMoon from '@lucide/svelte/icons/sun-moon';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import Bell from '@lucide/svelte/icons/bell';
  import Lock from '@lucide/svelte/icons/lock';
  import Trash from '@lucide/svelte/icons/trash-2';
  import Settings2 from '@lucide/svelte/icons/settings';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import RefreshCw from '@lucide/svelte/icons/refresh-cw';
  import CalendarSync from '@lucide/svelte/icons/calendar-sync';
  import { session } from '../../lib/state/session.svelte';
  import { data, phrase } from '../../lib/state/data.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api, type Settings } from '../../lib/api';
  import { inner } from '../../lib/perms';
  import { t, i18n, setLang, LANGS, LANG_NAMES } from '../../lib/i18n/index.svelte';
  import { theme, chooseTheme } from '../../lib/state/theme.svelte';
  import { power } from '../../lib/state/power.svelte';
  import { ago } from '../../lib/time';
  import { haptic, openLink, tg } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const me = $derived(session.me);
  // language and theme live on the phone; the server keeps them too, so the bot writes in your language
  const keep = (patch: Partial<Settings>) => { if (me) api.updateMe(patch).then((m) => (session.me = m)).catch(() => {}); };

  // my events in the phone's calendar: the address is fetched as the sheet opens, so the tap opens at once; Apple
  // through our page that hands webcal:// over, the rest through Google
  let cal = $state<{ page: string; feed: string } | null>(null);
  $effect(() => { if (me?.student) api.calendarFeed().then((x) => (cal = x)).catch(() => {}); });
  function subscribe() {
    if (!cal) { say(t('common.error'), 'pleading_face_3d'); return; }
    haptic.tap();
    openLink(/^(ios|macos)$/.test(tg.platform) ? cal.page : 'https://calendar.google.com/calendar/render?cid=' + encodeURIComponent(cal.feed));
  }

  // §4.8: a President hands the club over first; everyone else sees what goes and has a week to change their mind
  function deleteData() {
    if (me?.memberships.some((m) => m.role === 'president')) { haptic.error(); say(t('del.president'), 'pleading_face_3d'); return; }
    const a = data.myCard?.awards;
    const tickets = data.events.filter((e) => e.my && e.my.status !== 'cancelled' && !inner(e)).length;
    sheets.deleteAccount({ awards: a ? a.achievements.filter((x) => x.level > 0).length + a.badges.length : 0, tickets, clubs: me?.memberships.length ?? 0 });
  }
</script>

<Sheet {overlay} title={t('me.settings')} icon={Settings2} tall>
  <div class="col">
    <h2 class="t-h2 hd">{t('me.settings')}</h2>
    {#if me?.student}
      <div class="rows">
        <button class="r" onclick={() => sheets.settings('notify')}><span class="ic"><Bell size={20} /></span><span class="lb">{t('me.notifications')}</span><ChevronRight size={18} /></button>
      </div>
    {/if}

    <div class="rows">
      <div class="r"><span class="ic"><Globe size={20} /></span><span class="lb">{t('me.guestLang')}</span>
        <span class="seg">{#each LANGS as l (l)}<button class:on={i18n.lang === l} onclick={() => { if (i18n.lang !== l) { setLang(l); keep({ lang: l }); say(t('say.lang'), 'waving_hand_3d_default'); } }}>{LANG_NAMES[l]}</button>{/each}</span></div>
      <div class="r"><span class="ic"><SunMoon size={20} /></span><span class="lb">{t('me.guestTheme')}</span>
        <span class="seg"><button class:on={theme.current === 'light'} onclick={(e) => { if (theme.current !== 'light') { chooseTheme('light', e.currentTarget); keep({ theme: 'light' }); say(phrase('say.theme.light'), 'sparkles_3d'); } }}>{t('theme.light')}</button><button class:on={theme.current === 'dark'} onclick={(e) => { if (theme.current !== 'dark') { chooseTheme('dark', e.currentTarget); keep({ theme: 'dark' }); say(phrase('say.theme.dark'), 'sparkles_3d'); } }}>{t('theme.dark')}</button></span></div>
      <button class="r" onclick={() => sheets.settings('power')}><span class="ic"><BatteryMedium size={20} /></span>
        <span class="lb">{t('power.title')}<i class="sub">{t(power.mode === 'auto' ? (power.lite ? 'power.sub.autoOn' : 'power.sub.autoOff') : power.mode === 'on' ? 'power.sub.on' : 'power.sub.off')}</i></span><ChevronRight size={18} /></button>
    </div>

    {#if me?.student}
      <div class="rows">
        <!-- "Refresh" (§4.11) is signing in again: the app keeps no KBTU session to pull it with (§4.1) -->
        <button class="r" onclick={() => sheets.login()}><span class="ic"><RefreshCw size={20} /></span>
          <span class="lb">{t('me.schedule')}<i class="sub">{t('me.syncedAgo', { ago: ago(me.student.syncedAt) })}</i></span><ChevronRight size={18} /></button>
        <button class="r" onclick={subscribe}><span class="ic"><CalendarSync size={20} /></span><span class="lb">{t('me.calendar')}</span><ChevronRight size={18} /></button>
        <button class="r" onclick={() => sheets.settings('privacy')}><span class="ic"><Lock size={20} /></span><span class="lb">{t('me.privacy')}</span><ChevronRight size={18} /></button>
      </div>
    {/if}

    {#if me?.student && !me.deleteAt}
      <div class="rows">
        <button class="r danger" onclick={deleteData}><span class="ic"><Trash size={20} /></span><span class="lb">{t('me.deleteData')}</span></button>
      </div>
    {/if}
  </div>
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: 12px; padding-bottom: 8px; }
  .hd { margin: 4px 0 0; }
  .sub { display: block; margin-top: 2px; font: 500 12.5px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .rows { display: flex; flex-direction: column; padding: 2px 0; border-radius: var(--r-l); background: var(--surface-2); overflow: hidden; }
  .r { display: flex; align-items: center; gap: 12px; min-height: 54px; padding: 0 14px; text-align: left; color: var(--text-3); }
  .r + .r { box-shadow: inset 0 1px 0 var(--line); }
  button.r:active { background: var(--surface-3, var(--surface)); }
  .ic { display: flex; color: var(--accent-text); }
  .lb { flex: 1; min-width: 0; font: 580 15.5px/1.2 var(--font-text); color: var(--text); }
  .danger .ic, .danger .lb { color: var(--danger-text); }
  .seg { display: inline-flex; gap: 2px; padding: 3px; border-radius: var(--r-full); background: var(--surface); }
  .seg button { height: 30px; padding: 0 12px; border-radius: var(--r-full); font: 620 13px/1 var(--font-text); color: var(--text-2); }
  .seg button.on { background: var(--text); color: var(--bg); }
</style>
