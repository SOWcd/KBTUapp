<script lang="ts">
  // A page pushed in from the right (ui/Pane) from the settings under my lanyard (Me), the phone's own way: the
  // notification switches with a footnote under each; my name and ID (Settings' "My data" opens it, its school,
  // course, city and phone pages too); Privacy (whether friends see where I'm going; who sees what; the policy;
  // deleting the account) and About.
  // A row that leaves the app (the browser, Telegram) ends in ↗, one that stays in it in ›.
  import Lock from '@lucide/svelte/icons/lock';
  import Bell from '@lucide/svelte/icons/bell';
  import Info from '@lucide/svelte/icons/info';
  import Phone from '@lucide/svelte/icons/phone';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import User from '@lucide/svelte/icons/user';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Copy from '@lucide/svelte/icons/copy';
  import Button from '../../ui/Button.svelte';
  import { schoolOf, shortOf } from '../../lib/short';
  import { CITIES, cityName } from '../../lib/i18n/cities';
  import { say, close, type Overlay } from '../../lib/state/ui.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { onMount } from 'svelte';
  import { data, phrase, loadMyCard, dropSchedule } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api, ApiErr, type Fixable } from '../../lib/api';
  import { inner } from '../../lib/perms';
  import { t, i18n, type Key } from '../../lib/i18n/index.svelte';
  import { haptic, openLink, tg } from '../../lib/tg';
  import Emoji from '../../ui/Emoji.svelte';
  import { fmtPhone, kzPhone } from '../../lib/phone';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Notice from '../../ui/Notice.svelte';
  // my clubs as they are now: a club that took me in while the app was open gives its lanyard here (Choice, Nov 3)
  onMount(() => void loadMe());

  type Part = 'last' | 'first' | 'middle';
  type Typed = Exclude<Fixable, 'course' | 'school'>; // the ones typed in (fix); course and school are picked
  type Kind = 'notify' | 'name' | 'privacy' | 'phone' | 'city' | 'school' | 'course' | Part | 'sees' | 'about' | 'donate';
  let { overlay, kind }: { overlay: Overlay; kind: Kind } = $props();
  const TITLE: Record<Kind, [Key, typeof Lock]> = { notify: ['me.notifications', Bell], name: ['set.nameId', User], privacy: ['set.privacy', Lock], phone: ['pd.phone', Phone], city: ['pd.city', MapPin],
    school: ['look.school', GraduationCap], course: ['pd.course', GraduationCap], last: ['login.lastName', User], first: ['login.firstName', User], middle: ['pd.middle', User],
    sees: ['set.whoSees', Lock], about: ['set.about', Info], donate: ['set.donate', HandHeart] };
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
    const v = await sheets.askText({ title: t(label), text: fill ? t('pd.latFill') : undefined, ok: t('common.save'), cancel: t('common.cancel'), placeholder: was, max: 40, line: true, value: was });
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
    if (!me || (me.city && cityName(me.city.name, i18n.lang) === name)) { picking = false; return; }
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
  // Support the app (owner, Nov 3): a gift, never a purchase. The number is copied and nothing else: no Kaspi link (none
  // is public, and a payment link breaks Telegram's rules), no amounts, and nothing recorded, so no badge, status or
  // thanks can ever depend on it (.claude/reports/donate-review.md)
  const donate = $derived(session.donate ? fmtPhone(session.donate) : '');
  // owner, Nov 6: a transfer inside one bank is free, so the page lists every bank the number has (the same number in
  // each); a tap copies it and opens that bank's app. ponytail: banks publish no "transfer to this number" link, so the
  // App Store page (its Open button) on iOS and a Play search elsewhere; the bank's own link if one turns up.
  const BANKS = [['kaspi', 'Kaspi', 1195076505], ['halyk', 'Halyk', 440635615], ['freedom', 'Freedom', 1619733462], ['forte', 'Forte', 6474132802],
    ['bereke', 'Bereke', 6449958451], ['bcc', 'BCC', 743617904], ['homecredit', 'Home Credit', 6443964296], ['alatau', 'Alatau', 1441936010]] as const;
  async function toBank(name: string, ios: number) {
    await copyDonate();
    openLink(/^(ios|macos)$/.test(tg.platform) ? `https://apps.apple.com/kz/app/id${ios}` : `https://play.google.com/store/search?q=${encodeURIComponent(name + ' bank')}&c=apps`);
  }
  async function copyDonate() {
    // the plain digits ("+77001234567"): Kaspi's search takes it as is
    try { await navigator.clipboard.writeText(session.donate); haptic.ok(); say(t('pay.copied'), 'sparkles_3d'); }
    catch { haptic.error(); } // the number is selectable too
  }
</script>

<!-- in the app: ›; out of it (out = true): ↗ -->
{#snippet link(title: string, go: () => void, value = '', out = false)}
  <Row {title} {value} accessory={out ? 'external' : 'chevron'} onclick={() => { haptic.tap(); go(); }} />
{/snippet}
{#snippet act(title: string, go: () => void, red = false)}
  <Row {title} tone={red ? 'destructive' : 'action'} onclick={() => { haptic.tap(); go(); }} />
{/snippet}
<!-- a name part: Cyrillic over Latin at the row's end (one line when they're the same) -->
{#snippet two(a: string | null, b: string | null)}
  <span class="two"><span>{a || b}</span>{#if a && b && a !== b}<span class="sub">{b}</span>{/if}</span>
{/snippet}
<!-- a correction that can't be undone: said once, above the choices (the final confirm says it again) -->
{#snippet once()}<div class="once"><Notice tone="danger" title={t('pd.onceTitle')} text={t('pd.onceBig')} /></div>{/snippet}

<Pane {overlay} title={t(TITLE[kind][0])} icon={TITLE[kind][1]}>
  {#if kind === 'notify' && me}
    {#each SWITCHES as [k, title, hint], i (k)}
      <div class:sw={i > 0}><Group footnote={t(hint)}><Row title={t(title)} accessory="switch" checked={me.settings[k]} onchange={(on) => set(k, on)} /></Group></div>
    {/each}
    <p class="foot always">{t('set.always')}</p>
  {:else if kind === 'name' && me?.student}
    {@const st = me.student}
    <!-- who I am: each name part one row, its Latin form under it; correctable once (›), then a plain row -->
    <Group>
      {#each PARTS as [p, cyr, lat] (p)}
        {@const can = st.fixable?.includes(cyr) || st.fixable?.includes(lat)}
        {#if can}<Row title={t(TITLE[p][0])} accessory="chevron" onclick={() => { haptic.tap(); sheets.settings(p); }}>{#snippet detail()}{@render two(st[cyr], st[lat])}{/snippet}</Row>
        {:else if st[cyr] || st[lat]}<Row title={t(TITLE[p][0])}>{#snippet detail()}{@render two(st[cyr], st[lat])}{/snippet}</Row>{/if}
      {/each}
    </Group>
    <div class="gap">
      <Group footnote={st.fixable.length < ALL && st.consent !== 'staff' ? t('pd.support') : undefined}>
        <!-- the ID once too; the email is the Microsoft login, never edited -->
        {#if st.fixable?.includes('studentId')}{@render link(t('pd.sid'), () => void fix('studentId', 'pd.sid'), st.studentId)}
        {:else}<Row title={t('pd.sid')} value={st.studentId} />{/if}
        <!-- the email whole, on two lines if it must (owner, Oct 31) -->
        {#if st.email}<Row title={t('pd.email')}>{#snippet detail()}<span class="wide">{st.email}</span>{/snippet}</Row>{/if}
      </Group>
    </div>
  {:else if kind === 'privacy'}
    <!-- my data moved up to Settings' first group (owner, Nov 6); here what others see of me -->
    {#if me?.student}
      <!-- friends only: my profile's events, Afisha's faces, "bring a friend" (the server's showGoing); and off, nobody can
           send me a friend request (my friends and the requests waiting stay) -->
      <div class="gap"><Group>
        <Row title={t('set.showGoing')} accessory="switch" checked={me.settings.showGoing} onchange={(on) => set('showGoing', on, true)} />
        <Row title={t('set.canFriend')} accessory="switch" checked={me.settings.canFriend} onchange={(on) => set('canFriend', on, true)} />
      </Group></div>
    {/if}
    <div class:gap={me?.student}><Group>
      {@render link(t('set.whoSees'), () => sheets.settings('sees'))}
      {@render link(t('set.policy'), () => page('privacy'), '', true)}
    </Group></div>
    {#if me?.student && !me.deleteAt}
      <div class="gap"><Group>{@render act(t('set.calReset'), resetCal, true)}{#if data.schedule.length}{@render act(t('sched.del'), dropWeek, true)}{/if}</Group></div>
      <div class="gap"><Group>{@render act(t('me.deleteData'), deleteData, true)}</Group></div>
    {/if}
  {:else if kind === 'phone'}
    <Group footnote={t('pd.note')}><Row title={phone} /></Group>
    <div class="gap"><Group>{@render act(t('pd.phoneEdit'), editPhone)}{@render act(t('pd.phoneDel'), dropPhone, true)}</Group></div>
  {:else if kind === 'city' && me?.city && !picking}
    <Group footnote={t('pd.cityNote')}>
      <Row title={cityName(me.city.name, i18n.lang)} />
      <Row title={t('pd.cityHide')} accessory="switch" checked={me.city.hidden} onchange={(on) => cityHidden(on)} />
    </Group>
    <div class="gap"><Group>{@render act(t('pd.cityChange'), () => (picking = true))}{@render act(t('pd.cityDel'), dropCity, true)}</Group></div>
  {:else if kind === 'city' && me}
    <!-- the big cities in my language, any other typed in -->
    <Group>
      {#each CITIES as c (c.en)}
        {@const name = c[i18n.lang]}
        <Row title={name} accessory="check" checked={!!me.city && cityName(me.city.name, i18n.lang) === name} onclick={() => void setCity(name)} />
      {/each}
    </Group>
    <div class="gap"><Group footnote={t('pd.cityNote')}>{@render act(t('pd.cityOther'), () => void typeCity())}</Group></div>
  {:else if part && me?.student}
    {@const st = me.student}
    {@const [, cyr, lat, latKey] = part}
    {@const can = st.fixable?.includes(cyr) || st.fixable?.includes(lat)}
    <!-- the part's two spellings, each correctable once -->
    {#if can}{@render once()}{/if}
    <Group footnote={can ? undefined : t('pd.support')}>
      {#if st.fixable?.includes(cyr)}{@render link(t('pd.cyr'), () => void fix(cyr, TITLE[part[0]][0]), st[cyr] ?? '')}
      {:else}<Row title={t('pd.cyr')} value={st[cyr] ?? ''} />{/if}
      {#if st.fixable?.includes(lat)}{@render link(t('pd.lat'), () => void fix(lat, latKey), st[lat] ?? '')}
      {:else}<Row title={t('pd.lat')} value={st[lat] ?? ''} />{/if}
    </Group>
  {:else if kind === 'course' && me?.student}
    {#if me.student.fixable?.includes('course')}
      {@render once()}
      <Group>
        {#each courses as n (n)}
          <Row title={t('person.course', { n })} accessory="check" checked={me.student.course === n} onclick={() => void pickCourse(n)} />
        {/each}
      </Group>
    {:else}
      <Group footnote={t('pd.support')}><Row title={t('person.course', { n: me.student.course ?? 0 })} /></Group>
    {/if}
  {:else if kind === 'school' && me?.student && !me.student.fixable?.includes('school')}
    <!-- the once spent: my school alone, then support; a mis-tap undone: the one before comes back, free, once (owner,
         Nov 3: everyone wrote to support) -->
    {@const undo = me.student.undo && 'school' in me.student.undo}
    <Group footnote={undo ? undefined : t('pd.support')}><Row title={mySchool?.name ?? me.student.school ?? t('look.noSchool')}>{#snippet detail()}{#if mySchool}<span class="short">{shortOf(mySchool)}</span>{/if}{/snippet}</Row></Group>
    {#if undo}{@const was = me.student.undo?.school ?? null}
      <div class="gap"><Group footnote={t('pd.undoFoot')}>{@render act(t('pd.undo', { v: schoolOf(was)?.name ?? was ?? t('look.noSchool') }), () => void pickSchool(was))}</Group></div>{/if}
  {:else if kind === 'school' && me?.student}
    {#if me.student.school}{@render once()}{/if}
    <Group>
      {#each schools as o (o.id)}
        <Row title={o.name} accessory="check" checked={mySchool?.id === o.id} onclick={() => void pickSchool(o.orig?.name ?? o.name)}>{#snippet detail()}<span class="short">{shortOf(o)}</span>{/snippet}</Row>
      {/each}
    </Group>
    <!-- no "no school" here: two students cleared theirs by mistake (Nov 2), and the once went with it -->
  {:else if kind === 'sees'}
    <!-- who sees what: read rather than tapped -->
    <Group>{#each SEES as [h, text] (h)}<Row title={t(h)} subtitle={t(text)} />{/each}</Group>
  {:else if kind === 'about'}
    <Group>
      {@render link(t('set.terms'), () => page('terms'), '', true)}
      {@render link(t('set.policy'), () => page('privacy'), '', true)}
      {@render link(t('set.write'), () => openLink('https://t.me/Sowers'), '@Sowers', true)}
      {@render link(t('set.code'), () => openLink('https://github.com/SOWcd/KBTUapp'), 'GitHub', true)}
    </Group>
  {:else if kind === 'donate' && donate}
    <!-- owner, Nov 6: a heart, "not a purchase" as a quiet pill, two lines (the page's own title names it); the number with its copy; then the banks -->
    <div class="don">
      <span class="heart"><Emoji name="blue_heart_3d" size={88} /></span>
      <span class="pill">{t('don.head')}</span>
      <p class="fs-body dim">{t('don.text')}</p>
    </div>
    <div class="num-card">
      <span><small class="fs-sub faint">{t('don.bank')}</small><b class="fs-t2 num selectable">{donate}</b></span>
      <button class="cp" aria-label={t('pay.copy')} onclick={copyDonate}><Copy size={20} /></button>
    </div>
    <p class="banks-h fs-sub faint">{t('don.banks')}</p>
    <div class="banks">
      {#each BANKS as [id, name, ios] (id)}
        <button class="bank" onclick={() => { haptic.tap(); void toBank(name, ios); }}><img src="banks/{id}.webp" alt="" width="54" height="54" /><small>{name}</small></button>
      {/each}
    </div>
    <p class="foot always">{t('don.safe')}</p>
  {/if}
</Pane>

<style>
  .sw { margin-top: 22px; }
  .gap, .always { margin-top: 26px; }
  .once { margin-bottom: var(--s-4); }
  .foot { margin-inline: var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); } /* Group's footnote, alone */
  /* a name part's end: its Cyrillic over its Latin, each cut with … rather than wrapped */
  .two { display: flex; flex-direction: column; align-items: flex-end; max-width: 50vw; line-height: 1.25; color: var(--text-3); }
  .two > span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .two > .sub { font-size: var(--fs-sub); }
  /* a school's short name stays whole; its long name wraps beside it */
  .short { color: var(--text-3); }
  .don { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); padding: var(--s-2) var(--s-4) 0; text-align: center; }
  .heart { display: grid; place-items: center; width: 132px; height: 112px; background: radial-gradient(circle, var(--accent-soft), transparent 62%); }
  .pill { padding: 4px 12px; border-radius: var(--r-full); background: var(--surface-2); font: 700 var(--fs-cap)/1.4 var(--font-text); letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-2); }
  .num-card { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin-top: var(--s-6); padding: var(--s-4) var(--s-4) var(--s-4) var(--s-5);
    border-radius: var(--r-l); background: var(--surface); }
  .num-card > span { display: flex; flex-direction: column; min-width: 0; }
  .num-card .num { white-space: nowrap; }
  .cp { flex: none; display: grid; place-items: center; width: 46px; height: 46px; border-radius: var(--r-m); background: var(--accent); color: var(--on-accent); }
  .cp:active, .bank:active { transform: scale(0.95); }
  .banks-h { margin: var(--s-6) var(--s-4) var(--s-2); }
  .banks { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--s-4) var(--s-2); padding: var(--s-4) var(--s-2); border-radius: var(--r-l); background: var(--surface); }
  .bank { display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; }
  .bank img { width: 54px; height: 54px; border-radius: var(--r-m); box-shadow: var(--shadow-thumb); }
  .bank small { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-2); }
  .wide { max-width: 60vw; color: var(--text-3); overflow-wrap: anywhere; text-align: right; }
</style>
