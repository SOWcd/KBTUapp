<script lang="ts">
  import { fold } from '../../ui/fold';
  // The casting team's board for the live round (PLAN "Casting"): applications by stage (new, maybe, next, taken, no),
  // a department filter, "review one by one" (the next new one after each verdict). An application opens in place:
  // the profile, the picks in order, the answers, what only the app knows (the club's events they came to, friends in
  // the club, an earlier try, in the app since), the team's votes with who; my verdict with stars and a note; the
  // decision: into a department, or no. The results go out in one tap; "Share" passes the round on as our bot's card.
  import Star from '@lucide/svelte/icons/star';
  import Share from '@lucide/svelte/icons/share';
  import Pencil from '@lucide/svelte/icons/pencil';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { api, ApiErr, type AppStage, type Id, type Round, type RoundApp, type RoundSlot } from '../../lib/api';
  import X from '@lucide/svelte/icons/x';
  import Check from '@lucide/svelte/icons/check';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
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
  import Kanban from '@lucide/svelte/icons/kanban';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import { schoolShort } from '../../lib/short';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  let r = $state<Round | null>(null);
  let apps = $state<RoundApp[]>([]);
  async function load() {
    try {
      r = await api.round(org);
      apps = r ? await api.roundApps(r.id) : [];
    } catch { say(t('common.error'), 'warning_3d'); }
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
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function decide(s: AppStage, tagId: Id | null = null) {
    if (!cur) return;
    const a = cur;
    try {
      const res = await api.decideApp(a.id, { stage: s, tagId });
      a.stage = res.stage; a.takenTag = res.takenTag;
      haptic.ok(); cur = null;
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }

  async function closeIntake() {
    if (!r || !(await sheets.ask({ title: t('cast.closeAsk'), text: t('cast.closeText'), ok: t('cast.closeGo'), cancel: t('common.cancel') }))) return;
    try { r = await api.updateRound(r.id, { close: true }); haptic.ok(); studioChanged(); } catch { say(t('common.error'), 'warning_3d'); }
  }
  async function sendResults() {
    if (!r) return;
    const yes = apps.filter((a) => a.stage === 'yes').length, no = apps.length - yes, untouched = apps.filter((a) => a.stage === 'new').length;
    const text = t('cast.sendText', { yes, no }) + (untouched ? ' ' + t('cast.sendUntouched', { n: untouched }) : '');
    if (!(await sheets.ask({ title: t('cast.sendAsk'), text, ok: t('cast.sendGo'), cancel: t('common.cancel') }))) return;
    try {
      const res = await api.sendRound(r.id);
      haptic.ok(); burst(); say(t('cast.sentDone', { n: res.accepted }), 'party_popper_3d');
      studioChanged(); close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // the stages row scrolls at 375/320: a fade on the side with more
  let fade = $state({ l: false, r: false });
  const edges = (el: HTMLElement) => { fade = { l: el.scrollLeft > 2, r: el.scrollLeft + el.clientWidth < el.scrollWidth - 2 }; };
  function stagesRow(el: HTMLElement) { edges(el); const ro = new ResizeObserver(() => edges(el)); ro.observe(el); return () => ro.disconnect(); }

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
    } catch (x) { haptic.error(); say(x instanceof ApiErr && x.message === 'no_slots' ? t('cast.ivNoSlots') : t('common.error'), 'warning_3d'); }
  }
  async function showed(appId: Id, came: boolean | null) {
    try {
      await api.markShowed(appId, came);
      for (const s of slots) for (const p of s.people ?? []) if (p.appId === appId) p.showed = came;
      const a = apps.find((x) => x.id === appId); if (a) a.showed = came;
      haptic.select();
    } catch { say(t('common.error'), 'warning_3d'); }
  }

  function share() {
    haptic.tap();
    shareCard({ kind: 'rc', id: String(org) }, 'https://t.me/KBTUappBot?startapp=rc_' + org, r?.title ?? '')
      .then((sent) => { if (sent) say(t('cast.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
</script>

<!-- one Back (AGENTS.md): Telegram's Back leaves an application for the list, then closes the board -->
<Sheet {overlay} icon={Kanban} full title={r?.title ?? t('cast.board')} hold={() => cur != null} onhold={() => { cur = null; walking = false; }}>
  <div class="stack">
  {#if cur && r}
    {@const a = cur}
    <div class="who">
      <Avatar person={a.person} size={56} />
      <span class="tx"><b>{a.fullName}</b>
        <i>{[a.course ? t('person.course', { n: a.course }) : '', schoolShort(a.school)].filter(Boolean).join(' · ')}</i>
        <i>{[a.email, a.username ? '@' + a.username : ''].filter(Boolean).join(' · ')}</i></span>
    </div>
    {#if a.username}<span class="lone"><Button kind="tinted" size="s" onclick={() => openLink('https://t.me/' + a.username)}>{#snippet icon()}<TelegramMark size={16} />{/snippet}{t('cast.write')}</Button></span>{/if}

    {#if a.invited}
      <Notice tone="accent" icon={CalendarClock} text={a.slot ? `${dayMonth(a.slot.startsAt)}, ${time(a.slot.startsAt)} · ${placeOf(a.slot.place)}` : t('cast.ivNoTime')}>
        {#if a.slot}<div class="wrap">
          <Chip selected={a.showed === true} onclick={() => showed(a.id, a.showed === true ? null : true)}>{t('cast.ivCame')}</Chip>
          <Chip selected={a.showed === false} onclick={() => showed(a.id, a.showed === false ? null : false)}>{t('cast.ivMissed')}</Chip>
        </div>{/if}
      </Notice>
    {/if}
    <div class="wrap">{#each a.departments as id, i (id)}<Tag><i class="dot" style:--c={depColor(id)}></i>{a.departments.length > 1 ? i + 1 + '. ' : ''}{depName(id)}</Tag>{/each}</div>

    <div class="facts">
      <span>{a.came ? tn('cast.came', a.came) + (a.lastEvent ? ' · ' + a.lastEvent : '') : t('cast.cameNone')}</span>
      {#if a.friends}<span>{tn('cast.friends', a.friends)}</span>{/if}
      {#if a.before}<span>{t('cast.before')}</span>{/if}
      <span>{t('cast.since', { when: dayMonth(a.since) })}</span>
    </div>

    {#each Object.entries(a.answers) as [qid, ans] (qid)}
      <div class="ans"><span class="lbl">{qText(qid)}</span><p class="selectable">{Array.isArray(ans) ? ans.join(', ') : ans}</p></div>
    {/each}

    {#if a.votes.length}
      <Group caption={t('cast.votes')}>
        {#each a.votes as x, i (i)}
          <Row dense title={x.by} subtitle={[t(`cast.v.${x.verdict}`), x.stars ? '★'.repeat(x.stars) : '', x.note].filter(Boolean).join(' · ')} />
        {/each}
      </Group>
    {/if}

    <h3 class="cap">{t('cast.myVote')}</h3>
    <!-- engine: a star rating (five taps, the chosen ones filled) -->
    <div class="stars">{#each [1, 2, 3, 4, 5] as n (n)}<button class:on={(stars ?? 0) >= n} onclick={() => (stars = stars === n ? null : n)} aria-label={String(n)}><Star size={24} /></button>{/each}</div>
    <Field label={t('memo.note')} multiline rows={2} maxlength={500} bind:value={note} placeholder={t('cast.notePh')} />
    <div class="btns">
      <Button kind="gray" destructive full onclick={() => vote('no')}>{t('cast.v.no')}</Button>
      <Button kind="gray" full onclick={() => vote('maybe')}>{t('cast.v.maybe')}</Button>
    </div>
    <Button kind="tinted" full onclick={() => vote('next')}>{t('cast.v.next')}</Button>

    <h3 class="cap">{t('cast.decision')}</h3>
    <div class="wrap">
      {#each r.departments as d (d.tagId)}
        <Chip selected={a.stage === 'yes' && a.takenTag === d.tagId} onclick={() => decide('yes', d.tagId)}><i class="dot" style:--c={d.color}></i>{t('cast.takeInto', { name: d.name })}</Chip>
      {:else}
        <!-- no departments: into the club -->
        <Chip selected={a.stage === 'yes'} onclick={() => decide('yes')}>{t('cast.take')}</Chip>
      {/each}
      <Chip selected={a.stage === 'no'} onclick={() => decide('no')}>{t('cast.v.no')}</Chip>
    </div>
  {:else if r}
    <p class="hint">{r.open ? t('cast.until', { when: dayMonth(r.closesAt) + ', ' + time(r.closesAt) }) : t('cast.intakeClosed')} · {tn('cast.apps', apps.length)}</p>
    {#if apps.length}
      <!-- the funnel: applied, invited, came, taken -->
      <p class="hint">{t('cast.funnel', { apps: apps.length, invited: apps.filter((a) => a.invited).length, came: apps.filter((a) => a.showed).length, yes: apps.filter((a) => a.stage === 'yes').length })}</p>
    {/if}
    <div class="wrap">
      <Button kind="gray" size="s" onclick={share}>{#snippet icon()}<Share size={16} />{/snippet}{t('cast.share')}</Button>
      <Button kind="gray" size="s" onclick={() => sheets.roundSetup(org, r, () => void load())}>{#snippet icon()}<Pencil size={16} />{/snippet}{t('cast.edit')}</Button>
    </div>
    <Segmented items={[{ value: 'apps', label: t('cast.viewApps') }, { value: 'iv', label: t('cast.viewIv') }]} bind:value={view} label={t('cast.board')} />

    {#if view === 'iv'}
      {#if toInvite}<Button kind="primary" size="m" full onclick={inviteAll}>{t('cast.ivInviteGo', { n: toInvite })}</Button>{/if}
      <span class="lone"><Button kind="plain" size="s" onclick={() => (adding = !adding)}>{adding ? t('common.cancel') : t('cast.ivAdd')}</Button></span>
      {#if adding}
        <div class="stack" transition:fold>
          <!-- engine: Field has no date/time type: by hand, in Field's look (.fl) -->
          <label class="fl"><span>{t('ed.date')}</span><input type="date" bind:value={nf.date} /></label>
          <div class="two">
            <label class="fl"><span>{t('ed.start')}</span><input type="time" bind:value={nf.from} /></label>
            <label class="fl"><span>{t('ed.end')}</span><input type="time" bind:value={nf.to} /></label>
          </div>
          <span class="lbl">{t('cast.ivLen')}</span>
          <Segmented items={[15, 20, 30, 45].map((m) => ({ value: m, label: String(m) }))} bind:value={nf.minutes} label={t('cast.ivLen')} />
          <span class="lbl">{t('cast.ivCap')}</span>
          <Segmented items={[1, 3, 5, 10].map((n) => ({ value: n, label: String(n) }))} bind:value={nf.capacity} label={t('cast.ivCap')} />
          <Field label={t('memo.where')} bind:value={nf.place} maxlength={120} placeholder={t('cast.ivPlacePh')} />
          <Button kind="secondary" size="m" full onclick={addDay}>{t('cast.ivAddGo')}</Button>
        </div>
      {/if}
      {#each ivDays as [day, list] (day)}
        <Group caption={day}>
          {#each list as s (s.id)}
            {@const people = s.people ?? []}
            <Row title={time(s.startsAt)} subtitle={placeOf(s.place) + (s.capacity > 1 ? ' · ' + t('cast.ivLeft', { n: s.left }) : '')} value={people.length ? '' : t('cast.ivFree')}>
              {#snippet trailing()}{#if !people.length}<IconButton icon={X} kind="plain" size="s" label={t('memo.drop')} onclick={() => dropSlot(s)} />{/if}{/snippet}
            </Row>
            {#each people as p (p.appId)}
              <Row dense title={p.fullName} value={p.showed === true ? t('cast.ivCame') : p.showed === false ? t('cast.ivMissed') : ''} invalid={p.showed === false} accessory="chevron"
                onclick={() => { const a = apps.find((x) => x.id === p.appId); if (a) openApp(a); }}>
                {#snippet lead()}<span class="mark" class:came={p.showed === true}>{#if p.showed === true}<Check size={18} strokeWidth={2.4} />{/if}</span>{/snippet}
              </Row>
            {/each}
          {/each}
        </Group>
      {:else}<EmptyState inline text={t('cast.ivEmpty')} />{/each}
    {:else}

    {#if r.departments.length > 1}
      <div class="chips">
        <Chip selected={dep == null} onclick={() => (dep = null)}>{t('cast.allDeps')}</Chip>
        {#each r.departments as d (d.tagId)}
          {@const n = apps.filter((a) => a.stage === 'yes' && a.takenTag === d.tagId).length}
          <Chip selected={dep === d.tagId} icon={d.places && n >= d.places ? Check : undefined} onclick={() => (dep = d.tagId)}><i class="dot" style:--c={d.color}></i>{d.name}{n || d.places ? ` · ${n}${d.places ? '/' + d.places : ''}` : ''}</Chip>
        {/each}
      </div>
    {/if}
    <div class="chips stages" class:fl={fade.l} class:fr={fade.r} {@attach stagesRow} onscroll={(e) => edges(e.currentTarget)}>
      {#each STAGES as s (s)}<Chip selected={stage === s} onclick={(e) => { stage = s; (e.currentTarget as HTMLElement).scrollIntoView({ inline: 'nearest', block: 'nearest', behavior: 'smooth' }); }}>{t(`cast.s.${s}`)}{count(s) ? ' · ' + count(s) : ''}</Chip>{/each}
    </div>

    {#if stage === 'new' && count('new')}<Button kind="primary" size="m" full onclick={review}>{t('cast.reviewGo', { n: count('new') })}</Button>{/if}
    {#if shown.length}
      <Group>
        {#each shown as a (a.id)}
          {@const st = starsOf(a)}
          <Row dense title={a.fullName} subtitle={(a.stage === 'yes' && a.takenTag ? '→ ' + depName(a.takenTag) : a.departments.map(depName).join(', ')) + (st ? ' · ★ ' + st.toFixed(1) : '')}
            value={a.votes.length ? String(a.votes.length) : ''} accessory="chevron" onclick={() => openApp(a)}>
            {#snippet lead()}<Avatar person={a.person} size={40} tappable={false} />{/snippet}
          </Row>
        {/each}
      </Group>
    {:else}
      <EmptyState inline text={t('cast.none')} />
    {/if}
    {/if}
  {/if}
  </div>

  {#snippet footer()}
    {#if r && !cur}
      {#if r.open}<Button kind="plain" full onclick={closeIntake}>{t('cast.closeGo')}</Button>{/if}
      <Button kind="primary" size="l" full disabled={!apps.length} onclick={sendResults}>{t('cast.sendGo')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .stack { display: flex; flex-direction: column; gap: var(--s-3); }
  .hint { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  .lone { align-self: flex-start; }
  /* a heading in Group's caption style, over what isn't a list */
  .cap { margin: var(--s-3) var(--s-1) 0; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .stack > :global(section) { margin-top: var(--s-3); }
  .lbl { margin: 0 var(--s-4) -6px; font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .wrap { display: flex; flex-wrap: wrap; gap: var(--s-2); padding-block: var(--s-1); }
  .btns { display: flex; gap: var(--s-2); }
  .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--c); }
  /* the chips' rows scroll sideways (4 px of block padding keeps their 44 px hit areas) */
  .chips { display: flex; gap: var(--s-2); overflow-x: auto; scrollbar-width: none; padding-block: var(--s-1); max-width: 100%; }
  /* the stages wrap, never scroll: "Accepted" sat past the edge and a Vice couldn't find who she took (Nov 3) */
  .chips.stages { flex-wrap: wrap; overflow-x: visible; }
  .stages.fr { mask-image: linear-gradient(90deg, black calc(100% - 28px), transparent); }
  .stages.fl { mask-image: linear-gradient(90deg, transparent, black 28px); }
  .stages.fl.fr { mask-image: linear-gradient(90deg, transparent, black 28px, black calc(100% - 28px), transparent); }
  .mark { width: 24px; display: grid; place-items: center; }
  .mark.came { color: var(--success-text); }
  .who { display: flex; align-items: center; gap: var(--s-3); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .tx i { font: 450 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .facts { display: flex; flex-wrap: wrap; gap: 6px var(--s-3); font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .ans { display: flex; flex-direction: column; gap: 10px; }
  .ans p { margin: 0 var(--s-1); font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; }
  .stars { display: flex; gap: var(--s-1); }
  .stars button { position: relative; display: grid; place-items: center; width: var(--tap); height: var(--tap); color: var(--text-3); }
  .stars button.on { color: var(--warning); }
  .stars button.on :global(svg) { fill: currentColor; }
  .stars button:active { transform: scale(0.9); }
  /* Field's look for the date and time inputs it can't take yet */
  .fl { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .fl > span { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .fl > input { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
  .two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-2); }
</style>
