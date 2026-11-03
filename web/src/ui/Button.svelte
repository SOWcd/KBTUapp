<script lang="ts" module>
  // One family, Liquid Glass (owner, Nov 3: "Liquid Glass buttons next to plain old-iOS ones"): every kind has the glass
  // rim (a bright arc facing the light, a dim reflection opposite), a top sheen and the bevel with its pink/blue fringes.
  //   primary      the accent body with a sheen and a coloured lift: THE action (one in sight)
  //   secondary    clear glass on the --fill body (accent ink when called by an old accent-soft name)
  //   destructive  secondary with red ink
  //   glass        over photos, the map, the camera: the only kind that blurs what's under it
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
  //   size         l 50 (full width, a sheet's pinned footer; its label may take two lines on a narrow phone) | m 44 |
  //                s 36 (a 44 px hit area)
  //   destructive  red: a primary turns solid red, the others red ink. Always confirmed with the app's Ask
  //   onmedia      a primary over a photo or a poster: white with ink text (blue on a blue poster disappears)
  //   on           toggled on ("Subscribed", "Applied"): the calm secondary look and aria-pressed, whatever the kind
  //   loading      a spinner in place, the width kept, taps ignored;  done: it went through, a check (primary turns green)
  //   disabled     readable: flat fill, text-3, no rim
  //   lit          the rim follows the phone's tilt (glass.ts): ONE main button per sheet, never in a list (each lit one
  //                repaints while the phone moves); the others keep the light where it stands, still glass
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

<!-- the caller's own name stays a class (old overrides), but never "glass": base.css's .glass would paint over ours -->
<button {type} class="btn k-{look} {size} {kind === 'glass' ? '' : kind}" class:red class:ink class:onmedia class:full class:round class:loading class:done
  {disabled} aria-busy={loading} aria-label={label} aria-pressed={on || undefined} onclick={tap} onpointerdown={down} {@attach light}>
  <span class="fx"></span>
  {#if done}<span class="ic"><Check size={size === 's' ? 16 : 20} strokeWidth={2.4} /></span>
  {:else if icon}<span class="ic">{@render icon()}</span>{/if}
  {#if children && !round}<span class="lbl">{@render children()}</span>{/if}
  {#if loading}<span class="spin" aria-hidden="true"></span>{/if}
</button>

<style>
  .btn {
    /* the light: still unless this one is lit (glass.ts writes --gx inline), so a lit sheet's tilt never repaints rows */
    --gx: 0;
    --hx: calc(24% + var(--gx) * 38%);
    --ox: calc(76% - var(--gx) * 38%);
    --rim: 1.2px;
    position: relative; isolation: isolate; display: inline-flex; align-items: center; justify-content: center; gap: 8px; flex: none;
    border-radius: var(--r-full); font-weight: 600; letter-spacing: -0.01em; white-space: nowrap;
    transition: transform 450ms var(--ease-bounce), filter var(--t-fast), color var(--t-base) var(--ease), opacity var(--t-fast);
    -webkit-tap-highlight-color: transparent;
  }
  .btn:active:not(:disabled) { transform: scale(0.965); transition-duration: 80ms; }
  .full { width: 100%; }
  .l { min-height: var(--ctl-l); padding: 6px var(--s-6); font-size: var(--fs-row); line-height: 1.2; white-space: normal; text-align: center; }
  .m { height: var(--ctl-m); padding: 0 var(--s-5); font-size: var(--fs-body); }
  .s { --rim: 1px; height: var(--ctl-s); padding: 0 var(--s-4); font-size: var(--fs-sub); gap: 6px; }
  .s::before { content: ''; position: absolute; inset: -4px 0; } /* 36 seen, 44 to the finger (::after is the rim) */
  .round { width: var(--ctl-m); padding: 0; }
  .round.s { width: var(--ctl-s); }
  .round.l { width: var(--ctl-l); height: var(--ctl-l); }
  .round .ic { margin: 0; }
  .ic { display: inline-flex; flex: none; margin-left: -2px; }
  .lbl { min-width: 0; }
  .m .lbl, .s .lbl { overflow: hidden; text-overflow: ellipsis; }
  /* the bloom's layer: over the body, under the label */
  .fx { position: absolute; inset: 0; z-index: -1; border-radius: inherit; overflow: hidden; pointer-events: none; }

  /* the rim: static paint (two gradients through a ring mask), repainted only when a lit one's --gx moves */
  .btn::after {
    content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; padding: var(--rim);
    background:
      radial-gradient(ellipse 46% 140% at var(--hx) 0%, var(--rim-hi), transparent 72%),
      radial-gradient(ellipse 50% 130% at var(--ox) 100%, var(--rim-lo), transparent 75%),
      var(--rim-base);
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    transition: opacity var(--t-fast);
  }

  /* primary: the accent body (the label sits on the accent itself: contrast as before), a sheen in its top half, a
     white rim in both themes, the fringes, a lift in its own colour */
  .k-primary {
    --body: var(--accent);
    --rim-hi: rgba(255, 255, 255, 0.85); --rim-lo: rgba(255, 255, 255, 0.3); --rim-base: rgba(255, 255, 255, 0.14);
    color: var(--on-accent);
    background:
      radial-gradient(ellipse 40% 60% at var(--hx) 0%, rgba(255, 255, 255, 0.2), transparent 70%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.16), transparent 50%) var(--body); /* no color-mix: iOS < 16.2 drops it */
    box-shadow:
      inset 0 1px 1px rgba(255, 255, 255, 0.4), inset 0 -8px 14px -8px rgba(0, 0, 0, 0.22),
      inset 1.5px 0 1px -0.5px rgba(255, 120, 200, 0.4), inset -1.5px 0 1px -0.5px rgba(120, 210, 255, 0.45),
      0 10px 22px -12px var(--body), 0 2px 5px -2px rgba(0, 0, 0, 0.18);
  }
  .s.k-primary { box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.4), inset 0 -6px 10px -6px rgba(0, 0, 0, 0.2),
    inset 1px 0 1px -0.5px rgba(255, 120, 200, 0.4), inset -1px 0 1px -0.5px rgba(120, 210, 255, 0.45), 0 6px 14px -8px var(--body); }
  .k-primary.done { --body: var(--success); }
  .k-primary.red { --body: var(--danger); }
  .k-primary.onmedia { --body: var(--on-accent); color: var(--ink); --rim-lo: rgba(11, 20, 51, 0.2); }
  .k-primary:active:not(:disabled) { filter: brightness(1.08); } /* the glass lights under the finger */

  /* secondary (and destructive): clear glass over --fill, the theme's rim (tokens.css --lg-*: white in the dark, ink in
     the light, where white vanishes on white cards). No blur: on a solid card it would blur a flat colour into itself. */
  .k-secondary {
    --rim-hi: var(--lg-rim-hi); --rim-lo: var(--lg-rim-lo); --rim-base: var(--lg-rim-base);
    color: var(--text);
    background:
      radial-gradient(ellipse 40% 60% at var(--hx) 0%, var(--lg-spot), transparent 70%),
      linear-gradient(180deg, var(--lg-sheen), transparent 60%),
      linear-gradient(var(--fill), var(--fill)) var(--surface-solid); /* on solid ground: a colour under it never tints it */
    box-shadow: var(--lg-bevel), var(--lg-lift);
  }
  .k-secondary.ink { color: var(--accent-text); }
  .k-secondary.done { color: var(--success-text); }
  .k-secondary.red { color: var(--danger-text); }

  /* glass: over photos, the map, the camera; the capsule's pill body (base.css .glass-pill) and its blur */
  .k-glass {
    --rim-hi: var(--lg-rim-hi); --rim-lo: var(--lg-rim-lo); --rim-base: var(--lg-rim-base);
    color: var(--text);
    background: radial-gradient(ellipse 40% 60% at var(--hx) 0%, var(--lg-spot), transparent 70%) var(--glass-pill-bg);
    -webkit-backdrop-filter: blur(10px) saturate(200%) brightness(1.06);
    backdrop-filter: blur(10px) saturate(200%) brightness(1.06);
    box-shadow: var(--lg-bevel), 0 12px 32px -10px rgba(0, 0, 0, 0.35), 0 2px 6px rgba(0, 0, 0, 0.08);
  }
  .k-glass.red { color: var(--danger-text); }

  .k-plain { background: transparent; color: var(--plain-ink, var(--accent-text)); } /* a Toolbar inks its tools with --plain-ink */
  .k-plain::after { content: none; }
  .k-plain.red { color: var(--danger-text); }
  .k-plain:not(.round) { padding: 0 var(--s-2); }
  .k-plain:active:not(:disabled) { opacity: 0.5; }

  .btn:disabled { background: var(--fill); color: var(--text-3); cursor: default; box-shadow: none; filter: none; }
  .btn:disabled::after { opacity: 0; }
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
