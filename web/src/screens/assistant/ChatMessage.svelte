<script lang="ts">
  import type { AnswerLine } from '../../lib/answer';
  let { mine = false, text = '', lines = [{ e: '', t: text }], fresh = false }:
    { mine?: boolean; text?: string; lines?: AnswerLine[]; fresh?: boolean } = $props();
</script>

{#if mine}
  <div class={['mine', { new: fresh }]}><p class="selectable">{text}</p></div>
{:else}
  <div class={['say selectable', { one: lines.length === 1, new: fresh }]}>
    {#each lines as l, k (k)}<p style:--i={k}>{#if l.e}<span class="em">{l.e}</span>{/if}<span>{l.t}</span></p>{/each}
  </div>
{/if}

<style>
  .mine { align-self: flex-end; max-width: 86%; margin-top: var(--s-2); padding: 9px 14px; border-radius: var(--r-l); background: var(--accent-soft); transform-origin: 100% 100%; }
  .mine:first-child { margin-top: 0; }
  .mine p { font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .mine.new { animation: sent 340ms var(--ease-spring) backwards; }
  @keyframes sent { from { opacity: 0; transform: translateY(18px) scale(0.94); } }

  .say { display: flex; flex-direction: column; gap: 7px; }
  .say p { display: flex; gap: 8px; font: 450 var(--fs-body)/1.42 var(--font-text); letter-spacing: -0.008em; overflow-wrap: anywhere; }
  .say p > span:last-child { flex: 1; min-width: 0; }
  .say p:first-child { font: 600 var(--fs-row)/1.3 var(--font-text); letter-spacing: -0.014em; }
  .say.one p { font-weight: 450; line-height: 1.38; }
  .say p + p:nth-child(2) { margin-top: 3px; }
  .em { flex: none; width: 20px; text-align: center; }
  .say.new p { animation: down 460ms var(--ease) calc(80ms + var(--i, 0) * 70ms) backwards; }
  @keyframes down { from { opacity: 0; transform: translateY(-12px); } }
  @media (prefers-reduced-motion: reduce) { .say.new p, .mine.new { animation: none; } }
</style>
