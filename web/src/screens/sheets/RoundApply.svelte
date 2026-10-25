<script lang="ts">
  // Applying to a club's recruitment round (PLAN "Casting"): a minute. What the club knows already comes from the KBTU
  // sign-in and Telegram and is only shown; the student picks departments in order of wish (tap order = priority) and
  // answers the club's own questions (a department's question only once it's picked). The draft stays on the phone as
  // it's typed (Telegram may close the app mid-answer). After sending: the stages and "results by". Opened from the
  // club's sheet, the Join page, a shared card or the bot (rc_<club>).
  import Check from '@lucide/svelte/icons/check';
  import { api, ApiErr, type Id, type Round, type RoundSlot } from '../../lib/api';
  import { social } from '../../lib/social';
  import { placeOf } from '../../lib/i18n/index.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { data, loadAfisha } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth, time } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import { schoolShort } from '../../lib/short';

  let { overlay, org, source = 'club' }: { overlay: Overlay; org: Id; source?: string } = $props();

  const club = $derived(data.orgs.find((o) => o.id === org));
  const me = $derived(session.me);
  let r = $state<Round | null>(null);
  let gone = $state(false);
  let picks = $state<Id[]>([]);
  let answers = $state<Record<string, string | string[]>>({});
  let sent = $state(false);
  // a sent application shows where it stands; its form opens again only on "Change" (owner, Oct 22: the form stayed after
  // sending, and a pull after saving asked "leave without saving?")
  let editing = $state(false);
  let saved = $state('');
  let leaving = false;
  let busy = $state(false);
  let tried = $state(false);
  const key = () => `kb-round-${r?.id}`;

  $effect(() => {
    api.round(org).then((x) => {
      if (!x) { gone = true; return; }
      r = x;
      if (x.mine) { picks = [...x.mine.departments]; answers = { ...x.mine.answers }; sent = true; saved = snap; return; }
      try { const d = JSON.parse(localStorage.getItem(key()) ?? 'null'); if (d) { picks = d.picks ?? []; answers = d.answers ?? {}; } } catch { /* blocked */ }
    }).catch(() => { gone = true; });
  });
  // the draft, as it's typed
  $effect(() => {
    const draft = JSON.stringify({ picks, answers });
    if (!r || sent) return;
    try { localStorage.setItem(key(), draft); } catch { /* blocked */ }
  });

  function pick(id: Id) {
    haptic.select();
    if (picks.includes(id)) picks = picks.filter((x) => x !== id);
    else if (r && picks.length < r.picks) picks = [...picks, id];
    else if (r && r.picks === 1) picks = [id];
    else say(t('cast.pickMax', { n: r?.picks ?? 1 }), 'raising_hands_3d_default');
  }
  const shown = $derived((r?.questions ?? []).filter((q) => q.tagId == null || picks.includes(q.tagId)));
  const payload = () => Object.fromEntries(shown.map((q) => [String(q.id), answers[q.id] ?? '']));
  // what the club would get, as the server keeps it (no empty answers, no unpicked department's): typing and erasing
  // isn't a change
  const snap = $derived(JSON.stringify({ picks, answers: Object.fromEntries(Object.entries(payload())
    .map(([k, a]) => [k, Array.isArray(a) ? a : a.trim()] as const).filter(([, a]) => a.length)) }));
  const missing = (q: Round['questions'][number]) => q.required && !(Array.isArray(answers[q.id]) ? (answers[q.id] as string[]).length : String(answers[q.id] ?? '').trim());
  const ready = $derived(picks.length > 0 && !shown.some(missing));
  function toggleMany(qid: Id, opt: string) {
    const cur = (answers[qid] as string[] | undefined) ?? [];
    answers[qid] = cur.includes(opt) ? cur.filter((x) => x !== opt) : [...cur, opt];
  }

  async function send() {
    tried = true;
    if (!r || !ready) { haptic.error(); return; }
    busy = true;
    const sending = snap; // what's typed while it goes isn't saved yet
    try {
      r = await api.applyRound(r.id, { departments: picks, answers: payload(), source });
      try { localStorage.removeItem(key()); } catch { /* blocked */ }
      const first = !sent;
      sent = true; editing = false; saved = sending;
      haptic.ok();
      if (first) burst();
      say(first ? t('cast.sent') : t('cast.saved'), 'party_popper_3d');
      void loadAfisha(); // the club's "applied" mark
    } catch (x) {
      haptic.error();
      say(x instanceof ApiErr && x.code === 'closed' ? t('cast.closed') : x instanceof ApiErr && x.message === 'member' ? t('join.already', { club: club?.name ?? '' }) : t('common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
  // the interview (invited after screening): the times with room, mine on top; another time any time before it starts
  let slots = $state<RoundSlot[]>([]);
  let picking = $state(false);
  $effect(() => { if (r?.mine?.invited) api.roundSlots(r.id).then((x) => (slots = x)).catch(() => {}); });
  const days = $derived.by(() => {
    const by = new Map<string, RoundSlot[]>();
    for (const s of slots) { const k = dayMonth(s.startsAt); by.set(k, [...(by.get(k) ?? []), s]); }
    return [...by.entries()];
  });
  async function take(s: RoundSlot | null) {
    if (!r) return;
    try {
      slots = await api.bookSlot(r.id, s?.id ?? null);
      const m = slots.find((x) => x.mine);
      if (r.mine) r.mine.slot = m ? { id: m.id, startsAt: m.startsAt, minutes: m.minutes, place: m.place } : null;
      picking = false; haptic.ok();
      if (m) say(t('cast.ivBooked', { when: dayMonth(m.startsAt) + ', ' + time(m.startsAt) }), 'spiral_calendar_3d');
    } catch (x) { haptic.error(); say(x instanceof ApiErr && x.code === 'full' ? t('cast.ivFull') : t('common.error'), 'pleading_face_3d');
      api.roundSlots(r.id).then((y) => (slots = y)).catch(() => {}); }
  }
  function nothingFits() {
    const tgLink = club?.links.find((u) => social(u).kind === 'telegram') ?? club?.links[0];
    if (tgLink) openLink(tgLink); else say(t('cast.ivWrite'), 'raising_hands_3d_default');
  }

  function cancelEdit() {
    try { const d = JSON.parse(saved); picks = d.picks; answers = { ...d.answers }; } catch { /* never */ }
    editing = false; tried = false;
  }
  // only edits to a sent application ask before closing; an unsent one keeps its draft on the phone
  const changed = () => !leaving && sent && editing && snap !== saved;
  let asking = false;
  async function askLeave() {
    if (asking) return;
    asking = true;
    try { if (await sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('common.cancel'), danger: true })) { leaving = true; close(overlay.id); } }
    finally { asking = false; }
  }

  async function withdraw() {
    if (!r || !(await sheets.ask({ title: t('join.withdrawAsk'), text: t('cast.withdrawText'), ok: t('join.withdraw'), cancel: t('join.keep'), danger: true }))) return;
    try { await api.withdrawRound(r.id); haptic.soft(); void loadAfisha(); close(overlay.id); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} tall title={club?.name ?? t('cast.title')} hold={changed} onhold={askLeave}>
  {#if gone}
    <p class="t-callout dim">{t('cast.closed')}</p>
  {:else if r}
    <h2 class="t-h2">{r.title}</h2>
    <p class="t-foot sub">{club?.name} · {t('cast.until', { when: dayMonth(r.closesAt) + ', ' + time(r.closesAt) })}</p>

    {#if sent}
      <!-- after sending: where it stands -->
      <ol class="steps">
        <li class="done"><Check size={15} />{t('cast.stepSent')}</li>
        <li class:done={r.mine?.stage !== 'sent'}>{t('cast.stepReview')}</li>
        <li class:done={r.mine?.stage === 'yes' || r.mine?.stage === 'no'}>{r.resultsBy ? t('cast.stepResultsBy', { when: dayMonth(r.resultsBy) }) : t('cast.stepResults')}</li>
      </ol>
      <p class="t-foot note">{t('cast.botTells')}</p>
    {/if}

    {#if r.mine?.invited}
      <!-- the interview: the time to pick, or mine -->
      <section class="iv surface">
        <span class="t-cap">{t('cast.ivTitle')}</span>
        {#if r.mine.slot && !picking}
          <p class="ivmine"><b>{dayMonth(r.mine.slot.startsAt)}, {time(r.mine.slot.startsAt)}</b><span>{placeOf(r.mine.slot.place)}</span></p>
          <button class="ivlink" onclick={() => (picking = true)}>{t('cast.ivChange')}</button>
        {:else}
          <p class="t-foot">{t('cast.ivPick')}</p>
          {#each days as [day, list] (day)}
            <span class="ivday">{day}</span>
            <div class="ivtimes">{#each list as s (s.id)}<button class:on={s.mine} onclick={() => take(s)}>{time(s.startsAt)}{s.capacity > 1 ? ' · ' + t('cast.ivLeft', { n: s.left }) : ''}</button>{/each}</div>
          {:else}<p class="t-foot">{t('cast.ivNone')}</p>{/each}
          <button class="ivlink" onclick={nothingFits}>{t('cast.ivNothing')}</button>
          {#if r.mine.slot}<button class="ivlink" onclick={() => take(null)}>{t('cast.ivDrop')}</button>{/if}
        {/if}
      </section>
    {/if}

    {#if !sent || editing}
    <section class="known surface">
      <span class="t-cap">{t('cast.known')}</span>
      <div class="me">
        {#if me}<Avatar person={{ id: me.id, name: me.name, avatar: me.avatar }} size={44} tappable={false} />{/if}
        <span class="tx"><b>{me?.student ? `${me.student.lastName} ${me.student.firstName}` : me?.name}</b>
          <i>{[me?.student?.course ? t('person.course', { n: me.student.course }) : '', schoolShort(me?.student?.school)].filter(Boolean).join(' · ')}</i>
          <i>{[me?.student?.email, me?.tg.username ? '@' + me.tg.username : ''].filter(Boolean).join(' · ')}</i></span>
      </div>
    </section>

    <h3 class="t-cap sec">{r.picks > 1 ? t('cast.picksMany', { n: r.picks }) : t('cast.picksOne')}</h3>
    <div class="deps">
      {#each r.departments as d (d.tagId)}
        {@const n = picks.indexOf(d.tagId)}
        <button class="dep surface" class:on={n >= 0} style="--c:{d.color}" onclick={() => pick(d.tagId)} disabled={!r.open}>
          <span class="mark">{#if n >= 0}{r.picks > 1 ? n + 1 : '✓'}{/if}</span>
          <span class="tx"><b>{d.name}</b>{#if d.about}<i>{d.about}</i>{/if}</span>
        </button>
      {/each}
    </div>
    {#if tried && !picks.length}<p class="err">{t('cast.pickOne')}</p>{/if}

    {#each shown as q (q.id)}
      <div class="q">
        <span class="t-cap">{q.text}{q.required ? '' : ' · ' + t('cast.optional')}</span>
        {#if q.kind === 'long'}
          <label class="field" class:bad={tried && missing(q)}><textarea rows="4" maxlength="2000" bind:value={answers[q.id]} disabled={!r.open}></textarea></label>
        {:else if q.kind === 'one' || q.kind === 'many'}
          <div class="opts">
            {#each q.options ?? [] as o (o)}
              {@const on = q.kind === 'one' ? answers[q.id] === o : ((answers[q.id] as string[] | undefined) ?? []).includes(o)}
              <button class:on disabled={!r.open} onclick={() => { haptic.select(); if (q.kind === 'one') answers[q.id] = o; else toggleMany(q.id, o); }}>{o}</button>
            {/each}
          </div>
        {:else}
          <label class="field" class:bad={tried && missing(q)}><input bind:value={answers[q.id]} maxlength={q.kind === 'link' ? 300 : 200} disabled={!r.open}
            type={q.kind === 'link' ? 'url' : 'text'} inputmode={q.kind === 'link' ? 'url' : 'text'} placeholder={q.kind === 'link' ? 'https://' : ''} /></label>
        {/if}
        {#if tried && missing(q)}<p class="err">{t('ed.need')}</p>{/if}
      </div>
    {/each}

    {/if}

    {#if sent && r.open && !editing}<button class="wd" onclick={withdraw}>{t('join.withdraw')}</button>{/if}
  {/if}

  {#snippet footer()}
    {#if r?.open && !sent}
      <Button kind="primary" size="l" full loading={busy} onclick={send}>{t('cast.send')}</Button>
    {:else if r?.open && editing}
      <div class="row">
        <Button kind="neutral" size="l" onclick={cancelEdit}>{t('common.cancel')}</Button>
        <Button kind="primary" size="l" full loading={busy} disabled={snap === saved} onclick={send}>{t('cast.save')}</Button>
      </div>
    {:else if r?.open}
      <Button kind="secondary" size="l" full onclick={() => { haptic.select(); editing = true; }}>{t('cast.change')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .sub { margin-top: 2px; }
  .dim { color: var(--text-2); }
  .steps { display: flex; flex-direction: column; gap: 6px; margin: 14px 0 4px; padding: 12px 14px; border-radius: var(--r-l); background: var(--accent-soft); list-style: none; }
  .steps li { display: flex; align-items: center; gap: 8px; font: 600 14.5px/1.3 var(--font-text); color: var(--text-2); }
  .steps li.done { color: var(--text); }
  .note { margin: 6px 4px 0; }
  .iv { display: flex; flex-direction: column; gap: 8px; margin-top: 14px; padding: 12px 14px; box-shadow: inset 0 0 0 2px var(--accent); }
  .ivmine { display: flex; flex-direction: column; gap: 2px; }
  .ivmine b { font: 750 20px/1.2 var(--font-display); }
  .ivmine span { font: 550 14px/1.3 var(--font-text); color: var(--text-2); }
  .ivday { margin-top: 4px; font: 650 13px/1 var(--font-text); color: var(--text-2); }
  .ivtimes { display: flex; flex-wrap: wrap; gap: 6px; }
  .ivtimes button { height: 36px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); font: 650 14px/1 var(--font-text); }
  .ivtimes button.on { background: var(--accent); color: var(--on-accent); }
  .ivlink { align-self: flex-start; padding: 4px 0; font: 620 14px/1.2 var(--font-text); color: var(--accent-text); }
  .known { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; padding: 12px 14px; }
  .me { display: flex; align-items: center; gap: 12px; }
  .tx { display: flex; flex-direction: column; gap: 2px; min-width: 0; text-align: left; }
  .tx b { font: 650 15px/1.25 var(--font-text); }
  .tx i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .sec { margin: 20px 2px 8px; }
  .deps { display: flex; flex-direction: column; gap: 8px; }
  .dep { display: flex; align-items: center; gap: 12px; padding: 12px 14px; text-align: left; transition: transform var(--t-fast) var(--ease); }
  .dep:active { transform: scale(0.98); }
  .dep.on { box-shadow: inset 0 0 0 2px var(--c); }
  .mark { flex: none; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    box-shadow: inset 0 0 0 2px var(--line-2); font: 750 14px/1 var(--font-text); color: #fff; }
  .dep.on .mark { background: var(--c); box-shadow: none; }
  .q { display: flex; flex-direction: column; gap: 6px; margin-top: 16px; }
  .q > .t-cap { margin: 0 4px; text-transform: none; letter-spacing: 0; font: 650 14.5px/1.3 var(--font-text); color: var(--text); }
  .opts { display: flex; flex-wrap: wrap; gap: 6px; }
  .opts button { height: 38px; padding: 0 14px; border-radius: var(--r-full); background: var(--surface-2); font: 600 14px/1 var(--font-text); color: var(--text-2); }
  .opts button.on { background: var(--text); color: var(--bg); }
  .err { margin: 2px 4px 0; font: 600 12.5px/1.3 var(--font-text); color: var(--danger-text); }
  .row { display: flex; gap: 8px; }
  .wd { display: block; margin: 18px auto 4px; padding: 6px 10px; font: 620 14px/1 var(--font-text); color: var(--text-2); }
</style>
