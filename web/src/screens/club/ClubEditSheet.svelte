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
  import PencilLine from '@lucide/svelte/icons/pencil-line';
  import Button from '../../ui/Button.svelte';
  import OrgLogo, { COVERS } from '../../ui/OrgLogo.svelte';
  import ShortLinks from './ShortLinks.svelte';
  import OrgChats from './OrgChats.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';

  let { overlay, id, at }: { overlay: Overlay; id: Id; at?: 'chats' } = $props();
  // at 'chats' (the bot's "open in Studio" after linking a chat, the catalog sheet's "your club's channel?"): the
  // chats list in view once the form is there
  let chatsAt = $state<HTMLElement>();
  let shown = false;
  $effect(() => { if (at === 'chats' && o && chatsAt && !shown) { shown = true; setTimeout(() => chatsAt?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 320); } });

  let o = $state<Org | null>(null);
  // the logo: one of my uploads, or null — then the emoji on its cover shows again
  let logo = $state<{ id?: Id; url: string } | null>(null);
  let f = $state({ name: '', abbr: '', emoji: '', cover: 0, description: '', links: [] as LinkDraft[], hidden: false });
  $effect(() => {
    api.org(id).then((got) => { const x = original(got); o = x; /* as typed, never a translation (PLAN 9) */ f = { name: x.name, abbr: x.abbr ?? '', emoji: x.emoji, cover: x.cover, description: x.description ?? '', links: x.links.map(linkDraft), hidden: x.membersHidden }; logo = x.logo ? { url: x.logo } : null; })
      .catch(() => { say(t('common.error'), 'warning_3d'); close(overlay.id); });
  });
  let uploading = $state(false);
  let fileEl = $state<HTMLInputElement>();
  async function pickLogo(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, file = el.files?.[0];
    el.value = '';
    if (!file) return;
    if (file.size > 30 * 1024 * 1024) { say(t('ed.photoBig'), 'pleading_face_3d'); return; }
    const cut = await sheets.cropPhoto(file); // framed first, as my own photo (a president asked, Nov 2)
    if (!cut) return;
    uploading = true;
    try { const m = await api.uploadPhoto(await shrink(cut, 1200)); logo = { id: m.id, url: m.thumb }; haptic.ok(); }
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
      say(e instanceof ApiErr && e.message === 'taken' ? t('nc.taken') : e instanceof ApiErr && e.code === 'bad_input' ? t('nc.bad') : t('common.error'), 'warning_3d');
    } finally { busy = false; }
  }
  const hold = () => !leaving && changed;
  async function onhold() {
    if (await sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('common.cancel'), danger: true })) { leaving = true; close(overlay.id); }
  }
</script>

<Sheet {overlay} icon={PencilLine} full title={t('ce.title')} {hold} {onhold}>
  {#if !o || !preview}
    <Skeleton n={2} />
  {:else}
    <div class="pg">
      <Group footnote={t('ce.sub')}>
        <Row title={preview.name} subtitle={o.official ? t('clubs.official') : t('club.initiative')}>
          {#snippet lead()}<OrgLogo org={preview} size={48} />{/snippet}
        </Row>
      </Group>
      <div class="lg">
        <input bind:this={fileEl} type="file" accept="image/*" onchange={pickLogo} hidden />
        <Button kind="tinted" size="s" loading={uploading} onclick={() => fileEl?.click()}>{#snippet icon()}<ImagePlus size={17} />{/snippet}{logo ? t('ce.logoChange') : t('ce.logoAdd')}</Button>
        {#if logo}<Button kind="secondary" size="s" onclick={() => (logo = null)}>{#snippet icon()}<X size={16} />{/snippet}{t('ce.logoRemove')}</Button>{/if}
      </div>

      <div class="fl">
        <Field label={t('nc.name')} bind:value={f.name} maxlength={60} />
        <p class="note">{t('ce.nameHint')}</p>
      </div>
      {#if o.kind !== 'school'}<!-- a school's comes from KBTU's site (schools.json) -->
        <div class="fl">
          <Field label={t('ce.abbr')} bind:value={f.abbr} maxlength={8} />
          <p class="note">{t('ce.abbrHint')}</p>
        </div>
      {/if}
      {#if !logo}
        <div class="fl">
          <p class="note top">{t('ce.logoOr')}</p>
          <LookPick bind:emoji={f.emoji} bind:color={() => COVERS[f.cover], (c) => (f.cover = COVERS.indexOf(c))} colors={COVERS} size={26} />
        </div>
      {/if}
      <div class="fl">
        <Field label={t('nc.about')} bind:value={f.description} multiline maxlength={600} placeholder={t('nc.aboutPh')} />
        <p class="note">{t('ce.aboutHint')}</p>
      </div>

      <!-- engine: Group with free content (a caption and a footnote around something that isn't Rows, here ui/LinksEdit) -->
      <section>
        <h3 class="cap">{t('ce.links')}</h3>
        <p class="note under">{t('ce.linksNote')}</p>
        <LinksEdit bind:links={f.links} />
      </section>

      <Group footnote={t('ce.hideMembersNote')}>
        <Row title={t('ce.hideMembers')} accessory="switch" checked={f.hidden} onchange={(v) => (f.hidden = v)} />
      </Group>

      <div bind:this={chatsAt}><OrgChats org={id} /></div>
      <ShortLinks org={id} />
    </div>
  {/if}

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} disabled={!ready} onclick={save}>{t('common.save')}</Button>
  {/snippet}
</Sheet>

<style>
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-1); }
  .lg { display: flex; flex-wrap: wrap; gap: var(--s-2); margin-top: calc(var(--s-3) - var(--gap-group)); }
  .fl { display: flex; flex-direction: column; gap: var(--s-2); }
  /* Group's caption and footnote, for content that isn't Rows */
  .cap { margin: 0 var(--s-1) 10px; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .note { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  .note.top { margin-bottom: var(--s-1); }
  .note.under { margin: 0 var(--s-1) var(--s-3); }
</style>
