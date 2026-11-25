<script lang="ts" module>
  import { calm } from '../../ui/fold';
  import { homeScreen } from '../../lib/tg';
  // the app's icon on the home screen: asked once per launch when the chunk loads (warmed at 3 s), so the row never pops
  // in while the list rises
  const home = $state({ v: 'unsupported' });
  void homeScreen.status().then((x) => (home.v = x));
</script>

<script lang="ts">
  // Settings under my lanyard (Me's gear or my photo; Me runs the way in and out, this is the list). The phone's own
  // way (like Apple's): a short label, its value in grey, an end mark: › a page or a sheet, ⇅ a menu at
  // the row, ↗ out of the app, an accent label with no mark does it now. No subtitles; few words.
  // Sections (each a unit Me animates, [data-unit]), what students look for first on top (the student ID
  // hid in "Name", Privacy at the very bottom): the lanyard first (its editor opens here in place, under the badge:
  // `editing`, Me runs it); me (About me: my data a page deeper, Privacy, Notifications); the app; about. A guest: the
  // app and about.
  import User from '@lucide/svelte/icons/user';
  import Languages from '@lucide/svelte/icons/languages';
  import Bell from '@lucide/svelte/icons/bell';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import Smartphone from '@lucide/svelte/icons/smartphone';
  import Lock from '@lucide/svelte/icons/lock';
  import IdCard from '@lucide/svelte/icons/id-card';
  import Info from '@lucide/svelte/icons/info';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import LogOut from '@lucide/svelte/icons/log-out';
  import Monitor from '@lucide/svelte/icons/monitor';
  import Share from '@lucide/svelte/icons/share';
  import Send from '@lucide/svelte/icons/send';
  import RotateCw from '@lucide/svelte/icons/rotate-cw';
  import KeyRound from '@lucide/svelte/icons/key-round';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import { APPLE_CONSENT, TG_LINK, appleToken, inApp, native, nonce } from '../../lib/native';
  import { ApiErr } from '../../lib/api';
  import { loadMe } from '../../lib/state/session.svelte';
  import { api, type Settings } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { data, phrase, dropSchedule } from '../../lib/state/data.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, i18n, setLang, loadLang, LANGS, LANG_FULL, type Lang } from '../../lib/i18n/index.svelte';
  import { theme, chooseTheme, reveal, type Theme } from '../../lib/state/theme.svelte';
  import { power, setPowerMode, POWER_MODES } from '../../lib/state/power.svelte';
  import { haptic, inTelegram, openLink, openTelegramLink, telegramAppLink, on } from '../../lib/tg';
  import { copyText } from '../../ui/copy';
  import { menu } from '../../ui/menu';
  import { onMount } from 'svelte';
  import { photoItems } from './mine';
  import { notificationSettings } from './notificationSettings';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import ThemeGlyph, { glyph } from './ThemeGlyph.svelte';
  import { lookData } from '../../lib/state/looks.svelte';
  import LookPage from './LookPage.svelte';

  let { editing = false, onlanyard }: { editing?: boolean; onlanyard?: () => void } = $props();
  const me = $derived(session.me);
  const s = $derived(me?.settings);
  const bells = $derived(notificationSettings.filter(([key]) => s?.[key]).length);
  const wornName = $derived(lookData().wornName);
  // my photo's menu at my photo on the lanyard (Me); About me has the same at its row
  export function photoMenu(at: Element, align?: 'start' | 'end') { if (me) menu(at, photoItems(), align); }

  // ---- the app ----
  // language and theme live on the phone; the server keeps them too, so the bot writes in your language
  // the other languages' dictionaries are asked for as Settings opens, a beat before the language row can be tapped,
  // not by every launch at its start (~80 KB gzip of a first launch; most students never switch)
  for (const l of LANGS) void loadLang(l).catch(() => {});
  const keep = (patch: Partial<Settings>) => { if (me) api.updateMe(patch).then((m) => (session.me = m)).catch(() => {}); };
  function lang(l: Lang) {
    if (i18n.lang === l) return;
    keep({ lang: l });
    void loadLang(l).then(() => reveal(() => { setLang(l); say(phrase('say.lang'), 'speech_balloon_3d'); }, () => {}, undefined, 'lang'));
  }
  // the theme is a snap: the menu fades, the row's sun turns into the moon (or back) with a spring, and
  // at its peak a click and the new theme grows from that icon. The menu is gone by then (its exit is 150 ms), so the
  // transition's snapshots never hold it; the icon's tail plays in the live new snapshot, the circle opening on it
  $effect.pre(() => { glyph.dark = theme.current === 'dark'; });
  // no "as in the system" item: until a pick the app follows Telegram's scheme on its own
  function look(to: Theme, ic: Element | null) {
    if (theme.chosen === to) return;
    keep({ theme: to });
    if (to === theme.current) return chooseTheme(to); // the look stays: nothing to play
    glyph.dark = to === 'dark';
    setTimeout(() => {
      haptic.rigid();
      chooseTheme(to, ic ?? undefined);
      say(phrase(`say.theme.${to}`), to === 'dark' ? 'crescent_moon_3d' : 'sparkles_3d');
    }, calm() ? 0 : 160);
  }
  const POWER_EMOJI = { on: 'hot_beverage_3d', off: 'high_voltage_3d', auto: 'robot_3d' } as const;
  // my events in the phone's calendar, through our page (server/kbtu/calpage.py); asked on the tap: the address makes a
  // feed token on the server, and a reset kills the old link
  async function subscribe() {
    let cal: { page: string; feed: string };
    try { cal = await api.calendarFeed(); } catch { say(t('common.error'), 'warning_3d'); return; }
    openLink(cal.page);
  }
  // the calendar's address leaked (sent to someone, a shared screen): the old one stops, a new subscribe makes a new one
  async function resetCal() {
    if (!(await sheets.ask({ title: t('set.calResetAsk'), text: t('set.calResetText'), ok: t('set.calResetOk'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.resetCalendar(); haptic.ok(); say(t('set.calResetDone'), 'sparkles_3d'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // my week off the server, here too and not only in the Week sheet
  async function dropWeek() {
    if (await sheets.ask({ title: t('sched.delAsk'), text: t('sched.delText'), ok: t('cm.delete'), cancel: t('common.cancel'), danger: true })) void dropSchedule();
  }

  // the web app's own rows (they were the bar's ⋯ menu until quick launch took its place)
  async function share() {
    const url = telegramAppLink();
    try {
      if (navigator.share) await navigator.share({ url });
      else if (!(await copyText(url, t('sl.copied')))) say(t('common.error'), 'warning_3d');
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) say(t('common.error'), 'warning_3d');
    }
  }

  let signingOut = $state(false);
  async function signOut(all: boolean) {
    if (signingOut) return;
    signingOut = true;
    try {
      if (all) {
        if (!(await sheets.ask({ title: t('web.signOutAll'), text: t('web.signOutAllConfirm'), ok: t('web.signOut'), cancel: t('common.cancel'), danger: true }))) return;
        await api.webLogoutAll();
      } else {
        await api.webLogout();
      }
      if (inTelegram) { haptic.ok(); say(t('web.signedOutAll'), 'sparkles_3d'); }
      else location.reload();
    } catch {
      haptic.error(); say(t('common.error'), 'warning_3d');
    } finally {
      signingOut = false;
    }
  }

  // ---- sign-ins (outside Telegram: me.logins): one account reached by Telegram or Apple (server logic/apple.py) ----
  let linking = $state(false);
  async function linkWith(fn: () => Promise<void>, done: string) {
    if (linking) return;
    linking = true;
    try { await fn(); await loadMe(); haptic.ok(); say(done, 'sparkles_3d'); }
    catch (e) { haptic.error(); say(t(e instanceof ApiErr && e.message === 'apple_taken' ? 'logins.appleTaken' : 'common.error'), 'warning_3d'); }
    finally { linking = false; }
  }
  // Telegram's own sign-in page, then back here (WebEntrance reads its #tgAuthResult and links it): only a return this
  // tab started, marked by a one-time state for this account, gets linked
  async function linkTelegram() {
    haptic.tap();
    try {
      const state = nonce(), { url } = await api.telegramLinkStart(state);
      sessionStorage.setItem(TG_LINK, JSON.stringify({ state, uid: me?.id, at: Date.now() }));
      location.assign(url);
    } catch { say(t('common.error'), 'warning_3d'); }
  }
  // Apple's sheet closed: nothing to say
  async function linkApple() {
    const n = nonce(), token = await appleToken(n);
    if (token) void linkWith(() => api.linkApple({ token, nonce: n, consent: APPLE_CONSENT }), t('logins.appleDone'));
  }
  async function unlinkApple() {
    if (!(await sheets.ask({ title: t('logins.unlinkAsk'), ok: t('logins.unlink'), cancel: t('common.cancel'), danger: true }))) return;
    void linkWith(() => api.unlinkApple(), t('logins.unlinked'));
  }
  // an account Apple made (App Store 5.1.1(v)) deletes itself here too; a student's goes through Privacy as before
  const deleteApple = () => sheets.deleteAccount({ awards: 0, tickets: data.events.filter((e) => e.my && e.my.status !== 'cancelled').length, clubs: 0 });

  onMount(() => on('homeScreenAdded', () => { home.v = 'added'; clearTimeout(homeWait); say(t('set.homeDone'), 'rocket_3d'); }));
  // Android: a launcher that forbids Telegram's shortcuts (Xiaomi, Huawei...) swallows the dialog without a word;
  // no "added" within a few seconds -> say where to allow it, never a button that seems to do nothing
  let homeWait: ReturnType<typeof setTimeout> | undefined;
  function addHome() {
    haptic.tap();
    homeScreen.add();
    clearTimeout(homeWait);
    if (homeScreen.android()) homeWait = setTimeout(() => { if (home.v !== 'added') homeScreen.help(t('set.homeHelp')); }, 4000);
  }

</script>

<div class="set-list" role="region" aria-label={t('me.settings')} tabindex="-1">
  {#if me?.student && editing}
    <div data-unit class="first"><LookPage /></div>
  {:else}
  {#if me?.student}
    {@const st = me.student}
    {#if onlanyard}
      <div data-unit class="first">
        <Group><Row icon={IdCard} title={t('look.lanyard')} value={wornName} accessory="chevron" onclick={() => { haptic.tap(); onlanyard?.(); }} /></Group>
      </div>
    {/if}
    <div data-unit class={onlanyard ? 'sec' : 'first'}>
      <Group>
        <Row icon={User} title={t('set.aboutMe')} value={[st.firstName, st.lastName].filter(Boolean).join(' ')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('me'); }} />
        <Row icon={Lock} title={t('set.privacy')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('privacy'); }} />
        <Row icon={Bell} title={t('me.notifications')} value={bells === notificationSettings.length ? t('set.on') : bells ? `${bells}/${notificationSettings.length}` : t('set.off')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('notify'); }} />
      </Group>
    </div>
  {:else}
    <div class="spacer"></div>
  {/if}

  <div data-unit class={['sec', { first: !me?.student }]}>
    <Group caption={t('set.app')}>
      <Row icon={Languages} title={t('me.guestLang')} value={LANG_FULL[i18n.lang]} menu={LANGS.map((l) => ({ label: LANG_FULL[l], checked: i18n.lang === l, instant: true, onselect: () => lang(l) }))} />
      <Row icon={ThemeGlyph} title={t('me.guestTheme')} value={t(`theme.${theme.current}`)} menu={(['dark', 'light'] as const).map((x) => ({ label: t(`theme.${x}`), checked: theme.current === x, onselect: () => look(x, glyph.el) }))} />
      {#if me?.student}
        <!-- updating and deleting the timetable, subscribing and resetting the calendar: each at its own row -->
        {#if data.schedule.length && !me.deleteAt}<Row icon={CalendarPlus} title={t('set.schedule')} menu={[{ label: t('sched.weekTitle'), onselect: () => sheets.week() }, { label: t('sched.update'), onselect: () => sheets.schedHowTo() }, { label: t('sched.del'), destructive: true, onselect: () => void dropWeek() }]} />
        {:else}<Row icon={CalendarPlus} title={t('set.schedule')} accessory="chevron" onclick={() => { haptic.tap(); sheets.schedHowTo(); }} />{/if}
        {#if me.deleteAt}<Row icon={CalendarDays} title={t('set.calShort')} accessory="external" onclick={() => { haptic.tap(); void subscribe(); }} />
        {:else}<Row icon={CalendarDays} title={t('set.calShort')} menu={[{ label: t('set.calSub'), onselect: () => void subscribe() }, { label: t('set.calReset'), destructive: true, onselect: () => void resetCal() }]} />{/if}
      {/if}
      <Row icon={BatteryMedium} title={t('power.title')} value={t(`power.${power.mode}`)} menu={POWER_MODES.map((m) => ({ label: t(`power.${m}`), checked: power.mode === m,
        onselect: () => { if (power.mode !== m) { setPowerMode(m); say(phrase(`say.power.${m}`), POWER_EMOJI[m]); } } }))} />
      {#if home.v === 'unknown' || home.v === 'missed'}<Row icon={Smartphone} title={t('set.homeShort')} tone="action" onclick={addHome} />{/if}
    </Group>
  </div>

  <div data-unit class="sec">
    <Group>
      <Row icon={Info} title={t('set.about')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('about'); }} />
      <!-- the voluntary support page: this row is its only way in, no banners or reminders anywhere (donate-review.md) -->
      <!-- never in the iPhone app: a gift to the app outside Apple's in-app purchase breaks App Store rule 3.1.1 -->
      {#if session.donate && !inApp}<Row icon={HandHeart} title={t('set.donate')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('donate'); }} />{/if}
    </Group>
  </div>
  {#if !inTelegram}
    <div data-unit class="sec">
      <Group>
        <Row icon={Send} title={t('tgo.open')} accessory="external" onclick={() => openTelegramLink(telegramAppLink())} />
        <Row icon={Share} title={t('web.share')} tone="action" onclick={() => void share()} />
        <Row icon={RotateCw} title={t('web.reload')} tone="action" onclick={() => location.reload()} />
      </Group>
    </div>
  {/if}
  {#if me?.logins}
    {@const lg = me.logins}
    <div data-unit class="sec">
      <!-- bot messages come through Telegram alone: said under the group while it isn't linked -->
      <Group caption={t('logins.title')} footnote={lg.telegram ? undefined : t('logins.tgWhy')}>
        {#if lg.telegram}<Row icon={Send} title={t('logins.tg')} value={t('logins.linked')} />
        {:else}<Row icon={Send} title={t('logins.linkTg')} tone="action" disabled={linking} onclick={() => void linkTelegram()} />{/if}
        {#if lg.apple}<Row icon={KeyRound} title={t('logins.appleName')} value={t('logins.linked')}
          menu={lg.telegram ? [{ label: t('logins.unlink'), destructive: true, onselect: () => void unlinkApple() }] : undefined} />
        {:else if native.has('apple')}<Row icon={KeyRound} title={t('logins.linkApple')} tone="action" disabled={linking} onclick={() => void linkApple()} />{/if}
      </Group>
    </div>
    {#if lg.apple && !me.student && !me.deleteAt}
      <div data-unit class="sec">
        <Group><Row icon={Trash2} title={t('logins.delete')} tone="destructive" onclick={deleteApple} /></Group>
      </div>
    {/if}
  {/if}
  {#if me}
    <div data-unit class="sec">
      <Group>
        {#if !inTelegram}<Row icon={LogOut} title={t('web.signOut')} tone="destructive" disabled={signingOut} onclick={() => void signOut(false)} />{/if}
        <Row icon={Monitor} title={t('web.signOutAll')} tone="destructive" disabled={signingOut} onclick={() => void signOut(true)} />
      </Group>
    </div>
  {/if}
  {/if}
</div>

<style>
  /* Me's stagger child, but it rises by its units (Me): no second animation on top */
  .set-list { animation: none; display: flex; flex-direction: column; outline: none; }
  /* the sections' captions where Settings' headings stood: one rhythm between groups (iOS's) */
  .first { margin-top: 20px; }
  .sec { margin-top: 28px; }
  .sec.first { margin-top: 20px; }
  .spacer { height: 44px; } /* a guest: the check sits where the student's gear does, never on the first title */

</style>
