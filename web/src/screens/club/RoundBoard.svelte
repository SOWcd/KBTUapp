<script lang="ts">
  import { fold } from '../../ui/fold';
  // The casting team's board for the live round (PLAN "Casting"): applications by stage (new, maybe, next, taken, no),
  // a department filter, "review one by one" (the next new one after each verdict). An application opens in place:
  // the profile, the picks in order, the answers, what only the app knows (the club's events they came to, friends in
  // the club, an earlier try, in the app since), the team's votes with who; my verdict with stars and a note; the
  // decision: into a department, or no. The results go out in one tap; "Share" passes the round on as our bot's card.
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import Star from '@lucide/svelte/icons/star';
  import Share from '@lucide/svelte/icons/share';
  import Pencil from '@lucide/svelte/icons/pencil';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { api, ApiErr, type AppStage, type Id, type Round, type RoundApp, type RoundSlot } from '../../lib/api';
  import X from '@lucide/svelte/icons/x';
  import CalendarClock from '@lucide/svelte/icons/calendar-clock';
  import { dateInput, nowTs } from '../../lib/time';
  import { placeOf } from '../../lib/i18n/index.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { studioChanged } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth, time } from '../../lib/time';
  import { haptic, openLink, shareCard } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  let r = $state<Round | null>(null);
  let apps = $state<RoundApp[]>([]);
  async function load() {
    try {
      r = await api.round(org);
      apps = r ? await api.roundApps(r.id) : [];
    } catch { say(t('common.error'), 'pleading_face_3d'); }
  }
  $effect(() => { void load(); });

  const STAGES: AppStage[] = ['new', 'maybe', 'next', 'yes', 'no'];
  let stage = $state<AppStage>('new');
  let dep = $state<Id | null>(null);
  const shown = $derived(apps.filter((a) => a.stage === stage && (dep == null || a.departments.includes(dep))));
  const count = (s: AppStage) => apps.filter((a) => a.stage === s && (dep == null || a.departments.includes(dep))).length;
  const depName = (id: Id | null) => r?.departments.find((d) => d.tagId === id)?.name ?? '';
  const depColor = (id: Id) => r?.departments.find((d) => d.tagId === id)?.color ?? 'var(--accent)';
  const qText = (id: string) => r?.questions.find((q) => String(q.id) === id)?.text ?? '';
  const starsOf = (a: RoundApp) => { const s = a.votes.filter((x) => x.stars).map((x) => x.stars!); return s.length ? s.reduce((p, c) => p + c, 0) / s.length : null; };

  // one application open in place; review mode walks the new ones
  let cur = $state<RoundApp | null>(null);
  let walking = $state(false);
  let stars = $state<number | null>(null), note = $state('');
  function openApp(a: RoundApp) {
    cur = a;
    const mine = a.votes.find((x) => x.mine);
    stars = mine?.stars ?? null; note = mine?.note ?? '';
  }
  function review() {
    const next = apps.find((a) => a.stage === 'new' && (dep == null || a.departments.includes(dep)));
    if (!next) { say(t('cast.allSeen'), 'partying_face_3d'); walking = false; cur = null; return; }
    walking = true; openApp(next);
  }
  async function vote(verdict: 'no' | 'maybe' | 'next') {
    if (!cur) return;
    const a = cur;
    try {
      const res = await api.voteApp(a.id, { verdict, stars, note });
      a.stage = res.stage;
      const mine = a.votes.find((x) => x.mine);
      if (mine) Object.assign(mine, { verdict, stars, note }); else a.votes.push({ by: t('cast.me'), mine: true, verdict, stars, note });
      haptic.select();
      if (walking) review(); else cur = null;
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function decide(s: AppStage, tagId: Id | null = null) {
    if (!cur) return;
    const a = cur;
    try {
      const res = await api.decideApp(a.id, { stage: s, tagId });
      a.stage = res.stage; a.takenTag = res.takenTag;
      haptic.ok(); cur = null;
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }

  async function closeIntake() {
    if (!r || !(await sheets.ask({ title: t('cast.closeAsk'), text: t('cast.closeText'), ok: t('cast.closeGo'), cancel: t('common.cancel') }))) return;
    try { r = await api.updateRound(r.id, { close: true }); haptic.ok(); studioChanged(); } catch { say(t('common.error'), 'pleading_face_3d'); }
  }
  async function sendResults() {
    if (!r) return;
    const yes = apps.filter((a) => a.stage === 'yes').length, no = apps.length - yes;
    if (!(await sheets.ask({ title: t('cast.sendAsk'), text: t('cast.sendText', { yes, no }), ok: t('cast.sendGo'), cancel: t('common.cancel') }))) return;
    try {
      const res = await api.sendRound(r.id);
      haptic.ok(); burst(); say(t('cast.sentDone', { n: res.accepted }), 'party_popper_3d');
      studioChanged(); close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // interviews: the slots by day with who booked them, adding a day's slots, inviting the shortlisted, who came
  let view = $state<'apps' | 'iv'>('apps');
  let slots = $state<RoundSlot[]>([]);
  const loadSlots = () => { if (r) api.roundSlots(r.id).then((x) => (slots = x)).catch(() => {}); };
  $effect(() => { if (view === 'iv' && r) loadSlots(); });
  const ivDays = $derived.by(() => {
    const by = new Map<string, RoundSlot[]>();
    for (const s of slots) { const k = dayMonth(s.startsAt); by.set(k, [...(by.get(k) ?? []), s]); }
    return [...by.entries()];
  });
  const toInvite = $derived(apps.filter((a) => a.stage === 'next' && !a.invited).length);
  let adding = $state(false);
  let nf = $state({ date: dateInput(nowTs() + 2 * 86400), from: '15:00', to: '18:00', minutes: 20, capacity: 1, place: '' });
  async function addDay() {
    if (!r) return;
    try { slots = await api.addSlots(r.id, nf); adding = false; haptic.ok(); say(phrase('say.slotsAdded'), 'spiral_calendar_3d'); }
    catch { haptic.error(); say(t('cast.ivBad'), 'pleading_face_3d'); }
  }
  async function dropSlot(s: RoundSlot) {
    try { slots = await api.dropSlot(s.id); haptic.soft(); } catch { say(t('cast.ivBooked2'), 'pleading_face_3d'); }
  }
  async function inviteAll() {
    if (!r) return;
    try {
      const res = await api.inviteRound(r.id);
      for (const a of apps) if (a.stage === 'next') a.invited = true;
      haptic.ok(); say(t('cast.ivInvited', { n: res.invited }), 'party_popper_3d');
    } catch (x) { haptic.error(); say(x instanceof ApiErr && x.message === 'no_slots' ? t('cast.ivNoSlots') : t('common.error'), 'pleading_face_3d'); }
  }
  async function showed(appId: Id, came: boolean | null) {
    try {
      await api.markShowed(appId, came);
      for (const s of slots) for (const p of s.people ?? []) if (p.appId === appId) p.showed = came;
      const a = apps.find((x) => x.id === appId); if (a) a.showed = came;
      haptic.select();
    } catch { say(t('common.error'), 'pleading_face_3d'); }
  }

  function share() {
    haptic.tap();
    shareCard({ kind: 'rc', id: String(org) }, 'https://t.me/KBTUappBot?startapp=rc_' + org, r?.title ?? '')
      .then((sent) => { if (sent) say(t('cast.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'pleading_face_3d'); });
  }
</script>

<Sheet {overlay} full title={r?.title ?? t('cast.board')}>
  {#if cur && r}
    {@const a = cur}
    <button class="back" onclick={() => { cur = null; walking = false; }}><ChevronLeft size={18} />{walking ? t('cast.stopReview') : t('cast.back')}</button>
    <div class="who">
      <Avatar person={a.person} size={56} />
      <span class="tx"><b>{a.fullName}</b>
        <i>{[a.course ? t('person.course', { n: a.course }) : '', a.school].filter(Boolean).join(' · ')}</i>
        <i>{[a.email, a.username ? '@' + a.username : ''].filter(Boolean).join(' · ')}</i></span>
    </div>
    {#if a.username}<button class="tg" onclick={() => openLink('https://t.me/' + a.username)}><TelegramMark size={16} />{t('cast.write')}</button>{/if}

    {#if a.invited}
      <div class="ivline"><CalendarClock size={16} />
        <span>{a.slot ? `${dayMonth(a.slot.startsAt)}, ${time(a.slot.startsAt)} · ${placeOf(a.slot.place)}` : t('cast.ivNoTime')}</span>
        {#if a.slot}<span class="came"><button class:on={a.showed === true} onclick={() => showed(a.id, a.showed === true ? null : true)}>{t('cast.ivCame')}</button>
          <button class:on={a.showed === false} onclick={() => showed(a.id, a.showed === false ? null : false)}>{t('cast.ivMissed')}</button></span>{/if}
      </div>
    {/if}
    <div class="picks">{#each a.departments as id, i (id)}<span style="--c:{depColor(id)}">{a.departments.length > 1 ? i + 1 + '. ' : ''}{depName(id)}</span>{/each}</div>

    <div class="facts">
      <span>{a.came ? tn('cast.came', a.came) + (a.lastEvent ? ' · ' + a.lastEvent : '') : t('cast.cameNone')}</span>
      {#if a.friends}<span>{tn('cast.friends', a.friends)}</span>{/if}
      {#if a.before}<span>{t('cast.before')}</span>{/if}
      <span>{t('cast.since', { when: dayMonth(a.since) })}</span>
    </div>

    {#each Object.entries(a.answers) as [qid, ans] (qid)}
      <div class="ans"><span class="t-cap">{qText(qid)}</span><p class="selectable">{Array.isArray(ans) ? ans.join(', ') : ans}</p></div>
    {/each}

    {#if a.votes.length}
      <h3 class="t-cap sec">{t('cast.votes')}</h3>
      {#each a.votes as x, i (i)}
        <p class="vote"><b>{x.by}</b> · {t(`cast.v.${x.verdict}`)}{x.stars ? ' · ' + '★'.repeat(x.stars) : ''}{x.note ? ' — ' + x.note : ''}</p>
      {/each}
    {/if}

    <h3 class="t-cap sec">{t('cast.myVote')}</h3>
    <div class="stars">{#each [1, 2, 3, 4, 5] as n (n)}<button class:on={(stars ?? 0) >= n} onclick={() => (stars = stars === n ? null : n)} aria-label={String(n)}><Star size={22} /></button>{/each}</div>
    <label class="field"><textarea rows="2" maxlength="500" bind:value={note} placeholder={t('cast.notePh')}></textarea></label>
    <div class="verdicts">
      <button class="no" onclick={() => vote('no')}>{t('cast.v.no')}</button>
      <button class="maybe" onclick={() => vote('maybe')}>{t('cast.v.maybe')}</button>
      <button class="next" onclick={() => vote('next')}>{t('cast.v.next')}</button>
    </div>

    <h3 class="t-cap sec">{t('cast.decision')}</h3>
    <div class="take">
      {#each r.departments as d (d.tagId)}
        <button class:on={a.stage === 'yes' && a.takenTag === d.tagId} style="--c:{d.color}" onclick={() => decide('yes', d.tagId)}>{t('cast.takeInto', { name: d.name })}</button>
      {/each}
      <button class="nope" class:on={a.stage === 'no'} onclick={() => decide('no')}>{t('cast.v.no')}</button>
    </div>
  {:else if r}
    <h2 class="t-h2">{r.title}</h2>
    <p class="t-foot sub">{r.open ? t('cast.until', { when: dayMonth(r.closesAt) + ', ' + time(r.closesAt) }) : t('cast.intakeClosed')} · {tn('cast.apps', apps.length)}</p>
    {#if apps.length}
      <!-- the funnel: applied, invited, came, taken -->
      <p class="funnel">{t('cast.funnel', { apps: apps.length, invited: apps.filter((a) => a.invited).length, came: apps.filter((a) => a.showed).length, yes: apps.filter((a) => a.stage === 'yes').length })}</p>
    {/if}
    <div class="tools">
      <button onclick={share}><Share size={17} />{t('cast.share')}</button>
      <button onclick={() => sheets.roundSetup(org, r, () => void load())}><Pencil size={17} />{t('cast.edit')}</button>
    </div>
    <div class="seg views"><button class:on={view === 'apps'} onclick={() => (view = 'apps')}>{t('cast.viewApps')}</button>
      <button class:on={view === 'iv'} onclick={() => (view = 'iv')}>{t('cast.viewIv')}</button></div>

    {#if view === 'iv'}
      {#if toInvite}<Button kind="primary" size="m" full onclick={inviteAll}>{t('cast.ivInviteGo', { n: toInvite })}</Button>{/if}
      <button class="addday" onclick={() => (adding = !adding)}>{adding ? t('common.cancel') : t('cast.ivAdd')}</button>
      {#if adding}
        <div class="ivform" transition:fold>
          <label class="field"><span class="t-cap">{t('ed.date')}</span><input type="date" bind:value={nf.date} /></label>
          <div class="two">
            <label class="field"><span class="t-cap">{t('ed.start')}</span><input type="time" bind:value={nf.from} /></label>
            <label class="field"><span class="t-cap">{t('ed.end')}</span><input type="time" bind:value={nf.to} /></label>
          </div>
          <span class="t-cap">{t('cast.ivLen')}</span>
          <div class="seg">{#each [15, 20, 30, 45] as m (m)}<button class:on={nf.minutes === m} onclick={() => (nf.minutes = m)}>{m}</button>{/each}</div>
          <span class="t-cap">{t('cast.ivCap')}</span>
          <div class="seg">{#each [1, 3, 5, 10] as n (n)}<button class:on={nf.capacity === n} onclick={() => (nf.capacity = n)}>{n === 1 ? t('cast.ivSolo') : n}</button>{/each}</div>
          <label class="field"><span class="t-cap">{t('memo.where')}</span><input bind:value={nf.place} maxlength="120" placeholder={t('cast.ivPlacePh')} /></label>
          <Button kind="secondary" size="m" full onclick={addDay}>{t('cast.ivAddGo')}</Button>
        </div>
      {/if}
      {#each ivDays as [day, list] (day)}
        <h3 class="t-cap sec">{day}</h3>
        {#each list as s (s.id)}
          <div class="slot surface">
            <span class="st"><b>{time(s.startsAt)}</b><i>{placeOf(s.place)}{s.capacity > 1 ? ' · ' + t('cast.ivLeft', { n: s.left }) : ''}</i></span>
            <span class="who2">
              {#each s.people ?? [] as p (p.appId)}
                <button class="pp" class:came={p.showed === true} class:miss={p.showed === false} onclick={() => { const a = apps.find((x) => x.id === p.appId); if (a) openApp(a); }}>{p.fullName}</button>
              {:else}<span class="free">{t('cast.ivFree')}</span>{/each}
            </span>
            {#if !(s.people ?? []).length}<button class="x" onclick={() => dropSlot(s)} aria-label={t('memo.drop')}><X size={15} /></button>{/if}
          </div>
        {/each}
      {:else}<p class="t-foot empty">{t('cast.ivEmpty')}</p>{/each}
    {:else}

    {#if r.departments.length > 1}
      <div class="deps">
        <button class:on={dep == null} onclick={() => (dep = null)}>{t('cast.allDeps')}</button>
        {#each r.departments as d (d.tagId)}
          {@const n = apps.filter((a) => a.stage === 'yes' && a.takenTag === d.tagId).length}
          <button class:on={dep === d.tagId} class:full={!!d.places && n >= d.places} style="--c:{d.color}" onclick={() => (dep = d.tagId)}><i></i>{d.name}{n || d.places ? ` · ${n}${d.places ? '/' + d.places : ''}` : ''}</button>
        {/each}
      </div>
    {/if}
    <div class="seg stages">{#each STAGES as s (s)}<button class:on={stage === s} onclick={() => (stage = s)}>{t(`cast.s.${s}`)}{count(s) ? ' · ' + count(s) : ''}</button>{/each}</div>

    {#if stage === 'new' && count('new')}<Button kind="primary" size="m" full onclick={review}>{t('cast.reviewGo', { n: count('new') })}</Button>{/if}
    <div class="list">
      {#each shown as a (a.id)}
        {@const st = starsOf(a)}
        <button class="row surface" onclick={() => openApp(a)}>
          <Avatar person={a.person} size={40} tappable={false} />
          <span class="tx"><b class="ellipsis">{a.fullName}</b>
            <i class="ellipsis">{a.stage === 'yes' && a.takenTag ? '→ ' + depName(a.takenTag) : a.departments.map(depName).join(', ')}{st ? ' · ★ ' + st.toFixed(1) : ''}</i></span>
          <span class="n">{a.votes.length ? a.votes.length : ''}</span>
        </button>
      {:else}
        <p class="t-foot empty">{t('cast.none')}</p>
      {/each}
    </div>
    {/if}
  {/if}

  {#snippet footer()}
    {#if r && !cur}
      {#if r.open}<button class="shut" onclick={closeIntake}>{t('cast.closeGo')}</button>{/if}
      <Button kind="primary" size="l" full disabled={!apps.length} onclick={sendResults}>{t('cast.sendGo')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .sub { margin-top: 2px; }
  .tools { display: flex; gap: 8px; margin: 12px 0; }
  .tools button { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px; border-radius: var(--r-full); background: var(--surface-2); font: 620 14px/1 var(--font-text); }
  .deps { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin-bottom: 10px; }
  .deps button { flex: none; display: flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); font: 600 13.5px/1 var(--font-text); color: var(--text-2); }
  .deps button.on { background: var(--text); color: var(--bg); }
  .deps button.full { box-shadow: inset 0 0 0 1.5px var(--success); }
  .funnel { margin: 6px 0 0; font: 600 13px/1.3 var(--font-text); color: var(--text-2); }
  .deps i { width: 8px; height: 8px; border-radius: 50%; background: var(--c); }
  .stages { display: flex; overflow-x: auto; scrollbar-width: none; margin-bottom: 12px; max-width: 100%; }
  .stages button { flex: none; }
  .list { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
  .row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; text-align: left; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; text-align: left; }
  .tx b { font: 650 15px/1.25 var(--font-text); }
  .tx i { font: 500 13px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .n { font: 650 13px/1 var(--font-text); color: var(--text-3); }
  .empty { padding: 14px 4px; }
  .back { display: inline-flex; align-items: center; gap: 4px; margin: 0 0 10px -4px; padding: 6px 4px; font: 620 14px/1 var(--font-text); color: var(--accent-text); }
  .who { display: flex; align-items: center; gap: 12px; }
  .tg { display: inline-flex; align-items: center; gap: 6px; margin-top: 10px; height: 34px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 620 13.5px/1 var(--font-text); }
  .picks { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
  .picks span { padding: 6px 10px; border-radius: var(--r-full); background: color-mix(in srgb, var(--c) 22%, transparent); font: 650 13px/1 var(--font-text); }
  .facts { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 12px; font: 550 13px/1.3 var(--font-text); color: var(--text-2); }
  .ans { margin-top: 14px; }
  .ans p { margin-top: 4px; font: 500 15px/1.45 var(--font-text); white-space: pre-wrap; }
  .sec { margin: 20px 2px 8px; }
  .vote { font: 500 14px/1.4 var(--font-text); color: var(--text-2); margin-bottom: 4px; }
  .vote b { color: var(--text); }
  .stars { display: flex; gap: 4px; margin-bottom: 8px; }
  .stars button { color: var(--text-3); padding: 2px; }
  .stars button.on { color: #FFB23D; }
  .stars button.on :global(svg) { fill: currentColor; }
  .verdicts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px; }
  .verdicts button { display: flex; align-items: center; justify-content: center; height: 48px; border-radius: var(--r-m); font: 700 15px/1 var(--font-text); }
  .verdicts .no { background: var(--danger-soft); color: var(--danger-text); }
  .verdicts .maybe { background: var(--surface-2); color: var(--text); }
  .verdicts .next { background: var(--success-soft); color: var(--success-text); }
  .verdicts button:active, .take button:active { transform: scale(0.97); }
  .take { display: flex; flex-wrap: wrap; gap: 8px; }
  .take button { height: 40px; padding: 0 14px; border-radius: var(--r-full); background: var(--surface-2); font: 650 14px/1 var(--font-text); }
  .take button.on { background: var(--c); color: #fff; }
  .take .nope.on { background: var(--danger); color: #fff; }
  .views { display: flex; margin-bottom: 12px; }
  .views button { flex: 1; }
  .addday { display: block; margin: 10px 0; padding: 6px 2px; font: 650 14.5px/1 var(--font-text); color: var(--accent-text); }
  .ivform { display: flex; flex-direction: column; gap: 8px; margin-bottom: 8px; }
  .slot { display: flex; align-items: center; gap: 10px; padding: 10px 12px; margin-bottom: 6px; }
  .st { flex: none; width: 92px; display: flex; flex-direction: column; gap: 2px; }
  .st b { font: 750 16px/1 var(--font-display); }
  .st i { font: 500 12px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  .who2 { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; gap: 4px; }
  .pp { padding: 5px 9px; border-radius: var(--r-full); background: var(--surface-2); font: 600 13px/1.2 var(--font-text); text-align: left; }
  .pp.came { background: var(--success-soft); color: var(--success-text); }
  .pp.miss { background: var(--danger-soft); color: var(--danger-text); text-decoration: line-through; }
  .free { font: 500 13px/1.2 var(--font-text); color: var(--text-3); }
  .ivline { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; padding: 10px 12px; border-radius: var(--r-m); background: var(--accent-soft); font: 600 14px/1.3 var(--font-text); }
  .came { display: flex; gap: 6px; margin-left: auto; }
  .came button { height: 30px; padding: 0 10px; border-radius: var(--r-full); background: var(--surface); font: 650 13px/1 var(--font-text); }
  .came button.on { background: var(--text); color: var(--bg); }
  .shut { display: block; margin: 0 auto 10px; padding: 6px 10px; font: 620 14px/1 var(--font-text); color: var(--text-2); }
</style>
