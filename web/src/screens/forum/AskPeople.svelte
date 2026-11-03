<script lang="ts">
  // Who has the skills a request asks for (open to projects): a card each; "get in touch" goes to them in the bot,
  // and nothing of either side's Telegram shows until they accept.
  import { api, type ForumCard, type Id } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import PersonCards from './PersonCards.svelte';

  let { overlay, ask, title }: { overlay: Overlay; ask: Id; title: string } = $props();
  let list = $state<ForumCard[] | null>(null);
  $effect(() => { api.askPeople(ask).then((l) => (list = l)).catch(() => (list = [])); });
</script>

<Sheet {overlay} icon={UsersRound} tall title={t('fo.people')}>
  <p class="sub">{title}</p>
  <PersonCards cards={list ?? []} />
</Sheet>

<style>
  .sub { margin: 0 var(--s-4) var(--s-3); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
</style>
