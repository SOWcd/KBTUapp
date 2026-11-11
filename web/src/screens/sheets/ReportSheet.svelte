<script lang="ts">
  // One report sheet for everything: a post, a comment, an event, a profile, a photo. A reason, a few
  // words if they like, Send. The moderators see the reasons and the words, never who sent them.
  import Flag from '@lucide/svelte/icons/flag';
  import { api, ApiErr, type Id, type ReportReason } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';

  type Target = 'comment' | 'post' | 'event' | 'user' | 'photo' | 'ask' | 'fpost';
  let { overlay, target, id, about = '', onsent }: { overlay: Overlay; target: Target; id: Id; about?: string; onsent?: () => void } = $props();

  // a photo's own two with the Gallery on (GALLERY): it breaks the rules, or I'm in it and against it
  const REASONS = $derived<ReportReason[]>(target === 'photo' && data.galleryPost ? ['rules', 'me'] : ['spam', 'insult', 'danger', 'other']);
  let reason = $state<ReportReason | null>(null), note = $state(''), busy = $state(false);

  async function send() {
    if (!reason || busy) return;
    busy = true;
    try {
      await api.report(target, id, reason, note.trim() || undefined);
      haptic.ok();
      // a photo goes from my album at once; anything else waits for a moderator
      say(t(target === 'photo' ? 'rep.sentHidden' : 'rep.sent'), 'raising_hands_3d_default');
      onsent?.();
      close(overlay.id);
    } catch (x) {
      haptic.error();
      const code = x instanceof ApiErr ? x.code : '';
      say(t(code === 'rate_limited' ? 'rep.tooMany' : code === 'not_found' ? 'rep.gone' : 'common.error'), 'pleading_face_3d');
      if (code === 'not_found') close(overlay.id);
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('rep.title')} icon={Flag}>
  <div class="page">
    <div class="hd">
      {#if about}<p class="fs-sub faint ellipsis">{about}</p>{/if}
      <h2 class="fs-sec">{t(`rep.why.${target}`)}</h2>
    </div>
    <Group>
      {#each REASONS as r (r)}
        <Row dense title={t(`rep.${r}`)} subtitle={t(`rep.hint.${r}`)} accessory="check" checked={reason === r} onclick={() => { haptic.select(); reason = r; }} />
      {/each}
    </Group>
    <Field label={t('rep.notePh')} bind:value={note} multiline rows={3} maxlength={500} />
    <p class="fs-sub faint fine">{t('rep.anon')}</p>
  </div>

  {#snippet footer()}
    <Button kind="danger" size="l" full loading={busy} disabled={!reason} onclick={send}>{t('rep.send')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  .hd { display: flex; flex-direction: column; gap: var(--s-1); padding: 0 var(--s-1); }
  .fine { margin-top: calc(-1 * var(--s-2)); padding: 0 var(--s-4); }
</style>
