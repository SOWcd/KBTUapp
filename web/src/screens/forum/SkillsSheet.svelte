<script lang="ts">
  // My skills in the forum (up to 5), saved as a whole.
  import { api, type Skill } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Wrench from '@lucide/svelte/icons/wrench';
  import Button from '../../ui/Button.svelte';
  import SkillPicker from './SkillPicker.svelte';

  let { overlay, onsaved }: { overlay: Overlay; onsaved?: () => void } = $props();
  let chosen = $state<Skill[]>([]), busy = $state(false);
  $effect(() => { api.forumMe().then((m) => (chosen = m.skills)).catch(() => {}); });
  async function save() {
    busy = true;
    try { await api.setForumMe({ skills: chosen.map((s) => s.id) }); haptic.ok(); onsaved?.(); close(overlay.id); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={Wrench} tall title={t('fo.mySkills')}>
  <p class="note">{t('fo.mySkillsNote')}</p>
  <SkillPicker bind:chosen max={5} />
  {#snippet footer()}<Button kind="primary" size="l" full loading={busy} onclick={save}>{t('common.save')}</Button>{/snippet}
</Sheet>

<style>
  .note { margin: 0 var(--s-4) var(--s-1); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
</style>
