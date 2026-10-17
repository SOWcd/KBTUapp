<script lang="ts">
  // Admin → Clubs and schools (owner, Oct 14: the admin panel was one long page; now each job its own sheet). The list
  // with a search, one line a club; a tap opens it: the ✓, its team, a role by @username, the President's link, its
  // events (any deletable here only). A new club on top (schools come from the site).
  import { fold } from '../../ui/fold';
  import Plus from '@lucide/svelte/icons/plus';
  import BadgeCheck from '@lucide/svelte/icons/badge-check';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Search from '@lucide/svelte/icons/search';
  import Trash from '@lucide/svelte/icons/trash-2';
  import { sheets } from '../../lib/state/sheets';
  import { dayMonthShort } from '../../lib/time';
  import { api, ApiErr, type AdminEvent, type AdminOrg, type OrgRole } from '../../lib/api';
  import OrgLogo, { initials } from '../../ui/OrgLogo.svelte';
  import { shareCard, haptic, openLink } from '../../lib/tg';
  import Qr from '../../ui/Qr.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { QR_TONE } from '../../lib/awards';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { loadAfisha, phrase } from '../../lib/state/data.svelte';
  import { loadMe } from '../../lib/state/session.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { ROLE_NAME } from '../../lib/perms';
  import { PICK_EMOJI } from '../../lib/emoji';
  import EmojiPick from '../../ui/EmojiPick.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let orgs = $state<AdminOrg[] | null>(null);
  $effect(() => { api.adminOrgs().then((l) => (orgs = l)).catch(() => (orgs = [])); });
  let busy = $state(false);
  let q = $state('');
  // clubs and schools on their own tabs (owner, Oct 14: the admin comes for clubs; the 11 schools are seeded and rarely touched)
  let kind = $state<'club' | 'school'>('club');
  const ofKind = $derived((orgs ?? []).filter((o) => (o.kind === 'school') === (kind === 'school')));
  const schools = $derived((orgs ?? []).filter((o) => o.kind === 'school').length);
  const shown = $derived(ofKind.filter((o) => !q.trim() || o.name.toLowerCase().includes(q.trim().toLowerCase())));
  let card = $state<number | null>(null); // the club opened in the list
  const oops = (e: unknown) => {
    haptic.error();
    say(e instanceof ApiErr && e.message === 'who' ? t('adm.noUser') : e instanceof ApiErr && e.code === 'bad_input' ? t('adm.bad') : t('common.error'), 'pleading_face_3d');
  };

  // ---- a new club ----
  let adding = $state(false);
  // a club (schools come from KBTU's site, never by hand: owner, Oct 14)
  let nc = $state({ name: '', emoji: PICK_EMOJI[1], official: false });
  async function create(ev: Event) {
    ev.preventDefault();
    busy = true;
    try {
      const o = await api.adminCreateOrg({ name: nc.name.trim(), short: initials(nc.name), emoji: nc.emoji, official: nc.official });
      orgs = [o, ...(orgs ?? [])];
      adding = false; nc = { name: '', emoji: PICK_EMOJI[1], official: false };
      card = o.id; open = o.id;
      haptic.ok(); say(t('adm.created'), 'party_popper_3d');
      void loadAfisha(); // the club shows in Clubs at once
    } catch (e) { oops(e); } finally { busy = false; }
  }

  // ---- roles ----
  const ROLES: (OrgRole | 'none')[] = ['president', 'vice', 'head', 'member', 'none'];
  let open = $state<number | null>(null); // the club whose role form is out
  let who = $state('');
  let role = $state<OrgRole | 'none'>('president');
  async function assign(o: AdminOrg, ev: Event) {
    ev.preventDefault();
    busy = true;
    try {
      const fresh = await api.adminSetRole(o.id, who.trim(), role);
      orgs = orgs!.map((x) => (x.id === o.id ? fresh : x));
      haptic.ok(); say(t('adm.done', { who: who.trim(), role: role === 'none' ? t('adm.remove') : ROLE_NAME[role] }), 'raising_hands_3d_default');
      who = '';
      void loadMe(); // in case it was me
    } catch (e) { oops(e); } finally { busy = false; }
  }
  // the ✓ (§4.6): turning it on congratulates the President through the bot, as DMP's switch does
  async function official(o: AdminOrg, ev: Event) {
    const el = ev.currentTarget as HTMLInputElement;
    try {
      const on = (await api.setOfficial(o.id, el.checked)).official;
      orgs = orgs!.map((x) => (x.id === o.id ? { ...x, official: on } : x));
      void loadAfisha(); // Clubs shows the ✓ at once
      haptic.ok(); say(phrase(on ? 'reg.officialOn' : 'reg.officialOff'), on ? 'party_popper_3d' : 'waving_hand_3d_default');
    } catch { el.checked = o.official; haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // ---- a club's events, any of them deletable by the admin only (owner, Oct 13: a club asks him to remove a test,
  // test payments included). The confirm names what goes; payments or photos ask a second time, louder ----
  let evOf = $state<number | null>(null);
  let evs = $state<AdminEvent[] | null>(null);
  function showEvents(o: AdminOrg) {
    if (evOf === o.id) { evOf = null; return; }
    evOf = o.id; evs = null;
    api.adminOrgEvents(o.id).then((l) => { if (evOf === o.id) evs = l; }).catch(() => (evs = []));
  }
  async function dropEvent(x: AdminEvent) {
    const n = { people: x.people, came: x.came, paid: x.paid, photos: x.photos };
    if (!(await sheets.ask({ title: t('adm.delAsk', { title: x.title }), text: t('adm.delText', n), ok: t('adm.delGo'), cancel: t('tk.keep'), danger: true }))) return;
    if ((x.paid || x.photos) && !(await sheets.ask({ title: t('adm.delHard'), text: t('adm.delHardText'), ok: t('adm.delGo'), cancel: t('tk.keep'), danger: true }))) return;
    try {
      await api.deleteEvent(x.id);
      evs = evs!.filter((y) => y.id !== x.id);
      haptic.warn(); say(t('adm.deleted'), 'waving_hand_3d_default');
      void loadAfisha();
    } catch (e) { oops(e); }
  }
  // hide, never delete (owner, Oct 16: a lost phone must not wipe the clubs); back with one tap
  async function hide(o: AdminOrg) {
    if (!o.hidden && !(await sheets.ask({ title: t('adm.hideAsk', { club: o.name }), text: t('adm.hideText'), ok: t('adm.hide'), cancel: t('tk.keep'), danger: true }))) return;
    try {
      const fresh = await api.adminHideOrg(o.id, !o.hidden);
      orgs = orgs!.map((x) => (x.id === o.id ? fresh : x));
      haptic.ok(); say(t(fresh.hidden ? 'adm.hidden' : 'adm.back'), 'waving_hand_3d_default');
      void loadAfisha();
    } catch (e) { oops(e); }
  }
  // the President's link as a QR, to show face to face (owner, Oct 16: he goes round the schools' presidents)
  let qrOf = $state<number | null>(null), qrToken = $state('');
  async function showQr(o: AdminOrg) {
    if (qrOf === o.id) { qrOf = null; return; }
    haptic.tap(); qrOf = o.id; qrToken = '';
    try { const r = await api.adminPresLink(o.id); if (qrOf === o.id) qrToken = r.token; } catch (e) { qrOf = null; oops(e); }
  }
  // a new club's President by link (§2): our bot's card, one person, once, 7 days; each card is a fresh link
  function presLink(o: AdminOrg) {
    haptic.tap();
    shareCard({ kind: 'pres', id: String(o.id) }, 'https://t.me/KBTUappBot', o.name)
      .then((sent) => { if (sent) say(t('adm.presSent'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'pleading_face_3d'); });
  }
</script>

<Sheet {overlay} tall title={t('adm.clubs')}>
  <h2 class="t-h2 hd">{t('adm.clubs')}</h2>
  <p class="t-foot lead">{t('adm.lead')}</p>
  {#if schools}
    <div class="seg" role="tablist">
      <button class:on={kind === 'club'} onclick={() => { kind = 'club'; card = null; }}>{t('clubs.clubs')} · {(orgs?.length ?? 0) - schools}</button>
      <button class:on={kind === 'school'} onclick={() => { kind = 'school'; card = null; adding = false; }}>{t('clubs.schools')} · {schools}</button>
    </div>
  {/if}
  {#if adding && kind === 'club'}
    <form class="new" onsubmit={create} transition:fold>
      <label class="field"><span class="t-cap">{t('adm.name')}</span><input bind:value={nc.name} maxlength="60" enterkeyhint="next" /></label>
      <label class="switch"><span><b>{t('adm.official')}</b></span><input type="checkbox" role="switch" bind:checked={nc.official} /></label>
      <EmojiPick bind:value={nc.emoji} size={26} />
      <div class="acts">
        <Button kind="neutral" size="m" full onclick={() => (adding = false)}>{t('common.cancel')}</Button>
        <Button kind="primary" size="m" full type="submit" loading={busy} disabled={nc.name.trim().length < 2}>{t('adm.create')}</Button>
      </div>
    </form>
  {:else if kind === 'club'}
    <Button kind="secondary" size="l" full onclick={() => (adding = true)}>{#snippet icon()}<Plus size={18} />{/snippet}{t('adm.newClub')}</Button>
  {/if}

  {#if ofKind.length > 6}
    <label class="find"><Search size={17} /><input bind:value={q} placeholder={t('adm.find')} autocomplete="off" spellcheck="false" enterkeyhint="search" /></label>
  {/if}
  {#if orgs}
    <div class="list">
      {#each shown as o (o.id)}
        {@const pres = o.team.find((m) => m.role === 'president')}
        <article class="org" class:out={card === o.id}>
          <button class="top" aria-expanded={card === o.id} onclick={() => { haptic.select(); card = card === o.id ? null : o.id; open = null; evOf = null; qrOf = null; }}>
            <OrgLogo org={o} size={40} />
            <span class="tx"><b class="ellipsis">{o.name}{#if o.official}<span class="ok"><BadgeCheck size={16} /></span>{/if}</b>
              <i class="t-foot ellipsis">{o.hidden ? t('adm.hiddenTag') + ' · ' : ''}{o.kind === 'school' ? t('adm.kindSchool') + ' · ' : ''}{tn('adm.members', o.members)}{pres ? ' · ' + (pres.username ? '@' + pres.username : pres.name) : ' · ' + t('adm.noPres')}</i></span>
            <span class="chev"><ChevronRight size={18} /></span>
          </button>
          {#if card === o.id}
          <div class="body" transition:fold>
          {#if o.kind === 'club'}
            <label class="switch"><span><b>{t('reg.official')}</b><i class="t-foot">{t('reg.officialNote')}</i></span><input type="checkbox" role="switch" checked={o.official} onchange={(e) => official(o, e)} /></label>
          {/if}
          {#if o.team.length}
            <ul class="team">
              {#each o.team as m (m.id)}
                <li><span class="rl">{ROLE_NAME[m.role]}</span>{#if m.username}<!-- a tap opens their Telegram chat (owner, Oct 16: write to the President from here) -->
                  <button class="nm dm ellipsis" onclick={() => { haptic.tap(); openLink(`https://t.me/${m.username}`); }}>@{m.username}</button>
                {:else}<span class="nm ellipsis">{m.name}</span>{/if}{#if !m.student}<span class="ns">{t('adm.notSigned')}</span>{/if}</li>
              {/each}
            </ul>
          {:else}
            <p class="t-foot none">{t('adm.noTeam')}</p>
          {/if}
          {#if open === o.id}
            <form class="assign" onsubmit={(e) => assign(o, e)}>
              <input class="who" bind:value={who} placeholder="@username" autocapitalize="none" autocomplete="off" spellcheck="false" enterkeyhint="done" />
              <select bind:value={role} aria-label={t('adm.assign')}>
                {#each ROLES as r (r)}<option value={r}>{r === 'none' ? t('adm.remove') : ROLE_NAME[r]}</option>{/each}
              </select>
              <Button kind="primary" size="m" type="submit" loading={busy} disabled={!who.trim()}>{t('adm.set')}</Button>
            </form>
          {:else}
            <div class="links">
              <button class="lk" onclick={() => { open = o.id; who = ''; role = 'president'; }}>{t('adm.assign')}</button>
              <button class="lk" onclick={() => presLink(o)}>{t('adm.presLink')}</button>
              <button class="lk" class:on={qrOf === o.id} onclick={() => showQr(o)}>{t('adm.presQr')}</button>
              <button class="lk" class:on={evOf === o.id} onclick={() => showEvents(o)}>{t('adm.events')}</button>
              {#if o.kind === 'club'}<button class="lk" onclick={() => hide(o)}>{t(o.hidden ? 'adm.unhide' : 'adm.hide')}</button>{/if}
            </div>
          {/if}
          {#if qrOf === o.id}
            <div class="pq" transition:fold>
              <span class="plate">{#if qrToken}<Qr text={`https://t.me/KBTUappBot?startapp=pres_${o.id}_${qrToken}`} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr>{:else}<span class="wait"></span>{/if}</span>
              <p class="t-foot">{t('adm.presQrNote')}</p>
            </div>
          {/if}
          {#if evOf === o.id}
            <div class="evs" transition:fold>
              {#if !evs}<p class="t-foot none">…</p>
              {:else}
                {#each evs as x (x.id)}
                  <div class="ev"><span class="tx"><b class="ellipsis">{x.title}</b><i class="t-foot">{x.startsAt ? dayMonthShort(x.startsAt) + ' · ' : ''}{t('adm.evLine', { people: x.people, came: x.came, paid: x.paid, photos: x.photos })}</i></span>
                    <button class="del" aria-label={t('adm.delGo')} onclick={() => dropEvent(x)}><Trash size={18} /></button></div>
                {:else}<p class="t-foot none">{t('adm.noEvents')}</p>{/each}
              {/if}
            </div>
          {/if}
          </div>
          {/if}
        </article>
      {:else}
        <p class="t-foot none">{t(orgs.length ? 'adm.nothingFound' : 'adm.noClubs')}</p>
      {/each}
    </div>
  {/if}
</Sheet>

<style>
  .hd { margin: 4px 0 4px; }
  .seg { margin: 14px 0; }
  .lead { margin-bottom: 14px; text-wrap: pretty; }
  .new { display: flex; flex-direction: column; gap: 10px; }
  .acts { display: flex; gap: 8px; }
  .acts :global(.btn.full) { flex: 1; width: auto; min-width: 0; }
  .find { display: flex; align-items: center; gap: 8px; height: 44px; margin-top: 14px; padding: 0 14px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-3); }
  .find input { flex: 1; min-width: 0; height: 100%; background: none; color: var(--text); font: 550 16px/1 var(--font-text); }
  .list { display: flex; flex-direction: column; gap: 8px; margin-top: 14px; }
  .org { border-radius: var(--r-l); background: var(--surface-2); overflow: hidden; }
  .top { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 12px; text-align: left; }
  .top:active { background: var(--surface-3); }
  .chev { flex: none; display: flex; color: var(--text-3); transition: transform var(--t-base) var(--ease); }
  .out .chev { transform: rotate(90deg); }
  .body { display: flex; flex-direction: column; gap: 10px; padding: 0 12px 12px; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { display: flex; align-items: center; gap: 5px; font: 650 15.5px/1.25 var(--font-text); }
  .tx i { font-style: normal; }
  .ok { flex: none; display: flex; color: var(--accent-text); }
  .org .switch { padding: 10px 12px; background: var(--surface-3); }
  .team { display: flex; flex-direction: column; gap: 6px; padding: 0; margin: 0; list-style: none; }
  .team li { display: flex; align-items: center; gap: 8px; min-width: 0; font: 560 14px/1.2 var(--font-text); }
  .rl { flex: none; padding: 4px 8px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 700 11px/1 var(--font-text); letter-spacing: 0.04em; text-transform: uppercase; }
  .nm { min-width: 0; }
  .ns { flex: none; font: 550 12px/1 var(--font-text); color: var(--warning-text); }
  .none { padding: 2px; }
  .assign { display: grid; grid-template-columns: 1fr auto; gap: 6px; align-items: stretch; }
  .assign .who { grid-column: 1 / -1; }
  .assign input, .assign select { min-width: 0; height: 40px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface-3); color: var(--text); font: 560 15px/1 var(--font-text); }
  .assign select { padding-right: 8px; }
  select { width: 100%; background: none; color: var(--text); font: 500 16px/1 var(--font-text); }
  .links { display: flex; flex-wrap: wrap; gap: 6px; }
  .lk { height: 34px; padding: 0 14px; border-radius: var(--r-full); background: var(--surface-3); color: var(--text); font: 620 13.5px/1 var(--font-text); }
  .lk.on { background: var(--accent-soft); color: var(--accent-text); }
  .lk:active { transform: scale(0.96); }
  .evs { display: flex; flex-direction: column; }
  .ev { display: flex; align-items: center; gap: 10px; padding: 8px 0; }
  .ev + .ev { box-shadow: inset 0 1px 0 var(--line); }
  .del { flex: none; display: flex; padding: 8px; border-radius: var(--r-full); color: var(--danger-text); background: var(--surface-3); }
  .dm { all: unset; cursor: pointer; color: var(--accent); }
  .pq { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 6px 0 4px; text-align: center; }
  .plate { width: 220px; height: 220px; padding: 12px; border-radius: 22px; background: #fff; display: flex; align-items: center; justify-content: center; box-sizing: border-box; }
  .plate :global(.qr) { width: 100%; }
  .wait { width: 100%; height: 100%; border-radius: 12px; background: #EEF1F8; }
</style>
