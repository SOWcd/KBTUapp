<script lang="ts">
  // Who has the skills a request asks for (open to projects): a card each; "get in touch" goes to them in the bot,
  // and nothing of either side's Telegram shows until they accept.
  import { api, type ForumCard, type Id } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import PersonCards from './PersonCards.svelte';

  let { overlay, ask, title }: { overlay: Overlay; ask: Id; title: string } = $props();
  let list = $state<ForumCard[] | null>(null);
  $effect(() => { api.askPeople(ask).then((l) => (list = l)).catch(() => (list = [])); });
</script>

<Sheet {overlay} tall title={t('fo.people')}>
  <h2 class="t-h2 hd">{t('fo.people')}</h2>
  <p class="t-foot sub">{title}</p>
  <PersonCards cards={list ?? []} />
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 12px; }
</style>
