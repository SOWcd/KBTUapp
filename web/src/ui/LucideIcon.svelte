<script module lang="ts">
  // Lucide's own Icon.svelte, the same SVG out, built cheaper. Every lucide icon renders through it (vite.config.ts points
  // the icons' `../Icon.svelte` here): the original made each path a <svelte:element> with spread attributes and its own
  // effects, a third of the time of building a tab or a sheet (List 124 of 334 ms at 4x CPU). Here an icon's paths are
  // built once and cloned; the <svg> itself takes the same attributes as lucide's buildLucideIconNode (v1.51) gives it.
  import type { Snippet } from 'svelte';

  type El = [string, Record<string, string | number>, El[]?];
  type Node = El[];
  const SVG = 'http://www.w3.org/2000/svg';
  const made = new WeakMap<Node, { plain?: DocumentFragment; fixed?: DocumentFragment }>();
  function build(nodes: Node, fixed: boolean): DocumentFragment {
    const f = document.createDocumentFragment();
    const add = (to: ParentNode, list: Node) => {
      for (const [tag, attrs, kids] of list) {
        const el = document.createElementNS(SVG, tag);
        // nonScalingStroke: lucide puts vector-effect first, the path's own attributes after it
        for (const [k, v] of Object.entries(fixed ? { 'vector-effect': 'non-scaling-stroke', ...attrs } : attrs)) el.setAttribute(k, String(v));
        if (kids) add(el, kids);
        to.append(el);
      }
    };
    add(f, nodes);
    return f;
  }
  function paths(nodes: Node, fixed: boolean): DocumentFragment {
    let m = made.get(nodes);
    if (!m) made.set(nodes, (m = {}));
    const k = fixed ? 'fixed' : 'plain';
    return (m[k] ??= build(nodes, fixed)).cloneNode(true) as DocumentFragment;
  }
  const a11y = (props: Record<string, unknown>) => Object.keys(props).some((p) => p.startsWith('aria-') || p === 'role' || p === 'title');
  const merge = (...c: (string | undefined)[]) => c.filter((x, i, all) => !!x && x.trim() !== '' && all.indexOf(x) === i).join(' ').trim();
</script>

<script lang="ts">
  import { getLucideContext } from '@lucide/svelte/context';

  type Props = Record<string, unknown> & { color?: string; size?: number | string; width?: number | string; height?: number | string; strokeWidth?: number | string;
    absoluteStrokeWidth?: boolean; nonScalingStroke?: boolean; iconNode?: Node; icon?: { name?: string; aliases?: string[]; size?: number; width?: number; height?: number; node: Node };
    class?: unknown; children?: Snippet };
  const g = (getLucideContext() ?? {}) as Record<string, any>;
  const { color = g.color ?? 'currentColor', size = g.size ?? 24, width = size, height = size, strokeWidth = g.strokeWidth ?? 2,
    absoluteStrokeWidth = g.absoluteStrokeWidth ?? false, nonScalingStroke = g.nonScalingStroke ?? false, iconNode = [], icon = { node: iconNode, aliases: [], size: 24 },
    class: propsClass, children, ...props }: Props = $props();

  const attrs = $derived.by(() => {
    const vw = icon.size ?? icon.width ?? 24, vh = icon.size ?? icon.height ?? 24;
    const names = [...(icon.name ? [`lucide-${icon.name}`] : []), ...(icon.aliases ?? []).filter((a) => typeof a === 'string' && a.trim() !== '').map((a) => `lucide-${a}`)];
    const cls = merge('lucide', ...names, ...merge('lucide-icon', g.class).split(' ').filter(Boolean));
    const sw = absoluteStrokeWidth ? (Number(strokeWidth ?? 2) * Number(icon.size ?? icon.width ?? 24)) / Number(width ?? 24) : strokeWidth ?? 2;
    return {
      xmlns: SVG, width: width ?? 24, height: height ?? 24, viewBox: `0 0 ${vw} ${vh}`, fill: 'none', stroke: color || 'currentColor', 'stroke-width': sw,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: [...cls.split(' '), propsClass],
      ...(children || a11y(props) ? {} : { 'aria-hidden': 'true' }), ...props,
    } as Record<string, unknown>;
  });
  // the paths go in first, before any children, as lucide's {#each} put them
  const fill = (svg: SVGSVGElement) => {
    const f = paths(icon.node, nonScalingStroke), put = [...f.childNodes];
    svg.insertBefore(f, svg.firstChild);
    return () => put.forEach((n) => n.remove());
  };
</script>

<svg {...attrs} {@attach fill}>{@render children?.()}</svg>
