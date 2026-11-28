<script lang="ts">
  import { akoTeam } from '../../lib/api/akoTeam';
  // Studio → admissions (AKO): one applicant's package. Who it is and where the application stands, the contacts, the
  // interview (managers move or cancel it), every document of the program page by page, the team's note. One main
  // action by status in the footer; the rest in the ⋯. A reviewer reads the same sheet with nothing to press.
  import { onMount } from 'svelte';
  import { type Id, type AkoDesk, type AkoDoc, type AkoFile, type AkoPackage, type AkoSlot, type AkoStatus } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { i18n, t } from '../../lib/i18n/index.svelte';
  import { aw } from '../../lib/i18n/ako';
  import { dateInput, dayMonth, nowTs, time, weekday, whenLine } from '../../lib/time';
  import { downloadFile, haptic, openLink } from '../../lib/tg';
  import { menu, type MenuItem } from '../../ui/menu';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Notice from '../../ui/Notice.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import CalendarClock from '@lucide/svelte/icons/calendar-clock';
  import CalendarX from '@lucide/svelte/icons/calendar-x';
  import Download from '@lucide/svelte/icons/download';
  import Copy from '@lucide/svelte/icons/copy';
  import Link from '@lucide/svelte/icons/link';
  import Undo2 from '@lucide/svelte/icons/undo-2';
  import Trash2 from '@lucide/svelte/icons/trash-2';

  let { overlay, org, id, desk, onchange }: { overlay: Overlay; org: Id; id: Id; desk: AkoDesk; onchange?: () => void } = $props();

  let pkg = $state<AkoPackage | null>(null);
  let failed = $state(false);
  let sending = $state(false);              // a change is on its way: the footer waits (the next status's button appears under the same finger)
  let busy = $state<Id | 'zip' | null>(null); // the file being fetched
  let mode = $state<'move' | 'cancel' | null>(null);
  let reason = $state('');
  let noteText = $state('');
  let link = $state('');                    // a new link, shown once
  const manage = $derived(desk.manage);
  const now = nowTs();

  const row = $derived(desk.apps.find((a) => a.id === id));
  const name = $derived(pkg?.name || row?.name || pkg?.phone || row?.phone || '');
  const program = $derived(desk.programs.find((p) => p.key === (pkg?.program ?? row?.program)));
  const info = $derived(program?.info[i18n.lang]);
  const docs = $derived<AkoDoc[]>(program ? [...program.first, ...program.later, ...program.optional] : [...new Set((pkg?.files ?? []).map((f) => f.doc))]);
  const pages = (d: AkoDoc) => (pkg?.files ?? []).filter((f) => f.doc === d).sort((a, b) => a.at - b.at);
  const digits = (s: string) => s.replace(/\D/g, '');
  const fail = () => { haptic.error(); say(t('common.error'), 'warning_3d'); };

  async function load() {
    failed = false;
    try { const p = await akoTeam.akoPackage(org, id), first = !pkg; pkg = p; if (first) noteText = p.note; }
    catch { if (!pkg) failed = true; say(t('common.error'), 'warning_3d'); }
  }
  onMount(() => { void load(); });

  // ---- status ----
  async function setStatus(s: AkoStatus) {
    if (!pkg || sending) return;
    if (s === 'declined' && !(await sheets.ask({ title: aw('akd.declineAsk'), text: aw('akd.declineLead'), ok: aw('akd.decline'), cancel: t('common.cancel'), danger: true }))) return;
    const was = pkg.status;
    pkg.status = s; sending = true;
    try { await akoTeam.akoUpdate(org, id, { status: s }); haptic.ok(); onchange?.(); }
    catch { pkg.status = was; fail(); }
    finally { sending = false; }
  }

  // ---- the interview ----
  const dayTitle = (ts: number) => { const wd = weekday(ts); return `${wd.charAt(0).toUpperCase()}${wd.slice(1)}, ${dayMonth(ts)}`; };
  const free = $derived.by(() => {
    const out: { key: string; title: string; slots: AkoSlot[] }[] = [];
    for (const s of [...desk.slots].sort((a, b) => a.at - b.at)) {
      if (s.at <= now || s.apps.length >= s.cap || s.id === pkg?.slot?.id) continue;
      const key = dateInput(s.at);
      let d = out.at(-1);
      if (!d || d.key !== key) out.push((d = { key, title: dayTitle(s.at), slots: [] }));
      d.slots.push(s);
    }
    return out;
  });
  const slotMenu = $derived<MenuItem[]>([
    { label: aw('akd.move'), icon: CalendarClock, onselect: () => { mode = 'move'; } },
    { label: aw('akd.cancelSlot'), icon: CalendarX, destructive: true, onselect: () => { reason = ''; mode = 'cancel'; } },
  ]);
  async function setSlot(s: AkoSlot | null, why = '') {
    if (!pkg || sending) return;
    const was = $state.snapshot(pkg) as AkoPackage;
    pkg.slot = s ? { id: s.id, at: s.at, minutes: s.minutes, who: s.who } : null;
    pkg.teams = s ? (s.teams ?? desk.days[dateInput(s.at)] ?? null) : null;
    pkg.rebook = s ? null : why;
    mode = null; sending = true;
    try { await akoTeam.akoUpdate(org, id, s ? { slot: s.id } : { slot: null, reason: why }); haptic.ok(); onchange?.(); void load(); }
    catch { pkg = was; fail(); onchange?.(); } // most likely the time was just taken: the desk's truth again
    finally { sending = false; }
  }
  async function cancelSlot() {
    const why = reason.trim();
    if (!(await sheets.ask({ title: aw('akd.cancelAsk'), text: aw('akd.cancelLead'), ok: aw('akd.cancelSlot'), cancel: t('common.cancel'), danger: true }))) return;
    void setSlot(null, why);
  }
  function reveal(node: HTMLElement) {
    node.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }

  // ---- documents ----
  const pageLabel = (f: AkoFile, i: number, all: number) => (all > 1 ? String(i + 1) : f.mime === 'application/pdf' ? aw('ako.pdf') : aw('ako.photoPage'));
  const safe = (s: string) => s.replace(/[\\/:*?"<>|]+/g, ' ').trim();
  async function getFile(f: AkoFile, i: number, all: number) {
    if (busy) return;
    busy = f.id;
    try {
      const { url } = await akoTeam.akoFileLink(org, f.id);
      downloadFile(location.origin + url, safe(`${name} ${aw(`ako.doc.${f.doc}`)}${all > 1 ? ` ${i + 1}` : ''}`) + (f.mime === 'application/pdf' ? '.pdf' : '.jpg'));
    } catch { fail(); }
    finally { busy = null; }
  }
  async function getZip() {
    if (busy) return;
    busy = 'zip';
    try { const { url } = await akoTeam.akoZipLink(org, id); downloadFile(location.origin + url, safe(name) + '.zip'); }
    catch { fail(); }
    finally { busy = null; }
  }

  // ---- the note: saved as the field is left ----
  async function saveNote() {
    const text = noteText.trim();
    if (!pkg || text === pkg.note) return;
    const was = pkg.note;
    pkg.note = text;
    try { await akoTeam.akoUpdate(org, id, { note: text }); say(aw('akd.saved')); }
    catch { pkg.note = was; fail(); } // the typed text stays in the field: leaving it again retries
  }

  // ---- ⋯ ----
  async function newLink() {
    if (!(await sheets.ask({ title: aw('akd.newLink'), text: aw('akd.newLinkAsk'), ok: aw('akd.make'), cancel: t('common.cancel') }))) return;
    try {
      const { token } = await akoTeam.akoUpdate(org, id, { newLink: true });
      if (!token) throw new Error('no token');
      link = `${location.origin}/ako#${token}`; haptic.ok();
    } catch { fail(); }
  }
  async function remove() {
    if (!(await sheets.ask({ title: aw('akd.delete'), text: aw('akd.deleteAsk'), ok: aw('akd.delete'), cancel: t('common.cancel'), danger: true }))) return;
    try { await akoTeam.akoDrop(org, id); haptic.ok(); onchange?.(); close(overlay.id); }
    catch { fail(); }
  }
  const more = (e: MouseEvent) => menu(e.currentTarget as Element, [
    ...(pkg?.status === 'accepted' || pkg?.status === 'declined' ? [{ label: aw('akd.undo'), icon: Undo2, onselect: () => void setStatus('sent') }] : []),
    { label: aw('akd.newLink'), icon: Link, onselect: () => void newLink() },
    { label: aw('akd.delete'), icon: Trash2, destructive: true, onselect: () => void remove() },
  ], 'end');

  const sendWa = () => pkg && openLink(`https://wa.me/${digits(pkg.phone)}?text=${encodeURIComponent(aw('akd.waText', { name, program: info?.title ?? '', link }))}`);
  async function copyText(text: string) {
    try { await navigator.clipboard.writeText(text); haptic.ok(); say(aw('akd.copied')); }
    catch { fail(); }
  }
  const copy = () => copyText(link);
</script>

<Sheet {overlay} tall heading={link ? aw('akd.linkReady') : name}>
  {#snippet actions()}
    {#if manage && pkg && !link}
      <Button kind="secondary" size="s" round label={aw('akd.more')} onclick={more}>{#snippet icon()}<Ellipsis size={18} />{/snippet}</Button>
    {/if}
  {/snippet}

  {#if link}
    <div class="pack">
      <p class="sub">{[name, info?.title].filter(Boolean).join(' · ')}</p>
      <p class="link selectable">{link}</p>
      <p class="quiet">{aw('akd.linkOnce')}</p>
    </div>
  {:else}
    <div class="top">
      {#if info}<p class="sub">{[info.title, info.sub].filter(Boolean).join(' · ')}</p>{/if}
      {#if pkg ?? row}{@const st = (pkg ?? row)!.status}<span class="chip {st}">{aw(`akd.status.${st}`)}</span>{/if}
    </div>

    {#if !pkg}
      {#if failed}<EmptyState onretry={load} />{:else}<Skeleton kind="rows" n={6} />{/if}
    {:else}
      <div class="pack">
        {#if pkg.rebook != null && !pkg.slot}<Notice tone="warning" title={aw('akd.rebook')} text={pkg.rebook || undefined} />{/if}

        <Group caption={aw('akd.contacts')}>
          {#if digits(pkg.phone)}
            <Row icon={MessageCircle} title={aw('akd.whatsapp')} subtitle={pkg.phone} accessory="external" onclick={() => openLink('https://wa.me/' + digits(pkg!.phone))} />
          {/if}
          {#if pkg.email}
            <Row dense title={aw('akd.email')}>{#snippet detail()}<span class="val selectable">{pkg!.email}</span>{/snippet}</Row>
          {/if}
        </Group>

        {#if program?.interview || pkg.slot}
          <div class="block">
            <Group caption={aw('ako.step.slot')}>
              {#if pkg.slot}
                <Row dense title={whenLine(pkg.slot.at)} subtitle={[pkg.slot.who, aw('akd.minN', { n: pkg.slot.minutes })].filter(Boolean).join(' · ')}
                  menu={manage ? slotMenu : undefined} disabled={sending} />
                {#if pkg.teams}
                  <Row dense title={aw('akd.teamsRow')} subtitle={pkg.teams.replace(/^https?:\/\//, '')} onclick={() => void copyText(pkg!.teams!)}>
                    {#snippet detail()}<span class="cp"><Copy size={18} /></span>{/snippet}
                  </Row>
                {/if}
              {:else if manage}
                <Row dense tone="action" title={aw('akd.book')} disabled={sending} onclick={() => { mode = mode === 'move' ? null : 'move'; }} />
              {:else}
                <Row dense title={aw('akd.noSlot')} />
              {/if}
            </Group>
            {#if pkg.slot && !pkg.teams}<Notice tone="warning" text={aw('akd.teamsNone')} />{/if}

            {#if mode === 'move'}
              <div class="ed" use:reveal>
                {#each free as d (d.key)}
                  <p class="cap">{d.title}</p>
                  <div class="chips">
                    {#each d.slots as s (s.id)}
                      <button class="pick num" onclick={() => { haptic.select(); void setSlot(s); }}>{time(s.at)}</button>
                    {/each}
                  </div>
                {:else}
                  <p class="quiet">{aw('akd.noFree')}</p>
                {/each}
                <Button kind="secondary" full onclick={() => (mode = null)}>{t('common.cancel')}</Button>
              </div>
            {:else if mode === 'cancel'}
              <div class="ed" use:reveal>
                <Field label={aw('akd.reason')} bind:value={reason} multiline rows={2} maxlength={300} />
                <div class="acts btns">
                  <Button kind="secondary" full onclick={() => (mode = null)}>{t('common.cancel')}</Button>
                  <Button kind="destructive" full onclick={cancelSlot}>{aw('akd.cancelSlot')}</Button>
                </div>
              </div>
            {/if}
          </div>
        {/if}

        <Group caption={aw('akd.docs')} note={pkg.missing.length ? undefined : aw('akd.complete')}>
          {#snippet aside()}
            {#if pkg!.files.length}
              <span class="zip"><Button kind="plain" size="s" loading={busy === 'zip'} onclick={getZip}>{#snippet icon()}<Download size={16} />{/snippet}{aw('akd.download')}</Button></span>
            {/if}
          {/snippet}
          {#each docs as d (d)}
            {@const fs = pages(d)}
            <Row dense whole title={aw(`ako.doc.${d}`)} value={fs.length ? undefined : aw('akd.noFile')}>
              {#snippet detail()}
                {#if fs.length}
                  <span class="pages">
                    {#each fs as f, i (f.id)}
                      <button class="page num" class:wait={busy === f.id} aria-label="{aw(`ako.doc.${d}`)}, {i + 1}" onclick={() => { haptic.tap(); void getFile(f, i, fs.length); }}>{pageLabel(f, i, fs.length)}</button>
                    {/each}
                  </span>
                {/if}
              {/snippet}
            </Row>
          {/each}
        </Group>

        {#if manage}
          <div onfocusout={saveNote}>
            <Field label={aw('akd.note')} bind:value={noteText} placeholder={aw('akd.notePh')} multiline rows={2} maxlength={2000} />
          </div>
        {:else if pkg.note}
          <div class="note"><p class="cap">{aw('akd.note')}</p><p class="nt">{pkg.note}</p></div>
        {/if}

        <p class="quiet">{pkg.by ? aw('akd.madeBy', { name: pkg.by.name }) : aw('akd.fromSite')}{manage ? '' : ` · ${aw('akd.reviewOnly')}`}</p>
      </div>
    {/if}
  {/if}

  {#snippet footer()}
    {#if link}
      <div class="col">
        <Button size="l" full lit onclick={sendWa}>{aw('akd.sendWa')}</Button>
        <Button kind="secondary" size="l" full onclick={copy}>{aw('akd.copy')}</Button>
      </div>
    {:else if manage && pkg?.status === 'sent'}
      <Button size="l" full lit disabled={sending} onclick={() => setStatus('review')}>{aw('akd.pass')}</Button>
    {:else if manage && pkg?.status === 'review'}
      <div class="acts btns">
        <Button kind="destructive" size="l" full disabled={sending} onclick={() => setStatus('declined')}>{aw('akd.decline')}</Button>
        <Button size="l" full lit disabled={sending} onclick={() => setStatus('accepted')}>{aw('akd.accept')}</Button>
      </div>
    {/if}
  {/snippet}
</Sheet>

<style>
  /* the header block: program · sub, then the status (the desk's chip) */
  .top { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); margin: calc(-1 * var(--s-2)) 2px var(--s-4); }
  .sub { color: var(--text-3); font: 450 var(--fs-body)/1.35 var(--font-text); overflow-wrap: break-word; }
  .chip { display: inline-flex; align-items: center; padding: var(--s-1) var(--s-2); border-radius: var(--r-full); background: var(--fill); color: var(--text-2);
    font: 600 var(--fs-cap)/1.2 var(--font-text); white-space: nowrap; }
  .chip.sent { background: var(--accent-soft); color: var(--accent-text); }
  .chip.accepted { background: var(--success-soft); color: var(--success-text); }
  .chip.declined { background: var(--danger-soft); color: var(--danger-text); }
  .chip.draft { padding-inline: 0; background: none; color: var(--text-3); font-weight: 500; }

  .pack { display: flex; flex-direction: column; gap: var(--gap-group); animation: pack-in var(--t-base) var(--ease) both; }
  @keyframes pack-in { from { opacity: 0; transform: translateY(6px); } }
  .block, .ed { display: flex; flex-direction: column; gap: var(--s-3); }
  .ed { animation: pack-in var(--t-base) var(--ease) both; }
  @media (prefers-reduced-motion: reduce) { .pack, .ed { animation: none; } }
  .num { font-variant-numeric: tabular-nums; }
  .block :global(.tt) { font-variant-numeric: tabular-nums; }
  /* the Teams link: one line, cut at its end; a tap copies it whole */
  .block :global(.st) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cp { display: inline-flex; color: var(--text-3); }

  .val { max-width: 58vw; margin-left: auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-3); font: 450 var(--fs-body)/1.3 var(--font-text); }
  .cap { margin: 0 var(--s-4); color: var(--text-3); font: 450 var(--fs-sub)/1.2 var(--font-text); }
  .quiet { margin: 0 var(--s-4); color: var(--text-3); font: 450 var(--fs-sub)/1.4 var(--font-text); }

  /* free times to pick: one tap moves the interview */
  .chips { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .pick { height: var(--ctl-s); padding: 0 var(--s-4); border-radius: var(--r-full); background: var(--fill); color: var(--text); font: 600 var(--fs-sub)/1 var(--font-text);
    transition: background-color var(--t-fast); }
  .pick:active { background: var(--accent-soft); color: var(--accent-text); transform: none; }

  /* a document's pages: each one downloads */
  .zip { margin-left: auto; }
  .pages { display: inline-flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--s-1); max-width: 52vw; }
  .page { position: relative; min-width: var(--ctl-s); height: var(--ctl-s); padding: 0 var(--s-3); border-radius: var(--r-full); background: var(--fill); color: var(--accent-text);
    font: 600 var(--fs-sub)/1 var(--font-text); transition: opacity var(--t-fast); }
  .page::after { content: ''; position: absolute; inset: -4px 0; } /* 44 to the finger */
  .page:active, .page.wait { opacity: 0.5; transform: none; }

  .note { display: flex; flex-direction: column; gap: var(--s-2); }
  .nt { margin: 0 var(--s-4); color: var(--text); font: 450 var(--fs-body)/1.4 var(--font-text); white-space: pre-wrap; overflow-wrap: break-word; }

  /* the link moment */
  .link { padding: var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text); font: 500 var(--fs-row)/1.35 var(--font-text); overflow-wrap: anywhere; }
  .pack > .sub { margin: calc(-1 * var(--s-2)) 2px 0; }
  .pack > .link + .quiet { margin-top: calc(var(--s-3) - var(--gap-group)); }

  .acts { display: flex; gap: var(--s-2); }
  .col { display: flex; flex-direction: column; gap: var(--s-2); }
</style>
