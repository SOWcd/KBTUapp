<script lang="ts">
  // The Ascent (server clubs.py, official_path): a student initiative's checklist as a ladder; it locks nothing (owner,
  // Nov 6). Done ones are ticked, the first open one is lit, an open one shows its count; the collab and the top say their reward.
  // At the top: the ask to DMP for the ✓, a separate decision (not a step).
  import Check from '@lucide/svelte/icons/check';
  import MountainSnow from '@lucide/svelte/icons/mountain-snow';
  import Clock from '@lucide/svelte/icons/clock';
  import X from '@lucide/svelte/icons/x';
  import type { OfficialPath, PathStep } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { nowTs, dayMonth } from '../../lib/time';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { path, presVice, onask }: { path: OfficialPath; presVice: boolean; onask: () => void } = $props();
  const STEPS: PathStep[] = ['profile', 'round', 'channel', 'collab', 'top'];
  const REWARD: PathStep[] = ['collab', 'top']; // what a step gives (op.opens.*)
  const level = $derived(STEPS.filter((k) => path.steps[k]).length);
  const next = $derived(STEPS.findIndex((k) => !path.steps[k])); // -1: at the top
  const req = $derived(path.request);
  const later = $derived(!!req?.againAt && req.againAt > nowTs());
  const canAsk = $derived(path.steps.top && req?.status !== 'pending' && !later);
  const foot = $derived(later ? t('op.again', { when: dayMonth(req!.againAt!) }) : canAsk && !presVice ? t('op.byPres') : t('op.check'));
  // an open step's count: members toward a ready profile; toward the top, events with 5 guests and different guests in all
  const count = (k: PathStep) => k === 'profile' ? t('op.members', { n: Math.min(path.members, 5) })
    : k === 'top' ? `${t('op.events', { n: Math.min(path.events, 2) })} · ${t('op.guests', { n: Math.min(path.guests, 10) })}` : '';
</script>

<section class="asc" id="ascent">
  <h3 class="cap">{t('op.title')}<span class="note">{path.steps.top ? t('op.atTop') : t('op.level', { n: level })}</span></h3>
  <ol class="card">
    {#each STEPS as k, i (k)}
      {@const done = path.steps[k]}
      {@const now = i === next}
      <li class:done class:now>
        <span class="node" aria-hidden="true">
          {#if done}<Check size={16} strokeWidth={3} />{:else if k === 'top'}<MountainSnow size={16} strokeWidth={2.4} />{:else}<b class="num">{i + 1}</b>{/if}
        </span>
        <span class="txt">
          <b class="t">{t(`op.${k}`)}</b>
          {#if REWARD.includes(k)}<span class="t-foot opens">{t(`op.opens.${k as 'collab' | 'top'}`)}</span>{/if}
          {#if !done && count(k)}<span class="t-foot cnt num">{count(k)}</span>{/if}
        </span>
      </li>
    {/each}
  </ol>
  {#if path.steps.top && (req?.status === 'pending' || req?.status === 'rejected' || (canAsk && presVice))}
    <Group footnote={foot}>
      {#if req?.status === 'pending'}<Row icon={Clock} title={t('op.pending')} />
      {:else if req?.status === 'rejected'}<Row icon={X} title={t('op.no')} subtitle={req.reason ?? undefined} />{/if}
      {#if canAsk && presVice}<Row tone="action" title={t('op.ask')} onclick={onask} />{/if}
    </Group>
  {:else if path.steps.top}<p class="t-foot foot">{foot}</p>
  {/if}
</section>

<style>
  .asc { display: flex; flex-direction: column; gap: var(--s-2); }
  .cap { padding: 0 var(--s-1); font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.01em; }
  .note { margin-left: 0.4em; white-space: nowrap; color: var(--text-3); font-weight: 600; }
  .card { list-style: none; margin: 0; padding: 6px 14px; border-radius: var(--r-group); background: var(--surface); }
  li { position: relative; display: flex; gap: var(--s-3); padding: 10px 0; }
  /* the rail between nodes: lit up to the level reached */
  li:not(:last-child)::after { content: ''; position: absolute; left: 15px; top: 42px; bottom: -10px; width: 2px; border-radius: var(--r-full); background: var(--surface-3); }
  li.done:not(:last-child)::after { background: var(--accent); }
  .node { flex: none; position: relative; z-index: 1; display: grid; place-items: center; width: 32px; height: 32px; border-radius: 50%;
    background: var(--surface-3); color: var(--text-3); }
  .done .node { background: var(--accent); color: var(--on-accent); }
  .now .node { background: var(--accent-soft); color: var(--accent-text); box-shadow: 0 0 0 2px var(--accent); }
  .node b { font-weight: 800; font-size: var(--fs-body); }
  .txt { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding-top: 5px; }
  .t { font-weight: 600; font-size: var(--fs-body); line-height: 1.25; color: var(--text-3); }
  .done .t, .now .t { color: var(--text); }
  .opens { color: var(--text-3); }
  .now .opens { color: var(--accent-text); }
  .foot { padding: 0 var(--s-1); color: var(--text-3); }
  .cnt { color: var(--text-2); font-weight: 600; }
</style>
