<script lang="ts">
  // Starting a club (SPEC §4.6). Said up front: clubs open after the creator's check, so the form asks for the idea —
  // the name, an emoji on a cover (a live logo), what the club does, an optional link (https:// optional), and the required
  // "why this club, what in the first month". After sending: "on the check"; a yes opens the club (I'm its President),
  // a no shows the reason and when a new application is possible.
  import { api, ApiErr, type ClubApplication } from '../../lib/api';
  import { say, close, type Overlay } from '../../lib/state/ui.svelte';
  import { loadMe } from '../../lib/state/session.svelte';
  import { loadAfisha } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth, nowTs } from '../../lib/time';
  import { PICK_EMOJI } from '../../lib/emoji';
  import EmojiPick from '../../ui/EmojiPick.svelte';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import OrgLogo, { COVERS, initials } from '../../ui/OrgLogo.svelte';
  import { linkUrl } from '../../lib/social';

  let { overlay }: { overlay: Overlay } = $props();

  let mine = $state<ClubApplication | null | undefined>(undefined);
  $effect(() => { api.myClubApplication().then((a) => (mine = a)).catch(() => (mine = null)); });
  const waiting = $derived(!!mine && mine.status === 'rejected' && (mine.reapplyAt ?? 0) > nowTs());
  const form = $derived(mine !== undefined && (!mine || (mine.status === 'rejected' && !waiting)));

  let f = $state({ name: '', emoji: PICK_EMOJI[0], cover: 2, description: '', link: '', why: '' });
  const short = $derived(initials(f.name));
  const link = $derived(f.link.trim() ? linkUrl({ kind: 'web', v: f.link }) : null);
  const preview = $derived({ id: 0, slug: '', name: f.name || '…', short, emoji: f.emoji, cover: f.cover, kind: 'club' as const, official: false });
  const ready = $derived(f.name.trim().length >= 2 && (!f.link.trim() || !!link) && f.description.trim().length >= 10 && f.why.trim().length >= 20);

  let sending = $state(false);
  async function send() {
    sending = true;
    try {
      mine = await api.applyClub({ name: f.name.trim(), short, emoji: f.emoji, cover: f.cover, description: f.description.trim(), link, why: f.why.trim() });
      haptic.ok(); burst(); say(t('nc.sent'), 'party_popper_3d');
    } catch (e) {
      haptic.error();
      say(e instanceof ApiErr && e.message === 'taken' ? t('nc.taken') : e instanceof ApiErr && e.code === 'bad_input' ? t('nc.bad') : t('common.error'), 'pleading_face_3d');
    } finally { sending = false; }
  }
  async function openClub(id: number) { await loadMe(); void loadAfisha(); close(overlay.id); sheets.club(id); }
  const grow = (el: HTMLTextAreaElement) => { const fit = () => { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }; fit(); el.addEventListener('input', fit); };
</script>

<Sheet {overlay} full title={t('nc.title')}>
  <h2 class="t-h2 hd">{t('nc.title')}</h2>

  {#if mine === undefined}
    <div class="wait" aria-hidden="true"><span></span><span></span></div>
  {:else if mine && mine.status !== 'rejected'}
    <div class="status" class:ok={mine.status === 'approved'}>
      <OrgLogo org={{ id: 0, slug: '', name: mine.name, short: mine.short, emoji: mine.emoji, cover: mine.cover, kind: 'club', official: false }} size={72} />
      <b>{mine.name}</b>
      <p>{mine.status === 'pending' ? t('nc.pending') : t('nc.approved')}</p>
      {#if mine.status === 'approved' && mine.orgId}<Button kind="primary" size="l" full onclick={() => openClub(mine!.orgId!)}>{t('nc.open')}</Button>{/if}
    </div>
  {:else}
    {#if mine?.status === 'rejected'}
      <div class="no"><b>{t('nc.rejected', { name: mine.name })}</b><p class="selectable">{mine.reason}</p>
        {#if waiting}<p class="t-foot">{t('nc.reapply', { date: dayMonth(mine.reapplyAt!) })}</p>{/if}</div>
    {/if}
    {#if form}
      <p class="lead">{t('nc.lead', { dmp: t('tab.dmp') })}</p>
      <div class="pv"><OrgLogo org={preview} size={64} /><span><b class="ellipsis">{f.name || t('nc.namePh')}</b><i>{t('nc.initiative')}</i></span></div>
      <label class="field"><span class="t-cap">{t('nc.name')}</span><input bind:value={f.name} maxlength="60" placeholder={t('nc.namePh')} /></label>
      <div class="covers">{#each COVERS as c, i (i)}<button class:on={f.cover === i} style="background:{c}" onclick={() => (f.cover = i)} aria-label={String(i + 1)}></button>{/each}</div>
      <div class="ep"><EmojiPick bind:value={f.emoji} size={26} /></div>
      <label class="field"><span class="t-cap">{t('nc.about')}</span><textarea bind:value={f.description} maxlength="600" rows="2" placeholder={t('nc.aboutPh')} use:grow></textarea></label>
      <label class="field"><span class="t-cap">{t('nc.why')}</span><textarea bind:value={f.why} maxlength="500" rows="3" placeholder={t('nc.whyPh')} use:grow></textarea>
        {#if f.why.trim().length < 20}<i class="need">{t('nc.whyNeed', { n: 20 - f.why.trim().length })}</i>{/if}</label>
      <label class="field"><span class="t-cap">{t('nc.link')}</span><input bind:value={f.link} maxlength="200" placeholder="instagram.com/…" autocapitalize="none" spellcheck="false" inputmode="url" /></label>
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
  .pv span { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .pv b { font: 720 18px/1.2 var(--font-display); }
  .pv i { font: 600 12.5px/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .field { margin-bottom: 12px; }
  .field textarea { min-height: 0; color: var(--text); }
  .need { font: 550 12px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .covers { display: flex; gap: 10px; margin: 2px 2px 14px; }
  .covers button { width: 32px; height: 32px; border-radius: 50%; flex: none; }
  .covers button.on { box-shadow: 0 0 0 3px var(--bg), 0 0 0 5px var(--accent); }
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
