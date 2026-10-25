<script lang="ts">
  // The club's profile (Vice+, SPEC §2): what students see on its sheet — the name, its logo or an emoji on a cover
  // (a live logo), about, up to six links (a network and its username, or any address). Save sends only what changed; leaving with
  // changes asks first.
  import X from '@lucide/svelte/icons/x';
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import { api, ApiErr, original, type Id, type Org, type OrgPatch } from '../../lib/api';
  import { say, close, type Overlay } from '../../lib/state/ui.svelte';
  import { data, phrase } from '../../lib/state/data.svelte';
  import { loadMe } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import LookPick from '../../ui/LookPick.svelte';
  import LinksEdit from '../../ui/LinksEdit.svelte';
  import { linkUrl, linkDraft, type LinkDraft } from '../../lib/social';
  import { haptic } from '../../lib/tg';
  import { shrink } from '../../lib/photo';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import OrgLogo, { COVERS } from '../../ui/OrgLogo.svelte';
  import ShortLinks from './ShortLinks.svelte';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  let o = $state<Org | null>(null);
  // the logo (owner, Oct 5): one of my uploads, or null — then the emoji on its cover shows again
  let logo = $state<{ id?: Id; url: string } | null>(null);
  let f = $state({ name: '', abbr: '', emoji: '', cover: 0, description: '', links: [] as LinkDraft[], hidden: false });
  $effect(() => {
    api.org(id).then((got) => { const x = original(got); o = x; /* as typed, never a translation (PLAN 9) */ f = { name: x.name, abbr: x.abbr ?? '', emoji: x.emoji, cover: x.cover, description: x.description ?? '', links: x.links.map(linkDraft), hidden: x.membersHidden }; logo = x.logo ? { url: x.logo } : null; })
      .catch(() => { say(t('common.error'), 'pleading_face_3d'); close(overlay.id); });
  });
  let uploading = $state(false);
  async function pickLogo(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, file = el.files?.[0];
    el.value = '';
    if (!file) return;
    if (file.size > 30 * 1024 * 1024) { say(t('ed.photoBig'), 'pleading_face_3d'); return; }
    uploading = true;
    try { const m = await api.uploadPhoto(await shrink(file, 1200)); logo = { id: m.id, url: m.thumb }; haptic.ok(); }
    catch { haptic.error(); say(t('ed.photoBad'), 'pleading_face_3d'); }
    finally { uploading = false; }
  }
  // the club's own emoji stays pickable even when it isn't one of the twelve
  const urls = $derived(f.links.map(linkUrl));
  const links = $derived(urls.filter((u): u is string => !!u));
  const linksOk = $derived(f.links.every((d, i) => !d.v.trim() || !!urls[i]));
  const patch = $derived.by(() => {
    const p: OrgPatch = {};
    if (!o) return p;
    if (f.name.trim() !== o.name) p.name = f.name.trim();
    if (f.abbr.trim() !== (o.abbr ?? '')) p.abbr = f.abbr.trim();
    if (f.emoji !== o.emoji) p.emoji = f.emoji;
    if (f.cover !== o.cover) p.cover = f.cover;
    if (f.description.trim() !== (o.description ?? '')) p.description = f.description.trim();
    if (links.join('\n') !== o.links.join('\n')) p.links = links;
    if ((logo?.url ?? null) !== (o.logo ?? null)) p.logoId = logo?.id ?? null;
    if (f.hidden !== o.membersHidden) p.membersHidden = f.hidden;
    return p;
  });
  const changed = $derived(Object.keys(patch).length > 0);
  const ready = $derived(changed && f.name.trim().length >= 2 && (f.abbr.trim() === (o?.abbr ?? '') || /^\S{2,8}$/.test(f.abbr.trim())) && linksOk);
  const preview = $derived(o ? { ...o, name: f.name || o.name, emoji: f.emoji, cover: f.cover, logo: logo?.url ?? null } : null);

  let busy = $state(false);
  let leaving = false;
  async function save() {
    busy = true;
    try {
      const x = await api.updateOrg(id, patch);
      const i = data.orgs.findIndex((y) => y.id === id);
      if (i >= 0) data.orgs[i] = x;
      void loadMe();  // my memberships carry the club's name and logo (Studio's title, the club chips)
      leaving = true; haptic.ok(); say(phrase('ce.saved'), 'sparkles_3d'); close(overlay.id);
    } catch (e) {
      haptic.error();
      say(e instanceof ApiErr && e.message === 'taken' ? t('nc.taken') : e instanceof ApiErr && e.code === 'bad_input' ? t('nc.bad') : t('common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
  const hold = () => !leaving && changed;
  async function onhold() {
    if (await sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('common.cancel'), danger: true })) { leaving = true; close(overlay.id); }
  }
  const grow = (el: HTMLTextAreaElement) => { const fit = () => { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }; fit(); el.addEventListener('input', fit); };
</script>

<Sheet {overlay} full title={t('ce.title')} {hold} {onhold}>
  <h2 class="t-h2 hd">{t('ce.title')}</h2>
  <p class="t-foot sub">{t('ce.sub')}</p>

  {#if !o || !preview}
    <div class="wait" aria-hidden="true"><span></span><span></span></div>
  {:else}
    <div class="pv"><OrgLogo org={preview} size={64} /><span><b class="ellipsis">{preview.name}</b><i>{o.official ? t('clubs.official') : t('club.initiative')}</i></span></div>
    <div class="lg">
      <label class="pill" class:busy={uploading}><ImagePlus size={17} />{logo ? t('ce.logoChange') : t('ce.logoAdd')}
        <input type="file" accept="image/*" onchange={pickLogo} disabled={uploading} /></label>
      {#if logo}<button class="pill off" onclick={() => (logo = null)}><X size={16} />{t('ce.logoRemove')}</button>{/if}
    </div>
    <label class="field"><span class="t-cap">{t('nc.name')}</span><input bind:value={f.name} maxlength="60" /></label>
    <p class="t-foot note">{t('ce.nameHint')}</p>
    {#if o.kind !== 'school'}<!-- a school's comes from KBTU's site (schools.json) -->
      <label class="field"><span class="t-cap">{t('ce.abbr')}</span><input bind:value={f.abbr} maxlength="8" /></label>
      <p class="t-foot note">{t('ce.abbrHint')}</p>
    {/if}
    {#if !logo}
      <p class="t-foot note">{t('ce.logoOr')}</p>
      <div class="ep"><LookPick bind:emoji={f.emoji} bind:color={() => COVERS[f.cover], (c) => (f.cover = COVERS.indexOf(c))} colors={COVERS} size={26} /></div>
    {/if}
    <label class="field"><span class="t-cap">{t('nc.about')}</span><textarea bind:value={f.description} maxlength="600" rows="3" placeholder={t('nc.aboutPh')} use:grow></textarea></label>
    <p class="t-foot note">{t('ce.aboutHint')}</p>

    <h3 class="t-cap cap">{t('ce.links')}</h3>
    <p class="t-foot note">{t('ce.linksNote')}</p>
    <LinksEdit bind:links={f.links} />

    <label class="switch hide"><span><b>{t('ce.hideMembers')}</b><i class="t-foot">{t('ce.hideMembersNote')}</i></span>
      <input type="checkbox" role="switch" bind:checked={f.hidden} /></label>

    <ShortLinks org={id} />
  {/if}

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} disabled={!ready} onclick={save}>{t('common.save')}</Button>
  {/snippet}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 14px; }
  .pv { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
  .pv span { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .pv b { font: 720 18px/1.2 var(--font-display); }
  .pv i { font: 600 12.5px/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .field { margin-bottom: 12px; }
  .field textarea { min-height: 0; color: var(--text); }
  .ep { margin-bottom: 14px; }
  .cap { margin: 6px 2px 2px; }
  .note { margin: 0 2px 10px; }
  .lg { display: flex; gap: 8px; margin: -2px 0 12px; }
  .pill { display: inline-flex; align-items: center; gap: 7px; height: 38px; padding: 0 15px 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 620 14px/1 var(--font-text); }
  .pill input { display: none; }
  .pill.off { background: var(--surface-2); color: var(--text-2); }
  .pill.busy { opacity: 0.6; animation: pulse 1.1s ease-in-out infinite; }
  .wait { display: flex; flex-direction: column; gap: 12px; }
  .wait span { height: 60px; border-radius: var(--r-m); background: var(--surface-2); animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  .hide { margin-top: 22px; }
</style>
