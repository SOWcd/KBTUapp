<script lang="ts" module>
  // Kinds (the design system, Oct 30): filled = flat accent, THE primary (one in sight); tinted = accent-soft;
  // gray = --fill; plain = accent text, no fill; glass = over photos, the map, full-screen layers.
  export type Kind = 'filled' | 'tinted' | 'gray' | 'plain' | 'glass';
  // the names from before, aliases until their callers move: primary = filled, secondary = tinted, neutral = gray,
  // danger = tinted destructive
  export type OldKind = 'primary' | 'secondary' | 'neutral' | 'danger';
  const ALIAS: Record<OldKind, Kind> = { primary: 'filled', secondary: 'tinted', neutral: 'gray', danger: 'tinted' };
</script>

<script lang="ts">
  // The only button.
  //   kind         filled | tinted | gray | plain | glass (old names alias them, see above)
  //   size         l 50 (full width, a sheet's pinned footer; its label may take two lines on a narrow phone) | m 44 |
  //                s 36 (a 44 px hit area)
  //   destructive  red: filled solid red, the others red text. Always confirmed with the app's Ask
  //   onmedia      a filled one over a photo or a poster: white with ink text (blue on a blue poster disappears)
  //   on           toggled on ("Subscribed", "Applied"): the calm gray look and aria-pressed, whatever the kind
  //   loading      a spinner in place, the width kept, taps ignored;  done: it went through, a check (filled turns green)
  //   disabled     readable: gray fill, text-3
  //   round        the icon alone in a circle (IconButton); label is then required
  //   full         the row's whole width; side by side in a row with the base.css .btns class
  //   label        aria-label;  icon, children: snippets
  // Callers' :global(.btn…) overrides keep working: the classes btn, full, ic and the old kind names stay on it.
  import type { Snippet } from 'svelte';
  import Check from '@lucide/svelte/icons/check';
  import { haptic } from '../lib/tg';

  type Props = {
    kind?: Kind | OldKind;
    size?: 'l' | 'm' | 's';
    destructive?: boolean;
    onmedia?: boolean;
    on?: boolean;
    full?: boolean;
    round?: boolean;
    disabled?: boolean;
    loading?: boolean;
    done?: boolean;
    label?: string;
    type?: 'button' | 'submit';
    onclick?: (e: MouseEvent) => void;
    icon?: Snippet;
    children?: Snippet;
  };
  let { kind = 'filled', size = 'm', destructive = false, onmedia = false, on = false, full = false, round = false, disabled = false, loading = false,
    done = false, label, type = 'button', onclick, icon, children }: Props = $props();

  const base = $derived(kind in ALIAS ? ALIAS[kind as OldKind] : (kind as Kind));
  const look = $derived(on ? 'gray' : base); // "on": the calm gray of a thing already done
  const red = $derived(destructive || kind === 'danger');

  function tap(e: MouseEvent) {
    if (disabled || loading) return;
    haptic.tap();
    onclick?.(e);
  }
</script>

<button {type} class="btn {look} {size} {kind === look ? '' : kind}" class:glass-pill={look === 'glass'} class:red class:onmedia class:full class:round class:loading class:done
  {disabled} aria-busy={loading} aria-label={label} aria-pressed={on || undefined} onclick={tap}>
  {#if done}<span class="ic"><Check size={size === 's' ? 16 : 20} strokeWidth={2.4} /></span>
  {:else if icon}<span class="ic">{@render icon()}</span>{/if}
  {#if children && !round}<span class="lbl">{@render children()}</span>{/if}
  {#if loading}<span class="spin" aria-hidden="true"></span>{/if}
</button>

<style>
  .btn {
    position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 8px; flex: none;
    border-radius: var(--r-full); font-weight: 600; letter-spacing: -0.01em; white-space: nowrap;
    transition: transform 450ms var(--ease-bounce), background-color var(--t-base) var(--ease), color var(--t-base) var(--ease), opacity var(--t-fast);
    -webkit-tap-highlight-color: transparent;
  }
  .btn:active:not(:disabled) { transform: scale(0.965); transition-duration: 80ms; }
  .full { width: 100%; }
  .l { min-height: var(--ctl-l); padding: 6px var(--s-6); font-size: var(--fs-row); line-height: 1.2; white-space: normal; text-align: center; }
  .m { height: var(--ctl-m); padding: 0 var(--s-5); font-size: var(--fs-body); }
  .s { height: var(--ctl-s); padding: 0 var(--s-4); font-size: var(--fs-sub); gap: 6px; }
  .s:not(.glass)::after { content: ''; position: absolute; inset: -4px 0; } /* 36 seen, 44 to the finger (glass draws its rim there) */
  .round { width: var(--ctl-m); padding: 0; }
  .round.s { width: var(--ctl-s); }
  .round.l { width: var(--ctl-l); height: var(--ctl-l); }
  .round .ic { margin: 0; }
  .ic { display: inline-flex; flex: none; margin-left: -2px; }
  .lbl { min-width: 0; }
  .m .lbl, .s .lbl { overflow: hidden; text-overflow: ellipsis; }

  .filled { background: var(--accent); color: var(--on-accent); }
  .filled.done { background: var(--success); }
  .filled.red { background: var(--danger); }
  .filled.onmedia { background: var(--on-accent); color: var(--ink); }
  .tinted { background: var(--accent-soft); color: var(--accent-text); }
  .tinted.done { background: var(--success-soft); color: var(--success-text); }
  .tinted.red { background: var(--danger-soft); color: var(--danger-text); }
  .gray { background: var(--fill); color: var(--text); }
  .gray:active:not(:disabled) { background: var(--fill-2); }
  .gray.red, .plain.red { color: var(--danger-text); }
  .plain { background: transparent; color: var(--plain-ink, var(--accent-text)); } /* a Toolbar inks its tools with --plain-ink */
  .plain:not(.round) { padding: 0 var(--s-2); }
  .plain:active:not(:disabled) { opacity: 0.5; }
  /* glass: the capsule's pill glass (base.css .glass .glass-pill: its rim and blur), for controls over photos and the map */
  .glass { color: var(--text); }
  .btn:disabled { background: var(--fill); color: var(--text-3); cursor: default; box-shadow: none; }
  .plain:disabled { background: transparent; }
  @media (hover: hover) {
    .btn:hover:not(:disabled):not(.plain) { filter: brightness(1.08); }
    .plain:hover:not(:disabled) { opacity: 0.75; }
  }

  .loading .lbl, .loading .ic { opacity: 0; }
  .spin {
    position: absolute; width: 18px; height: 18px; border-radius: 50%;
    border: 2px solid currentColor; border-right-color: transparent; animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
