<script lang="ts">
  // A club's report after its own or co-hosted event (server logic/evreports.py, REPORTS): which department ran it, who of the team
  // was there (a mark each), the guests by the club's own count beside what the app knows, a note. For the club's
  // President, Vices and a role given "reports" (HR). The checklist: the department's people (the whole team when
  // none is picked) and anyone marked; the rest of the team is added by hand. A mark answers at once; back if the
  // server says no. Its own consent first (lib/reports.ts): no yes, the sheet closes; a member without theirs is listed,
  // never marked.
  import { onMount } from 'svelte';
  import { api, ApiErr, type EventReport, type Id, type ReportMark, type ReportMarkPatch, type ReportPerson } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { withReportConsent } from '../../lib/reports';
  import { eventById } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { nameOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import { relDay, time } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import ClipboardCheck from '@lucide/svelte/icons/clipboard-check';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import { menu } from '../../ui/menu';

  // org: the co-host's own report (the host's without it); on a co-hosted event the subtitle names whose it is
  let { overlay, id, org }: { overlay: Overlay; id: Id; org?: Id } = $props();
  const e = $derived(eventById(id));
  const club = $derived(e?.coHost ? (e.coHost.id === org ? e.coHost : e.org) : null);

  let saved = $state<EventReport | null>(null);
  type Apply = (report: EventReport) => EventReport;
  let pending = $state<Apply[]>([]);
  const r = $derived(saved && pending.reduce((report, apply) => apply(report), saved));
  let serial = Promise.resolve();
  // Keep newer taps visible while previous writes settle, including if one of those writes fails.
  function change(apply: Apply, send: () => Promise<EventReport>): Promise<boolean> {
    pending = [...pending, apply];
    const result = serial.then(async () => {
      try {
        if (!saved) return false;
        saved = await send();
        return true;
      } catch (err) {
        if (err instanceof ApiErr && (err.code === 'forbidden' || err.message === 'not_started')) {
          saved = null;
          drafts = {};
          close(overlay.id);
        }
        haptic.error(); say(t('common.error'), 'warning_3d');
        return false;
      } finally {
        pending = pending.slice(1);
      }
    });
    serial = result.then(() => {});
    return result;
  }
  // the typed fields stay mine while marks come back from the server; a number input hands back a number (or null), kept as text
  let guests = $state('');
  let note = $state('');
  async function load() {
    try {
      const x = await withReportConsent(() => api.eventReport(id, org));
      if (!x) { close(overlay.id); return; }
      saved = x; guests = x.guests == null ? '' : String(x.guests); note = x.note;
    } catch {
      say(t('common.error'), 'warning_3d');
      close(overlay.id);
    }
  }
  onMount(() => void load());

  const MARKS: ReportMark[] = ['present', 'late', 'absent', 'excused'];
  const label = (s: ReportMark) => t(`evr.${s}`);
  const deptOf = $derived(r?.depts.find((d) => d.id === r?.dept) ?? null);
  const listed = (p: ReportPerson) => !!p.status || (p.team && (r?.dept == null || p.depts.includes(r.dept)));
  const list = $derived((r?.people ?? []).filter(listed));
  let adding = $state(false);
  let q = $state('');
  const rest = $derived.by(() => {
    const l = (r?.people ?? []).filter((p) => p.team && !listed(p));
    return q.trim() ? l.filter((p) => hit(q, [p.fullName, p.person.name])) : l;
  });

  let drafts = $state<Record<Id, string>>({});
  function patchPerson(person: Id, patch: ReportMarkPatch) {
    return change((report) => ({
      ...report, people: report.people.map((p) => p.person.id === person
        ? { ...p, ...patch, comment: patch.status === null ? '' : patch.comment ?? p.comment }
        : p),
    }), () => api.eventReportMark(id, person, patch, org));
  }

  async function mark(p: ReportPerson, status: ReportMark | null) {
    haptic.tap();
    const uid = p.person.id;
    const draft = drafts[uid];
    if (await patchPerson(uid, { status }) && status === null && drafts[uid] === draft) delete drafts[uid];
  }
  const markMenu = (p: ReportPerson) => [
    ...(p.team && p.consent ? MARKS : []).map((s) => ({ label: label(s), checked: p.status === s, onselect: () => { if (p.status !== s) void mark(p, s); } })),
    ...(p.status ? [{ label: t('evr.clear'), destructive: true, onselect: () => void mark(p, null) }] : []),
  ];

  async function saveComment(p: ReportPerson) {
    const uid = p.person.id;
    const draft = drafts[uid];
    if (draft == null || draft.trim() === p.comment) return;
    haptic.tap();
    if (await patchPerson(uid, { comment: draft.trim() }) && drafts[uid] === draft) delete drafts[uid];
  }

  function editComment(uid: Id, field: HTMLTextAreaElement) {
    const chars = Array.from(field.value);
    if (chars.length > 300) field.value = chars.slice(0, 300).join('');
    drafts[uid] = field.value;
  }

  function setDept(d: Id | null) {
    if (!r || r.dept === d) return;
    haptic.select();
    void change((report) => ({ ...report, dept: d }), () => api.eventReportSave(id, { dept: d }, org));
  }
  const deptMenu = $derived([
    ...(r?.depts ?? []).map((d) => ({ label: d.name, checked: r?.dept === d.id, onselect: () => void setDept(d.id) })),
    { label: t('evr.deptNone'), checked: r?.dept == null, onselect: () => void setDept(null) },
  ]);

  const count = $derived(guests.trim() === '' ? null : Number(guests));
  const bad = $derived(count != null && !(Number.isInteger(count) && count >= 0 && count <= 100000));
  const dirty = $derived(!!r && (count !== r.guests || note.trim() !== r.note));
  let busy = $state(false);
  async function save() {
    if (!r || bad || busy) return;
    const patch = { guests: count, note: note.trim() };
    busy = true;
    if (await change((report) => ({ ...report, ...patch }), () => api.eventReportSave(id, patch, org))) {
      haptic.ok(); say(t('evr.saved'), 'sparkles_3d');
    }
    busy = false;
  }
  const when = (ts: number) => `${relDay(ts)}, ${time(ts)}`;
  const byline = $derived(!r?.filledAt ? '' : [
    r.filledBy && t('evr.filled', { who: r.filledBy.name, when: when(r.filledAt) }),
    r.editedAt && r.editedAt !== r.filledAt && r.editedBy && t('evr.edited', { who: r.editedBy.name, when: when(r.editedAt) }),
  ].filter(Boolean).join('\n'));
</script>

<Sheet {overlay} icon={ClipboardCheck} full title={t('evr.title')}>
  {#if e}<p class="t-foot sub">{e.title} · {relDay(e.startsAt)}{club ? ` · ${nameOf(club)}` : ''}</p>{/if}
  {#if r}
    <div class="pg">
      {#if r.depts.length}
        <Group><Row title={t('evr.dept')} value={deptOf?.name ?? t('evr.deptNone')} menu={deptMenu} /></Group>
      {/if}

      <Group caption={t('evr.team')} footnote={list.some((p) => p.team && p.consent) ? t('evr.tapPresent') : undefined}>
        {#each list as p (p.person.id)}
          <div class="member">
            <div class={['member-mark', { present: p.status === 'present' }]}>
              <div class="member-name">
                <Row title={p.fullName} subtitle={p.team ? undefined : t('evr.left')}
                  value={p.status ? (p.status === 'present' ? `+1 · ${label(p.status)}` : label(p.status)) : p.consent ? '+1' : t('evr.noConsent')}
                  onclick={p.team && p.consent ? () => mark(p, p.status === 'present' ? null : 'present') : undefined}>
                  {#snippet lead()}<Avatar person={p.person} size={30} tappable={false} />{/snippet}
                </Row>
              </div>
              {#if p.team && p.consent || p.status}
                <button type="button" class="options" aria-haspopup="menu" aria-label={t('evr.markFor', { who: p.fullName })}
                  onclick={(event) => menu(event.currentTarget, markMenu(p), 'end')}><Ellipsis size={20} /></button>
              {/if}
            </div>
            {#if p.team && p.status && p.consent}
              <div class="comment">
                <textarea rows="2" aria-label={t('evr.commentFor', { who: p.fullName })} placeholder={t('evr.commentPh')}
                  value={drafts[p.person.id] ?? p.comment} oninput={(event) => editComment(p.person.id, event.currentTarget)}></textarea>
                {#if drafts[p.person.id] != null && drafts[p.person.id].trim() !== p.comment}
                  <Button kind="tinted" size="s" onclick={() => saveComment(p)}>{t('common.save')}</Button>
                {/if}
              </div>
            {:else if p.comment}
              <p class="comment comment-text t-foot">{p.comment}</p>
            {/if}
          </div>
        {:else}
          <Row dense title={t('evr.nobody')} />
        {/each}
        {#if r.people.some((p) => p.team && !listed(p))}
          <Row tone="add" title={t('evr.add')} accessory="disclosure" open={adding} onclick={() => { haptic.select(); adding = !adding; }} />
        {/if}
      </Group>
      {#if adding}
        {#if r.people.length > 8}<SearchField bind:value={q} placeholder={t('evr.find')} />{/if}
        <Group>
          {#each rest as p (p.person.id)}
            {#snippet add()}<Button kind="tinted" size="s" onclick={() => mark(p, 'present')}>{label('present')}</Button>{/snippet}
            <Row dense title={p.fullName} trailing={p.consent ? add : undefined} value={p.consent ? undefined : t('evr.noConsent')}>
              {#snippet lead()}<Avatar person={p.person} size={30} tappable={false} />{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}

      <Group caption={t('evr.guests')}>
        <Row title={t('evr.signed')} value={String(r.signed)} />
        <Row title={t('evr.scanned')} value={String(r.came)} />
      </Group>
      <div class="form">
        <Field label={t('evr.counted')} type="number" inputmode="numeric"
          bind:value={() => guests, (v) => (guests = v == null ? '' : String(v))} error={bad ? t('common.error') : undefined} />
        <Field label={t('evr.note')} placeholder={t('evr.notePh')} multiline rows={3} maxlength={1000} bind:value={note} />
        <div class="fa"><Button kind="primary" size="s" loading={busy} disabled={!dirty || bad} onclick={save}>{t('common.save')}</Button></div>
        {#if byline}<p class="t-foot by">{byline}</p>{/if}
      </div>
    </div>
  {/if}
</Sheet>

<style>
  .sub { margin: 2px var(--s-1) 0; }
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-4); }
  .form { display: flex; flex-direction: column; gap: var(--s-3); }
  .fa { display: flex; gap: var(--s-2); }
  .by { margin: 0 var(--s-1); white-space: pre-line; }
  .member + .member { border-top: 0.5px solid var(--separator); }
  .member-mark { display: flex; align-items: stretch; }
  .member-name { flex: 1; min-width: 0; }
  .present .member-name :global(.val) { color: var(--accent); }
  .options { display: grid; width: 44px; flex: none; min-height: 44px; place-items: center; color: var(--text-2); }
  .comment { display: flex; align-items: center; gap: var(--s-2); padding: 0 var(--s-3) var(--s-3); }
  .comment-text { display: block; white-space: pre-wrap; overflow-wrap: anywhere; }
  .comment textarea { flex: 1; width: 100%; min-width: 0; resize: none; padding: var(--s-2) var(--s-3); border-radius: var(--r-m);
    background: var(--fill); color: var(--text); font: 450 var(--fs-row)/1.35 var(--font-text); }
  .comment textarea::placeholder { color: var(--text-3); }
  .comment textarea:focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
</style>
