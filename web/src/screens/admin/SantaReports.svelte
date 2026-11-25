<script lang="ts">
  // Admin → Santa reports (server santa.reports), the app's staff alone: a reported Secret Santa thread, whole, with
  // both its people (a tap opens the profile, where the staff's own tools are). "Handled" takes it off the list.
  import { staffOnly } from '../../lib/state/staffGate.svelte';
  import Gift from '@lucide/svelte/icons/gift';
  import { api, type Id, type PersonRef, type SantaReport } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Sheet from '../../ui/Sheet.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  staffOnly(() => overlay, 'staff');
  let list = $state<SantaReport[] | null>(null);
  $effect(() => { api.santaReports().then((l) => (list = l)).catch(() => (list = [])); });
  async function done(id: Id) {
    try {
      await api.santaReportDone(id);
      list = (list ?? []).filter((r) => r.id !== id);
      if (data.inbox) data.inbox.santa = list.length;
      haptic.ok();
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

{#snippet who(p: PersonRef | null, role: 'santa.repSanta' | 'santa.repTo', by: boolean)}
  {#if p}
    <Row dense title={p.name} subtitle={t(role) + (by ? ' · ' + t('santa.repBy') : '')} accessory="chevron" onclick={() => sheets.person(p.id)}>
      {#snippet lead()}<Avatar person={p} size={36} tappable={false} />{/snippet}
    </Row>
  {/if}
{/snippet}

<Sheet {overlay} icon={Gift} full title={t('santa.repTitle')}>
  {#if list && !list.length}<EmptyState icon={Gift} title={t('santa.repNone')} />{/if}
  {#each list ?? [] as r (r.id)}
    <Group caption="{r.title} · {ago(r.at)}">
      {@render who(r.giver, 'santa.repSanta', r.byGiver)}
      {@render who(r.to, 'santa.repTo', !r.byGiver)}
    </Group>
    <div class="log">
      {#each r.msgs as m (m.id)}<p class="selectable" class:to={!m.fromGiver}><b>{t(m.fromGiver ? 'santa.repSanta' : 'santa.repTo')}</b>{m.text}</p>{/each}
    </div>
    <div class="act"><Button kind="tinted" full onclick={() => done(r.id)}>{t('santa.repDone')}</Button></div>
  {/each}
</Sheet>

<style>
  .log { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); margin: var(--s-3) 0; }
  .log p { max-width: 86%; margin: 0; padding: var(--s-2) var(--s-3); border-radius: var(--r-l); background: var(--fill); font: 450 var(--fs-body)/1.45 var(--font-text); overflow-wrap: anywhere; }
  .log p.to { align-self: flex-end; background: var(--accent-soft); }
  .log b { display: block; color: var(--text-2); font: 600 var(--fs-cap)/1.3 var(--font-text); }
  .act { margin-bottom: var(--s-6); }
</style>
