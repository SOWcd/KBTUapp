<script lang="ts">
  // A team event's sign-up (server evteams.py): make a team (its name; you're its captain and invite friends by link)
  // or "I have no team" (the app places you). Joining a friend's team comes by their link, not here. Closed without a
  // choice: no sign-up.
  import { onDestroy } from 'svelte';
  import type { TeamPick } from '../../lib/api';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { overlay, title, min, max, done }: { overlay: Overlay; title: string; min: number; max: number; done: (p: TeamPick | 'solo' | null) => void } = $props();
  let way = $state<'create' | 'solo'>('create');
  let name = $state('');
  let tried = $state(false);
  let sent = false;
  // the server's rule (evteams.clean_name): 2-40 characters, no links or @handles
  const bad = $derived(way === 'create' && (name.trim().length < 2 || /@|https?:|t\.me\/|www\./i.test(name)));
  function go() {
    tried = true;
    if (bad) { haptic.error(); return; }
    sent = true; done(way === 'solo' ? 'solo' : { create: name.trim() }); close(overlay.id);
  }
  const choose = (w: 'create' | 'solo') => { haptic.select(); way = w; };
  onDestroy(() => { if (!sent) done(null); });
</script>

<Sheet {overlay} icon={UsersRound} {title}>
  <div class="page">
    <div class="hd">
      <h2 class="fs-sec">{t('tm.pickTitle')}</h2>
      <p class="fs-sub dim">{t('tm.size', { min, max })}</p>
    </div>
    <Group>
      <Row title={t('tm.create')} subtitle={t('tm.pickCreateSub')} accessory="check" checked={way === 'create'} onclick={() => choose('create')} />
      <Row title={t('tm.pickSolo')} subtitle={t('tm.pickSoloSub')} accessory="check" checked={way === 'solo'} onclick={() => choose('solo')} />
    </Group>
    {#if way === 'create'}
      <Field label={t('tm.name')} bind:value={name} maxlength={40} enterkeyhint="done" error={tried && bad ? t('tm.nameBad') : undefined} />
    {/if}
  </div>
  {#snippet footer()}
    <Button kind="primary" size="l" full onclick={go}>{way === 'create' ? t('tm.create') : t('event.go')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-5); }
  .hd { display: flex; flex-direction: column; gap: var(--s-1); padding: 0 var(--s-1); }
</style>
