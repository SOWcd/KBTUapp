<script lang="ts">
  // The club's profile (Vice+, SPEC §2), Settings' way (owner, Nov 9: the old form was "maximally unclear, a lot of text"):
  // the logo, rows that say what is set, each long thing a tap deeper. A text's page writes straight into this form, so
  // Back there keeps it; Save sends only what changed, and leaving with changes asks first. Chats and short links save
  // on their own pages, at once.
  import { onMount, untrack, type Snippet } from 'svelte';
  import { api, ApiErr, original, type Id, type Org, type OrgCategory, type OrgPatch } from '../../lib/api';
  import { say, close, open, type Overlay } from '../../lib/state/ui.svelte';
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
  import Pane from '../../ui/Pane.svelte';
  import PencilLine from '@lucide/svelte/icons/pencil-line';
  import Button from '../../ui/Button.svelte';
  import OrgLogo, { COVERS } from '../../ui/OrgLogo.svelte';
  import ShortLinks from './ShortLinks.svelte';
  import OrgChats from './OrgChats.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import { menu } from '../../ui/menu';

  let { overlay, id, at }: { overlay: Overlay; id: Id; at?: 'chats' } = $props();
  const CATEGORIES: OrgCategory[] = ['it', 'art', 'sport', 'business', 'science', 'volunteer'];

  let o = $state<Org | null>(null);
  // the logo: one of my uploads, or null — then the emoji on its cover shows again
  let logo = $state<{ id?: Id; url: string } | null>(null);
  let f = $state({ name: '', abbr: '', emoji: '', cover: 0, description: '', links: [] as LinkDraft[], hidden: false, category: null as OrgCategory | null });
  // as typed, never a translation (PLAN 9)
  function fill(x: Org) {
    o = x;
    f = { name: x.name, abbr: x.abbr ?? '', emoji: x.emoji, cover: x.cover, description: x.description ?? '', links: x.links.map(linkDraft), hidden: x.membersHidden, category: x.category };
    logo = x.logo ? { url: x.logo } : null;
  }
  // the page opens full from the store (it has the club from the app's start); the server's copy replaces it unless I've begun
  untrack(() => { const had = [...data.orgs, ...data.small].find((x) => x.id === id); if (had) fill(original(had)); });
  $effect(() => {
    api.org(id).then((got) => { const x = original(got); if (changed) o = x; else fill(x); })
      .catch(() => { say(t('common.error'), 'warning_3d'); close(overlay.id); });
  });

  let chatsN = $state<number>();
  let shortN = $state<number>();
  $effect(() => {
    api.orgChats(id).then((l) => (chatsN = l.length)).catch(() => {});
    api.shortLinks(id).then((l) => (shortN = l.length)).catch(() => {});
  });

  // keeps: the page's fields write into this form, so its Back never asks; a page with its own unsent text does
  function page(title: string, children: Snippet, keeps = true) { haptic.tap(); open(Pane, { title, icon: PencilLine, children, keeps }); }
  // at 'chats' (the bot's "open in Studio" after linking a chat, the catalog sheet's "your club's channel?"): straight there
  onMount(() => { if (at === 'chats') page(t('oc.studio'), chatsPage, false); });
  const focused = (n: HTMLElement) => { n.querySelector<HTMLElement>('input, textarea')?.focus({ preventScroll: true }); };

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
  async function dropLogo() {
    if (await sheets.ask({ title: t('ce.logoRemoveAsk'), ok: t('oc.drop'), cancel: t('common.cancel'), danger: true })) logo = null;
  }
  function change(e: MouseEvent) {
    if (uploading) return;
    menu(e.currentTarget as Element, [
      { label: t(logo ? 'ce.logoChange' : 'ce.logoAdd'), instant: true, onselect: () => fileEl?.click() }, // instant: a file picker needs the tap's own moment
      logo ? { label: t('ce.logoRemove'), destructive: true, onselect: dropLogo } : { label: t('ce.look'), onselect: () => page(t('ce.look'), lookPage) },
    ]);
  }

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
    if (f.category !== o.category) p.category = f.category;
    return p;
  });
  const changed = $derived(Object.keys(patch).length > 0);
  const nameBad = $derived(f.name.trim().length < 2);
  const abbrBad = $derived(f.abbr.trim() !== (o?.abbr ?? '') && !/^\S{2,8}$/.test(f.abbr.trim()));
  const ready = $derived(changed && !nameBad && !abbrBad && linksOk);
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
      say(e instanceof ApiErr && e.message === 'taken' ? t('nc.taken') : e instanceof ApiErr && (e.message === 'club_word' || e.message === 'emoji') ? t(`nc.${e.message}`) : e instanceof ApiErr && e.code === 'bad_input' ? t('nc.bad') : t('common.error'), 'warning_3d');
    } finally { busy = false; }
  }
  const hold = () => !leaving && changed;
  async function onhold() {
    if (await sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('common.cancel'), danger: true })) { leaving = true; close(overlay.id); }
  }
</script>

<!-- a label says what a mistake would be: the page's large title already says what the field is -->
{#snippet namePage()}<div {@attach focused}><Field label={t('ce.nameHint')} bind:value={f.name} maxlength={60} /></div>{/snippet}
{#snippet abbrPage()}<div {@attach focused}><Field label={t('ce.abbrHint')} bind:value={f.abbr} maxlength={8} /></div>{/snippet}
{#snippet aboutPage()}<div {@attach focused}><Field label={t('ce.aboutHint')} bind:value={f.description} multiline rows={5} maxlength={600} placeholder={t('nc.aboutPh')} /></div>{/snippet}
{#snippet lookPage()}
  {#if preview}<div class="hero"><OrgLogo org={preview} size={88} /></div>{/if}
  <LookPick bind:emoji={f.emoji} bind:color={() => COVERS[f.cover], (c) => (f.cover = COVERS.indexOf(c))} colors={COVERS} size={26} />
{/snippet}
{#snippet chatsPage()}<OrgChats org={id} bind:n={chatsN} />{/snippet}
{#snippet shortPage()}<ShortLinks org={id} bind:n={shortN} />{/snippet}

<Sheet {overlay} icon={PencilLine} full title={t('ce.title')} {hold} {onhold}>
  {#if !o || !preview}
    <Skeleton n={2} />
  {:else}
    <div class="pg">
      <div class="hero">
        <input bind:this={fileEl} type="file" accept="image/*" onchange={pickLogo} hidden />
        <button class="lg" onclick={change} aria-label={t('ce.change')}><OrgLogo org={preview} size={88} /></button>
        <Button kind="plain" size="s" loading={uploading} onclick={change}>{t('ce.change')}</Button>
      </div>

      <Group>
        <Row title={t('nc.name')} value={f.name.trim()} invalid={nameBad} accessory="chevron" onclick={() => page(t('nc.name'), namePage)} />
        {#if o.kind !== 'school'}<!-- a school's comes from KBTU's site (schools.json) -->
          <Row title={t('ce.abbr')} value={f.abbr.trim()} invalid={abbrBad} accessory="chevron" onclick={() => page(t('ce.abbr'), abbrPage)} />
        {/if}
        <Row title={t('nc.about')} value={f.description.trim()} accessory="chevron" onclick={() => page(t('nc.about'), aboutPage)} />
        <Row title={t('clubs.category')} value={f.category ? t(`clubs.cat.${f.category}`) : t('clubs.noCategory')} menu={[null, ...CATEGORIES].map((c) => ({ label: c ? t(`clubs.cat.${c}`) : t('clubs.noCategory'), checked: f.category === c, onselect: () => (f.category = c) }))} />
      </Group>

      <LinksEdit bind:links={f.links} caption={t('ce.links')} />

      <Group>
        <Row title={t('oc.studio')} value={chatsN ? String(chatsN) : undefined} accessory="chevron" onclick={() => page(t('oc.studio'), chatsPage, false)} />
        <Row title={t('sl.title')} value={shortN ? String(shortN) : undefined} accessory="chevron" onclick={() => page(t('sl.title'), shortPage, false)} />
      </Group>

      <Group footnote={t('ce.hideMembersNote')}>
        <Row title={t('ce.hideMembers')} accessory="switch" checked={f.hidden} onchange={(v) => (f.hidden = v)} />
      </Group>
    </div>
  {/if}

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} disabled={!ready} onclick={save}>{t('common.save')}</Button>
  {/snippet}
</Sheet>

<style>
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-1); }
  .hero { display: flex; flex-direction: column; align-items: center; gap: var(--s-1); }
  .lg { display: block; border-radius: 50%; }
</style>
