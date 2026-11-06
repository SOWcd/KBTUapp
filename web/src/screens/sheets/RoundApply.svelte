<script lang="ts">
  // Applying to a club's recruitment round (PLAN "Casting"): a minute. What the club knows already comes from the KBTU
  // sign-in and Telegram and is only shown; the student picks departments in order of wish (tap order = priority) and
  // answers the club's own questions (a department's question only once it's picked). The draft stays on the phone as
  // it's typed (Telegram may close the app mid-answer). The steps (application, screening, the audition when the club
  // holds one, results) with the club's own "what's next" under them, before and after sending. One department or none:
  // nothing to pick. Opened from the
  // club's sheet, the Join page, a shared card or the bot (rc_<club>).
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import Circle from '@lucide/svelte/icons/circle';
  import { api, ApiErr, type Id, type Round, type RoundSlot } from '../../lib/api';
  import { clubDm } from '../../lib/clubdm';
  import { session } from '../../lib/state/session.svelte';
  import { placeOf } from '../../lib/i18n/index.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, loadAfisha } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth, time } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import ClipboardPen from '@lucide/svelte/icons/clipboard-pen';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, org, source = 'club' }: { overlay: Overlay; org: Id; source?: string } = $props();

  const club = $derived(data.orgs.find((o) => o.id === org));
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
      if (x.departments.length === 1) picks = [x.departments[0].tagId];  // one department: nothing to pick
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
  const ready = $derived((picks.length > 0 || (r?.departments.length ?? 0) <= 1) && !shown.some(missing));
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
      say(x instanceof ApiErr && x.code === 'closed' ? t('cast.closed') : x instanceof ApiErr && x.message === 'member' ? t('join.already', { club: club?.name ?? '' }) : t('common.error'), 'warning_3d');
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
    } catch (x) { haptic.error(); say(x instanceof ApiErr && x.code === 'full' ? t('cast.ivFull') : t('common.error'), 'warning_3d');
      api.roundSlots(r.id).then((y) => (slots = y)).catch(() => {}); }
  }
  // no time fits: "Message the club" (its President's DM, lib/clubdm), fetched ahead so the tap opens it at once
  let contact = $state<string | null>(null);
  $effect(() => { api.org(org).then((x) => (contact = x.contact ?? null)).catch(() => {}); });
  function nothingFits() {
    if (contact && club) openLink(clubDm(contact, club, session.me?.memberships ?? [])); else say(t('cast.ivWrite'), 'raising_hands_3d_default');
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
    catch { say(t('common.error'), 'warning_3d'); }
  }
</script>

<Sheet {overlay} icon={ClipboardPen} tall title={club?.name ?? t('cast.title')} hold={changed} onhold={askLeave}>
  {#if gone}
    <EmptyState icon={ClipboardPen} title={t('cast.closed')} />
  {:else if r}
    {@const final = r.mine?.stage === 'yes' || r.mine?.stage === 'no'}
    {@const steps = [[t('cast.stepSent'), sent], [t('cast.stepReview'), !!r.mine?.invited || final], ...(r.interviews ? [[t('cast.stepAudition'), final]] : []),
      [r.resultsBy ? t('cast.stepResultsBy', { when: dayMonth(r.resultsBy) }) : t('cast.stepResults'), final]] as [string, boolean][]}
    <h2 class="t-h2">{r.title}</h2>
    <p class="t-foot sub">{club?.name} · {t('cast.until', { when: dayMonth(r.closesAt) + ', ' + time(r.closesAt) })}</p>

    <div class="body">
    <!-- the steps, done as they pass; the club's own "what's next" under them (shown like its description) -->
    <div>
      <!-- the steps once it's sent (before: one line on what the club gets, over the button; owner, Nov 3) -->
      {#if sent}<Group>
        {#each steps as [label, done] (label)}<Row icon={done ? CircleCheck : Circle} title={label} />{/each}
      </Group>{/if}
      {#if r.nextText}<p class="t-body nexttx selectable">{r.nextText}</p>{/if}
      {#if sent}
        {#if r.status === 'done' && r.declineText}<p class="t-callout nexttx">{r.declineText}</p>{:else}<p class="t-foot note">{t('cast.botTells')}</p>{/if}
      {/if}
    </div>

    {#if r.mine?.invited}
      <!-- the interview: the time to pick, or mine -->
      {#if r.mine.slot && !picking}
        <Group caption={t('cast.ivTitle')}>
          <Row title="{dayMonth(r.mine.slot.startsAt)}, {time(r.mine.slot.startsAt)}" subtitle={placeOf(r.mine.slot.place)} />
          <Row tone="action" title={t('cast.ivChange')} onclick={() => (picking = true)} />
        </Group>
      {:else}
        <Group caption={t('cast.ivTitle')} footnote={days.length ? t('cast.ivPick') : t('cast.ivNone')}>
          {#each days as [day, list] (day)}
            <!-- engine: ui/Row could hold a wrapping row of Chips under its title (a day's free times) -->
            <div class="kb-row ivday"><span class="dl">{day}</span>
              <div class="chips">{#each list as s (s.id)}<Chip selected={s.mine} onclick={() => take(s)}>{time(s.startsAt)}{s.capacity > 1 ? ' · ' + t('cast.ivLeft', { n: s.left }) : ''}</Chip>{/each}</div></div>
          {/each}
          <Row tone="action" title={t('cast.ivNothing')} onclick={nothingFits} />
          {#if r.mine.slot}<Row tone="action" title={t('cast.ivDrop')} onclick={() => take(null)} />{/if}
        </Group>
      {/if}
    {/if}

    {#if !sent || editing}
    <fieldset disabled={!r.open}>

    {#if r.departments.length > 1}
    <div>
      <Group caption={r.picks > 1 ? t('cast.picksMany', { n: r.picks }) : t('cast.picksOne')}>
        {#each r.departments as d (d.tagId)}
          {@const n = picks.indexOf(d.tagId)}
          <Row title={d.name} subtitle={d.about || undefined} accessory="check" checked={n >= 0} onclick={() => pick(d.tagId)}>
            <!-- the department's colour, and the wish's place when there are several -->
            {#snippet lead()}<span class="mark" class:on={n >= 0} style="--c:{d.color}">{#if n >= 0 && r!.picks > 1}{n + 1}{/if}</span>{/snippet}
          </Row>
        {/each}
      </Group>
      {#if tried && !picks.length}<p class="err">{t('cast.pickOne')}</p>{/if}
    </div>
    {/if}

    {#each shown as q (q.id)}
      {@const label = q.text + (q.required ? '' : ' · ' + t('cast.optional'))}
      {@const error = tried && missing(q) ? t('ed.need') : undefined}
      {#if q.kind === 'one' || q.kind === 'many'}
        <div class="q">
          <span class="lab">{label}</span>
          <div class="opts">
            {#each q.options ?? [] as o (o)}
              {@const on = q.kind === 'one' ? answers[q.id] === o : ((answers[q.id] as string[] | undefined) ?? []).includes(o)}
              <Chip selected={on} onclick={() => { haptic.select(); if (q.kind === 'one') answers[q.id] = o; else toggleMany(q.id, o); }}>{o}</Chip>
            {/each}
          </div>
          {#if error}<p class="err">{error}</p>{/if}
        </div>
      {:else}
        <Field {label} {error} multiline={q.kind === 'long'} rows={4} maxlength={q.kind === 'long' ? 2000 : q.kind === 'link' ? 300 : 200}
          type={q.kind === 'link' ? 'url' : 'text'} inputmode={q.kind === 'link' ? 'url' : 'text'} placeholder={q.kind === 'link' ? 'https://' : ''}
          bind:value={() => String(answers[q.id] ?? ''), (v) => (answers[q.id] = v)} />
      {/if}
    {/each}
    </fieldset>
    {/if}

    {#if sent && r.open && !editing}<Group><Row tone="destructive" title={t('join.withdraw')} onclick={withdraw} /></Group>{/if}
    </div>
  {/if}

  {#snippet footer()}
    {#if r?.open && !sent}
      <p class="t-foot shares">{t('cast.shares')}</p>
      <Button kind="primary" size="l" full loading={busy} onclick={send}>{t('cast.send')}</Button>
    {:else if r?.open && editing}
      <div class="btns">
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
  .shares { margin: 0 var(--s-4) var(--s-2); text-align: center; }
  .body { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-4); }
  fieldset { display: flex; flex-direction: column; gap: var(--gap-group); min-width: 0; margin: 0; padding: 0; border: 0; }
  .note { margin: var(--s-2) var(--s-4) 0; }
  .nexttx { margin: var(--s-3) var(--s-1) 0; white-space: pre-line; overflow-wrap: anywhere; }
  /* a day's free times: a plain row of the group (kb-row draws the line above the next row) */
  .ivday { position: relative; display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); }
  .ivday + .ivday::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .dl { font: 600 var(--fs-body)/1.3 var(--font-text); }
  .chips { display: flex; flex-wrap: wrap; gap: var(--s-2); padding-block: var(--s-1); }
  .mark { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    box-shadow: inset 0 0 0 2px var(--c); font: 700 var(--fs-body)/1 var(--font-text); color: var(--on-accent); }
  .mark.on { background: var(--c); box-shadow: none; }
  .q { display: flex; flex-direction: column; gap: 6px; }
  .lab { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); } /* ui/Field's label */
  .opts { display: flex; flex-wrap: wrap; gap: var(--s-2); padding-block: var(--s-1); }
  /* engine: ui/Chip could wrap a long label (a question's options are sentences sometimes) */
  .opts :global(.fc) { max-width: 100%; height: auto; min-height: var(--ctl-s); padding-block: var(--s-2); white-space: normal; line-height: 1.25; text-align: left; }
  .err { margin-top: 6px; padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--danger-text); }
</style>
