<script lang="ts">
  // DMP's clubs registry (SPEC §4.13): every club with its live numbers for this month and its President — instead of
  // asking in chats who leads what and instead of monthly reports. A club opens its roster; a name or a student ID finds a
  // member and their clubs; CSV sends every roster into my chat with the bot. A sheet, from Studio (DMP) and the Admin panel.
  import Search from '@lucide/svelte/icons/search';
  import FileDown from '@lucide/svelte/icons/file-down';
  import BadgeCheck from '@lucide/svelte/icons/badge-check';
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

  let { inSheet = false }: { inSheet?: boolean } = $props();
  // the month: this one (loaded with the app, so the page opens full), or up to a year back (the numbers DMP used to
  // collect as monthly reports)
  let back = $state(0);
  let past = $state<RegistryOrg[] | null>(null);
  const orgs = $derived(back === 0 ? data.registry : past);
  $effect(() => {
    const b = back;
    untrack(() => {
      if (b === 0) { void loadRegistry().then((ok) => { if (!ok) { data.registry ??= []; say(t('common.error'), 'pleading_face_3d'); } }); return; }
      past = null;
      api.registry(b).then((l) => { if (b === back) past = l; }).catch(() => { past = []; say(t('common.error'), 'pleading_face_3d'); });
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
    catch (e) { haptic.error(); say(e instanceof ApiErr && e.message === 'no_dm' ? t('att.noDm') : t('common.error'), 'pleading_face_3d'); }
    finally { sending = false; }
  }
</script>

<div class:page={!inSheet} class:scroll={!inSheet}>
  <header class="hd">
    <span><h1 class="t-h1">{t('reg.title')}</h1><p class="t-foot">{orgs ? `${tn('reg.clubs', orgs.length)} · ${tn('reg.people', people)}` : ' '}</p></span>
    <button class="pill" disabled={sending} onclick={exportCsv}><FileDown size={17} />CSV</button>
  </header>

  <label class="find"><Search size={18} /><input bind:value={q} placeholder={t('reg.find')} autocomplete="off" spellcheck="false" enterkeyhint="search" /></label>

  {#if hits}
    <div class="list">
      {#each hits as h (h.person.id)}
        <div class="hit surface">
          <Avatar person={h.person} size={40} />
          <span class="tx"><b>{withNick(h.fullName, h.person)}</b><i>{h.studentId}{h.course ? ' · ' + t('person.year', { n: h.course }) : ''}{h.school ? ' · ' + schoolShort(h.school) : ''}</i>
            <span class="clubs">{#each h.clubs as c (c.org.id)}<button class="club" onclick={() => sheets.roster(c.org)}><OrgLogo org={c.org} size={16} />{shortOf(c.org)} · {ROLE_NAME[c.role]}</button>{/each}</span></span>
        </div>
      {:else}<p class="t-foot none">{t('reg.nobody')}</p>{/each}
    </div>
  {:else if orgs}
    {#if back === 0 && memos.length}
      <h2 class="sh">{t('reg.memos')}</h2>
      <div class="list memos">
        {#each memos as m (`${m.org.id}:${m.sentAt}`)}
          <div class="memo surface">
            <OrgLogo org={m.org} size={36} />
            <span class="tx"><b class="ellipsis">{nameOf(m.org)}</b><i>{t('reg.memoSent', { who: m.by ?? '—', when: `${relDay(m.sentAt)} ${time(m.sentAt)}` })}</i>
              {#each m.events as e (e.id)}<button class="ev" onclick={() => sheets.event(e.id)}><span class="ellipsis">{e.title}</span><span class="num">{relDay(e.startsAt)}</span></button>{/each}</span>
          </div>
        {/each}
      </div>
      <p class="t-foot note">{t('reg.memoNote')}</p>
    {/if}
    <div class="mh">
      <button onclick={() => back++} disabled={back >= 12} aria-label="‹"><ChevronLeft size={18} /></button>
      <h2 class="sh">{t('reg.month', { month: monthName(monthTs) })}</h2>
      <button onclick={() => back--} disabled={back <= 0} aria-label="›"><ChevronRight size={18} /></button>
    </div>
    <div class="list">
      {#each orgs as o (o.org.id)}
        <button class="org surface" onclick={() => sheets.roster(o.org, (on) => (o.org = { ...o.org, official: on }))}>
          <OrgLogo org={o.org} size={44} />
          <span class="tx">
            <b class="ellipsis">{nameOf(o.org)}{#if o.org.official}<BadgeCheck size={15} />{/if}</b>
            <i class="ellipsis">{o.president ? t('reg.president', { name: o.president.fullName }) : t('reg.noPresident')}</i>
            <span class="nums"><span><b class="num">{o.members}</b>{tn('reg.members', o.members)}</span><span><b class="num">{o.month.events}</b>{tn('reg.events', o.month.events)}</span>
              <span><b class="num">{o.month.registrations}</b>{tn('reg.regs', o.month.registrations)}</span><span><b class="num">{o.month.came}</b>{tn('reg.came', o.month.came)}</span></span>
          </span>
          <ChevronRight size={18} />
        </button>
      {/each}
    </div>
  {:else}
    <div class="wait" aria-hidden="true"><span></span><span></span><span></span></div>
  {/if}
  {#if !inSheet}<div class="tail"></div>{/if}
</div>

<style>
  /* as a page of DMP's tab (the sheet brings its own): under the capsule, the bottom nav's room at the end */
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; background: var(--glow), var(--bg); }
  .tail { height: calc(var(--bottom) + 24px); }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
  .hd p { margin-top: 4px; }
  .pill { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 14px/1 var(--font-text); }
  .pill:active { transform: scale(0.95); }
  .find { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 14px; margin-bottom: 14px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-3); }
  .find input { flex: 1; min-width: 0; height: 100%; background: none; color: var(--text); font: 500 16px/1 var(--font-text); }
  .find input::placeholder { color: var(--text-3); }
  .mh { display: flex; align-items: center; gap: 6px; margin: 0 0 10px; }
  .mh button { width: 32px; height: 32px; flex: none; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface-2); color: var(--text-2); }
  .mh button:disabled { opacity: 0.35; }
  .mh .sh { flex: 1; text-align: center; margin: 0; }
  .sh { margin: 4px 2px 10px; font: 650 13px/1.2 var(--font-text); letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-3); }
  .list { display: flex; flex-direction: column; gap: 10px; }
  .org { display: flex; align-items: center; gap: 12px; width: 100%; padding: 12px 10px 12px 12px; text-align: left; color: var(--text-3); }
  .org:active { transform: scale(0.99); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx > b { display: flex; align-items: center; gap: 5px; font: 680 15.5px/1.25 var(--font-text); color: var(--text); }
  .tx > b :global(svg) { flex: none; color: var(--accent-text); }
  .tx > i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .nums { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; font: 500 12.5px/1.2 var(--font-text); color: var(--text-3); }
  .nums b { margin-right: 4px; font: 720 14px/1 var(--font-text); color: var(--text); }
  .hit { display: flex; gap: 12px; align-items: flex-start; padding: 12px; }
  .clubs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .club { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px 0 6px; border-radius: var(--r-full); background: var(--surface-2); font: 600 12.5px/1 var(--font-text); color: var(--text); }
  .memo { display: flex; gap: 12px; align-items: flex-start; padding: 12px; }
  .ev { display: flex; justify-content: space-between; gap: 10px; margin-top: 4px; padding: 6px 10px; border-radius: var(--r-s); background: var(--surface-2); font: 600 13px/1.3 var(--font-text); color: var(--text); text-align: left; }
  .ev .num { flex: none; color: var(--text-3); font-weight: 550; }
  .note { margin: 8px 2px 18px; }
  .none { padding: 16px 4px; text-align: center; }
  .wait { display: flex; flex-direction: column; gap: 10px; }
  .wait span { height: 86px; border-radius: var(--r-l); background: var(--surface-2); animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
</style>
