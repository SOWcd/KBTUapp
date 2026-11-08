<script lang="ts" module>
  import { homeScreen } from '../../lib/tg';
  // the app's icon on the home screen: asked once per launch when the chunk loads (warmed at 3 s), so the row never pops
  // in while the list rises
  const home = $state({ v: 'unsupported' });
  void homeScreen.status().then((x) => (home.v = x));
</script>

<script lang="ts">
  // Settings under my lanyard (Me's gear or my photo; Me runs the way in and out, this is the list). The phone's own
  // way (owner, Oct 30: "like Apple"): a short label, its value in grey, an end mark: › a page or a sheet, ⇅ a menu at
  // the row, ↗ out of the app, an accent label with no mark does it now. No subtitles; few words.
  // Sections (each a unit Me animates, [data-unit]), what students look for first on top (owner, Nov 6: nobody found
  // where to change the name): the lanyard first (its editor opens here in place, under the badge: `editing`, Me runs
  // it), my data (photo, name, nick, school, course, city, phone), the app, then privacy and about. A guest: the app and about.
  import ImageIcon from '@lucide/svelte/icons/image';
  import AtSign from '@lucide/svelte/icons/at-sign';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import School from '@lucide/svelte/icons/school';
  import User from '@lucide/svelte/icons/user';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import Phone from '@lucide/svelte/icons/phone';
  import { cityName } from '../../lib/i18n/cities';
  import { fmtPhone, kzPhone } from '../../lib/phone';
  import { schoolShort } from '../../lib/short';
  import Languages from '@lucide/svelte/icons/languages';
  import Bell from '@lucide/svelte/icons/bell';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import Smartphone from '@lucide/svelte/icons/smartphone';
  import Lock from '@lucide/svelte/icons/lock';
  import IdCard from '@lucide/svelte/icons/id-card';
  import Info from '@lucide/svelte/icons/info';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import { api, ApiErr, type Me, type Settings } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { data, phrase } from '../../lib/state/data.svelte';
  import { say, ui } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, i18n, setLang, loadLang, LANGS, LANG_FULL, type Lang } from '../../lib/i18n/index.svelte';
  import { theme, chooseTheme, reveal, type Theme } from '../../lib/state/theme.svelte';
  import { power, setPowerMode, POWER_MODES } from '../../lib/state/power.svelte';
  import { haptic, openLink, on } from '../../lib/tg';
  import { menu, type MenuItem } from '../../ui/menu';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import ThemeGlyph, { glyph } from './ThemeGlyph.svelte';
  import { lookData } from '../../lib/state/looks.svelte';
  import LookPage from './LookPage.svelte';

  let { editing = false, onlanyard }: { editing?: boolean; onlanyard: () => void } = $props();
  const me = $derived(session.me);
  const s = $derived(me?.settings);
  const phone = $derived(me?.student?.phone ? (kzPhone(me.student.phone) ? fmtPhone(me.student.phone) : me.student.phone) : '');
  // the course is picked a tap deeper while it can still be (the ID's year up to the 6th), else it's just shown
  const courseFix = $derived(!!me?.student?.fixable?.includes('course') && (me.student.courseMin ?? 6) < 6);
  const bells = $derived(s ? [s.nRemind, s.nNewEvents].filter(Boolean).length : 0);

  const wornName = $derived(lookData().wornName);
  let busy = false;

  function oops(e: unknown) {
    haptic.error();
    say(e instanceof ApiErr && e.message === 'nick' ? t('look.badNick') : e instanceof ApiErr && e.message === 'not_an_image' ? t('look.badPhoto') : t('common.error'), 'warning_3d');
  }
  // one change of my photo or nick at a time; `word`: what the capsule says meanwhile (an upload takes a moment)
  async function work(job: () => Promise<Me>, msg: (m: Me) => string, word = '') {
    if (busy) return;
    busy = true; ui.busy = word;
    try { const m = await job(); session.me = m; haptic.ok(); say(msg(m), 'sparkles_3d'); } catch (e) { oops(e); } finally { busy = false; ui.busy = ''; }
  }

  // ---- the photo: Telegram's (it refreshes by itself) or my own ----
  let file = $state<HTMLInputElement>();
  async function upload(f: File | undefined) {
    if (file) file.value = '';  // the same photo picked again opens the crop again
    const cut = f && await sheets.cropPhoto(f);
    if (cut) void work(() => api.uploadMyPhoto(cut), () => t('look.photoSet'), t('look.uploading'));
  }
  async function dropOwn() {
    if (await sheets.ask({ title: t('look.dropOwn'), ok: t('look.dropOwn'), cancel: t('common.cancel'), danger: true })) void work(() => api.deleteMyPhoto(), () => t('look.photoGone'));
  }
  // the photo's menu: at its row (Row opens it) or at my photo on the lanyard (Me)
  const photoItems = (): MenuItem[] => {
    if (!me) return [];
    const { telegram, own } = me.photo;
    return [
      { label: t('look.fromTg'), checked: telegram, onselect: () => { if (!telegram) void work(() => api.updateMe({ avatarTg: true }), () => t('look.tgOn')); } },
      ...(own ? [{ label: t('look.own'), checked: !telegram, onselect: () => { if (telegram) void work(() => api.updateMe({ avatarTg: false }), () => t('look.photoSet')); } }] : []),
      // instant: the file picker opens inside the tap itself (iOS opens none from a later task)
      { label: t('look.upload'), instant: true, onselect: () => file?.click() },
      ...(own ? [{ label: t('look.dropOwn'), destructive: true, onselect: () => void dropOwn() }] : []),
    ];
  };
  export function photoMenu(at: Element, align?: 'start' | 'end') { if (me) menu(at, photoItems(), align); }

  // ---- the nick: lists and feeds show it instead of my name, my profile shows both (the nick rule, Nov 2) ----
  async function editNick() {
    const v = await sheets.askText({ title: t('look.nick'), placeholder: t('look.nickPh'), max: 24, line: true, value: me?.nick ?? '', ok: t('common.save'), cancel: t('common.cancel') });
    if (v != null && v !== (me?.nick ?? '')) setNick(v);
  }
  const setNick = (v: string | null) => void work(() => api.updateMe({ nick: v }), (m) => t(m.nick ? 'look.nickSet' : 'look.nickOff'));

  // ---- the app ----
  // language and theme live on the phone; the server keeps them too, so the bot writes in your language
  // the other languages' dictionaries are asked for as Settings opens, a beat before the language row can be tapped,
  // not by every launch at its start (perf round 4: ~80 KB gzip of a first launch; most students never switch)
  for (const l of LANGS) void loadLang(l).catch(() => {});
  const keep = (patch: Partial<Settings>) => { if (me) api.updateMe(patch).then((m) => (session.me = m)).catch(() => {}); };
  function lang(l: Lang) {
    if (i18n.lang === l) return;
    keep({ lang: l });
    void loadLang(l).then(() => reveal(() => { setLang(l); say(phrase('say.lang'), 'speech_balloon_3d'); }, () => {}, undefined, 'lang'));
  }
  // the theme is a snap (owner, Oct 31): the menu fades, the row's sun turns into the moon (or back) with a spring, and
  // at its peak a click and the new theme grows from that icon. The menu is gone by then (its exit is 150 ms), so the
  // transition's snapshots never hold it; the icon's tail plays in the live new snapshot, the circle opening on it
  $effect.pre(() => { glyph.dark = theme.current === 'dark'; });
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('lowfx');
  // no "as in the system" item: until a pick the app follows Telegram's scheme on its own (owner, Oct 31)
  function look(to: Theme, ic: Element | null) {
    if (theme.chosen === to) return;
    keep({ theme: to });
    if (to === theme.current) return chooseTheme(to); // the look stays: nothing to play
    glyph.dark = to === 'dark';
    setTimeout(() => {
      haptic.rigid();
      chooseTheme(to, ic ?? undefined);
      say(phrase(`say.theme.${to}`), to === 'dark' ? 'crescent_moon_3d' : 'sparkles_3d');
    }, still() ? 0 : 160);
  }
  const POWER_EMOJI = { on: 'hot_beverage_3d', off: 'high_voltage_3d', auto: 'robot_3d' } as const;
  // my events in the phone's calendar, through our page (server/kbtu/calpage.py); asked on the tap: the address makes a
  // feed token on the server, and a reset kills the old link
  async function subscribe() {
    let cal: { page: string; feed: string };
    try { cal = await api.calendarFeed(); } catch { say(t('common.error'), 'warning_3d'); return; }
    openLink(cal.page);
  }
  $effect(() => on('homeScreenAdded', () => { home.v = 'added'; clearTimeout(homeWait); say(t('set.homeDone'), 'rocket_3d'); }));
  // Android: a launcher that forbids Telegram's shortcuts (Xiaomi, Huawei...) swallows the dialog without a word;
  // no "added" within a few seconds -> say where to allow it (owner, Nov 2: "the button does nothing")
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
    <input bind:this={file} type="file" accept="image/*" hidden onchange={(e) => void upload(e.currentTarget.files?.[0])} />
    <div data-unit class="first">
      <Group><Row icon={IdCard} title={t('look.lanyard')} value={wornName} accessory="chevron" onclick={() => { haptic.tap(); onlanyard(); }} /></Group>
    </div>
    <div data-unit class="sec">
      <Group caption={t('set.myData')} footnote={t('look.nickFoot')}>
        <Row icon={ImageIcon} title={t('look.photo')} value={me.photo.telegram ? 'Telegram' : t('look.own')} menu={photoItems()} />
        <Row icon={User} title={t('set.name')} value={[me.student.firstName, me.student.lastName].filter(Boolean).join(' ')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('name'); }} />
        {#if me.nick}<Row icon={AtSign} title={t('look.nick')} value={me.nick} menu={[{ label: t('look.nickEdit'), onselect: () => void editNick() }, { label: t('look.dropNick'), destructive: true, onselect: () => setNick(null) }]} />
        {:else}<Row icon={AtSign} title={t('look.nick')} value={t('look.noNick')} accessory="chevron" onclick={() => { haptic.tap(); void editNick(); }} />{/if}
        <Row icon={School} title={t('look.school')} value={schoolShort(me.student.school) || t('look.noSchool')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('school'); }} />
        {#if courseFix}<Row icon={GraduationCap} title={t('pd.course')} value={String(me.student.course ?? '')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('course'); }} />
        {:else if me.student.course}<Row icon={GraduationCap} title={t('pd.course')} value={String(me.student.course)} />{/if}
        <Row icon={MapPin} title={t('pd.city')} value={me.city ? cityName(me.city.name, i18n.lang) : t('pd.cityNone')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('city'); }} />
        {#if phone}<Row icon={Phone} title={t('pd.phoneShort')} value={phone} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('phone'); }} />{/if}
      </Group>
    </div>
  {:else}
    <div class="spacer"></div>
  {/if}

  <div data-unit class="sec" class:first={!me?.student}>
    <Group caption={t('set.app')}>
      <Row icon={Languages} title={t('me.guestLang')} value={LANG_FULL[i18n.lang]} menu={LANGS.map((l) => ({ label: LANG_FULL[l], checked: i18n.lang === l, instant: true, onselect: () => lang(l) }))} />
      <Row icon={ThemeGlyph} title={t('me.guestTheme')} value={t(`theme.${theme.current}`)} menu={(['dark', 'light'] as const).map((x) => ({ label: t(`theme.${x}`), checked: theme.current === x, onselect: () => look(x, glyph.el) }))} />
      {#if me?.student}
        <Row icon={Bell} title={t('me.notifications')} value={bells === 3 ? t('set.on') : bells ? `${bells}/3` : t('set.off')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('notify'); }} />
        <Row icon={CalendarDays} title={t('set.calShort')} accessory="external" onclick={() => { haptic.tap(); void subscribe(); }} />
      {/if}
      <Row icon={BatteryMedium} title={t('power.title')} value={t(`power.${power.mode}`)} menu={POWER_MODES.map((m) => ({ label: t(`power.${m}`), checked: power.mode === m,
        onselect: () => { if (power.mode !== m) { setPowerMode(m); say(phrase(`say.power.${m}`), POWER_EMOJI[m]); } } }))} />
      {#if home.v === 'unknown' || home.v === 'missed'}<Row icon={Smartphone} title={t('set.homeShort')} tone="action" onclick={addHome} />{/if}
    </Group>
  </div>

  <div data-unit class="sec">
    <Group>
      {#if me?.student}<Row icon={Lock} title={t('set.privacy')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('privacy'); }} />{/if}
      <Row icon={Info} title={t('set.about')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('about'); }} />
      <!-- the voluntary support page: this row is its only way in, no banners or reminders anywhere (donate-review.md) -->
      {#if session.donate}<Row icon={HandHeart} title={t('set.donate')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('donate'); }} />{/if}
    </Group>
  </div>
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
