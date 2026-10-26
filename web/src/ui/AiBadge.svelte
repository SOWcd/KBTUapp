<script lang="ts">
  // The mark on everything an AI made: a translation now, more later (PLAN AI1-AI7).
  import Sparkles from '@lucide/svelte/icons/sparkles';
</script>

<span class="aib"><Sparkles size={11} strokeWidth={2.4} />KBTU AI</span>

<style>
  .aib { display: inline-flex; align-items: center; gap: 3px; height: 18px; padding: 0 7px; border-radius: var(--r-full); vertical-align: middle;
    background: linear-gradient(120deg, color-mix(in srgb, var(--accent) 22%, transparent), color-mix(in srgb, #b46cff 22%, transparent));
    color: var(--accent-text); font: 700 10.5px/1 var(--font-text); letter-spacing: 0.02em; white-space: nowrap; }
</style>
