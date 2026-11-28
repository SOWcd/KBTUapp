<script lang="ts" module>
  // One family on the three materials (tokens.css):
  //   primary      THE action (one in sight): a calm ink capsule, white with dark text in the dark theme, near-black
  //                with light text in the light one. Never a saturated fill: prominence is contrast, not hue
  //   secondary    quiet fill: a flat --fill body, no rim (accent ink when called by an old accent-soft name)
  //   destructive  secondary with red ink
  //   glass        floating glass, for what floats over content (photos, the map, the camera, a sheet's actions): the
  //                tab bar's recipe (base.css .glass-pill), the only kind that blurs what's under it
  //   plain        text only (a Toolbar's tools)
  export type Kind = 'primary' | 'secondary' | 'destructive' | 'glass' | 'plain';
  // the names from before (filled, tinted, gray, neutral, danger), all routed through this one table: callers keep theirs
  export type OldKind = 'filled' | 'tinted' | 'gray' | 'neutral' | 'danger';
  const KIND: Record<Kind | OldKind, [Kind, boolean?]> = { // [look, accent ink]
    primary: ['primary'], filled: ['primary'],
    secondary: ['secondary', true], tinted: ['secondary', true], gray: ['secondary'], neutral: ['secondary'],
    destructive: ['destructive'], danger: ['destructive'],
    glass: ['glass'], plain: ['plain'],
  };
</script>

<script lang="ts">
  // The only button.
  //   kind         see above (old names map onto the family)
  //   size         l 50 (full width, a sheet's floating action; its label may take two lines on a narrow phone) | m 44 |
  //                s 36 (a 44 px hit area)
  //   destructive  red: a primary turns solid red, the others red ink. Always confirmed with the app's Ask
  //   onmedia      a primary over a photo or a poster: white with ink text in both themes
  //   on           toggled on ("Subscribed", "Applied"): the calm secondary look and aria-pressed, whatever the kind
  //   loading      a spinner in place, the width kept, taps ignored;  done: it went through, a check (primary turns green)
  //   disabled     readable: flat fill, text-3
  //   lit          a glass one's rim follows the phone's tilt (glass.ts): one per view, never in a list (each lit one
  //                repaints while the phone moves); the others keep the light where it stands
  //   round        the icon alone in a circle (IconButton); label is then required
  //   full         the row's whole width; side by side in a row with the base.css .btns class
  //   label        aria-label;  icon, children: snippets
  // Callers' :global(.btn…) overrides keep working: the classes btn, full, ic and the name the caller used stay on it.
  import type { Snippet } from 'svelte';
  import Check from '@lucide/svelte/icons/check';
  import { haptic } from '../lib/tg';
  import { bloomAt, glass } from './glass';

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
    lit?: boolean;
    label?: string;
    type?: 'button' | 'submit';
    onclick?: (e: MouseEvent) => void;
    icon?: Snippet;
    children?: Snippet;
  };
  let { kind = 'primary', size = 'm', destructive = false, onmedia = false, on = false, full = false, round = false, disabled = false, loading = false,
    done = false, lit = false, label, type = 'button', onclick, icon, children }: Props = $props();

  const base = $derived(KIND[kind] ?? KIND.primary);
  const look = $derived(on ? 'secondary' : base[0] === 'destructive' ? 'secondary' : base[0]); // "on": the calm look of a thing already done
  const red = $derived(destructive || base[0] === 'destructive');
  const ink = $derived(!on && !!base[1]);
  // a lit one joins glass.ts's tilt light (it writes --gx on it)
  const light = (node: HTMLElement) => (lit ? glass(node).destroy : undefined);
  function tap(e: MouseEvent) {
    if (disabled || loading) return;
    haptic.tap();
    onclick?.(e);
  }
  // the touch bloom (glass.ts): compositor-only, clipped to the button by .fx
  function down(e: PointerEvent) {
    const fx = (e.currentTarget as HTMLElement).firstElementChild as HTMLElement;
    if (!disabled && !loading && look !== 'plain') bloomAt(fx, e);
  }
</script>

<!-- the caller's own name stays a class (old overrides); a glass one wears base.css's recipe itself (.glass .glass-pill) -->
<button {type} class="btn k-{look} {size} {kind === 'glass' ? '' : kind} {look === 'glass' ? 'glass glass-pill' : ''}" class:red class:ink class:onmedia class:full class:round class:loading class:done
  {disabled} aria-busy={loading} aria-label={label} aria-pressed={on || undefined} onclick={tap} onpointerdown={down} {@attach light}>
  <span class="fx"></span>
  {#if done}<span class="ic"><Check size={size === 's' ? 16 : 20} strokeWidth={2.4} /></span>
  {:else if icon}<span class="ic">{@render icon()}</span>{/if}
  {#if children && !round}<span class="lbl">{@render children()}</span>{/if}
  {#if loading}<span class="spin" aria-hidden="true"></span>{/if}
</button>

<style>
  .btn {
    --gx: 0; /* the light stands still unless this one is lit (glass.ts writes --gx inline) */
    position: relative; isolation: isolate; display: inline-flex; align-items: center; justify-content: center; gap: 8px; flex: none;
    border-radius: var(--r-full); font-weight: 600; letter-spacing: -0.01em; white-space: nowrap;
    transition: transform var(--t-spring) var(--ease-bounce), filter var(--t-fast), color var(--t-base) var(--ease), opacity var(--t-fast);
    -webkit-tap-highlight-color: transparent;
  }
  .btn:active:not(:disabled) { transform: scale(0.965); transition-duration: var(--t-press); }
  .btn.l:active:not(:disabled), .btn.full:active:not(:disabled) { transform: scale(0.985); } /* the same few px of give on a wide one */
  .full { width: 100%; }
  .l { min-height: var(--ctl-l); padding: 6px var(--s-6); font-size: var(--fs-row); line-height: 1.2; white-space: normal; text-align: center; }
  .m { height: var(--ctl-m); padding: 0 var(--s-5); font-size: var(--fs-body); }
  .s { height: var(--ctl-s); padding: 0 var(--s-4); font-size: var(--fs-sub); gap: 6px; }
  /* 36 seen, 44 to the finger: on the first child after .fx (not positioned, so the box is the button's; the button's
     own ::before and ::after are the glass's) */
  .s > :nth-child(2)::after { content: ''; position: absolute; inset: -4px 0; }
  .round { width: var(--ctl-m); padding: 0; }
  .round.s { width: var(--ctl-s); }
  .round.l { width: var(--ctl-l); height: var(--ctl-l); }
  .round .ic { margin: 0; }
  .ic { display: inline-flex; flex: none; margin-left: -2px; }
  .lbl { min-width: 0; }
  .m .lbl, .s .lbl { overflow: hidden; text-overflow: ellipsis; }
  /* the bloom's layer: over the body, under the label */
  .fx { position: absolute; inset: 0; z-index: -1; border-radius: inherit; overflow: hidden; pointer-events: none; }

  /* primary: the calm ink capsule. The text colour as its body and the ground as its ink give white on black and
     black on white by themselves; a short neutral lift, never a glow in its own colour (it leaked onto neighbours) */
  .k-primary { --body: var(--text); color: var(--bg); background: var(--body); box-shadow: var(--elev-2); }
  .k-primary.done { --body: var(--success); color: var(--on-accent); }
  .k-primary.red { --body: var(--danger); color: var(--on-accent); }
  .k-primary.onmedia { --body: var(--on-accent); color: var(--ink); }
  .k-primary:active:not(:disabled) { opacity: 0.86; }

  /* secondary (and destructive): quiet fill on solid ground (a colour under it never tints it). No rim, no shadow. */
  .k-secondary { color: var(--text); background: linear-gradient(var(--fill), var(--fill)) var(--surface-solid); }
  .k-secondary.ink { color: var(--accent-text); }
  .k-secondary.done { color: var(--success-text); }
  .k-secondary.red { color: var(--danger-text); }
  .k-secondary:active:not(:disabled) { background: linear-gradient(var(--fill-2), var(--fill-2)) var(--surface-solid); }

  /* glass: the look is base.css's .glass.glass-pill (the classes are on the button); monochrome ink */
  .k-glass { color: var(--text); }
  .k-glass.red { color: var(--danger-text); }

  .k-plain { background: transparent; color: var(--plain-ink, var(--accent-text)); } /* a Toolbar inks its tools with --plain-ink */
  .k-plain.red { color: var(--danger-text); }
  .k-plain:not(.round) { padding: 0 var(--s-2); }
  .k-plain:active:not(:disabled) { opacity: 0.5; }

  .btn:disabled { background: var(--fill); color: var(--text-3); cursor: default; box-shadow: none; filter: none; -webkit-backdrop-filter: none; backdrop-filter: none; }
  .btn:disabled::before, .btn:disabled::after { opacity: 0; }
  .k-plain:disabled { background: transparent; }
  @media (hover: hover) {
    .btn:hover:not(:disabled):not(.k-plain) { filter: brightness(1.08); }
    .k-plain:hover:not(:disabled) { opacity: 0.75; }
  }

  .loading .lbl, .loading .ic { opacity: 0; }
  .spin {
    position: absolute; width: 18px; height: 18px; border-radius: 50%;
    border: 2px solid currentColor; border-right-color: transparent; animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
