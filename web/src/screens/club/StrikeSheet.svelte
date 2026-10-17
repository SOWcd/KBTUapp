<script lang="ts">
  // A strike for someone on probation (Team 2.0, SPEC §2b): why — a missed meeting, a missed important event, or
  // something else said in a line. They see it and why, and the bot tells them "n of 3"; the third asks the President
  // and Vice whether they stay.
  import { api, ApiErr, type Id, type Strike } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, org, user, name, ondone }: { overlay: Overlay; org: Id; user: Id; name: string; ondone?: () => void } = $props();

  const REASONS: Strike['reason'][] = ['meeting', 'event', 'other'];
  let reason = $state<Strike['reason']>('meeting');
  let note = $state('');
  let busy = $state(false);
  const ready = $derived(reason !== 'other' || note.trim().length > 0);

  async function give() {
    if (!ready || busy) return;
    busy = true;
    try {
      const team = await api.addStrike(org, user, reason, note.trim());
      haptic.warn(); say(t('strike.given', { n: team.find((x) => x.person.id === user)?.strikes ?? 1 }), 'pleading_face_3d');
      ondone?.();
      close(overlay.id);
    } catch (e) {
      haptic.error(); say(e instanceof ApiErr && e.message === 'probation' ? t('strike.notOn') : t('common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('strike.title', { name })}>
  <h2 class="t-h2 hd">{t('strike.title', { name })}</h2>
  <p class="t-foot sub">{t('strike.hint')}</p>
  <div class="opts" role="radiogroup" aria-label={t('strike.title', { name })}>
    {#each REASONS as r (r)}
      <button role="radio" aria-checked={reason === r} class:on={reason === r} onclick={() => { reason = r; haptic.select(); }}>{t(`strike.${r}`)}</button>
    {/each}
  </div>
  <textarea bind:value={note} maxlength="140" rows="2" placeholder={reason === 'other' ? t('strike.notePhOther') : t('strike.notePh')}></textarea>

  {#snippet footer()}
    <Button kind="danger" size="l" full loading={busy} disabled={!ready} onclick={give}>{t('strike.give')}</Button>
  {/snippet}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 14px; text-wrap: pretty; }
  .opts { display: flex; flex-direction: column; gap: 8px; }
  .opts button { min-height: 48px; padding: 0 16px; border-radius: var(--r-m); background: var(--surface-2); text-align: left; font: 620 15.5px/1.2 var(--font-text); color: var(--text);
    box-shadow: inset 0 0 0 1.5px transparent; transition: box-shadow var(--t-fast), background-color var(--t-fast); }
  .opts button.on { background: var(--danger-soft); color: var(--danger-text); box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--danger) 55%, transparent); }
  textarea { width: 100%; margin-top: 12px; padding: 12px 14px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text); resize: none; font: 450 16px/1.4 var(--font-text); }
  textarea::placeholder { color: var(--text-3); }
</style>
