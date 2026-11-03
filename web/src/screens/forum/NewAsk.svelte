<script lang="ts">
  // A request: a project (1-3 skills) or a quick bit of help (skills optional), for 1, 3, 7 or 30 days. The AI reads
  // it first; without a clear OK it waits for a moderator.
  import { api, ApiErr, type Ask, type Skill } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Segmented from '../../ui/Segmented.svelte';
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

<Sheet {overlay} icon={SquarePen} full title={t('fo.newAsk')}>
  <div class="col">
    <div>
      <Segmented items={(['project', 'help'] as const).map((k) => ({ value: k, label: t(`fo.kind.${k}`) }))} bind:value={kind} label={t('fo.newAsk')} />
      <p class="note">{t(`fo.kindNote.${kind}`)}</p>
    </div>
    <Field label={t('fo.askTitle')} bind:value={title} maxlength={80} placeholder={t(`fo.askTitlePh.${kind}`)} />
    <Field label={t('fo.askBody')} bind:value={body} maxlength={500} multiline rows={4} />
    <!-- a form's own small label, as Field's (the picker and the switch aren't Fields) -->
    <div>
      <h3 class="lb">{t(kind === 'project' ? 'fo.askSkills' : 'fo.askSkillsOpt')}</h3>
      <SkillPicker bind:chosen={skills} max={3} />
    </div>
    <div>
      <h3 class="lb">{t('fo.days')}</h3>
      <Segmented items={([1, 3, 7, 30] as const).map((d) => ({ value: d, label: tn('fo.dayN', d) }))} bind:value={days} label={t('fo.days')} />
    </div>
  </div>
  {#snippet footer()}<Button kind="primary" size="l" full loading={busy} disabled={!ok} onclick={send}>{t('fo.post')}</Button>{/snippet}
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--s-4); padding-top: var(--s-1); }
  .note { margin: var(--s-2) var(--s-4) 0; font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .lb { margin-bottom: 6px; padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
</style>
