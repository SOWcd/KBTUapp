<script lang="ts">
  // A request: a project (1-3 skills) or a quick bit of help (skills optional), for 1, 3, 7 or 30 days. The AI reads
  // it first; without a clear OK it waits for a moderator.
  import { api, ApiErr, type Ask, type Skill } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import SkillPicker from './SkillPicker.svelte';

  let { overlay, onmade }: { overlay: Overlay; onmade?: () => void } = $props();
  let kind = $state<Ask['kind']>('project'), title = $state(''), body = $state(''), skills = $state<Skill[]>([]);
  let days = $state<1 | 3 | 7 | 30>(7), busy = $state(false);
  $effect(() => { days = kind === 'help' ? 1 : 7; });
  const ok = $derived(title.trim().length >= 3 && (kind === 'help' || skills.length > 0));
  async function send() {
    busy = true;
    try {
      const a = await api.newAsk({ kind, title: title.trim(), body: body.trim(), skills: skills.map((s) => s.id), days });
      haptic.ok(); say(t(a.status === 'held' ? 'fo.heldSay' : 'fo.postedSay'), 'raising_hands_3d_default');
      onmade?.(); close(overlay.id);
    } catch (e) { haptic.error(); say(t(e instanceof ApiErr && e.message === 'asks' ? 'fo.tooMany' : 'common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} full title={t('fo.newAsk')}>
  <div class="seg kinds" role="tablist">
    {#each ['project', 'help'] as const as k (k)}<button class:on={kind === k} onclick={() => (kind = k)}>{t(`fo.kind.${k}`)}</button>{/each}
  </div>
  <p class="t-foot note">{t(`fo.kindNote.${kind}`)}</p>
  <label class="field"><span class="t-cap">{t('fo.askTitle')}</span><input bind:value={title} maxlength="80" placeholder={t(`fo.askTitlePh.${kind}`)} /></label>
  <label class="field"><span class="t-cap">{t('fo.askBody')}</span><textarea bind:value={body} maxlength="500" rows="4"></textarea></label>
  <h3 class="t-cap cap">{t(kind === 'project' ? 'fo.askSkills' : 'fo.askSkillsOpt')}</h3>
  <SkillPicker bind:chosen={skills} max={3} />
  <h3 class="t-cap cap">{t('fo.days')}</h3>
  <div class="seg" role="tablist">{#each [1, 3, 7, 30] as const as d (d)}<button class:on={days === d} onclick={() => (days = d)}>{tn('fo.dayN', d)}</button>{/each}</div>
  {#snippet footer()}<Button kind="primary" size="l" full loading={busy} disabled={!ok} onclick={send}>{t('fo.post')}</Button>{/snippet}
</Sheet>

<style>
  .kinds { margin-top: 4px; }
  .note { margin: 8px 4px 14px; }
  .field { margin-bottom: 10px; }
  .cap { margin: 16px 4px 0; }
</style>
