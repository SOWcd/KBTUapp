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
  import CirclePlus from '@lucide/svelte/icons/circle-plus';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import OrgLogo, { COVERS, initials } from '../../ui/OrgLogo.svelte';
  import { linkUrl, type LinkDraft } from '../../lib/social';

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
      say(e instanceof ApiErr && e.message === 'taken' ? t('nc.taken') : e instanceof ApiErr && (e.message === 'club_word' || e.message === 'emoji') ? t(`nc.${e.message}`) : e instanceof ApiErr && e.code === 'bad_input' ? t('nc.bad') : t('common.error'), 'warning_3d');
    } finally { sending = false; }
  }
  async function openClub(id: number) { await loadMe(); void loadAfisha(); close(overlay.id); sheets.club(id); }
</script>

<Sheet {overlay} icon={CirclePlus} full title={t('nc.title')}>
  {#if mine === undefined}
    <Skeleton n={2} />
  {:else if mine && mine.status !== 'rejected' && !again}
    <div class="status">
      <OrgLogo org={{ id: 0, slug: '', name: mine.name, short: mine.short, emoji: mine.emoji, cover: mine.cover, kind: 'club', official: false }} size={72} />
      <b>{mine.name}</b>
      <p>{mine.status === 'pending' ? t('nc.pending') : t('nc.approved')}</p>
      {#if mine.status === 'approved' && mine.orgId}<Button kind="primary" size="l" full onclick={() => openClub(mine!.orgId!)}>{t('nc.open')}</Button>
        <Button kind="secondary" size="l" full onclick={() => (again = true)}>{t('nc.another')}</Button>{/if}
    </div>
  {:else}
    <div class="form">
      {#if mine?.status === 'rejected'}
        <Notice tone="danger" title={t('nc.rejected', { name: mine.name })}>
          <p class="nt selectable">{mine.reason}</p>
          {#if waiting}<p class="t-foot">{t('nc.reapply', { date: dayMonth(mine.reapplyAt!) })}</p>{/if}
        </Notice>
      {/if}
      {#if form}
        <Notice tone="accent" text={t('nc.lead', { dmp: t('tab.dmp') })}>{#if again}<p class="nt more">{t('nc.anotherNote')}</p>{/if}</Notice>
        <div class="pv"><OrgLogo org={preview} size={64} /><b class="ellipsis" class:ph={!f.name.trim()}>{f.name || example}</b></div>
        <Field label={t('nc.name')} bind:value={f.name} maxlength={60} placeholder={example} />
        <LookPick bind:emoji={f.emoji} bind:color={f.cover} colors={COVERS} size={26} />
        <div>
          <Field label={t('nc.about')} multiline rows={4} bind:value={f.description} maxlength={600} placeholder={t('nc.aboutPh')} />
          <!-- engine: ui/Field could take a grey count line ("10 more letters"); its rule is no hint lines -->
          {#if f.description.trim().length < 10}<p class="need">{t('nc.whyNeed', { n: 10 - f.description.trim().length })}</p>{/if}
        </div>
        <div class="links">
          <span class="lab">{t('ce.links')}</span>
          <LinksEdit bind:links={f.links} />
        </div>
      {/if}
    </div>
  {/if}

  {#snippet footer()}
    {#if form}<Button kind="primary" size="l" full loading={sending} disabled={!ready} onclick={send}>{t('nc.send')}</Button>{/if}
  {/snippet}
</Sheet>

<style>
  .form { display: flex; flex-direction: column; gap: var(--s-4); }
  .nt { font: 450 var(--fs-body)/1.35 var(--font-text); }
  .more { margin-top: var(--s-2); }
  .pv { display: flex; align-items: center; gap: var(--s-3); }
  .pv b { min-width: 0; font: 700 var(--fs-t3)/1.2 var(--font-display); }
  .pv b.ph { color: var(--text-3); }
  /* the same label as ui/Field's, over the links */
  .links { display: flex; flex-direction: column; gap: 6px; }
  .lab { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .need { margin-top: 6px; padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .status { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 18px var(--s-2); text-align: center; }
  .status b { font: 700 var(--fs-sec)/1.2 var(--font-display); }
  .status p { color: var(--text-2); font: 450 var(--fs-body)/1.45 var(--font-text); text-wrap: balance; }
</style>
