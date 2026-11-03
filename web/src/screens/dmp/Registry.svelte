<script lang="ts">
  // DMP's clubs registry (SPEC §4.13): every club with its live numbers for this month and its President — instead of
  // asking in chats who leads what and instead of monthly reports. A club opens its roster; a name or a student ID finds a
  // member and their clubs; CSV sends every roster into my chat with the bot. A sheet, from Studio (DMP) and the Admin panel.
  import FileDown from '@lucide/svelte/icons/file-down';
  import OfficialMark from '../../ui/OfficialMark.svelte';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import { api, ApiErr, type RegistryHit, type RegistryOrg, type SentMemo } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { monthName, nowTs, relDay, time } from '../../lib/time';
  import { ROLE_NAME, withNick } from '../../lib/perms';
  import { haptic } from '../../lib/tg';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import { data, loadRegistry } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { nameOf, schoolShort, shortOf } from '../../lib/short';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';

  let { inSheet = false }: { inSheet?: boolean } = $props();
  // the month: this one (loaded with the app, so the page opens full), or up to a year back (the numbers DMP used to
  // collect as monthly reports)
  let back = $state(0);
  let past = $state<RegistryOrg[] | null>(null);
  const orgs = $derived(back === 0 ? data.registry : past);
  $effect(() => {
    const b = back;
    untrack(() => {
      if (b === 0) { void loadRegistry().then((ok) => { if (!ok) { data.registry ??= []; say(t('common.error'), 'warning_3d'); } }); return; }
      past = null;
      api.registry(b).then((l) => { if (b === back) past = l; }).catch(() => { past = []; say(t('common.error'), 'warning_3d'); });
    });
  });
  const monthTs = $derived.by(() => { const d = new Date((nowTs() + 5 * 3600) * 1000); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - back, 15) / 1000; });
  const people = $derived((orgs ?? []).reduce((s, o) => s + o.members, 0));

  // the memos clubs marked sent this week (DMP sees them in the app, not only in its mailbox)
  let memos = $state<SentMemo[]>([]);
  $effect(() => { api.registryMemos().then((l) => (memos = l)).catch(() => {}); });

  let q = $state('');
  let hits = $state<RegistryHit[] | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const s = q.trim();
    clearTimeout(timer);
    if (s.length < 2) { hits = null; return; }
    timer = setTimeout(() => { api.registrySearch(s).then((l) => { if (q.trim() === s) hits = l; }).catch(() => {}); }, 250);
  });

  let sending = $state(false);
  async function exportCsv() {
    sending = true; haptic.tap();
    try { await api.registryExport(); haptic.ok(); say(t('reg.sent'), 'sparkles_3d'); }
    catch (e) { haptic.error(); say(e instanceof ApiErr && e.message === 'no_dm' ? t('att.noDm') : t('common.error'), 'warning_3d'); }
    finally { sending = false; }
  }
</script>

<div class="pg" class:page={!inSheet} class:scroll={!inSheet}>
  <header class="hd">
    <span><h1 class="t-h1">{t('reg.title')}</h1><p class="t-foot">{orgs ? `${tn('reg.clubs', orgs.length)} · ${tn('reg.people', people)}` : ' '}</p></span>
    <Button kind="tinted" size="s" loading={sending} onclick={exportCsv}>{#snippet icon()}<FileDown size={17} />{/snippet}CSV</Button>
  </header>

  <SearchField bind:value={q} placeholder={t('reg.find')} />

  {#if hits}
    <Group>
      {#each hits as h (h.person.id)}
        <Row dense title={withNick(h.fullName, h.person)} subtitle={[h.studentId, h.course && t('person.year', { n: h.course }), h.school && schoolShort(h.school)].filter(Boolean).join(' · ')}>
          {#snippet lead()}<Avatar person={h.person} size={36} />{/snippet}
        </Row>
        {#each h.clubs as c (c.org.id)}
          <Row dense title="{shortOf(c.org)} · {ROLE_NAME[c.role]}" accessory="chevron" onclick={() => sheets.roster(c.org)}>
            {#snippet lead()}<span class="in"><OrgLogo org={c.org} size={24} /></span>{/snippet}
          </Row>
        {/each}
      {:else}<EmptyState inline text={t('reg.nobody')} />{/each}
    </Group>
  {:else if orgs}
    {#if back === 0 && memos.length}
      <Group caption={t('reg.memos')} footnote={t('reg.memoNote')}>
        {#each memos as m (`${m.org.id}:${m.sentAt}`)}
          <Row dense title={nameOf(m.org)} subtitle={t('reg.memoSent', { who: m.by ?? '—', when: `${relDay(m.sentAt)} ${time(m.sentAt)}` })}>
            {#snippet lead()}<OrgLogo org={m.org} size={36} />{/snippet}
          </Row>
          {#each m.events as e (e.id)}<Row dense title={e.title} value={relDay(e.startsAt)} accessory="chevron" onclick={() => sheets.event(e.id)} />{/each}
        {/each}
      </Group>
    {/if}
    <section class="mo">
      <div class="mh">
        <IconButton icon={ChevronLeft} label="‹" kind="plain" size="s" disabled={back >= 12} onclick={() => back++} />
        <h3 class="cap">{t('reg.month', { month: monthName(monthTs) })}</h3>
        <IconButton icon={ChevronRight} label="›" kind="plain" size="s" disabled={back <= 0} onclick={() => back--} />
      </div>
      <Group>
        {#each orgs as o (o.org.id)}
          <Row dense title={nameOf(o.org)} accessory="chevron" onclick={() => sheets.roster(o.org, (on) => (o.org = { ...o.org, official: on }))}
            subtitle={[o.president ? t('reg.president', { name: o.president.fullName }) : t('reg.noPresident'), `${o.members} ${tn('reg.members', o.members)}`,
              `${o.month.events} ${tn('reg.events', o.month.events)}`, `${o.month.registrations} ${tn('reg.regs', o.month.registrations)}`, `${o.month.came} ${tn('reg.came', o.month.came)}`].join(' · ')}>
            {#snippet lead()}<OrgLogo org={o.org} size={40} />{/snippet}
            <!-- engine: Row's mark after the title (the official ✓); here it stands at the row's end -->
            {#snippet detail()}{#if o.org.official}<span class="ok"><OfficialMark size={15} /></span>{/if}{/snippet}
          </Row>
        {/each}
      </Group>
    </section>
  {:else}
    <Skeleton n={3} />
  {/if}
  {#if !inSheet}<div class="tail"></div>{/if}
</div>

<style>
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); }
  /* as a page of DMP's tab (the sheet brings its own): under the capsule, the bottom nav's room at the end */
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; background: var(--glow), var(--bg); }
  .tail { flex: none; height: calc(var(--bottom) + 24px); }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--s-3); margin-bottom: calc(var(--s-3) - var(--gap-group)); }
  .hd p { margin-top: var(--s-1); }
  .mo { display: flex; flex-direction: column; }
  .mh { display: flex; align-items: center; gap: var(--s-1); margin-bottom: var(--s-2); }
  /* Group's caption, between the month's arrows */
  .cap { flex: 1; min-width: 0; text-align: center; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .in { padding-left: var(--s-8); }
  .ok { display: inline-flex; color: var(--accent-text); }
</style>
