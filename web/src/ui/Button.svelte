<script lang="ts">
  // The only button. Kinds (SPEC §8.1): primary = one per screen; secondary = tinted; neutral = grey
  // (toggled-on states like "Subscribed"); plain = text; danger = destructive, always confirmed in-app.
  // done: a primary that went through ("Going") turns green in place (mockup v23)
  import type { Snippet } from 'svelte';
  import { haptic } from '../lib/tg';

  type Props = {
    kind?: 'primary' | 'secondary' | 'neutral' | 'plain' | 'danger';
    size?: 'l' | 'm' | 's';
    full?: boolean;
    disabled?: boolean;
    loading?: boolean;
    done?: boolean;
    label?: string;
    type?: 'button' | 'submit';
    onclick?: (e: MouseEvent) => void;
    icon?: Snippet;
    children?: Snippet;
  };
  let { kind = 'primary', size = 'm', full = false, disabled = false, loading = false, done = false, label, type = 'button', onclick, icon, children }: Props = $props();

  function tap(e: MouseEvent) {
    if (disabled || loading) return;
    haptic.tap();
    onclick?.(e);
  }
</script>

<button {type} class="btn {kind} {size}" class:full class:loading class:done {disabled} aria-busy={loading} aria-label={label} onclick={tap}>
  {#if icon}<span class="ic">{@render icon()}</span>{/if}
  {#if children}<span class="lbl">{@render children()}</span>{/if}
  {#if loading}<span class="spin" aria-hidden="true"></span>{/if}
</button>

<style>
  .btn {
    position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    font-weight: 620; letter-spacing: -0.01em; white-space: nowrap; flex: none;
    transition: transform 450ms var(--ease-bounce), background-color var(--t-base) var(--ease), color var(--t-base) var(--ease), box-shadow 500ms, opacity var(--t-fast);
    -webkit-tap-highlight-color: transparent;
  }
  .btn:active:not(:disabled) { transform: scale(0.965); transition-duration: 80ms; }
  .btn:disabled { opacity: 0.42; cursor: default; }
  .full { width: 100%; }

  .l { height: var(--btn-l); padding: 0 22px; border-radius: var(--r-full); font-size: 16px; font-weight: 700; }
  .m { height: var(--btn-m); padding: 0 18px; border-radius: var(--r-full); font-size: 15px; }
  .s { height: var(--btn-s); padding: 0 13px; border-radius: var(--r-full); font-size: 13px; gap: 6px; }

  /* a lit top edge and a darker foot: the pill reads as an object, not a flat label */
  .primary { color: var(--on-accent); background: var(--accent) linear-gradient(180deg, #5C85FF, #3B6BFF 55%, #3457E0);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), inset 0 -1px 0 rgba(0, 0, 0, 0.2), 0 12px 26px -12px rgba(59, 107, 255, 0.95); }
  .primary.done { background: var(--success) linear-gradient(180deg, #5EE3A2, #2FBF71 55%, #22A35F);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), 0 12px 26px -12px rgba(47, 191, 113, 0.9); }
  .secondary { background: var(--accent-soft); color: var(--accent-text); }
  .neutral { background: var(--surface-2); color: var(--text); }
  .plain { background: transparent; color: var(--accent-text); padding-left: 6px; padding-right: 6px; }
  .danger { background: var(--danger-soft); color: var(--danger-text); }

  .ic { display: inline-flex; margin-left: -2px; }
  .loading .lbl, .loading .ic { opacity: 0; }
  .spin {
    position: absolute; width: 18px; height: 18px; border-radius: 50%;
    border: 2px solid currentColor; border-right-color: transparent; animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
