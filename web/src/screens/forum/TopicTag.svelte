<script lang="ts">
  // A thread's topic as a line icon and its name in the topic's colour: above a card's words, in the thread's sheet.
  import type { Topic } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { TOPIC_ICON, TOPIC_TINT } from '../../lib/forum';

  let { topic }: { topic: Topic } = $props();
  const Icon = $derived(TOPIC_ICON[topic]);
</script>

<span class="tag" style:--tint={TOPIC_TINT[topic]}><Icon size={14} strokeWidth={2.4} />{t(`bd.topic.${topic}`)}</span>

<style>
  .tag { display: inline-flex; align-items: center; gap: 5px; color: var(--tint); font: 650 13px/1 var(--font-text); white-space: nowrap; }
</style>
