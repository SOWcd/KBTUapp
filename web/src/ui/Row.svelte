<script lang="ts" module>
  /** a row tile's flat colour (tokens.css --tile-*) */
  export type Tile = 'gray' | 'indigo' | 'red' | 'orange' | 'green' | 'teal' | 'blue' | 'accent' | 'purple' | 'pink';
  let seq = 0;
</script>

<script lang="ts">
  // One row of a Group: Settings' approved row made general. Rows sit directly inside a Group, so the 0.5 px line
  // between them starts where the title does.
  //   title      17 px (menu-like rows: Settings, the admin hub, pickers); dense: 15/600 for data rows (classes,
  //              events, people), 44 high without a tile. It wraps, never "…"
  //   subtitle   a second grey line: CONTENT only (a person's course, an event's time), never a hint
  //   value      grey, before the end mark ("Russian", "2/3")
  //   icon+tile  a 30 px tile of one flat colour with a white glyph;  lead: anything else at the start (an avatar, a
  //              content emoji, a club's logo)
  //   detail     a snippet before the end (a few faces);  count: a red badge there. Both combine with the end mark
  //   accessory  chevron › (pushes a page or opens a sheet; never expands in place) | external ↗ (leaves the app) |
  //              check (a pick: `checked`) | disclosure (a chevron-down that turns with `open`: expands in place) |
  //              switch (`checked`, `onchange`) | none
  //   menu       the value with ⌃⌄, the visible trigger; the tap opens this Menu at it (2-6 choices)
  //   trailing   a snippet at the end instead of a mark: an S gray Button
  //   tone       action (accent: the row does something) | add (accent with a +: "Add…" at a group's end) |
  //              destructive (red: last and alone in its group, confirmed with the app's Ask)
  //   onclick    the row is a button; with a switch or `trailing` it stays a plain row and only its control is tapped
  import type { Component, Snippet } from 'svelte';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ChevronsUpDown from '@lucide/svelte/icons/chevrons-up-down';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Check from '@lucide/svelte/icons/check';
  import Plus from '@lucide/svelte/icons/plus';
  import Badge from './Badge.svelte';
  import { menu as openMenu, type MenuItem } from './menu';

  type Props = {
    title: string; subtitle?: string; value?: string; dense?: boolean;
    icon?: Component<any>; tile?: Tile; lead?: Snippet; detail?: Snippet; count?: number;
    accessory?: 'chevron' | 'external' | 'check' | 'switch' | 'disclosure' | 'none';
    checked?: boolean; open?: boolean; menu?: MenuItem[]; trailing?: Snippet;
    tone?: 'action' | 'add' | 'destructive'; disabled?: boolean;
    onclick?: (e: MouseEvent) => void; onchange?: (on: boolean) => void;
  };
  let { title, subtitle, value, dense = false, icon: Icon, tile = 'gray', lead, detail, count = 0, accessory = 'none', checked = false, open = false,
    menu, trailing, tone, disabled = false, onclick, onchange }: Props = $props();

  const id = `row${++seq}`;
  const still = $derived(accessory === 'switch' || !!trailing || (!onclick && !menu)); // a plain row: no button around it
  let end = $state<HTMLElement>();
  function tap(e: MouseEvent) {
    if (menu) openMenu(end ?? (e.currentTarget as Element), menu, 'end');
    else onclick?.(e);
  }
</script>

{#snippet inner()}
  {#if tone === 'add'}<span class="plus"><Plus size={22} strokeWidth={2.2} /></span>
  {:else if Icon}<span class="tile" style:background="var(--tile-{tile})"><Icon size={18} strokeWidth={2.2} /></span>
  {:else if lead}<span class="lead">{@render lead()}</span>{/if}
  <span class="body" class:hv={!!value || !!menu}>
    <span class="txt"><span class="tt" {id}>{title}</span>{#if subtitle}<span class="st">{subtitle}</span>{/if}</span>
    {#if detail}<span class="end">{@render detail()}</span>{/if}
    {#if menu}
      <span class="end menu" bind:this={end}>{#if value}<span class="val">{value}</span>{/if}<ChevronsUpDown size={16} /></span>
    {:else}
      {#if value}<span class="val">{value}</span>{/if}
      {#if count > 0}<Badge n={count} />{/if}
      {#if trailing}<span class="end">{@render trailing()}</span>
      {:else if accessory === 'chevron'}<span class="mk"><ChevronRight size={18} /></span>
      {:else if accessory === 'external'}<span class="mk"><ArrowUpRight size={18} /></span>
      {:else if accessory === 'check'}<span class="ok">{#if checked}<Check size={20} strokeWidth={2.4} />{/if}</span>
      {:else if accessory === 'disclosure'}<span class="mk turn" class:open><ChevronDown size={18} /></span>
      {:else if accessory === 'switch'}<label class="sw sw-on"><input type="checkbox" role="switch" {checked} {disabled} aria-labelledby={id}
        onchange={(e) => onchange?.(e.currentTarget.checked)} /></label>{/if}
    {/if}
  </span>
{/snippet}

{#if still}
  <div class="row kb-row {tone ?? ''}" class:dense class:two={!!subtitle} class:lone={!Icon && !lead && tone !== 'add'} class:off={disabled}>{@render inner()}</div>
{:else}
  <button class="row kb-row tap {tone ?? ''}" class:dense class:two={!!subtitle} class:lone={!Icon && !lead && tone !== 'add'} {disabled}
    aria-pressed={accessory === 'check' ? checked : undefined} aria-expanded={accessory === 'disclosure' ? open : undefined}
    aria-haspopup={menu ? 'menu' : undefined} onclick={tap}>{@render inner()}</button>
{/if}

<style>
  .row { position: relative; display: flex; align-items: center; gap: var(--s-3); width: 100%; min-height: var(--row-h); padding-left: var(--s-4);
    text-align: left; color: var(--text); font: 450 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.012em; }
  .row.two { min-height: var(--row-h2); }
  .row.dense { font: 600 var(--fs-body)/1.3 var(--font-text); letter-spacing: -0.008em; }
  .row.dense.lone { min-height: var(--row-dense); }
  .tap { transition: background-color var(--t-fast); }
  .tap:active:not(:disabled) { background: var(--fill); transform: none; opacity: 1; }
  @media (hover: hover) { .tap:hover:not(:disabled) { background: var(--fill); } }
  .tap:disabled, .off { opacity: 0.45; cursor: default; }
  .body { position: relative; flex: 1; min-width: 0; align-self: stretch; display: flex; align-items: center; gap: var(--s-2); padding: var(--s-2) var(--s-4) var(--s-2) 0; }
  /* the line between rows starts where the title does and runs to the group's edge */
  :global(.kb-row) + .row .body::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 0.5px; background: var(--separator); }
  .txt { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  /* beside a value the title keeps its whole width (up to the row less two letters of the value) and wraps only
     between words; the value gives way, down to an ellipsis */
  .hv .txt { flex: 0 0 auto; max-width: calc(100% - 2.5em); }
  .tt { overflow-wrap: break-word; }
  .st { font: 450 var(--fs-body)/1.3 var(--font-text); letter-spacing: -0.008em; color: var(--text-3); overflow-wrap: break-word; }
  .dense .st { font: 450 var(--fs-sub)/1.3 var(--font-text); letter-spacing: 0; }
  .val { flex: 0 1 auto; min-width: 0; margin-left: auto; color: var(--text-3); font-weight: 450; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tile { flex: none; width: 30px; height: 30px; border-radius: var(--r-xs); display: grid; place-items: center; color: var(--on-accent); }
  .plus { flex: none; width: 30px; display: grid; place-items: center; color: var(--accent-text); }
  .lead { flex: none; display: inline-flex; }
  .mk { flex: none; display: inline-flex; margin-right: -4px; color: var(--text-3); opacity: 0.6; }
  .turn { transition: transform var(--t-base) var(--ease); }
  .turn.open { transform: rotate(180deg); }
  .ok { flex: none; display: inline-flex; width: 20px; color: var(--accent-text); }
  .end { flex: none; display: inline-flex; align-items: center; gap: 4px; }
  .menu { flex: 0 1 auto; min-width: 0; margin-left: auto; color: var(--text-3); }
  .menu :global(svg) { flex: none; }
  .sw { position: relative; flex: none; display: inline-flex; }
  .sw::after { content: ''; position: absolute; inset: -7px -4px; } /* 44 to the finger */
  .action, .row.add { color: var(--accent-text); }
  .destructive { color: var(--danger-text); }
</style>
