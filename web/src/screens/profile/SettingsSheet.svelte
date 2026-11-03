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
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import Check from '@lucide/svelte/icons/check';
  import User from '@lucide/svelte/icons/user';
  import { schoolOf, shortOf } from '../../lib/short';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import { CITIES } from '../../lib/i18n/cities';
  import { say, close, type Overlay } from '../../lib/state/ui.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { onMount } from 'svelte';
  import { data, phrase, loadMyCard, dropSchedule } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api, ApiErr, type Fixable } from '../../lib/api';
  import { inner } from '../../lib/perms';
  import { t, i18n, type Key } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { fmtPhone, kzPhone } from '../../lib/phone';
  import Pane from '../../ui/Pane.svelte';
  // my clubs as they are now: a club that took me in while the app was open gives its lanyard here (Choice, Nov 3)
  onMount(() => void loadMe());

  type Part = 'last' | 'first' | 'middle';
  type Typed = Exclude<Fixable, 'course' | 'school'>; // the ones typed in (fix); course and school are picked
  type Kind = 'notify' | 'privacy' | 'phone' | 'city' | 'school' | 'course' | Part | 'sees' | 'about';
  let { overlay, kind }: { overlay: Overlay; kind: Kind } = $props();
  const TITLE: Record<Kind, [Key, typeof Lock]> = { notify: ['me.notifications', Bell], privacy: ['set.privacy', Lock], phone: ['pd.phone', Phone], city: ['pd.city', MapPin],
    school: ['look.school', GraduationCap], course: ['pd.course', GraduationCap], last: ['login.lastName', User], first: ['login.firstName', User], middle: ['pd.middle', User],
    sees: ['set.whoSees', Lock], about: ['set.about', Info] };
  // where "‹ Back" goes: Privacy for its own pages, else Settings
  const me = $derived(session.me);
  const phone = $derived(me?.student?.phone ? (kzPhone(me.student.phone) ? fmtPhone(me.student.phone) : me.student.phone) : '');

  // a switch saves at once and puts itself back if the server says no
  const SWITCHES = [['nRemind', 'set.remind', 'set.remindHint'], ['nNewEvents', 'set.newEvents', 'set.newEventsHint']] as const;
  // (quiet: no toast, the label says it all: whether friends see where I'm going)
  async function set(k: (typeof SWITCHES)[number][0] | 'showGoing' | 'canFriend', on: boolean, quiet = false) {
    if (!me) return;
    haptic.tap();
    me.settings[k] = on;
    try { session.me = await api.updateMe({ [k]: on }); if (!quiet) say(phrase(on ? 'say.notifyOn' : 'say.notifyOff'), on ? 'megaphone_3d' : 'crescent_moon_3d'); }
    catch { if (session.me) session.me.settings[k] = !on; say(t('common.error'), 'warning_3d'); } // the one on screen now
  }

  // My data (PLAN 71): the phone an event asked for, changed or deleted (null deletes it); the city from the club's
  // roster (PLAN 95), off the profile or gone. A deleted one takes its page with it.
  async function savePhone(p: string | null, done: string) {
    try { session.me = await api.updateMe({ phone: p }); haptic.ok(); say(done, 'sparkles_3d'); if (p == null) close(overlay.id); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function editPhone() {
    const p = await sheets.askText({ title: t('pd.phone'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: '+7 (707) 123 45 67', max: 18, tel: true });
    if (p) await savePhone(p, t('pd.saved'));
  }
  async function dropPhone() {
    if (await sheets.ask({ title: t('pd.delAsk'), text: t('pd.delText'), ok: t('pd.del'), cancel: t('common.cancel'), danger: true })) await savePhone(null, t('pd.deleted'));
  }
  // my name and student ID: corrected once each (it came in wrong), then through support; the server holds the rules
  // (account.fix_identity: the ID's year stays, the name stays KBTU's in another spelling at most)
  // each name part one row (owner, Nov 2: six rows read as duplicates): its Cyrillic and Latin forms together, both a
  // tap deeper on the part's own page
  const PARTS: [Part, Typed, Typed, Key][] = [['last', 'lastName', 'lastLat', 'pd.lastLat'], ['first', 'firstName', 'firstLat', 'pd.firstLat'],
    ['middle', 'middleName', 'middleLat', 'pd.middleLat']];
  const part = $derived(PARTS.find((p) => p[0] === kind));
  const LAT: Fixable[] = ['lastLat', 'firstLat', 'middleLat'];
  const ALL = PARTS.length * 2 + 3; // every Fixable (the parts', the ID, course, school): one fixed, the "through support" footnote
  const WHY: Record<string, Key> = { sid_year: 'pd.sidYear', name_far: 'pd.nameFar', sid_taken: 'pd.sidTaken', sid_tries: 'pd.sidTries', fixed: 'pd.support' };
  async function fix(k: Typed, label: Key) {
    const was = me?.student?.[k] ?? '';
    const fill = LAT.includes(k) && !was; // an empty Latin one filled doesn't spend the once (the server's rule)
    const v = await sheets.askText({ title: t(label), text: t(fill ? 'pd.latFill' : 'pd.once'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: was, max: 40, line: true, value: was });
    if (v == null || v.trim() === was) return;
    // a typo would spend the once: the new value read back before it's saved
    if (!fill && !(await sheets.ask({ title: t('pd.onceTitle'), text: t('pd.onceSure', { v: v.trim() }), ok: t('common.save'), cancel: t('common.cancel'), danger: true }))) return;
    try { session.me = await api.updateMe({ [k]: v }); haptic.ok(); say(t('pd.saved'), 'sparkles_3d'); }
    catch (e) {
      haptic.error();
      const why = e instanceof ApiErr ? (e.message === 'bad_input' ? (k === 'studentId' ? 'pd.badSid' : LAT.includes(k) ? 'pd.badLat' : 'pd.badName') : WHY[e.message]) : undefined;
      say(t(why ?? 'common.error'), 'pleading_face_3d');
    }
  }
  // my school over the list's, which can be wrong (owner, Nov 2): KBTU's schools from the store, or none. The lanyard
  // turns at once and the page goes back to it; the server keeps the school's own name (account.update_me)
  const schools = $derived(data.orgs.filter((o) => o.kind === 'school').sort((a, b) => a.name.localeCompare(b.name, i18n.lang)));
  const mySchool = $derived(schoolOf(me?.student?.school));
  async function pickSchool(name: string | null) {
    if (!me?.student || name === me.student.school) return;
    if (me.student.school && !(await sheets.ask({ title: t('pd.onceTitle'), text: t('pd.onceSure', { v: name ?? t('look.noSchool') }), ok: t('common.save'), cancel: t('common.cancel'), danger: true }))) return;
    const was = me, card = data.myCard;
    haptic.select();
    session.me = { ...me, student: { ...me.student, school: name } };
    if (card) data.myCard = { ...card, school: name }; // the lanyard reads my card once it's loaded (Me)
    close(overlay.id);
    try { session.me = await api.updateMe({ school: name }); void loadMyCard(); }
    catch (e) { session.me = was; data.myCard = card; haptic.error(); say(t(e instanceof ApiErr && WHY[e.message] || 'common.error'), 'warning_3d'); }
  }
  // my year up from the one the ID says (a transfer's new ID reads 1st year), never below it: the server holds that
  // (account.update_me: free 1st-year seats). The lanyard turns at once, as with the school
  const courses = $derived(me?.student?.courseMin ? Array.from({ length: 7 - me.student.courseMin }, (_, i) => me.student!.courseMin! + i) : []);
  async function pickCourse(n: number) {
    if (!me?.student || n === me.student.course) return;
    if (me.student.course && !(await sheets.ask({ title: t('pd.onceTitle'), text: t('pd.onceSure', { v: t('person.course', { n }) }), ok: t('common.save'), cancel: t('common.cancel'), danger: true }))) return;
    const was = me, card = data.myCard;
    haptic.select();
    session.me = { ...me, student: { ...me.student, course: n } };
    if (card) data.myCard = { ...card, course: n };
    close(overlay.id);
    try { session.me = await api.updateMe({ course: n }); void loadMyCard(); }
    catch (e) { session.me = was; data.myCard = card; haptic.error(); say(t(e instanceof ApiErr && WHY[e.message] || 'common.error'), 'warning_3d'); }
  }
  async function cityHidden(on: boolean) {
    try { session.me = await api.updateMe({ cityHidden: on }); void loadMyCard(); haptic.select(); }
    catch { say(t('common.error'), 'warning_3d'); }
  }
  // my city, picked or typed (owner, Nov 3: students set it themselves); optimistic, the card follows
  let picking = $state(false);
  async function setCity(name: string) {
    const was = me;
    if (!me || name === me.city?.name) { picking = false; return; }
    haptic.select();
    session.me = { ...me, city: { name, hidden: me.city?.hidden ?? false } };
    picking = false;
    try { session.me = await api.updateMe({ city: name }); void loadMyCard(); }
    catch { session.me = was; haptic.error(); say(t('pd.cityBad'), 'warning_3d'); }
  }
  async function typeCity() {
    const v = await sheets.askText({ title: t('pd.cityOther'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: t('pd.city'), max: 40, line: true });
    if (v?.trim()) void setCity(v.trim());
  }
  async function dropCity() {
    if (!(await sheets.ask({ title: t('pd.cityDelAsk'), ok: t('pd.del'), cancel: t('common.cancel'), danger: true }))) return;
    try { session.me = await api.updateMe({ city: null }); void loadMyCard(); say(t('pd.deleted'), 'sparkles_3d'); close(overlay.id); }
    catch { say(t('common.error'), 'warning_3d'); }
  }
  // the calendar's address leaked (sent to someone, a shared screen): the old one stops, Calendar makes a new one
  async function resetCal() {
    if (!(await sheets.ask({ title: t('set.calResetAsk'), text: t('set.calResetText'), ok: t('set.calResetOk'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.resetCalendar(); haptic.ok(); say(t('set.calResetDone'), 'sparkles_3d'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // my week off the server, here too and not only in the Week sheet (owner, Nov 1)
  async function dropWeek() {
    if (await sheets.ask({ title: t('sched.delAsk'), text: t('sched.delText'), ok: t('cm.delete'), cancel: t('common.cancel'), danger: true })) void dropSchedule();
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
<!-- a correction that can't be undone: said big and red above the choices, not in a grey footnote (owner, Nov 2) -->
{#snippet once()}<p class="once" role="note"><TriangleAlert size={20} strokeWidth={2.4} /><span><b>{t('pd.onceTitle')}</b>{t('pd.onceBig')}</span></p>{/snippet}
{#snippet link(label: string, go: () => void, value = '', out = false)}
  <button class="set-row" onclick={() => { haptic.tap(); go(); }}><span class="lb">{label}</span>{#if value}<span class="val">{value}</span>{/if}
    {#if out}<ArrowUpRight class="chev" size={18} />{:else}<ChevronRight class="chev" size={18} />{/if}</button>
{/snippet}
{#snippet act(label: string, go: () => void, red = false)}
  <button class="set-row act" class:red onclick={() => { haptic.tap(); go(); }}><span class="lb">{label}</span></button>
{/snippet}
<!-- a name part: Cyrillic over Latin at the row's end (one line when they're the same) -->
{#snippet two(label: string, a: string | null, b: string | null)}
  <span class="lb">{label}</span><span class="val two"><span>{a || b}</span>{#if a && b && a !== b}<span class="sub">{b}</span>{/if}</span>
{/snippet}

<Pane {overlay} title={t(TITLE[kind][0])} icon={TITLE[kind][1]}>
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
    {#if me?.student}
      {@const st = me.student}
      <!-- who I am: each name part one row, its Latin form under it; correctable once (›), then a plain row -->
      <div class="set-group plain">
        {#each PARTS as [p, cyr, lat] (p)}
          {@const can = st.fixable?.includes(cyr) || st.fixable?.includes(lat)}
          {#if can}<button class="set-row" onclick={() => { haptic.tap(); sheets.settings(p); }}>{@render two(t(TITLE[p][0]), st[cyr], st[lat])}<ChevronRight class="chev" size={18} /></button>
          {:else if st[cyr] || st[lat]}<div class="set-row">{@render two(t(TITLE[p][0]), st[cyr], st[lat])}</div>{/if}
        {/each}
      </div>
    {/if}
    {#if me?.student || phone || me?.city}
      <div class="set-group plain" class:gap={me?.student}>
        {#if me?.student}
          {@const st = me.student}
          <!-- the ID once too; the year up from the ID's; the email is the Microsoft login, never edited -->
          {#if st.fixable?.includes('studentId')}{@render link(t('pd.sid'), () => void fix('studentId', 'pd.sid'), st.studentId)}
          {:else}<div class="set-row"><span class="lb">{t('pd.sid')}</span><span class="val">{st.studentId}</span></div>{/if}
          {#if courses.length > 1 && st.fixable?.includes('course')}{@render link(t('pd.course'), () => sheets.settings('course'), String(st.course ?? ''))}
          {:else if st.course}<div class="set-row"><span class="lb">{t('pd.course')}</span><span class="val">{st.course}</span></div>{/if}
          {#if st.email}<div class="set-row"><span class="lb">{t('pd.email')}</span><span class="val wide">{st.email}</span></div>{/if}
        {/if}
        {#if phone}{@render link(t('pd.phoneShort'), () => sheets.settings('phone'), phone)}{/if}
        {#if me?.student || me?.city}{@render link(t('pd.city'), () => sheets.settings('city'), me?.city?.name ?? t('pd.cityNone'))}{/if}
      </div>
      {#if me?.student && me.student.fixable.length < ALL && me.student.consent !== 'staff'}<p class="set-foot">{t('pd.support')}</p>{/if}
    {/if}
    {#if me?.student}
      <!-- friends only: my profile's events, Afisha's faces, "bring a friend" (the server's showGoing); and off, nobody can
           send me a friend request (my friends and the requests waiting stay) -->
      <div class="set-group plain sw-on gap">
        <label class="set-row"><span class="lb">{t('set.showGoing')}</span><input type="checkbox" role="switch" checked={me.settings.showGoing} onchange={(e) => set('showGoing', e.currentTarget.checked, true)} /></label>
        <label class="set-row"><span class="lb">{t('set.canFriend')}</span><input type="checkbox" role="switch" checked={me.settings.canFriend} onchange={(e) => set('canFriend', e.currentTarget.checked, true)} /></label>
      </div>
    {/if}
    <div class="set-group plain" class:gap={phone || me?.city || me?.student}>
      {@render link(t('set.whoSees'), () => sheets.settings('sees'))}
      {@render link(t('set.policy'), () => page('privacy'), '', true)}
    </div>
    {#if me?.student && !me.deleteAt}
      <div class="set-group plain gap">{@render act(t('set.calReset'), resetCal, true)}{#if data.schedule.length}{@render act(t('sched.del'), dropWeek, true)}{/if}</div>
      <div class="set-group plain gap">{@render act(t('me.deleteData'), deleteData, true)}</div>
    {/if}
  {:else if kind === 'phone'}
    <div class="set-group plain"><div class="set-row"><span class="lb big">{phone}</span></div></div>
    <p class="set-foot">{t('pd.note')}</p>
    <div class="set-group plain gap">{@render act(t('pd.phoneEdit'), editPhone)}{@render act(t('pd.phoneDel'), dropPhone, true)}</div>
  {:else if kind === 'city' && me?.city && !picking}
    <div class="set-group plain sw-on">
      <div class="set-row"><span class="lb big">{me.city.name}</span></div>
      <label class="set-row"><span class="lb">{t('pd.cityHide')}</span><input type="checkbox" role="switch" checked={me.city.hidden} onchange={(e) => cityHidden(e.currentTarget.checked)} /></label>
    </div>
    <p class="set-foot">{t('pd.cityNote')}</p>
    <div class="set-group plain gap">{@render act(t('pd.cityChange'), () => { haptic.tap(); picking = true; })}{@render act(t('pd.cityDel'), dropCity, true)}</div>
  {:else if kind === 'city' && me}
    <!-- the big cities in my language, any other typed in -->
    <div class="set-group plain" role="radiogroup" aria-label={t('pd.city')}>
      {#each CITIES as c (c.en)}
        {@const name = c[i18n.lang]}
        <button class="set-row" role="radio" aria-checked={me.city?.name === name} onclick={() => void setCity(name)}>
          <span class="lb">{name}</span><span class="tick">{#if me.city?.name === name}<Check size={20} strokeWidth={2.4} />{/if}</span></button>
      {/each}
    </div>
    <div class="set-group plain gap">{@render act(t('pd.cityOther'), () => void typeCity())}</div>
    <p class="set-foot">{t('pd.cityNote')}</p>
  {:else if part && me?.student}
    {@const st = me.student}
    {@const [, cyr, lat, latKey] = part}
    <!-- the part's two spellings, each correctable once -->
    {#if st.fixable?.includes(cyr) || st.fixable?.includes(lat)}{@render once()}{/if}
    <div class="set-group plain">
      {#if st.fixable?.includes(cyr)}{@render link(t('pd.cyr'), () => void fix(cyr, TITLE[part[0]][0]), st[cyr] ?? '')}
      {:else}<div class="set-row"><span class="lb">{t('pd.cyr')}</span><span class="val">{st[cyr] ?? ''}</span></div>{/if}
      {#if st.fixable?.includes(lat)}{@render link(t('pd.lat'), () => void fix(lat, latKey), st[lat] ?? '')}
      {:else}<div class="set-row"><span class="lb">{t('pd.lat')}</span><span class="val">{st[lat] ?? ''}</span></div>{/if}
    </div>
    <p class="set-foot">{t(st.fixable?.includes(cyr) || st.fixable?.includes(lat) ? 'pd.once' : 'pd.support')}</p>
  {:else if kind === 'course' && me?.student}
    {#if me.student.fixable?.includes('course')}
      {@render once()}
      <div class="set-group plain" role="radiogroup" aria-label={t('pd.course')}>
        {#each courses as n (n)}
          <button class="set-row" role="radio" aria-checked={me.student.course === n} onclick={() => void pickCourse(n)}>
            <span class="lb">{t('person.course', { n })}</span><span class="tick">{#if me.student.course === n}<Check size={20} strokeWidth={2.4} />{/if}</span></button>
        {/each}
      </div>
    {:else}
      <div class="set-group plain"><div class="set-row"><span class="lb">{t('person.course', { n: me.student.course ?? 0 })}</span></div></div>
      <p class="set-foot">{t('pd.support')}</p>
    {/if}
  {:else if kind === 'school' && me?.student && !me.student.fixable?.includes('school')}
    <!-- the once spent: my school alone, then support -->
    <div class="set-group plain"><div class="set-row"><span class="lb school">{mySchool?.name ?? me.student.school ?? t('look.noSchool')}</span>
      {#if mySchool}<span class="val">{shortOf(mySchool)}</span>{/if}</div></div>
    <!-- a mis-tap undone: the one before comes back, free, once (owner, Nov 3: everyone wrote to support) -->
    {#if me.student.undo && 'school' in me.student.undo}{@const was = me.student.undo.school ?? null}
      <div class="set-group plain gap">{@render act(t('pd.undo', { v: schoolOf(was)?.name ?? was ?? t('look.noSchool') }), () => void pickSchool(was))}</div>{/if}
    <p class="set-foot">{t(me.student.undo && 'school' in me.student.undo ? 'pd.undoFoot' : 'pd.support')}</p>
  {:else if kind === 'school' && me?.student}
    {#if me.student.school}{@render once()}{/if}
    <div class="set-group plain" role="radiogroup" aria-label={t('look.school')}>
      {#each schools as o (o.id)}
        {@const on = mySchool?.id === o.id}
        <button class="set-row" role="radio" aria-checked={on} onclick={() => void pickSchool(o.orig?.name ?? o.name)}>
          <span class="lb school">{o.name}</span><span class="val">{shortOf(o)}</span><span class="tick">{#if on}<Check size={20} strokeWidth={2.4} />{/if}</span></button>
      {/each}
    </div>
    <!-- no "no school" here: two students cleared theirs by mistake (Nov 2), and the once went with it -->
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
  /* the pick's check, Apple's: a fixed slot at the row's end so the short names line up */
  /* a long school's name breaks between syllables, never mid-letter; at 320 px the short name
     makes room for it */
  .once { display: flex; gap: var(--s-3); align-items: flex-start; margin: 0 0 var(--s-4); padding: var(--s-4); border-radius: var(--r-l);
    background: var(--danger-soft); color: var(--text); font: 500 var(--fs-body)/1.35 var(--font-text); }
  .once :global(svg) { flex: none; margin-top: 2px; color: var(--danger); }
  .once b { display: block; margin-bottom: 2px; font-weight: 700; color: var(--danger-text); }
  .set-row > .lb.school { overflow-wrap: break-word; hyphens: auto; }
  @media (max-width: 340px) { .lb.school + .val { display: none; } }
  /* a name part's end: its Cyrillic over its Latin, each cut with … rather than wrapped */
  .val.two { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.25; }
  .val.two > span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
  .val.two > .sub { font-size: var(--fs-sub); }
  .tick { flex: none; width: 20px; margin-right: -4px; display: grid; place-items: center; color: var(--accent-text); }
  /* who sees what: a heading and its text in each cell, read rather than tapped */
  .see { padding: 12px 16px; }
  .see + .see { border-top: 1px solid var(--line); }
  .see b { display: block; font: 600 16px/1.3 var(--font-text); }
  .see p { margin-top: 3px; font: 450 15px/1.45 var(--font-text); color: var(--text-2); }
</style>
