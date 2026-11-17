<script lang="ts">
  // Admin → an organization (owner, Nov 17: "I type an organization and go"; the list's card dropped six pills). One page
  // a club, from the search, the recent ones or the list: its face (a tap opens its public page), one main action (the
  // creator: its Studio as its President; an admin: a new event for it as staff), then plain rows: its events (any
  // deletable here only), the ✓, the leaders with their roles (a row's menu changes one), the President's one-time link
  // (sent as our bot's card, or shown as a QR face to face), its short links. Hiding is last and alone: never a delete.
  //   org  as the list had it (the hero shows at once); the admin's copy (team, links) comes from the shared store
  import { staffOnly } from '../../lib/state/staffGate.svelte';
  import { api, ApiErr, type AdminEvent, type AdminMember, type AdminOrg, type OrgRef, type OrgRole } from '../../lib/api';
  import { onDestroy } from 'svelte';
  import { adminOrgs, loadAdminOrgs, patchOrg, putOrg, seen } from '../../lib/state/adminOrgs.svelte';
  import { staffStill } from '../../lib/state/staffAccess.svelte';
  import { openAsCreator } from '../../lib/state/creator.svelte';
  import { loadAfisha, loadInbox, phrase } from '../../lib/state/data.svelte';
  import { loadMe, session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { QR_TONE } from '../../lib/awards';
  import { dayMonthShort } from '../../lib/time';
  import { shareCard, haptic, openLink } from '../../lib/tg';
  import '../../lib/qrnow'; // its code in the first frame (lib/qr.svelte.ts)
  import { fold } from '../../ui/fold';
  import type { MenuItem } from '../../ui/menu';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Qr from '../../ui/Qr.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  let { overlay, org }: { overlay: Overlay; org: OrgRef } = $props();
  staffOnly(() => overlay);
  const o = $derived<AdminOrg | undefined>(adminOrgs.list?.find((x) => x.id === org.id));
  const club = $derived(org.kind === 'club');
  const owner = $derived(!!session.me?.founder);
  // svelte-ignore state_referenced_locally
  seen(org.id);
  void loadAdminOrgs(); // as the server has it now, behind what the store shows meanwhile

  let busy = $state(false);
  const oops = (e: unknown) => {
    haptic.error();
    say(e instanceof ApiErr && e.message === 'who' ? t('adm.noUser') : e instanceof ApiErr && e.code === 'bad_input' ? t('adm.bad') : t('common.error'), 'warning_3d');
  };

  const studio = () => { haptic.tap(); openAsCreator(org); sheets.studio(org.id, true); };
  const newEvent = () => { haptic.tap(); sheets.editor(org.id, undefined, true); };

  // ---- the ✓ (§4.6): turning it on congratulates the President through the bot, as DMP's switch does. The switch
  // answers at once and steps back on a "no"
  let official = $state<boolean | null>(null); // while the question is up or the save is on its way
  async function setOfficial(x: AdminOrg, on: boolean) {
    official = on;
    const ask = on ? { title: t('reg.officialOnAsk', { name: x.name }), ok: t('reg.officialOnOk') } : { title: t('reg.officialOffAsk', { name: x.name }), ok: t('reg.officialOffOk') };
    try {
      if (!(await sheets.ask({ ...ask, cancel: t('common.cancel'), danger: !on }))) return;
      const still = staffStill();
      const now = (await api.setOfficial(x.id, on)).official;
      if (!still()) return;
      patchOrg(x.id, () => ({ official: now })); // into the club as it is now: a role given meanwhile stays
      void loadAfisha(); // Clubs shows the ✓ at once
      haptic.ok(); say(phrase(now ? 'reg.officialOn' : 'reg.officialOff'), now ? 'party_popper_3d' : 'waving_hand_3d_default');
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { official = null; }
  }

  // ---- roles: a leader's row changes theirs, by the app's own id (an @username may be someone else's by now);
  // anyone else by an @username or Telegram ID typed by hand (they opened the app once): a role, or out of the club ----
  const ROLES: OrgRole[] = ['president', 'vice', 'head', 'member'];
  const roleName = (r: OrgRole | 'none') => (r === 'none' ? t('adm.remove') : t(`role.${r}`));
  let adding = $state(false), who = $state(''), role = $state<OrgRole | 'none'>('president');
  async function assign(x: AdminOrg, whom: string | { userId: number }, name: string, r: OrgRole | 'none') {
    if (r === 'none' && !(await sheets.ask({ title: t('adm.removeAsk', { name, club: x.name }), ok: t('adm.remove'), cancel: t('common.cancel'), danger: true }))) return;
    busy = true;
    try {
      const still = staffStill();
      const fresh = await api.adminSetRole(x.id, whom, r);
      if (!still()) return; // the role went while it was on its way: nothing of the club is put back
      putOrg(fresh);
      haptic.ok(); say(t('adm.done', { who: name, role: roleName(r) }), 'raising_hands_3d_default');
      who = ''; adding = false;
      void loadMe(); // in case it was me
    } catch (e) { oops(e); } finally { busy = false; }
  }
  const memberMenu = (x: AdminOrg, m: AdminMember): MenuItem[] => {
    const name = m.name || '@' + m.username;
    return [
      ...ROLES.map((r) => ({ label: roleName(r), checked: m.role === r, onselect: () => { if (m.role !== r) void assign(x, { userId: m.id }, name, r); } })),
      ...(m.username ? [{ label: t('adm.cappWrite'), onselect: () => openLink(`https://t.me/${m.username}`) }] : []),
      { label: t('adm.remove'), destructive: true, onselect: () => void assign(x, { userId: m.id }, name, 'none') },
    ];
  };

  // ---- the President's one-time link (§2): our bot's card, one person, once, 7 days; or the same as a QR, to show face
  // to face (he goes round the schools' presidents). Each card and each QR is a fresh link
  let qr = $state<string | null>(null); // '' while its token is on the way
  function sendLink() {
    haptic.tap();
    shareCard({ kind: 'pres', id: String(org.id) }, 'https://t.me/KBTUappBot', org.name)
      .then((sent) => { if (sent) say(t('adm.presSent'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
  let qrGen = 0; // which asking is the current one: Hide, another Show or leaving makes a late answer nobody's
  async function showQr() {
    haptic.tap(); qr = '';
    const g = ++qrGen;
    try { const r = await api.adminPresLink(org.id); if (g === qrGen) qr = r.token; }
    catch (e) { if (g === qrGen) { qr = null; oops(e); } }
  }
  const hideQr = () => { qrGen++; qr = null; };
  onDestroy(() => { qrGen++; });
  const linkMenu = $derived<MenuItem[]>([
    { label: t('adm.presSend'), onselect: sendLink },
    qr == null ? { label: t('adm.presShow'), onselect: () => void showQr() } : { label: t('adm.presHide'), onselect: hideQr },
  ]);
  // a club's own short link: the admin takes any down (one leading somewhere it shouldn't)
  async function revoke(x: AdminOrg, slug: string) {
    if (!(await sheets.ask({ title: t('adm.linkAsk', { link: `${location.host}/${slug}` }), ok: t('adm.linkGo'), cancel: t('tk.keep'), danger: true }))) return;
    try {
      const still = staffStill();
      await api.dropShortLink(slug);
      if (!still()) return;
      patchOrg(x.id, (now) => ({ shortLinks: now.shortLinks.filter((s) => s !== slug) }));
      haptic.warn();
    } catch (e) { oops(e); }
  }

  // ---- its events, any of them deletable by the admin only (owner, Oct 13: a club asks him to remove a test, test
  // payments included). The confirm names what goes; hidden at once, gone in a day: Undo in the queue's Done ----
  let evOpen = $state(false), evs = $state<AdminEvent[] | null>(null), evFailed = $state(false);
  // read again on every opening (one made a moment ago, another admin's delete); the last list shows meanwhile
  let evGen = 0; // a new read or a change here makes an older answer nobody's (a deleted event must not come back)
  function loadEvents() {
    const g = ++evGen;
    evFailed = false;
    api.adminOrgEvents(org.id).then((l) => { if (g === evGen) evs = l; }).catch(() => { if (g === evGen) evFailed = true; });
  }
  function events() {
    haptic.select(); evOpen = !evOpen;
    if (evOpen) loadEvents();
  }
  // its day, what it is if not live, and its numbers once it has any
  const evLine = (x: AdminEvent) => [x.startsAt ? dayMonthShort(x.startsAt) : '', x.status === 'draft' ? t('studio.draft') : x.status === 'cancelled' ? t('event.cancelled') : '',
    x.people || x.came || x.paid || x.photos ? t('adm.evLine', { people: x.people, came: x.came, paid: x.paid, photos: x.photos }) : ''].filter(Boolean).join(' · ') || undefined;
  async function dropEvent(x: AdminEvent) {
    const n = { people: x.people, came: x.came, paid: x.paid, photos: x.photos };
    // people hold seats or paid: it's cancelled first (they hear it), then deleted
    const live = x.status === 'published' && (x.startsAt ?? 0) * 1000 > Date.now() && (x.people > 0 || x.paid > 0);
    if (live) {
      if (!(await sheets.ask({ title: t('adm.cancelFirst', { title: x.title }), text: t('adm.cancelFirstText'), ok: t('adm.cancelGo'), cancel: t('tk.keep'), danger: true }))) return;
      try { await api.cancelEvent(x.id); evGen++; evs = evs!.map((y) => (y.id === x.id ? { ...y, status: 'cancelled' } : y)); void loadAfisha(); }
      catch (e) { oops(e); return; }
    }
    if (!(await sheets.ask({ title: t('adm.delAsk', { title: x.title }), text: t('adm.delText', n), ok: t('adm.delGo'), cancel: t('tk.keep'), danger: true }))) return;
    const before = evs;
    evGen++;
    evs = evs!.filter((y) => y.id !== x.id);
    try {
      await api.adminDeleteEvent(x.id);
      evGen++; // a read begun while the delete was on its way may still hold the event
      haptic.warn(); say(t('adm.evDeleted'), 'waving_hand_3d_default');
      void loadAfisha(); void loadInbox(); // its Undo is in Done
    } catch (e) { evs = before; oops(e); if (evOpen) loadEvents(); }
  }

  // hide, never delete (a lost phone must not wipe the clubs); back with one tap
  async function hide(x: AdminOrg) {
    if (!x.hidden && !(await sheets.ask({ title: t('adm.hideAsk', { club: x.name }), text: t('adm.hideText'), ok: t('adm.hide'), cancel: t('tk.keep'), danger: true }))) return;
    busy = true;
    try {
      const still = staffStill();
      const fresh = await api.adminHideOrg(x.id, !x.hidden);
      if (!still()) return;
      putOrg(fresh);
      haptic.ok(); say(t(fresh.hidden ? 'adm.hidden' : 'adm.back'), 'waving_hand_3d_default');
      void loadAfisha();
    } catch (e) { oops(e); } finally { busy = false; }
  }
</script>

<Pane {overlay} title={org.name}>
  <div class="page stagger">
    <button class="hero" onclick={() => { haptic.tap(); sheets.club(org.id); }}>
      <OrgLogo {org} size={64} />
      <span class="who">
        <span class="sub">{org.kind === 'school' ? t('adm.kindSchool') : ''}{org.kind === 'school' && o ? ' · ' : ''}{o ? tn('adm.members', o.members) : ''}</span>
        {#if o?.hidden}<Tag tone="danger">{t('adm.hiddenTag')}</Tag>{/if}
      </span>
    </button>

    {#if owner}<Button kind="filled" size="l" full onclick={studio}>{t('adm.studio')}</Button>
    {:else}<Button kind="filled" size="l" full onclick={newEvent}>{t('ed.new')}</Button>{/if}

    <Group>
      {#if owner}<Row title={t('ed.new')} accessory="chevron" onclick={newEvent} />{/if}
      <Row title={t('adm.events')} accessory="disclosure" open={evOpen} onclick={events} />
      {#if evOpen}
        {#each evs ?? [] as x (x.id)}
          <Row dense title={x.title} subtitle={evLine(x)}>
            {#snippet trailing()}<Button kind="gray" size="s" destructive onclick={() => dropEvent(x)}>{t('adm.delGo')}</Button>{/snippet}
          </Row>
        {:else}
          {#if !evFailed}<Row dense title={evs ? t('adm.noEvents') : '…'} disabled />{/if}
        {/each}
        {#if evFailed}<Row dense tone="action" title={t('common.retry')} onclick={loadEvents} />{/if}
      {/if}
      {#if club && o}<Row title={t('reg.official')} accessory="switch" checked={official ?? o.official} disabled={official != null} onchange={(on) => setOfficial(o, on)} />{/if}
    </Group>

    {#if !o && adminOrgs.failed}<EmptyState inline text={t('common.error')} onretry={loadAdminOrgs} />{/if}
    {#if o}
      <Group caption={t('adm.team')}>
        {#each o.team as m (m.id)}
          <Row dense title={m.name || '@' + m.username} subtitle={[m.username ? '@' + m.username : '', m.student ? '' : t('adm.notSigned')].filter(Boolean).join(' · ') || undefined}
            value={roleName(m.role)} whole disabled={busy} menu={memberMenu(o, m)} />
        {/each}
        <Row tone="add" title={t('adm.assign')} onclick={() => { haptic.select(); adding = !adding; who = ''; role = o.team.some((m) => m.role === 'president') ? 'member' : 'president'; }} />
      </Group>
      {#if adding}
        <!-- not a <form>: the role row is a button, and a button in a form submits it -->
        <div class="form" transition:fold>
          <Field label={t('adm.who')} bind:value={who} autocomplete="off" enterkeyhint="done" />
          <Group><Row title={t('staff.role')} value={roleName(role)} menu={[...ROLES.map((r) => ({ label: roleName(r), checked: role === r, onselect: () => (role = r) })),
            { label: roleName('none'), destructive: true, onselect: () => (role = 'none') }]} /></Group>
          <Button kind="filled" full destructive={role === 'none'} loading={busy} disabled={!who.trim()} onclick={() => assign(o, who.trim(), who.trim(), role)}>{role === 'none' ? t('adm.remove') : t('adm.set')}</Button>
        </div>
      {/if}

      <Group caption={t('adm.links')}>
        <Row title={t('adm.presLink')} menu={linkMenu} />
        {#each o.shortLinks as s (s)}
          <Row dense title="{location.host}/{s}">
            {#snippet trailing()}<Button kind="gray" size="s" destructive onclick={() => revoke(o, s)}>{t('adm.revoke')}</Button>{/snippet}
          </Row>
        {/each}
      </Group>
      {#if qr != null}
        <div class="pq" transition:fold {@attach (el) => { setTimeout(() => el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 260); }}>
          <span class="plate">{#if qr}<Qr text={`https://t.me/KBTUappBot?startapp=pres_${org.id}_${qr}`} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr>{:else}<span class="wait"></span>{/if}</span>
          <p class="note">{t('adm.presQrNote')}</p>
        </div>
      {/if}

      {#if club}
        <Group>
          {#if o.hidden}<Row tone="action" title={t('adm.unhide')} disabled={busy} onclick={() => hide(o)} />
          {:else}<Row tone="destructive" title={t('adm.hide') + '…'} disabled={busy} onclick={() => hide(o)} />{/if}
        </Group>
      {/if}
    {/if}
  </div>
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-6); }
  .hero { display: flex; align-items: center; gap: var(--s-4); padding: 0 var(--s-1); text-align: left; }
  .who { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; min-width: 0; }
  .sub { font: 450 var(--fs-row)/1.2 var(--font-text); color: var(--text-3); }
  .form { display: flex; flex-direction: column; gap: var(--s-3); margin-top: calc(-1 * var(--s-2)); }
  .pq { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); margin-top: calc(-1 * var(--s-2)); text-align: center; }
  .plate { width: 220px; height: 220px; padding: 12px; border-radius: var(--r-l); background: white; display: flex; align-items: center; justify-content: center; box-sizing: border-box; }
  .plate :global(.qr) { width: 100%; }
  .wait { width: 100%; height: 100%; border-radius: var(--r-s); background: rgb(0 0 0 / 0.06); }
  .note { max-width: 30ch; font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); text-wrap: balance; }
</style>
