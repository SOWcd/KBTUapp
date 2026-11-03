<script lang="ts">
  // A new post (SPEC §4.10), Head+: the club (if I lead several), a photo (re-encoded by the server like a cover), the
  // title, the text, a label, who sees it (broadcast orgs only: every club member, with a bot message, or every
  // student), and the pin. Publish shows it in News at once; leaving with something written asks first.
  // `post`: editing it (its club's Head+) — the same form, filled; who sees it stays; Save sends only what changed.
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import X from '@lucide/svelte/icons/x';
  import { untrack } from 'svelte';
  import { api, type Id, type Media, type Post, type PostPatch, type PostTag } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { data, phrase, loadNews } from '../../lib/state/data.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { byRank, may } from '../../lib/perms';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import { POST_TAGS } from '../../lib/posts';
  import { shrink } from '../../lib/photo';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import Button from '../../ui/Button.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import IconButton from '../../ui/IconButton.svelte';

  let { overlay, org, post }: { overlay: Overlay; org: Id; post?: Post } = $props();
  const mine = $derived([...(session.me?.memberships ?? [])].filter((m) => m.role !== 'member').sort(byRank));
  const pick = $derived(org);
  const club = $derived(mine.find((m) => m.org.id === pick)?.org);
  // "Important" messages the club's members (once a day per club), so it's Vice+'s
  const vice = $derived(may(mine.find((m) => m.org.id === pick), 'team'));
  const events = $derived(may(mine.find((m) => m.org.id === pick), 'events'));
  const broadcast = $derived(!!data.orgs.find((o) => o.id === pick)?.canBroadcast || club?.kind === 'office' || club?.kind === 'app');

  const was = untrack(() => post); // the post as it was when the form opened
  let title = $state(was?.title ?? '');
  let body = $state(was?.body ?? '');
  let tag = $state<string | null>(was?.tag ?? null); // older posts may carry a free-text label: kept unless changed
  let toClubs = $state(true);
  let pinned = $state(was?.pinned ?? false);
  let photo = $state<Media | null>(was?.photo ?? null);
  const patch = $derived.by(() => {
    const p: PostPatch = {};
    if (!was) return p;
    if (title.trim() !== was.title) p.title = title.trim();
    if (body.trim() !== was.body) p.body = body.trim();
    if (tag !== was.tag) p.tag = tag;
    if ((photo?.url ?? null) !== (was.photo?.url ?? null)) p.photoId = photo?.id ?? null;
    if (pinned !== was.pinned) p.pinned = pinned;
    return p;
  });
  const changed = $derived(Object.keys(patch).length > 0);
  let uploading = $state(false);
  let busy = $state(false);
  // the title is the post's headline (the bot's message, the comments): a tap without one says so and puts the cursor
  // there, never a grey button that doesn't say why (a tester)
  // engine: Field could hand out its input (focus): found in its wrapper for now
  let titleBox = $state<HTMLElement>();
  let tried = $state(false);
  const noTitle = $derived(title.trim().length < 2);
  const needTitle = () => { tried = true; haptic.error(); titleBox?.querySelector('input')?.focus(); return noTitle; };

  async function pickPhoto(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, file = el.files?.[0];
    el.value = '';
    if (!file) return;
    if (file.size > 30 * 1024 * 1024) { say(t('ed.photoBig'), 'pleading_face_3d'); return; }
    uploading = true;
    try { photo = await api.uploadPhoto(await shrink(file)); haptic.ok(); }
    catch { haptic.error(); say(t('ed.photoBad'), 'pleading_face_3d'); }
    finally { uploading = false; }
  }

  async function publish() {
    if (noTitle && needTitle()) return;
    busy = true;
    try {
      await api.createPost(pick, { title: title.trim(), body: body.trim(), tag: tag as PostTag | null, photoId: photo?.id ?? null, audience: broadcast && toClubs ? 'clubs' : 'public', pinned });
      leaving = true; // published: nothing left to lose
      haptic.ok(); burst(); say(t('post.published'), 'party_popper_3d');
      void loadNews();
      close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }

  async function save() {
    if (!was || (noTitle && needTitle())) return;
    busy = true;
    try {
      Object.assign(was, await api.updatePost(was.id, patch)); // a story or club page showing it updates in place
      leaving = true; haptic.ok(); say(phrase('post.saved'), 'sparkles_3d');
      void loadNews();
      close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }

  // leaving with something written (or changed) asks first (Back, a tap outside, a pull down)
  let leaving = false;
  const hold = () => !leaving && (was ? changed : !!(title.trim() || body.trim() || photo));
  async function onhold() {
    if (await sheets.ask({ title: t('post.discard'), text: t('post.discardText'), ok: t('post.leave'), cancel: t('common.cancel'), danger: true })) { leaving = true; close(overlay.id); }
  }
</script>

<Sheet {overlay} icon={SquarePen} full title={was ? t('post.edit') : t('post.new')} {hold} {onhold}>
  <div class="stack">
    <!-- the club chosen in Studio, no picker -->
    {#if club}
      <p class="from"><OrgLogo org={club} size={22} /><b>{club.name}</b></p>
    {/if}
    <!-- an event announces itself in News once published: no post for it as well -->
    {#if !was && events}<Group><Row icon={CalendarPlus} title={t('post.eventTip')} accessory="chevron" onclick={() => sheets.editor(pick)} /></Group>{/if}

    {#if photo}
      <div class="shot"><img src={photo.url} alt="" /><span class="rm"><IconButton icon={X} kind="glass" size="s" label={t('ed.photoRemove')} onclick={() => (photo = null)} /></span></div>
    {:else}
      <label class="add" class:busy={uploading}>
        <ImagePlus size={24} /><span>{t('post.photo')}</span>
        <input type="file" accept="image/*" onchange={pickPhoto} disabled={uploading} />
      </label>
    {/if}

    <div bind:this={titleBox}><Field label={t('post.title')} bind:value={title} maxlength={120} error={tried && noTitle ? t('post.needTitle') : undefined} /></div>
    <Field label={t('post.text')} multiline rows={3} bind:value={body} maxlength={2000} placeholder={t('post.body')} />

    <span class="lbl">{t('post.tag')}</span>
    <div class="wrap">
      <Chip selected={tag === null} onclick={() => (tag = null)}>{t('post.noTag')}</Chip>
      {#each POST_TAGS.filter((x) => x !== 'important' || vice || tag === x) as x (x)}<Chip selected={tag === x} onclick={() => (tag = x)}>{t(`tag.${x}`)}</Chip>{/each}
    </div>
    {#if tag === 'important' && !was && !(broadcast && toClubs)}<p class="hint">{t('post.importantNote')}</p>{/if}

    {#if broadcast && !was}
      <span class="lbl">{t('post.audience')}</span>
      <Segmented items={[{ value: 'clubs', label: t('post.toClubs') }, { value: 'public', label: t('post.toPublic') }]} value={toClubs ? 'clubs' : 'public'} label={t('post.audience')}
        onchange={(v) => (toClubs = v === 'clubs')} />
      {#if toClubs}<p class="hint">{t('post.clubsNote')}</p>{/if}
    {/if}

    <Group footnote={t('post.pinNote')}><Row title={t('post.pin')} accessory="switch" checked={pinned} onchange={(on) => (pinned = on)} /></Group>
  </div>

  {#snippet footer()}
    {#if was}<Button kind="primary" size="l" full loading={busy} disabled={uploading || !changed} onclick={save}>{t('common.save')}</Button>
    {:else}<Button kind="primary" size="l" full loading={busy} disabled={uploading || !(title.trim() || body.trim() || photo)} onclick={publish}>{t('post.publish')}</Button>{/if}
  {/snippet}
</Sheet>

<style>
  .stack { display: flex; flex-direction: column; gap: var(--s-3); }
  .stack > :global(section:last-child) { margin-top: var(--s-2); }
  .from { display: flex; align-items: center; gap: var(--s-2); font: 600 var(--fs-body)/1 var(--font-text); }
  .lbl { margin: var(--s-2) var(--s-4) -6px; font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .hint { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  .wrap { display: flex; flex-wrap: wrap; gap: var(--s-2); padding-block: var(--s-1); }

  .add { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; height: 112px; border-radius: var(--r-group); color: var(--accent-text);
    background: var(--accent-soft); font: 600 var(--fs-body)/1 var(--font-text); }
  .add input { display: none; }
  .add.busy { opacity: 0.6; animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.35; } }
  .shot { position: relative; }
  .shot img { width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-radius: var(--r-group); display: block; animation: in 360ms cubic-bezier(.2, .9, .25, 1) backwards; }
  @keyframes in { from { opacity: 0; transform: scale(0.96); } }
  .rm { position: absolute; top: var(--s-2); right: var(--s-2); }
</style>
