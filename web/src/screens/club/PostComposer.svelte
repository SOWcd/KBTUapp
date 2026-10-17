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
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { POST_TAGS } from '../../lib/posts';
  import { shrink } from '../../lib/photo';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  let { overlay, org, post }: { overlay: Overlay; org: Id; post?: Post } = $props();
  const mine = $derived([...(session.me?.memberships ?? [])].filter((m) => m.role !== 'member').sort(byRank));
  let pick = $state(0);
  $effect.pre(() => { if (!pick) pick = org; });
  const club = $derived(mine.find((m) => m.org.id === pick)?.org);
  // "Important" messages the club's members (once a day per club), so it's Vice+'s (owner, Oct 13)
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
  // there, never a grey button that doesn't say why (a tester, Oct 5)
  let titleEl = $state<HTMLInputElement>();
  let tried = $state(false);
  const noTitle = $derived(title.trim().length < 2);
  const needTitle = () => { tried = true; haptic.error(); titleEl?.focus(); return noTitle; };

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
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }

  async function save() {
    if (!was || (noTitle && needTitle())) return;
    busy = true;
    try {
      await api.updatePost(was.id, patch);
      leaving = true; haptic.ok(); say(phrase('post.saved'), 'sparkles_3d');
      void loadNews();
      close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }

  // leaving with something written (or changed) asks first (Back, a tap outside, a pull down)
  let leaving = false;
  const hold = () => !leaving && (was ? changed : !!(title.trim() || body.trim() || photo));
  async function onhold() {
    if (await sheets.ask({ title: t('post.discard'), text: t('post.discardText'), ok: t('post.leave'), cancel: t('common.cancel'), danger: true })) { leaving = true; close(overlay.id); }
  }
  // the textarea grows with the text
  const grow = (el: HTMLTextAreaElement) => { const fit = () => { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }; fit(); el.addEventListener('input', fit); };
</script>

<Sheet {overlay} tall title={was ? t('post.edit') : t('post.new')} {hold} {onhold}>
  <h2 class="t-h2 hd">{was ? t('post.edit') : t('post.new')}</h2>

  {#if !was && mine.length > 1}
    <div class="clubs hscroll" data-noswipe>
      {#each mine as m (m.org.id)}
        <button class:on={m.org.id === pick} onclick={() => (pick = m.org.id)}><OrgLogo org={m.org} size={22} /><span class="ellipsis">{m.org.name}</span></button>
      {/each}
    </div>
  {:else if club}
    <p class="from"><OrgLogo org={club} size={22} /><b>{club.name}</b></p>
  {/if}
  <!-- an event announces itself in News once published: no post for it as well (owner, Oct 13) -->
  {#if !was && events && pick}<button class="tip" onclick={() => sheets.editor(pick!)}><CalendarPlus size={18} /><span>{t('post.eventTip')}</span><ChevronRight size={16} /></button>{/if}

  {#if photo}
    <div class="shot"><img src={photo.url} alt="" /><button class="rm" aria-label="×" onclick={() => (photo = null)}><X size={18} /></button></div>
  {:else}
    <label class="add" class:busy={uploading}>
      <ImagePlus size={24} /><span>{t('post.photo')}</span>
      <input type="file" accept="image/*" onchange={pickPhoto} disabled={uploading} />
    </label>
  {/if}

  <input class="title" class:bad={tried && noTitle} bind:this={titleEl} bind:value={title} placeholder={t('post.title')} maxlength="120" enterkeyhint="next" />
  {#if tried && noTitle}<p class="err">{t('post.needTitle')}</p>{/if}
  <textarea class="text" bind:value={body} placeholder={t('post.body')} maxlength="2000" rows="3" use:grow></textarea>

  <p class="t-cap lbl">{t('post.tag')}</p>
  <div class="tags">
    <button class:on={tag === null} onclick={() => (tag = null)}>{t('post.noTag')}</button>
    {#each POST_TAGS.filter((x) => x !== 'important' || vice || tag === x) as x (x)}<button class:on={tag === x} onclick={() => (tag = x)}>{t(`tag.${x}`)}</button>{/each}
  </div>
  {#if tag === 'important' && !was && !(broadcast && toClubs)}<p class="t-foot note">{t('post.importantNote')}</p>{/if}

  {#if broadcast && !was}
    <p class="t-cap lbl">{t('post.audience')}</p>
    <div class="seg wide"><button class:on={toClubs} onclick={() => (toClubs = true)}>{t('post.toClubs')}</button><button class:on={!toClubs} onclick={() => (toClubs = false)}>{t('post.toPublic')}</button></div>
    {#if toClubs}<p class="t-foot note">{t('post.clubsNote')}</p>{/if}
  {/if}

  <label class="switch"><span><b>{t('post.pin')}</b><i>{t('post.pinNote')}</i></span><input type="checkbox" role="switch" bind:checked={pinned} /></label>

  {#snippet footer()}
    {#if was}<Button kind="primary" size="l" full loading={busy} disabled={uploading || !changed} onclick={save}>{t('common.save')}</Button>
    {:else}<Button kind="primary" size="l" full loading={busy} disabled={uploading || !(title.trim() || body.trim() || photo)} onclick={publish}>{t('post.publish')}</Button>{/if}
  {/snippet}
</Sheet>

<style>
  .tip { display: flex; align-items: center; gap: 10px; width: 100%; margin-bottom: 12px; padding: 10px 12px; border-radius: var(--r-m); background: var(--accent-soft);
    color: var(--accent-text); font: 600 13.5px/1.3 var(--font-text); text-align: left; }
  .tip span { flex: 1; }
  .tip :global(svg) { flex: none; }
  .hd { margin: 4px 0 12px; }
  .from { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font: 600 14px/1 var(--font-text); }
  .clubs { gap: 6px; margin: 0 calc(-1 * var(--gutter)) 12px; padding: 0 var(--gutter); }
  .clubs button { flex: none; display: inline-flex; align-items: center; gap: 6px; max-width: 220px; height: 36px; padding: 0 12px 0 7px; border-radius: var(--r-full);
    background: var(--surface-2); font: 620 13.5px/1 var(--font-text); }
  .clubs button.on { background: var(--text); color: var(--bg); }

  .add { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; height: 112px; border-radius: 18px; color: var(--accent-text);
    border: 1.5px dashed color-mix(in srgb, var(--accent) 45%, transparent); background: var(--accent-soft); font: 620 14px/1 var(--font-text); }
  .add input { display: none; }
  .add.busy { opacity: 0.6; animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.35; } }
  .shot { position: relative; }
  .shot img { width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-radius: 18px; display: block; animation: in 360ms cubic-bezier(.2, .9, .25, 1) backwards; }
  @keyframes in { from { opacity: 0; transform: scale(0.96); } }
  .rm { position: absolute; top: 8px; right: 8px; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    color: #fff; background: rgba(10, 12, 24, 0.5); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); }

  .title { width: 100%; margin-top: 14px; padding: 4px 2px; background: none; color: var(--text); font: 740 21px/1.25 var(--font-display); letter-spacing: -0.02em; }
  .text { width: 100%; min-height: 72px; margin-top: 6px; padding: 4px 2px; resize: none; background: none; color: var(--text); font: 450 16px/1.5 var(--font-text); }
  .title::placeholder, .text::placeholder { color: var(--text-3); }
  .title.bad::placeholder { color: var(--danger-text); }
  .err { margin: 2px 2px 0; font: 600 13px/1.3 var(--font-text); color: var(--danger-text); }

  .lbl { margin: 14px 0 8px; }
  .tags { display: flex; flex-wrap: wrap; gap: 6px; }
  .tags button { height: 32px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text-2); font: 620 13px/1 var(--font-text); }
  .tags button.on { background: var(--text); color: var(--bg); }
  .seg.wide { display: flex; }
  .seg.wide button { flex: 1; }
  .note { margin-top: 6px; }
  .switch { margin-top: 16px; }
</style>
