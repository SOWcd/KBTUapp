<script lang="ts">
  // Starting a club (SPEC §4.6). Said up front: clubs open after the creator's check, so the form asks for the idea —
  // the name (a real club's as the example), its look (LookPick, as the event editor), one description and the club's
  // networks (LinksEdit; no "why / first month", a button per network). After sending: "on the check";
  // a yes opens the club (I'm its President), a no shows the reason and when a new application is possible.
  import { api, ApiErr, type ClubApplication } from '../../lib/api';
  import { say, close, type Overlay } from '../../lib/state/ui.svelte';
  import { loadMe } from '../../lib/state/session.svelte';
  import { data, loadAfisha } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth, nowTs } from '../../lib/time';
  import { PICK_EMOJI } from '../../lib/emoji';
  import LookPick from '../../ui/LookPick.svelte';
  import LinksEdit from '../../ui/LinksEdit.svelte';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import OrgLogo, { COVERS, initials } from '../../ui/OrgLogo.svelte';
  import { linkUrl, type LinkDraft } from '../../lib/social';
  import { grow } from '../../ui/grow';

  let { overlay }: { overlay: Overlay } = $props();

  let mine = $state<ClubApplication | null | undefined>(undefined);
  $effect(() => { api.myClubApplication().then((a) => (mine = a)).catch(() => (mine = null)); });
  const waiting = $derived(!!mine && mine.status === 'rejected' && (mine.reapplyAt ?? 0) > nowTs());
  // after a yes, another club too (owner, Oct 24: a President starts one with a friend and hands it over; KBTU allows one
  // presidency, so the form says so)
  let again = $state(false);
  const form = $derived(mine !== undefined && (!mine || again || (mine.status === 'rejected' && !waiting)));

  let f = $state({ name: '', emoji: PICK_EMOJI[0], cover: COVERS[2], description: '', links: [] as LinkDraft[] });
  // the example: a real club's name, picked once ("e.g. Chess club" read as a template)
  const clubs = data.orgs.filter((o) => o.kind === 'club');
  const example = clubs.length ? clubs[Math.floor(Math.random() * clubs.length)].name : t('nc.namePh');
  const short = $derived(initials(f.name));
  const urls = $derived(f.links.map(linkUrl));
  const preview = $derived({ id: 0, slug: '', name: f.name || example, short: short || initials(example), emoji: f.emoji, cover: COVERS.indexOf(f.cover), kind: 'club' as const, official: false });
  const ready = $derived(f.name.trim().length >= 2 && f.links.every((d, i) => !d.v.trim() || !!urls[i]) && f.description.trim().length >= 10);

  let sending = $state(false);
  async function send() {
    sending = true;
    try {
      mine = await api.applyClub({ name: f.name.trim(), short, emoji: f.emoji, cover: COVERS.indexOf(f.cover), description: f.description.trim(), links: urls.filter((u): u is string => !!u) });
      haptic.ok(); burst(); say(t('nc.sent'), 'party_popper_3d');
    } catch (e) {
      haptic.error();
      say(e instanceof ApiErr && e.message === 'taken' ? t('nc.taken') : e instanceof ApiErr && e.code === 'bad_input' ? t('nc.bad') : t('common.error'), 'pleading_face_3d');
    } finally { sending = false; }
  }
  async function openClub(id: number) { await loadMe(); void loadAfisha(); close(overlay.id); sheets.club(id); }
</script>

<Sheet {overlay} full title={t('nc.title')}>
  <h2 class="t-h2 hd">{t('nc.title')}</h2>

  {#if mine === undefined}
    <div class="wait" aria-hidden="true"><span></span><span></span></div>
  {:else if mine && mine.status !== 'rejected' && !again}
    <div class="status" class:ok={mine.status === 'approved'}>
      <OrgLogo org={{ id: 0, slug: '', name: mine.name, short: mine.short, emoji: mine.emoji, cover: mine.cover, kind: 'club', official: false }} size={72} />
      <b>{mine.name}</b>
      <p>{mine.status === 'pending' ? t('nc.pending') : t('nc.approved')}</p>
      {#if mine.status === 'approved' && mine.orgId}<Button kind="primary" size="l" full onclick={() => openClub(mine!.orgId!)}>{t('nc.open')}</Button>
        <Button kind="secondary" size="l" full onclick={() => (again = true)}>{t('nc.another')}</Button>{/if}
    </div>
  {:else}
    {#if mine?.status === 'rejected'}
      <div class="no"><b>{t('nc.rejected', { name: mine.name })}</b><p class="selectable">{mine.reason}</p>
        {#if waiting}<p class="t-foot">{t('nc.reapply', { date: dayMonth(mine.reapplyAt!) })}</p>{/if}</div>
    {/if}
    {#if form}
      <p class="lead">{t('nc.lead', { dmp: t('tab.dmp') })}{#if again}<br /><br />{t('nc.anotherNote')}{/if}</p>
      <div class="pv"><OrgLogo org={preview} size={64} /><b class="ellipsis" class:ph={!f.name.trim()}>{f.name || example}</b></div>
      <label class="field"><span class="t-cap">{t('nc.name')}</span><input bind:value={f.name} maxlength="60" placeholder={example} /></label>
      <div class="ep"><LookPick bind:emoji={f.emoji} bind:color={f.cover} colors={COVERS} size={26} /></div>
      <label class="field"><span class="t-cap">{t('nc.about')}</span><textarea bind:value={f.description} maxlength="600" rows="4" placeholder={t('nc.aboutPh')} use:grow></textarea>
        {#if f.description.trim().length < 10}<i class="need">{t('nc.whyNeed', { n: 10 - f.description.trim().length })}</i>{/if}</label>
      <h3 class="t-cap cap">{t('ce.links')}</h3>
      <LinksEdit bind:links={f.links} />
    {/if}
  {/if}

  {#snippet footer()}
    {#if form}<Button kind="primary" size="l" full loading={sending} disabled={!ready} onclick={send}>{t('nc.send')}</Button>{/if}
  {/snippet}
</Sheet>

<style>
  .ep { margin-bottom: 14px; }
  .hd { margin: 4px 0 10px; }
  .lead { margin-bottom: 14px; padding: 12px 14px; border-radius: var(--r-m); background: var(--accent-soft); color: var(--accent-text); font: 550 14px/1.4 var(--font-text); }
  .pv { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
  .pv b { min-width: 0; font: 720 18px/1.2 var(--font-display); }
  .pv b.ph { color: var(--text-3); }
  .cap { margin: 6px 2px 8px; }
  .field { margin-bottom: 12px; }
  .field textarea { min-height: 0; color: var(--text); }
  .need { font: 550 12px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .status { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 18px 8px; text-align: center; }
  .status b { font: 760 22px/1.2 var(--font-display); }
  .status p { color: var(--text-2); font: 500 15px/1.45 var(--font-text); text-wrap: balance; }
  .no { margin-bottom: 14px; padding: 12px 14px; border-radius: var(--r-m); background: var(--danger-soft); }
  .no b { font: 650 14.5px/1.3 var(--font-text); }
  .no p { margin-top: 4px; font: 500 14px/1.4 var(--font-text); }
  .wait { display: flex; flex-direction: column; gap: 12px; }
  .wait span { height: 60px; border-radius: var(--r-m); background: var(--surface-2); animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
</style>
