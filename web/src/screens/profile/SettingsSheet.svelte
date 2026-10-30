<script lang="ts">
  // A Settings row's page, pushed in from the right (ui/Pane), the phone's own way: a list to pick from with a check
  // (language, appearance, power saving), the notification switches with a footnote under each, Privacy (my phone and
  // my city, each its own page with what can be done to it; who sees what; the policy; deleting the account) and About.
  // A row that leaves the app (the browser, Telegram) ends in ↗, one that stays in it in ›.
  import Check from '@lucide/svelte/icons/check';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Lock from '@lucide/svelte/icons/lock';
  import Languages from '@lucide/svelte/icons/languages';
  import SunMoon from '@lucide/svelte/icons/sun-moon';
  import Bell from '@lucide/svelte/icons/bell';
  import Info from '@lucide/svelte/icons/info';
  import Phone from '@lucide/svelte/icons/phone';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import { power, setPowerMode, POWER_MODES } from '../../lib/state/power.svelte';
  import { say, close, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { data, phrase, loadMyCard } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api, type Settings } from '../../lib/api';
  import { inner } from '../../lib/perms';
  import { t, i18n, setLang, loadLang, LANGS, LANG_FULL, type Lang, type Key } from '../../lib/i18n/index.svelte';
  import { theme, chooseTheme, reveal } from '../../lib/state/theme.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { fmtPhone, kzPhone } from '../../lib/phone';
  import Pane from '../../ui/Pane.svelte';

  type Kind = 'lang' | 'look' | 'notify' | 'power' | 'privacy' | 'phone' | 'city' | 'sees' | 'about';
  let { overlay, kind }: { overlay: Overlay; kind: Kind } = $props();
  const TITLE: Record<Kind, [Key, typeof Lock]> = { lang: ['me.guestLang', Languages], look: ['me.guestTheme', SunMoon], notify: ['me.notifications', Bell],
    power: ['power.title', BatteryMedium], privacy: ['set.privacy', Lock], phone: ['pd.phone', Phone], city: ['pd.city', MapPin], sees: ['set.whoSees', Lock], about: ['set.about', Info] };
  // where "‹ Back" goes: Privacy for its own pages, else Settings
  const BACK: Key = $derived(kind === 'phone' || kind === 'city' || kind === 'sees' ? 'set.privacy' : 'me.settings');
  const me = $derived(session.me);
  const phone = $derived(me?.student?.phone ? (kzPhone(me.student.phone) ? fmtPhone(me.student.phone) : me.student.phone) : '');

  // language and theme live on the phone; the server keeps them too, so the bot writes in your language
  const keep = (patch: Partial<Settings>) => { if (me) api.updateMe(patch).then((m) => (session.me = m)).catch(() => {}); };
  function lang(l: Lang) {
    if (i18n.lang === l) return;
    haptic.select(); keep({ lang: l });
    void loadLang(l).then(() => reveal(() => { setLang(l); say(phrase('say.lang'), 'speech_balloon_3d'); }, () => {}, undefined, 'lang'));
  }
  function look(x: 'dark' | 'light', el: Element) {
    if (theme.current === x) return;
    haptic.select(); chooseTheme(x, el); keep({ theme: x });
    say(phrase(`say.theme.${x}`), x === 'dark' ? 'crescent_moon_3d' : 'sparkles_3d');
  }
  const POWER_EMOJI = { on: 'hot_beverage_3d', off: 'high_voltage_3d', auto: 'robot_3d' } as const;
  const NOW = { fps: 'power.now.fps', battery: 'power.now.battery', device: 'power.now.device' } as const;
  const now = $derived(power.mode === 'on' ? 'power.now.on' : power.mode === 'off' ? 'power.now.off' : power.why ? NOW[power.why] : 'power.now.autoOff');

  // a switch saves at once and puts itself back if the server says no
  const SWITCHES = [['nRemind', 'set.remind', 'set.remindHint'], ['nNewEvents', 'set.newEvents', 'set.newEventsHint'], ['nForum', 'set.forum', 'set.forumHint']] as const;
  async function set(k: (typeof SWITCHES)[number][0], on: boolean) {
    if (!me) return;
    haptic.tap();
    me.settings[k] = on;
    try { session.me = await api.updateMe({ [k]: on }); say(phrase(on ? 'say.notifyOn' : 'say.notifyOff'), on ? 'megaphone_3d' : 'crescent_moon_3d'); }
    catch { if (session.me) session.me.settings[k] = !on; say(t('common.error'), 'pleading_face_3d'); } // the one on screen now
  }

  // My data (PLAN 71): the phone an event asked for, changed or deleted (null deletes it); the city from the club's
  // roster (PLAN 95), off the profile or gone. A deleted one takes its page with it.
  async function savePhone(p: string | null, done: string) {
    try { session.me = await api.updateMe({ phone: p }); haptic.ok(); say(done, 'sparkles_3d'); if (p == null) close(overlay.id); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function editPhone() {
    const p = await sheets.askText({ title: t('pd.phone'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: '+7 (707) 123 45 67', max: 18, tel: true });
    if (p) await savePhone(p, t('pd.saved'));
  }
  async function dropPhone() {
    if (await sheets.ask({ title: t('pd.delAsk'), text: t('pd.delText'), ok: t('pd.del'), cancel: t('common.cancel'), danger: true })) await savePhone(null, t('pd.deleted'));
  }
  async function cityHidden(on: boolean) {
    try { session.me = await api.updateMe({ cityHidden: on }); void loadMyCard(); haptic.select(); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
  }
  async function dropCity() {
    if (!(await sheets.ask({ title: t('pd.cityDelAsk'), ok: t('pd.del'), cancel: t('common.cancel'), danger: true }))) return;
    try { session.me = await api.updateMe({ city: null }); void loadMyCard(); say(t('pd.deleted'), 'sparkles_3d'); close(overlay.id); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
  }
  // the calendar's address leaked (sent to someone, a shared screen): the old one stops, Calendar makes a new one
  async function resetCal() {
    if (!(await sheets.ask({ title: t('set.calResetAsk'), text: t('set.calResetText'), ok: t('set.calResetOk'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.resetCalendar(); haptic.ok(); say(t('set.calResetDone'), 'sparkles_3d'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // §4.8: what goes, then a week to change one's mind (a President's club passes on at the deletion: the sheet says so)
  function deleteData() {
    const a = data.myCard?.awards;
    const tickets = data.events.filter((e) => e.my && e.my.status !== 'cancelled' && !inner(e)).length;
    sheets.deleteAccount({ awards: a ? a.achievements.filter((x) => x.level > 0).length + a.badges.length : 0, tickets, clubs: me?.memberships.length ?? 0 });
  }
  // what we keep about a student first
  const SEES = [['set.portal', 'set.portalText'], ['set.allSee', 'set.allSeeText'], ['set.orgSee', 'set.orgSeeText'],
    ['set.teamSee', 'set.teamSeeText'], ['set.youSee', 'set.youSeeText'], ['set.never', 'set.neverText']] as const;
  const page = (path: string) => openLink(`${location.origin}/${path}?lang=${i18n.lang}`);
</script>

{#snippet pick(label: string, on: boolean, go: (el: Element) => void)}
  <button class="set-row" aria-pressed={on} onclick={(e) => go(e.currentTarget)}><span class="lb">{label}</span>{#if on}<Check class="ok" size={20} strokeWidth={2.4} />{/if}</button>
{/snippet}
<!-- in the app: ›; out of it (out = true): ↗ -->
{#snippet link(label: string, go: () => void, value = '', out = false)}
  <button class="set-row" onclick={() => { haptic.tap(); go(); }}><span class="lb">{label}</span>{#if value}<span class="val">{value}</span>{/if}
    {#if out}<ArrowUpRight class="chev" size={18} />{:else}<ChevronRight class="chev" size={18} />{/if}</button>
{/snippet}
{#snippet act(label: string, go: () => void, red = false)}
  <button class="set-row act" class:red onclick={() => { haptic.tap(); go(); }}><span class="lb">{label}</span></button>
{/snippet}

<Pane {overlay} title={t(TITLE[kind][0])} icon={TITLE[kind][1]} back={t(BACK)}>
  {#if kind === 'lang'}
    <div class="set-group plain">{#each LANGS as l (l)}{@render pick(LANG_FULL[l], i18n.lang === l, () => lang(l))}{/each}</div>
  {:else if kind === 'look'}
    <div class="set-group plain">
      {@render pick(t('theme.dark'), theme.current === 'dark', (el) => look('dark', el))}
      {@render pick(t('theme.light'), theme.current === 'light', (el) => look('light', el))}
    </div>
  {:else if kind === 'power'}
    <div class="set-group plain">
      {#each POWER_MODES as m (m)}{@render pick(t(`power.${m}`), power.mode === m, () => { if (power.mode !== m) { haptic.select(); setPowerMode(m); say(phrase(`say.power.${m}`), POWER_EMOJI[m]); } })}{/each}
    </div>
    <p class="set-foot">{t(now)}{#if power.mode === 'auto' && power.fps}{' '}{t('power.fps', { n: power.fps })}{/if}</p>
    <p class="set-foot">{t('power.lead')} {t('power.what')}</p>
  {:else if kind === 'notify' && me}
    {#each SWITCHES as [k, title, hint] (k)}
      <div class="sw">
        <label class="set-group plain sw-on"><span class="set-row"><span class="lb">{t(title)}</span>
          <input type="checkbox" role="switch" checked={me.settings[k]} onchange={(e) => set(k, e.currentTarget.checked)} /></span></label>
        <p class="set-foot">{t(hint)}</p>
      </div>
    {/each}
    <p class="set-foot always">{t('set.always')}</p>
  {:else if kind === 'privacy'}
    <!-- my data: one row each, what can be done to it a tap deeper -->
    {#if phone || me?.city}
      <div class="set-group plain">
        {#if phone}{@render link(t('pd.phoneShort'), () => sheets.settings('phone'), phone)}{/if}
        {#if me?.city}{@render link(t('pd.city'), () => sheets.settings('city'), me.city.name)}{/if}
      </div>
    {/if}
    <div class="set-group plain" class:gap={phone || me?.city}>
      {@render link(t('set.whoSees'), () => sheets.settings('sees'))}
      {@render link(t('set.policy'), () => page('privacy'), '', true)}
    </div>
    {#if me?.student && !me.deleteAt}
      <div class="set-group plain gap">{@render act(t('set.calReset'), resetCal, true)}</div>
      <div class="set-group plain gap">{@render act(t('me.deleteData'), deleteData, true)}</div>
    {/if}
  {:else if kind === 'phone'}
    <div class="set-group plain"><div class="set-row"><span class="lb big">{phone}</span></div></div>
    <p class="set-foot">{t('pd.note')}</p>
    <div class="set-group plain gap">{@render act(t('pd.phoneEdit'), editPhone)}{@render act(t('pd.phoneDel'), dropPhone, true)}</div>
  {:else if kind === 'city' && me?.city}
    <div class="set-group plain sw-on">
      <div class="set-row"><span class="lb big">{me.city.name}</span></div>
      <label class="set-row"><span class="lb">{t('pd.cityHide')}</span><input type="checkbox" role="switch" checked={me.city.hidden} onchange={(e) => cityHidden(e.currentTarget.checked)} /></label>
    </div>
    <p class="set-foot">{t('pd.cityNote')}</p>
    <div class="set-group plain gap">{@render act(t('pd.cityDel'), dropCity, true)}</div>
  {:else if kind === 'sees'}
    <div class="set-group plain">
      {#each SEES as [h, text] (h)}<div class="see"><b>{t(h)}</b><p>{t(text)}</p></div>{/each}
    </div>
  {:else if kind === 'about'}
    <div class="set-group plain">
      {@render link(t('set.terms'), () => page('terms'), '', true)}
      {@render link(t('set.policy'), () => page('privacy'), '', true)}
      {@render link(t('set.write'), () => openLink('https://t.me/Sowers'), '@Sowers', true)}
      {@render link(t('set.code'), () => openLink('https://github.com/SOWcd/KBTUapp'), 'GitHub', true)}
    </div>
  {/if}
</Pane>

<style>
  .set-row :global(.ok) { flex: none; color: var(--accent-text); }
  .big { font-size: 19px; font-weight: 600; }
  .sw + .sw { margin-top: 22px; }
  .always { margin-top: 26px; }
  .gap { margin-top: 26px; }
  /* who sees what: a heading and its text in each cell, read rather than tapped */
  .see { padding: 12px 16px; }
  .see + .see { border-top: 1px solid var(--line); }
  .see b { display: block; font: 600 16px/1.3 var(--font-text); }
  .see p { margin-top: 3px; font: 450 15px/1.45 var(--font-text); color: var(--text-2); }
</style>
