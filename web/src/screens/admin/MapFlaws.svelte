<script lang="ts">
  // The map's flaws people marked with a long press (server logic/mapflaws.py): open ones first, oldest first; a tap marks
  // one fixed (or back). The map session reads the same list with `kbtu.admin mapflaws` (floor and the plan's units).
  import Check from '@lucide/svelte/icons/check';
  import { api } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let list = $state<Awaited<ReturnType<typeof api.mapFlaws>> | null>(null);
  const load = () => api.mapFlaws().then((l) => (list = l)).catch(() => (list = []));
  $effect(() => { void load(); });
  async function toggle(id: number, done: boolean) {
    try { await api.mapFlawDone(id, done); haptic.select(); void load(); } catch { say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} full title={t('mf.title')}>
  <h2 class="t-h2 hd">{t('mf.title')}</h2>
  <p class="t-foot sub">{t('mf.sub')}</p>
  {#if list && !list.length}<p class="t-foot">{t('mf.none')}</p>{/if}
  {#each list ?? [] as f (f.id)}
    <div class="row surface" class:done={f.done}>
      <span class="tx"><b>{f.body}</b><i class="t-foot">{t('mf.where', { floor: f.floor })} · {f.ver} · {f.px != null ? `${Math.round(f.px)}, ${Math.round(f.py ?? 0)}` : ''} · {ago(f.at)}</i></span>
      <button class="ok" class:on={!!f.done} aria-pressed={!!f.done} onclick={() => toggle(f.id, !f.done)} aria-label={t('mf.fixed')}><Check size={18} /></button>
    </div>
  {/each}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 12px; }
  .row { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: var(--r-l); margin-bottom: 8px; transition: opacity var(--t-base) var(--ease); }
  .row.done { opacity: 0.5; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { font: 600 15px/1.35 var(--font-text); overflow-wrap: anywhere; }
  .tx i { font-style: normal; }
  .ok { flex: none; width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-3); }
  .ok.on { background: var(--success); color: #fff; }
</style>
