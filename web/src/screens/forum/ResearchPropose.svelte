<script lang="ts">
  import ChartNoAxesColumn from '@lucide/svelte/icons/chart-no-axes-column';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { loadResearchRequests } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const CONSENT = '2026-11-24'; // server research.CONSENT
  let title = $state(''), goal = $state(''), questions = $state(''), organizer = $state(''), busy = $state(false);
  const lines = $derived(questions.split(/\r\n|[\n\r\v\f\u001c-\u001e\u0085\u2028\u2029]/).filter((q) => q.trim()));
  const valid = $derived(!!title.trim() && !!goal.trim() && !!organizer.trim() && lines.length > 0 && lines.length <= 10);
  async function send() {
    if (busy || !valid) return;
    busy = true;
    try {
      await api.proposeResearch({ title: title.trim(), goal: goal.trim(), questions: questions.trim(), organizer: organizer.trim(), consent: CONSENT });
      haptic.ok(); say(t('research.sent'), 'raising_hands_3d_default'); close(overlay.id);
      void loadResearchRequests();
    } catch (e) {
      haptic.error();
      const code = e instanceof ApiErr ? e.code : null;
      say(t(code === 'rate_limited' ? 'research.cap' : code === 'need_student' ? 'research.studentOnly' : 'common.error'), 'warning_3d');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={ChartNoAxesColumn} title={t('research.propose')} heading={t('research.propose')} full>
  <div class="proposal">
    <p class="t-body dim">{t('research.intro')}</p>
    <Field label={t('research.name')} bind:value={title} maxlength={120} />
    <Field label={t('research.goal')} bind:value={goal} multiline rows={3} maxlength={1200} />
    <Field label={t('research.questions')} bind:value={questions} multiline rows={6} maxlength={4000} error={lines.length > 10 ? t('research.tooMany') : undefined} />
    <Field label={t('research.organizer')} bind:value={organizer} maxlength={200} />
  </div>
  {#snippet footer()}
    <p class="t-foot consent">{t('research.consent')}</p>
    <Button kind="primary" size="l" full loading={busy} disabled={!valid} onclick={send}>{t('research.send')}</Button>
  {/snippet}
</Sheet>

<style>
  .proposal { display: flex; flex-direction: column; gap: var(--s-4); }
  .dim { margin: 0; color: var(--text-2); }
  .consent { margin: 0 0 var(--s-2); color: var(--text-2); }
</style>
