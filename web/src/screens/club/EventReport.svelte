<script lang="ts">
  // A club's report after its own or co-hosted event (server logic/evreports.py, REPORTS): which department ran it, who of the team
  // was there (a mark each), the guests by the club's own count beside what the app knows, a note. For the club's
  // President, Vices and a role given "reports" (HR). The checklist: the department's people (the whole team when
  // none is picked) and anyone marked; the rest of the team is added by hand. A mark answers at once; back if the
  // server says no. Its own consent first (lib/reports.ts): no yes, the sheet closes; a member without theirs is listed,
  // never marked.
  import { onMount } from 'svelte';
  import { api, ApiErr, type EventReport, type Id, type ReportMark, type ReportPerson } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { setReportConsent } from '../../lib/reports';
  import { eventById } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { nameOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import { relDay, time } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import ClipboardCheck from '@lucide/svelte/icons/clipboard-check';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import SearchField from '../../ui/SearchField.svelte';

  // org: the co-host's own report (the host's without it); on a co-hosted event the subtitle names whose it is
  let { overlay, id, org }: { overlay: Overlay; id: Id; org?: Id } = $props();
  const e = $derived(eventById(id));
  const club = $derived(e?.coHost ? (e.coHost.id === org ? e.coHost : e.org) : null);

  let r = $state<EventReport | null>(null);
  // the typed fields stay mine while marks come back from the server; a number input hands back a number (or null), kept as text
  let guests = $state('');
  let note = $state('');
  async function load() {
    if (!session.me?.reports?.consent && !(await setReportConsent(true))) { close(overlay.id); return; }
    try { const x = await api.eventReport(id, org); r = x; guests = x.guests == null ? '' : String(x.guests); note = x.note; }
    catch (err) {
      // the server knows better (taken back on another phone): ask again
      if (err instanceof ApiErr && err.message === 'consent' && session.me?.reports) { session.me.reports.consent = false; void load(); }
      else say(t('common.error'), 'warning_3d');
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

  async function mark(p: ReportPerson, status: ReportMark | null) {
    if (!r) return;
    haptic.tap();
    const was = r;
    r = { ...r, people: r.people.map((x) => (x.person.id === p.person.id ? { ...x, status } : x)) };
    try { r = await api.eventReportMark(id, p.person.id, status, org); }
    catch { r = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  const markMenu = (p: ReportPerson) => [
    ...(p.consent ? MARKS : []).map((s) => ({ label: label(s), checked: p.status === s, onselect: () => { if (p.status !== s) void mark(p, s); } })),
    ...(p.status ? [{ label: t('evr.clear'), destructive: true, onselect: () => void mark(p, null) }] : []),
  ];

  async function setDept(d: Id | null) {
    if (!r || r.dept === d) return;
    haptic.select();
    const was = r;
    r = { ...r, dept: d };
    try { r = await api.eventReportSave(id, { dept: d }, org); }
    catch { r = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
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
    busy = true;
    try { r = await api.eventReportSave(id, { guests: count, note: note.trim() }, org); note = r.note; haptic.ok(); say(t('evr.saved'), 'sparkles_3d'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
  const when = (ts: number) => `${relDay(ts)}, ${time(ts)}`;
  const byline = $derived(!r?.filledAt ? '' : [
    r.filledBy && t('evr.filled', { who: r.filledBy.name, when: when(r.filledAt) }),
    r.editedAt && r.editedAt !== r.filledAt && r.editedBy && t('evr.edited', { who: r.editedBy.name, when: when(r.editedAt) }),
  ].filter(Boolean).join('\n'));
</script>

<Sheet {overlay} icon={ClipboardCheck} full title={t('evr.title')}>
  {#if e}<p class="t-foot sub">{e.title}{club ? ` · ${nameOf(club)}` : ''}</p>{/if}
  {#if r}
    <div class="pg">
      {#if r.depts.length}
        <Group><Row title={t('evr.dept')} value={deptOf?.name ?? t('evr.deptNone')} menu={deptMenu} /></Group>
      {/if}

      <Group caption={t('evr.team')}>
        {#each list as p (p.person.id)}
          <Row dense title={p.fullName} subtitle={p.team ? undefined : t('evr.left')} value={p.status ? label(p.status) : p.consent ? t('evr.mark') : t('evr.noConsent')}
            menu={p.consent || p.status ? markMenu(p) : undefined}>
            {#snippet lead()}<Avatar person={p.person} size={30} tappable={false} />{/snippet}
          </Row>
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
</style>
