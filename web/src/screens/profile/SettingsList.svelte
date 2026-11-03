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
  import ImageIcon from '@lucide/svelte/icons/image';
  import AtSign from '@lucide/svelte/icons/at-sign';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import { nameOf, schoolOf, schoolShort } from '../../lib/short';
  import Languages from '@lucide/svelte/icons/languages';
  import Bell from '@lucide/svelte/icons/bell';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import Smartphone from '@lucide/svelte/icons/smartphone';
  import Lock from '@lucide/svelte/icons/lock';
  import IdCard from '@lucide/svelte/icons/id-card';
  import { slide } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import Info from '@lucide/svelte/icons/info';
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
  import { skinOf, skinned, STRAP, banded, clubLook, lookVars, type Look } from '../../lib/awards';
  // each lanyard's card art at the swatch's size, one small picture (tools/scene-rasters.mjs draws them from LanyardBand)
  const MINI = import.meta.glob('../../assets/lanyards/minis/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
  import { byRank } from '../../lib/perms';

  const me = $derived(session.me);
  const s = $derived(me?.settings);
  const bells = $derived(s ? [s.nRemind, s.nNewEvents].filter(Boolean).length : 0);

  // the lanyards: my clubs' by my role in them (owner, Oct 13: "no chaos"), then every other club's under a lock (owner,
  // Oct 31: a club's lanyard is its members' alone; the server holds it too, `_skin_ok`), KBTU's last; SOWER first for the founder
  // a school's lanyard is its students' alone, even for a member of its org (staff are): only my own school's (server: _skin_ok)
  const mine = $derived(me ? [...me.memberships].sort(byRank).map((m) => m.org).filter((o) => skinned(o) && o.kind !== 'school') : []);
  // my school's lanyard: mine with no joining, nobody else's (the server holds it too: logic.school_slug); others' schools
  // show locked, to try on
  const school = $derived(schoolOf(me?.student?.school));
  // once each: a member of my school's org (staff often are) had it twice, a duplicate key that blanked Settings (Nov 2)
  const own = $derived([...mine, ...(school && skinned(school) && !mine.some((o) => o.id === school.id) ? [school] : [])]);
  const skins = $derived([...own, ...data.orgs.filter((o) => skinned(o) && !own.some((x) => x.id === o.id))]
    .filter((o, i, all) => all.findIndex((x) => x.id === o.id) === i));  // a key twice blanks the list: never
  // the creator wears any (owner, Nov 2; the server holds it too)
  const swatches = $derived([...(me?.founder ? [{ id: 'sower' as const, kind: 'sower', name: 'SOWER', word: 'SOWER' }] : []),
    ...skins.map((o) => ({ id: o.id, kind: skinOf(o)!, name: nameOf(o), word: STRAP[skinOf(o)!], locked: !me?.founder && !own.some((x) => x.id === o.id) })),
    { id: null, kind: 'kbtu', name: 'KBTU', word: 'KBTU' }]);
  // two rows (owner, Nov 2: three pushed the card off the screen): organisations (SOWER, mine, KBTU, the rest locked),
  // then the schools (mine first)
  const kindOf = (k: (typeof swatches)[number]) => data.orgs.find((o) => o.id === k.id)?.kind;
  const rows = $derived.by(() => {
    const isMine = (k: (typeof swatches)[number]) => typeof k.id !== 'number' || own.some((o) => o.id === k.id);
    const orgs = swatches.filter((k) => kindOf(k) !== 'school');
    const sorted = [...orgs.filter((k) => isMine(k) && k.id !== null), ...orgs.filter((k) => k.id === null), ...orgs.filter((k) => !isMine(k))];
    return ([['look.gClubs', sorted], ['look.gSchools', swatches.filter((k) => kindOf(k) === 'school')]] as const).filter(([, ks]) => ks.length);
  });
  // the picker folds under one row (owner, Nov 2: opening Settings for the theme met a wall of lanyards)
  let looks = $state(false);
  const wornName = $derived(swatches.find((k) => k.id === (worn ?? null))?.name ?? 'KBTU');

  // a locked one can be tried on: the lanyard above wears it, the check then says it isn't mine (Me) and turns it back
  const worn = $derived(ui.tryOn?.id ?? me?.skin);
  let busy = false;
  // no toast on a skin (owner, Oct 29): the lanyard above turns at once (Hero); a failure puts the old one back
  async function pickSkin(id: number | 'sower' | null) {
    if (busy || !me || id === me.skin) return;
    const was = me;
    busy = true;
    session.me = { ...me, skin: id };
    try { session.me = await api.updateMe({ skin: id }); } catch (e) { session.me = was; oops(e); } finally { busy = false; }
  }

  // the frame: in place at once, back on a failure (as the lanyard)
  const FRAMES = [null, 'flowers', 'space', 'hearts', 'sparkles', 'laurel', 'leaves', 'snow', 'notes', 'neon', 'blossom', 'gold'] as const;
  async function pickFrame(f: string | null) {
    if (busy || !me || (me.frame ?? null) === f) return;
    const was = me;
    busy = true;
    session.me = { ...me, frame: f };
    try { session.me = await api.updateMe({ frame: f }); } catch (e) { session.me = was; oops(e); } finally { busy = false; }
  }

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
  {#if me?.student}
    <input bind:this={file} type="file" accept="image/*" hidden onchange={(e) => void upload(e.currentTarget.files?.[0])} />
    <div data-unit>
      <div class="pick first">
        <Group caption={t('look.skin')}>
          <Row icon={IdCard} title={t('look.change')} value={wornName} accessory="disclosure" open={looks} onclick={() => { haptic.tap(); looks = !looks; if (!looks) ui.tryOn = null; }} />
        </Group>
      </div>
      {#if looks}
      <div class="looks" transition:slide={{ duration: 320, easing: cubicOut }}>
      {#if skins.length || me.founder}
        <!-- each lanyard drawn small, as it hangs above (names alone said nothing; with many clubs the row scrolls) -->
        {#each rows as [label, ks], r (label)}
        <h3 class="sub" class:first={r === 0}>{t(label)}</h3>
        <div class="skins" role="radiogroup" aria-label={t(label)}>
          {#each ks as k (k.id ?? 'kbtu')}
            <button class="ly {k.kind}" class:club={!!clubLook(k.kind as Look)} style={lookVars(k.kind as Look)} role="radio" aria-checked={worn === k.id} class:on={worn === k.id} class:locked={'locked' in k && k.locked}
                    onclick={() => { haptic.select(); if ('locked' in k && k.locked) ui.tryOn = { id: k.id as number, name: k.name, school: kindOf(k) === 'school' }; else { ui.tryOn = null; void pickSkin(k.id); } }}>
              <span class="st"><i>{k.word}</i></span><span class="cl"></span>
              <!-- a scene for mine only: every club's full scene at once (20+) left the whole list unpainted on iPhones (Nov 2);
                   now a picture each (perf round 3), the locked ones keep their plain colours as before -->
              <span class="cd">{#if banded(k.kind as Look) && !('locked' in k && k.locked)}<img class="mini" src={MINI[`../../assets/lanyards/minis/${k.kind}.webp`]} alt="" loading="lazy" decoding="async" />{/if}<span class="ph"></span><span class="ln"></span><span class="ln s"></span><span class="hl"></span></span>
              {#if 'locked' in k && k.locked}<span class="lk"><Lock size={12} strokeWidth={2.4} /></span>{/if}
              <b>{k.name}</b>
            </button>
          {/each}
        </div>
        {/each}
      {/if}
      <!-- a frame over the photo, apart from the lanyard: any frame with any lanyard (owner, Nov 2) -->
      <h3 class="sub">{t('look.frame')}</h3>
      <div class="frames" role="radiogroup" aria-label={t('look.frame')}>
        {#each FRAMES as f (f ?? 'none')}
          <button class="fr" role="radio" aria-checked={(me.frame ?? null) === f} class:on={(me.frame ?? null) === f} onclick={() => { haptic.select(); void pickFrame(f); }}>
            <span class="fb"><span class="fp"></span>{#if f}<img src="frames/{f}.svg" alt="" draggable="false" />{/if}</span>
            <b class="ellipsis">{t(f ? `look.frame.${f}` : 'look.frameNone')}</b>
          </button>
        {/each}
      </div>
      </div>
      {/if}
    </div>
    <div data-unit>
      <Group footnote={t('look.nickFoot')}>
        <Row icon={ImageIcon} title={t('look.photo')} value={me.photo.telegram ? 'Telegram' : t('look.own')} menu={photoItems()} />
        {#if me.nick}<Row icon={AtSign} title={t('look.nick')} value={me.nick} menu={[{ label: t('look.nickEdit'), onselect: () => void editNick() }, { label: t('look.dropNick'), destructive: true, onselect: () => setNick(null) }]} />
        {:else}<Row icon={AtSign} title={t('look.nick')} value={t('look.noNick')} accessory="chevron" onclick={() => { haptic.tap(); void editNick(); }} />{/if}
        <Row icon={GraduationCap} title={t('look.school')} value={schoolShort(me.student.school) || t('look.noSchool')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('school'); }} />
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

  <div data-unit class="gap">
    <Group>
      {#if me?.student}<Row icon={Lock} title={t('set.privacy')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('privacy'); }} />{/if}
      <Row icon={Info} title={t('set.about')} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings('about'); }} />
    </Group>
  </div>
</div>

<style>
  /* Me's stagger child, but it rises by its units (Me): no second animation on top */
  .set-list { animation: none; display: flex; flex-direction: column; outline: none; }
  /* the sections' captions where Settings' headings stood */
  .first { margin-top: 20px; }
  .sec { margin-top: 28px; }
  .sec.first { margin-top: 20px; }
  .spacer { height: 44px; } /* a guest: the check sits where the student's gear does, never on the first title */
  .gap { margin-top: 28px; }

  /* the lanyards, small: strap, clip and card in each one's colours (Hero.svelte's, scaled down); bleeds to the edges */
  .pick { margin-bottom: var(--s-4); }
  .looks { margin-top: calc(-1 * var(--s-2)); padding-bottom: var(--s-2); }
  .sub { margin: var(--s-3) 0 var(--s-2); font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); text-transform: uppercase; letter-spacing: 0.04em; }
  .sub.first { margin-top: 0; }
  .skins { display: flex; gap: 10px; overflow-x: auto; margin: 0 calc(-1 * var(--gutter)) 8px; padding: 4px var(--gutter) 6px; scrollbar-width: none; }
  .skins::-webkit-scrollbar { display: none; }
  .frames { display: flex; gap: 10px; overflow-x: auto; margin: 0 calc(-1 * var(--gutter)) 8px; padding: 4px var(--gutter) 6px; scrollbar-width: none; }
  .frames::-webkit-scrollbar { display: none; }
  .fr { flex: none; display: flex; flex-direction: column; align-items: center; gap: 6px; width: 76px; color: var(--text-2); }
  .fr b { max-width: 100%; font: 600 var(--fs-cap)/1.2 var(--font-text); }
  .fb { position: relative; display: grid; place-items: center; width: 76px; height: 76px; border-radius: var(--r-l); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); overflow: hidden; }
  .fp { width: 40px; height: 40px; border-radius: var(--r-s); background: var(--grad-accent); opacity: 0.55; }
  .fb img { position: absolute; left: 8px; top: 8px; width: 60px; height: 60px; }
  .fr.on .fb { box-shadow: inset 0 0 0 2px var(--accent); }
  .fr.on b { color: var(--text); }
  .ly { flex: none; width: 92px; display: flex; flex-direction: column; align-items: center; padding: 8px 6px 8px; border-radius: 16px; background: var(--surface);
    box-shadow: inset 0 0 0 2px transparent; transition: box-shadow var(--t-fast), transform var(--t-fast) var(--ease); }
  .ly:active { transform: scale(0.95); }
  .ly.on { box-shadow: inset 0 0 0 2px var(--accent); }
  /* someone else's club: seen, not worn; a small lock on the card's corner */
  .ly { position: relative; }
  .ly.locked .st, .ly.locked .cl, .ly.locked .cd { opacity: 0.45; filter: saturate(0.4); }
  .ly .lk { position: absolute; top: 6px; right: 6px; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--text); color: var(--bg); }
  .ly .st { width: 12px; height: 26px; display: flex; justify-content: center; overflow: hidden; background: linear-gradient(90deg, #1B36A0, #3B6BFF 50%, #1B36A0); }
  .ly .st i { writing-mode: vertical-rl; transform: rotate(180deg); font: 800 4.5px/12px var(--font-text); font-style: normal; letter-spacing: 0.2em; color: rgba(255, 255, 255, 0.85); white-space: nowrap; }
  .ly .cl { width: 18px; height: 7px; margin-bottom: -4px; z-index: 1; border-radius: 3px; background: linear-gradient(180deg, #F4F6FB, #9AA4B8); }
  .ly .cd { position: relative; width: 74px; height: 48px; padding: 9px 7px 6px; border-radius: 9px; display: grid; grid-template-columns: 16px 1fr; grid-template-rows: 6px 6px 1fr; gap: 3px 5px; overflow: hidden;
    background: radial-gradient(110% 90% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(155deg, #2A4FD6, #121A3D 72%); }
  .ly .ph { grid-row: 1 / 3; width: 16px; height: 16px; border-radius: 5px; background: rgba(255, 255, 255, 0.85); }
  .ly .ln { height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.85); }
  .ly .ln.s { width: 60%; opacity: 0.6; }
  .ly .hl { grid-column: 1 / 3; align-self: end; height: 7px; border-radius: 3px; background: linear-gradient(100deg, #FFA6DA, #B9A3FF, #86E3FF, #A6FFD6, #FFE69A); }
  .ly b { max-width: 100%; margin-top: 7px; font: 620 12px/1.2 var(--font-text); text-align: center; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; }  /* whole names on two lines (owner: "Big City Lig..." cut) */
  .ly .ph { z-index: 1; }
  .ly .ln, .ly .hl { position: relative; z-index: 1; }
  /* the club's real card art, the profile's (LanyardBand wide) shrunk to the swatch, still and flat: its picture */
  .mini { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
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
  .ly.locked .cd { background: linear-gradient(135deg, var(--c1, rgb(58, 66, 110)), var(--c2, rgb(22, 26, 48))); }
  .ly.club .st { background: linear-gradient(90deg, var(--s1), var(--s2) 50%, var(--s1)); }
  .ly.club .st i { color: var(--s3); font-size: calc(var(--sf) * 0.6); font-weight: var(--sfw); letter-spacing: var(--sl); line-height: calc(var(--slh) * 0.6); white-space: pre; text-align: center; }
  .ly.club .hl { background: linear-gradient(100deg, var(--h1), var(--h2)); }
</style>
