<script lang="ts">
  // Profile → Settings, the third page (mockup v24, owner Oct 21; until then a sheet behind a gear). Language and theme,
  // what the bot sends (switches right here), the phone, "My data" (only what an event asked for, once there is
  // some: PLAN 71), "About the app" (who sees what, the rules, the code: an overlay, so Telegram's Back closes it),
  // deleting the account last and quiet.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import { session } from '../../lib/state/session.svelte';
  import { data, phrase } from '../../lib/state/data.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api, type Settings } from '../../lib/api';
  import { inner } from '../../lib/perms';
  import { t, i18n, setLang, LANGS, LANG_NAMES } from '../../lib/i18n/index.svelte';
  import { theme, chooseTheme, reveal } from '../../lib/state/theme.svelte';
  import { power } from '../../lib/state/power.svelte';
  import { haptic, openLink, tg } from '../../lib/tg';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { fmtPhone } from '../../lib/phone';

  const me = $derived(session.me);
  // language and theme live on the phone; the server keeps them too, so the bot writes in your language
  const keep = (patch: Partial<Settings>) => { if (me) api.updateMe(patch).then((m) => (session.me = m)).catch(() => {}); };

  const SWITCHES = [['nRemind', 'set.remind', 'set.remindHint'], ['nNewEvents', 'set.newEvents', 'set.newEventsHint']] as const;
  // a switch saves at once and puts itself back if the server says no
  async function set(k: 'nRemind' | 'nNewEvents', on: boolean) {
    if (!me) return;
    haptic.tap();
    me.settings[k] = on;
    try { session.me = await api.updateMe({ [k]: on }); say(phrase(on ? 'say.notifyOn' : 'say.notifyOff'), on ? 'megaphone_3d' : 'crescent_moon_3d'); }
    catch { if (session.me) session.me.settings[k] = !on; say(t('common.error'), 'pleading_face_3d'); } // the one on screen now
  }

  // my events in the phone's calendar: Apple through our page that hands webcal:// over, the rest through Google. Asked
  // for on the tap: the page mounts unseen next to Me, and the address makes a feed token on the server
  let cal: { page: string; feed: string } | null = null;
  async function subscribe() {
    haptic.tap();
    try { cal ??= await api.calendarFeed(); } catch { say(t('common.error'), 'pleading_face_3d'); return; }
    openLink(/^(ios|macos)$/.test(tg.platform) ? cal.page : 'https://calendar.google.com/calendar/render?cid=' + encodeURIComponent(cal.feed));
  }

  // My data (PLAN 71): the phone an event asked for, seen, changed or deleted here (null deletes it)
  async function savePhone(phone: string | null, done: string) {
    try { session.me = await api.updateMe({ phone }); haptic.ok(); say(done, 'sparkles_3d'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function editPhone() {
    haptic.tap();
    const p = await sheets.askText({ title: t('pd.phone'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: '+7 707 123 45 67', max: 16, tel: true });
    if (p) await savePhone(p, t('pd.saved'));
  }
  async function dropPhone() {
    haptic.tap();
    if (await sheets.ask({ title: t('pd.delAsk'), text: t('pd.delText'), ok: t('pd.del'), cancel: t('common.cancel'), danger: true })) await savePhone(null, t('pd.deleted'));
  }

  // §4.8: what goes, then a week to change one's mind (a President's club passes on at the deletion: the sheet says so)
  function deleteData() {
    const a = data.myCard?.awards;
    const tickets = data.events.filter((e) => e.my && e.my.status !== 'cancelled' && !inner(e)).length;
    sheets.deleteAccount({ awards: a ? a.achievements.filter((x) => x.level > 0).length + a.badges.length : 0, tickets, clubs: me?.memberships.length ?? 0 });
  }
</script>

<div class="page scroll">
  <h1 class="ttl">{t('me.settings')}</h1>
  <div class="rows surface">
    <div class="r"><span class="lb">{t('me.guestLang')}</span>
      <span class="seg">{#each LANGS as l (l)}<button class:on={i18n.lang === l} onclick={() => { if (i18n.lang !== l) { haptic.select(); keep({ lang: l }); reveal(() => { setLang(l); say(phrase('say.lang'), 'speech_balloon_3d'); }, () => {}, undefined, 'lang'); } }}>{LANG_NAMES[l]}</button>{/each}</span></div>
    <div class="r"><span class="lb">{t('me.guestTheme')}</span>
      <span class="seg"><button class:on={theme.current === 'dark'} onclick={(e) => { if (theme.current !== 'dark') { chooseTheme('dark', e.currentTarget); keep({ theme: 'dark' }); say(phrase('say.theme.dark'), 'crescent_moon_3d'); } }}>{t('theme.dark')}</button><button class:on={theme.current === 'light'} onclick={(e) => { if (theme.current !== 'light') { chooseTheme('light', e.currentTarget); keep({ theme: 'light' }); say(phrase('say.theme.light'), 'sparkles_3d'); } }}>{t('theme.light')}</button></span></div>
  </div>

  {#if me?.student}
    <h2 class="sec">{t('me.notifications')}<span>{t('set.notifyBot')}</span></h2>
    <div class="rows surface">
      {#each SWITCHES as [k, title, hint] (k)}
        <label class="r switch"><span><b>{t(title)}</b><i>{t(hint)}</i></span>
          <input type="checkbox" role="switch" checked={me.settings[k]} onchange={(e) => set(k, e.currentTarget.checked)} /></label>
      {/each}
    </div>
    <p class="note">{t('set.always')}</p>
  {/if}

  <h2 class="sec">{t('set.phone')}</h2>
  <div class="rows surface">
    <button class="r" onclick={() => sheets.settings('power')}>
      <span class="lb">{t('power.title')}<i>{t(power.mode === 'auto' ? (power.lite ? 'power.sub.autoOn' : 'power.sub.autoOff') : power.mode === 'on' ? 'power.sub.on' : 'power.sub.off')}</i></span><ChevronRight size={18} /></button>
    {#if me?.student}
      <button class="r" onclick={subscribe}><span class="lb">{t('me.calendar')}<i>{t('set.calendarSub')}</i></span><ChevronRight size={18} /></button>
    {/if}
  </div>

  {#if me?.student?.phone}
    <h2 class="sec">{t('pd.title')}</h2>
    <div class="rows surface">
      <div class="r"><button class="lb" onclick={editPhone}>{t('pd.phone')}<i>{fmtPhone(me.student.phone)}</i></button>
        <button class="x" aria-label={t('pd.del')} onclick={dropPhone}><Trash2 size={18} /></button></div>
    </div>
    <p class="note">{t('pd.note')}</p>
  {/if}

  <div class="rows surface about">
    <button class="r" onclick={() => sheets.settings('privacy')}><span class="mk"><KbtuMark size={20} /></span>
      <span class="lb">{t('set.about')}<i>{t('set.aboutSub')}</i></span><ChevronRight size={18} /></button>
  </div>

  {#if me?.student && !me.deleteAt}
    <button class="del" onclick={deleteData}>{t('me.deleteData')}</button>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: 12px; }
  .page > :global(*) { flex-shrink: 0; }
  .ttl { margin: 6px 4px 8px; font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .sec { display: flex; align-items: baseline; gap: 8px; margin: 20px 4px 0; font: 760 var(--fs-sec)/1.1 var(--font-display); letter-spacing: -0.025em; }
  .sec span { font: 550 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); letter-spacing: 0; }
  .rows { display: flex; flex-direction: column; overflow: hidden; border-radius: var(--r-l); }
  .r { display: flex; align-items: center; gap: 12px; min-height: 56px; padding: 10px 16px; text-align: left; color: var(--text-3); }
  .r + .r { box-shadow: inset 0 1px 0 var(--line); }
  button.r:active { background: var(--surface-2); }
  .lb, .switch b { flex: 1; min-width: 0; font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  .lb i, .switch i { display: block; margin-top: 2px; font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-3); }
  .switch { justify-content: space-between; border-radius: 0; background: none; }
  .switch > span { flex: 1; }
  .switch b { display: block; }
  .seg { display: inline-flex; gap: 2px; padding: 3px; border-radius: var(--r-full); background: var(--surface-2); }
  .seg button { height: 30px; padding: 0 12px; border-radius: var(--r-full); font: 620 var(--fs-sub)/1 var(--font-text); color: var(--text-2); }
  .seg button.on { background: var(--text); color: var(--bg); }
  .note { margin: 0 4px; font: 500 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  button.lb { text-align: left; }
  .x { display: flex; padding: 8px; margin-right: -8px; color: var(--danger-text); }
  .about { margin-top: 20px; }
  .mk { display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 10px; color: #fff; background: linear-gradient(135deg, #2A4FD6, #5B2BC0); }
  .del { align-self: center; margin-top: 18px; padding: 8px 14px; font: 600 var(--fs-body)/1 var(--font-text); color: var(--danger-text); }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
</style>
