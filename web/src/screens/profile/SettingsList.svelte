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
  // Sections (each a unit Me animates, [data-unit]): the lanyard (the carousel of skins; my photo and nick), the app,
  // then privacy and about. A guest: the app and about.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ChevronsUpDown from '@lucide/svelte/icons/chevrons-up-down';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import ImageIcon from '@lucide/svelte/icons/image';
  import AtSign from '@lucide/svelte/icons/at-sign';
  import Languages from '@lucide/svelte/icons/languages';
  import Sun from '@lucide/svelte/icons/sun';
  import Moon from '@lucide/svelte/icons/moon';
  import Bell from '@lucide/svelte/icons/bell';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import Smartphone from '@lucide/svelte/icons/smartphone';
  import Lock from '@lucide/svelte/icons/lock';
  import Info from '@lucide/svelte/icons/info';
  import { api, ApiErr, type Me, type Settings } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { data, phrase } from '../../lib/state/data.svelte';
  import { say, ui, overlays } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, i18n, setLang, loadLang, LANGS, LANG_FULL, type Lang } from '../../lib/i18n/index.svelte';
  import { theme, chooseTheme, reveal, type Theme } from '../../lib/state/theme.svelte';
  import { power, setPowerMode, POWER_MODES } from '../../lib/state/power.svelte';
  import { haptic, openLink, on, tg } from '../../lib/tg';
  import { menu, type MenuItem } from '../../ui/menu';
  import { skinOf, skinned, STRAP, banded, type Look } from '../../lib/awards';
  import LanyardBand from '../../ui/LanyardBand.svelte';
  import { byRank } from '../../lib/perms';

  const me = $derived(session.me);
  const s = $derived(me?.settings);
  const bells = $derived(s ? [s.nRemind, s.nNewEvents, s.nForum].filter(Boolean).length : 0);
  const real = $derived(me?.student ? `${me.student.firstName} ${me.student.lastName.slice(0, 1)}.` : '');

  // the lanyards: my clubs' by my role in them (owner, Oct 13: "no chaos"), then every other club's to try on, KBTU's
  // last; SOWER first for the founder
  const mine = $derived(me ? [...me.memberships].sort(byRank).map((m) => m.org).filter(skinned) : []);
  const skins = $derived([...mine, ...data.orgs.filter((o) => skinned(o) && !mine.some((x) => x.id === o.id))]);
  const swatches = $derived([...(me?.founder ? [{ id: 'sower' as const, kind: 'sower', name: 'SOWER', word: 'SOWER' }] : []),
    ...skins.map((o) => ({ id: o.id, kind: skinOf(o)!, name: o.name, word: STRAP[skinOf(o)!] })), { id: null, kind: 'kbtu', name: 'KBTU', word: 'KBTU' }]);

  let busy = false;
  // no toast on a skin (owner, Oct 29): the lanyard above turns at once (Hero); a failure puts the old one back
  async function pickSkin(id: number | 'sower' | null) {
    if (busy || !me || id === me.skin) return;
    const was = me;
    busy = true;
    session.me = { ...me, skin: id };
    try { session.me = await api.updateMe({ skin: id }); } catch (e) { session.me = was; oops(e); } finally { busy = false; }
  }

  function oops(e: unknown) {
    haptic.error();
    say(e instanceof ApiErr && e.message === 'nick' ? t('look.badNick') : e instanceof ApiErr && e.message === 'not_an_image' ? t('look.badPhoto') : t('common.error'), 'pleading_face_3d');
  }
  // one change of my photo or nick at a time; `word`: what the capsule says meanwhile (an upload takes a moment)
  async function work(job: () => Promise<Me>, msg: (m: Me) => string, word = '') {
    if (busy) return;
    busy = true; ui.busy = word;
    try { const m = await job(); session.me = m; haptic.ok(); say(msg(m), 'sparkles_3d'); } catch (e) { oops(e); } finally { busy = false; ui.busy = ''; }
  }

  // ---- the photo: Telegram's (it refreshes by itself) or my own ----
  let file = $state<HTMLInputElement>();
  function upload(f: File | undefined) {
    if (f) void work(() => api.uploadMyPhoto(f), () => t('look.photoSet'), t('look.uploading')).then(() => { if (file) file.value = ''; });
  }
  async function dropOwn() {
    if (await sheets.ask({ title: t('look.dropOwn'), ok: t('look.dropOwn'), cancel: t('common.cancel'), danger: true })) void work(() => api.deleteMyPhoto(), () => t('look.photoGone'));
  }
  /** the photo's menu, at its row or at my photo on the lanyard (Me) */
  export function photoMenu(at: Element, align?: 'start' | 'end') {
    if (!me) return;
    const { telegram, own } = me.photo;
    open('photo', at, [
      { label: t('look.fromTg'), checked: telegram, onselect: () => { if (!telegram) void work(() => api.updateMe({ avatarTg: true }), () => t('look.tgOn')); } },
      ...(own ? [{ label: t('look.own'), checked: !telegram, onselect: () => { if (telegram) void work(() => api.updateMe({ avatarTg: false }), () => t('look.photoSet')); } }] : []),
      // instant: the file picker opens inside the tap itself (iOS opens none from a later task)
      { label: t('look.upload'), instant: true, onselect: () => file?.click() },
      ...(own ? [{ label: t('look.dropOwn'), destructive: true, onselect: () => void dropOwn() }] : []),
    ], align);
  }

  // ---- the nick: everyone sees it, organizers see my real name beside it ----
  async function editNick() {
    const v = await sheets.askText({ title: t('look.nick'), placeholder: t('look.nickPh'), max: 24, line: true, value: me?.nick ?? '', ok: t('common.save'), cancel: t('common.cancel') });
    if (v != null && v !== (me?.nick ?? '')) setNick(v);
  }
  const setNick = (v: string | null) => void work(() => api.updateMe({ nick: v }), (m) => t(m.nick ? 'look.nickSet' : 'look.nickOff'));
  function nickMenu(at: Element) {
    open('nick', at, [{ label: t('look.nickEdit'), onselect: () => void editNick() }, { label: t('look.dropNick'), destructive: true, onselect: () => setNick(null) }]);
  }

  // ---- the app ----
  // language and theme live on the phone; the server keeps them too, so the bot writes in your language
  const keep = (patch: Partial<Settings>) => { if (me) api.updateMe(patch).then((m) => (session.me = m)).catch(() => {}); };
  function lang(l: Lang) {
    if (i18n.lang === l) return;
    keep({ lang: l });
    void loadLang(l).then(() => reveal(() => { setLang(l); say(phrase('say.lang'), 'speech_balloon_3d'); }, () => {}, undefined, 'lang'));
  }
  // the theme is a snap (owner, Oct 31): the menu fades, the row's sun turns into the moon (or back) with a spring, and
  // at its peak a click and the new theme grows from that icon. The menu is gone by then (its exit is 150 ms), so the
  // transition's snapshots never hold it; the icon's tail plays in the live new snapshot, the circle opening on it
  let glyph = $derived(theme.current);
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('lowfx');
  function look(x: Theme | null, ic: Element) {
    if (theme.chosen === x) return;
    keep({ theme: x });
    const to = x ?? tg.colorScheme();
    if (to === theme.current) return chooseTheme(x); // the look stays: nothing to play
    glyph = to;
    setTimeout(() => {
      haptic.rigid();
      chooseTheme(x, ic);
      say(phrase(`say.theme.${to}`), to === 'dark' ? 'crescent_moon_3d' : 'sparkles_3d');
    }, still() ? 0 : 160);
  }
  const POWER_EMOJI = { on: 'hot_beverage_3d', off: 'high_voltage_3d', auto: 'robot_3d' } as const;
  // my events in the phone's calendar, through our page (server/kbtu/calpage.py); asked on the tap: the address makes a
  // feed token on the server, and a reset kills the old link
  async function subscribe() {
    let cal: { page: string; feed: string };
    try { cal = await api.calendarFeed(); } catch { say(t('common.error'), 'pleading_face_3d'); return; }
    openLink(cal.page);
  }
  $effect(() => on('homeScreenAdded', () => { home.v = 'added'; say(t('set.homeDone'), 'rocket_3d'); }));

  // a row's menu, open: its aria-expanded
  let opened = $state<{ row: string; id: number } | null>(null);
  const isOpen = (row: string) => opened?.row === row && overlays.some((o) => o.id === opened!.id && !o.closing);
  function open(row: string, at: Element, items: MenuItem[], align: 'start' | 'end' | undefined = 'end') { opened = { row, id: menu(at, items, align) }; }
  // the menu grows out of the row's value
  const at = (row: HTMLElement) => row.querySelector('.val') ?? row;
</script>

{#snippet row(Icon: typeof Bell, label: string, value: string, end: 'in' | 'menu' | 'out', go: (row: HTMLElement) => void, key = '')}
  <button class="set-row" aria-haspopup={end === 'menu' ? 'menu' : undefined} aria-expanded={end === 'menu' ? isOpen(key) : undefined}
    onclick={(e) => { haptic.tap(); go(e.currentTarget); }}>
    {#if key === 'theme'}<span class="ic sm" class:moon={glyph === 'dark'}><Sun size={20} strokeWidth={2} /><Moon size={20} strokeWidth={2} /></span>
    {:else}<span class="ic"><Icon size={20} strokeWidth={2} /></span>{/if}<span class="lb">{label}</span>{#if value}<span class="val">{value}</span>{/if}
    {#if end === 'in'}<ChevronRight class="chev" size={18} />{:else if end === 'menu'}<ChevronsUpDown class="chev" size={18} />{:else}<ArrowUpRight class="chev" size={18} />{/if}</button>
{/snippet}

<div class="set-list" role="region" aria-label={t('me.settings')}>
  {#if me?.student}
    <input bind:this={file} type="file" accept="image/*" hidden onchange={(e) => upload(e.currentTarget.files?.[0])} />
    <div data-unit>
      <h2 class="set-h first" tabindex="-1">{t('look.skin')}</h2>
      {#if skins.length || me.founder}
        <!-- each lanyard drawn small, as it hangs above (names alone said nothing; with many clubs the row scrolls) -->
        <div class="skins" role="radiogroup" aria-label={t('look.skin')}>
          {#each swatches as k (k.id ?? 'kbtu')}
            <button class="ly {k.kind}" role="radio" aria-checked={me.skin === k.id} class:on={me.skin === k.id} onclick={() => { haptic.select(); void pickSkin(k.id); }}>
              <span class="st"><i>{k.word}</i></span><span class="cl"></span>
              <span class="cd">{#if banded(k.kind as Look)}<span class="mini"><LanyardBand look={k.kind as Look} wide /></span>{/if}<span class="ph"></span><span class="ln"></span><span class="ln s"></span><span class="hl"></span></span>
              <b class="ellipsis">{k.name}</b>
            </button>
          {/each}
        </div>
      {/if}
    </div>
    <div data-unit>
      <div class="set-group">
        {@render row(ImageIcon, t('look.photo'), me.photo.telegram ? 'Telegram' : t('look.own'), 'menu', (r) => photoMenu(at(r)), 'photo')}
        {#if me.nick}{@render row(AtSign, t('look.nick'), me.nick, 'menu', (r) => nickMenu(at(r)), 'nick')}
        {:else}{@render row(AtSign, t('look.nick'), t('look.noNick'), 'in', () => void editNick())}{/if}
      </div>
      <p class="set-foot">{t('look.nickFoot', { name: real })}</p>
    </div>
  {:else}
    <div class="spacer"></div>
  {/if}

  <div data-unit>
    <h2 class="set-h" class:first={!me?.student} tabindex="-1">{t('set.app')}</h2>
    <div class="set-group">
      {@render row(Languages, t('me.guestLang'), LANG_FULL[i18n.lang], 'menu', (r) => open('lang', at(r), LANGS.map((l) => ({ label: LANG_FULL[l], checked: i18n.lang === l, instant: true, onselect: () => lang(l) }))), 'lang')}
      {@render row(Sun, t('me.guestTheme'), t(theme.chosen ? `theme.${theme.chosen}` : 'theme.system'), 'menu', (r) => open('theme', at(r), (['dark', 'light', null] as const).map((x) => ({
        label: t(x ? `theme.${x}` : 'theme.system'), checked: theme.chosen === x, onselect: () => look(x, r.querySelector('.ic')!) }))), 'theme')}
      {#if me?.student}
        {@render row(Bell, t('me.notifications'), bells === 3 ? t('set.on') : bells ? `${bells}/3` : t('set.off'), 'in', () => sheets.settings('notify'))}
        {@render row(CalendarDays, t('set.calShort'), '', 'out', () => void subscribe())}
      {/if}
      {@render row(BatteryMedium, t('power.title'), t(`power.${power.mode}`), 'menu', (r) => open('power', at(r), POWER_MODES.map((m) => ({ label: t(`power.${m}`), checked: power.mode === m,
        onselect: () => { if (power.mode !== m) { setPowerMode(m); say(phrase(`say.power.${m}`), POWER_EMOJI[m]); } } }))), 'power')}
      {#if home.v === 'unknown' || home.v === 'missed'}
        <button class="set-row act" onclick={() => { haptic.tap(); homeScreen.add(); }}><span class="ic"><Smartphone size={20} strokeWidth={2} /></span><span class="lb">{t('set.homeShort')}</span></button>
      {/if}
    </div>
  </div>

  <div data-unit>
    <div class="set-group gap">
      {#if me?.student}{@render row(Lock, t('set.privacy'), '', 'in', () => sheets.settings('privacy'))}{/if}
      {@render row(Info, t('set.about'), '', 'in', () => sheets.settings('about'))}
    </div>
  </div>
</div>

<style>
  /* Me's stagger child, but it rises by its units (Me): no second animation on top */
  .set-list { animation: none; display: flex; flex-direction: column; }
  .set-h { margin: 28px 4px 10px; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; color: var(--text); outline: none; }
  .set-h.first { margin-top: 20px; }
  .spacer { height: 44px; } /* a guest: the check sits where the student's gear does, never on the first title */
  .gap { margin-top: 28px; }
  .act .ic { color: inherit; }
  /* the theme row's sun and moon, one over the other; the one leaving turns away and shrinks, the other springs in */
  .sm > :global(svg) { grid-area: 1 / 1; transition: transform 300ms var(--ease-bounce), opacity 120ms ease; }
  .sm > :global(svg:last-child), .sm.moon > :global(svg:first-child) { opacity: 0; transform: rotate(-90deg) scale(0.3); }
  .sm.moon > :global(svg:first-child) { transform: rotate(90deg) scale(0.3); }
  .sm.moon > :global(svg:last-child) { opacity: 1; transform: none; }
  :global(html.lowfx) .sm > :global(svg) { transition: none; }
  @media (prefers-reduced-motion: reduce) { .sm > :global(svg) { transition: none; } }

  /* the lanyards, small: strap, clip and card in each one's colours (Hero.svelte's, scaled down); bleeds to the edges */
  .skins { display: flex; gap: 10px; overflow-x: auto; margin: 0 calc(-1 * var(--gutter)) 8px; padding: 4px var(--gutter) 6px; scrollbar-width: none; }
  .skins::-webkit-scrollbar { display: none; }
  .ly .mini :global(*) { animation: none !important; } /* swatches stay still: many full lanyards at once */
  .ly .mini { --gx: 0; --gy: 0; } /* and flat: no depth layer (base.css .z) ever moves or gets its own layer here */
  .ly .mini :global(.z) { will-change: auto; }
  .ly { flex: none; width: 92px; display: flex; flex-direction: column; align-items: center; padding: 8px 6px 8px; border-radius: 16px; background: var(--surface);
    box-shadow: inset 0 0 0 2px transparent; transition: box-shadow var(--t-fast), transform var(--t-fast) var(--ease); }
  .ly:active { transform: scale(0.95); }
  .ly.on { box-shadow: inset 0 0 0 2px var(--accent); }
  .ly .st { width: 12px; height: 26px; display: flex; justify-content: center; overflow: hidden; background: linear-gradient(90deg, #1B36A0, #3B6BFF 50%, #1B36A0); }
  .ly .st i { writing-mode: vertical-rl; transform: rotate(180deg); font: 800 4.5px/12px var(--font-text); font-style: normal; letter-spacing: 0.2em; color: rgba(255, 255, 255, 0.85); white-space: nowrap; }
  .ly .cl { width: 18px; height: 7px; margin-bottom: -4px; z-index: 1; border-radius: 3px; background: linear-gradient(180deg, #F4F6FB, #9AA4B8); }
  .ly .cd { position: relative; width: 74px; height: 48px; padding: 9px 7px 6px; border-radius: 9px; display: grid; grid-template-columns: 16px 1fr; grid-template-rows: 6px 6px 1fr; gap: 3px 5px; overflow: hidden;
    background: radial-gradient(110% 90% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(155deg, #2A4FD6, #121A3D 72%); }
  .ly .ph { grid-row: 1 / 3; width: 16px; height: 16px; border-radius: 5px; background: rgba(255, 255, 255, 0.85); }
  .ly .ln { height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.85); }
  .ly .ln.s { width: 60%; opacity: 0.6; }
  .ly .hl { grid-column: 1 / 3; align-self: end; height: 7px; border-radius: 3px; background: linear-gradient(100deg, #FFA6DA, #B9A3FF, #86E3FF, #A6FFD6, #FFE69A); }
  .ly b { max-width: 100%; margin-top: 7px; font: 620 12px/1.2 var(--font-text); }
  .ly .ph { z-index: 1; }
  .ly .ln, .ly .hl { position: relative; z-index: 1; }
  /* the club's real card art, the profile's (LanyardBand wide) shrunk to the swatch: 340 px wide -> 74 */
  .mini { position: absolute; left: 0; top: 0; width: 340px; height: 221px; transform: scale(0.2176); transform-origin: 0 0; pointer-events: none; }
  .ly.studex .st { background: linear-gradient(90deg, #A9271E, #CF3428 50%, #A9271E); }
  .ly.studex .hl { background: #fff; }
  .ly.cheer .st { background: linear-gradient(90deg, rgb(20, 22, 44), rgb(46, 50, 88) 50%, rgb(20, 22, 44)); }
  .ly.cheer .hl { background: linear-gradient(100deg, rgb(196, 154, 64), rgb(236, 204, 128), rgb(190, 148, 60)); }
  .ly.knights .st { background: linear-gradient(90deg, #163E7C, #2F6BD0 50%, #163E7C); }
  .ly.knights .hl { background: linear-gradient(90deg, #1C4C94, #2F6BD0); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.35); }
  .ly.moments .st { background: linear-gradient(90deg, #7A321F, #B5603F 50%, #7A321F); }
  .ly.moments .st i { color: #F4D9BE; }
  .ly.moments .hl { background: linear-gradient(100deg, #F2DEC8, #E3A985, #C9C391); }
  .ly.faces .st { background: linear-gradient(90deg, rgba(0, 0, 0, 0.3), transparent 35% 65%, rgba(0, 0, 0, 0.3)), linear-gradient(180deg, #6E7BFF, #C04BFF 55%, #FF4F9A); } /* shaded round like the others */
  .ly.faces .hl { background: linear-gradient(100deg, #6E7BFF, #C04BFF, #FF4F9A, #FFA43D); }
  .ly.sower .st { background: linear-gradient(90deg, #DCDCE0, #fff 50%, #DCDCE0); }
  .ly.sower .st i { color: #000; }
  .ly.sower .cd { background: radial-gradient(90% 120% at 0% 0%, #26262B, #000 62%); }
  .ly.sower .cd::before { content: ''; position: absolute; right: -30px; top: -30px; width: 76px; height: 76px; border-radius: 50%;
    background: repeating-radial-gradient(circle, transparent 0 5px, rgba(255, 255, 255, 0.14) 5px 5.6px); }
  .ly.sower .hl { background: #fff; }
</style>
