<script lang="ts">
  // A page pushed in from the right (ui/Pane) from the settings under my lanyard (Me), the phone's own way: the
  // notification switches with a footnote under each, Privacy (my phone and my city, each its own page with what can be
  // done to it; whether friends see where I'm going; who sees what; the policy; deleting the account) and About.
  // A row that leaves the app (the browser, Telegram) ends in ↗, one that stays in it in ›.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Lock from '@lucide/svelte/icons/lock';
  import Bell from '@lucide/svelte/icons/bell';
  import Info from '@lucide/svelte/icons/info';
  import Phone from '@lucide/svelte/icons/phone';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import { say, close, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { data, phrase, loadMyCard } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api } from '../../lib/api';
  import { inner } from '../../lib/perms';
  import { t, i18n, type Key } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { fmtPhone, kzPhone } from '../../lib/phone';
  import Pane from '../../ui/Pane.svelte';

  type Kind = 'notify' | 'privacy' | 'phone' | 'city' | 'sees' | 'about';
  let { overlay, kind }: { overlay: Overlay; kind: Kind } = $props();
  const TITLE: Record<Kind, [Key, typeof Lock]> = { notify: ['me.notifications', Bell], privacy: ['set.privacy', Lock], phone: ['pd.phone', Phone], city: ['pd.city', MapPin], sees: ['set.whoSees', Lock], about: ['set.about', Info] };
  // where "‹ Back" goes: Privacy for its own pages, else Settings
  const BACK: Key = $derived(kind === 'phone' || kind === 'city' || kind === 'sees' ? 'set.privacy' : 'me.settings');
  const me = $derived(session.me);
  const phone = $derived(me?.student?.phone ? (kzPhone(me.student.phone) ? fmtPhone(me.student.phone) : me.student.phone) : '');

  // a switch saves at once and puts itself back if the server says no
  const SWITCHES = [['nRemind', 'set.remind', 'set.remindHint'], ['nNewEvents', 'set.newEvents', 'set.newEventsHint'], ['nForum', 'set.forum', 'set.forumHint']] as const;
  // (quiet: no toast, the label says it all: whether friends see where I'm going)
  async function set(k: (typeof SWITCHES)[number][0] | 'showGoing', on: boolean, quiet = false) {
    if (!me) return;
    haptic.tap();
    me.settings[k] = on;
    try { session.me = await api.updateMe({ [k]: on }); if (!quiet) say(phrase(on ? 'say.notifyOn' : 'say.notifyOff'), on ? 'megaphone_3d' : 'crescent_moon_3d'); }
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

<!-- in the app: ›; out of it (out = true): ↗ -->
{#snippet link(label: string, go: () => void, value = '', out = false)}
  <button class="set-row" onclick={() => { haptic.tap(); go(); }}><span class="lb">{label}</span>{#if value}<span class="val">{value}</span>{/if}
    {#if out}<ArrowUpRight class="chev" size={18} />{:else}<ChevronRight class="chev" size={18} />{/if}</button>
{/snippet}
{#snippet act(label: string, go: () => void, red = false)}
  <button class="set-row act" class:red onclick={() => { haptic.tap(); go(); }}><span class="lb">{label}</span></button>
{/snippet}

<Pane {overlay} title={t(TITLE[kind][0])} icon={TITLE[kind][1]} back={t(BACK)}>
  {#if kind === 'notify' && me}
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
    {#if me?.student}
      <!-- friends only: my profile's events, Afisha's faces, "bring a friend" (the server's showGoing) -->
      <label class="set-group plain sw-on" class:gap={phone || me.city}><span class="set-row"><span class="lb">{t('set.showGoing')}</span>
        <input type="checkbox" role="switch" checked={me.settings.showGoing} onchange={(e) => set('showGoing', e.currentTarget.checked, true)} /></span></label>
    {/if}
    <div class="set-group plain" class:gap={phone || me?.city || me?.student}>
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
