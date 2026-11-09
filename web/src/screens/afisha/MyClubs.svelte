<script lang="ts">
  // A list of clubs pushed from the Clubs tab's "All" (mine; `title`: the open rounds): the rows of its "I run" part, for
  // every club: my role there and what's next. A tap opens it as on the tab (a club I'm in its Studio, one I follow its page).
  // A row of a club I can leave swipes left to its red Leave, as in iOS lists: one out at a time, any other tap puts it back.
  // ponytail: the rows are the tab's at the tap, not live (only a club I leave goes); fine for a list opened and left, derive here if it must update
  import type { OrgRef } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { leaveClub } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { canLeave } from '../../lib/perms';
  import { shortOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import { TAB_ICON } from '../../ui/icons';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  let { overlay, rows, title }: { overlay: Overlay; rows: { org: OrgRef; role: string | null; sub: string }[]; title?: string } = $props();
  const open = (x: { org: OrgRef; role: string | null }) => { haptic.tap(); if (x.role) sheets.studio(x.org.id); else sheets.club(x.org.id); };

  const mine = $derived(new Map((session.me?.memberships ?? []).map((m) => [m.org.id, m])));
  const shown = $derived(rows.filter((x) => !x.role || mine.has(x.org.id))); // a club I've just left goes at once
  const leavable = (id: number) => { const m = mine.get(id); return m && canLeave(m) ? m : null; };

  const W = 84; // the red action's width
  let out = $state<number | null>(null); // the row whose Leave shows
  let drag = $state<{ id: number; dx: number } | null>(null);
  let start: { id: number; x: number; y: number; from: number; el: HTMLElement } | null = null;
  let sliding = false, eat = false; // eat: this press only slid or put a row back, its click opens nothing
  const offset = (id: number) => (drag?.id === id ? drag.dx : out === id ? -W : 0);

  function anyDown(e: PointerEvent) {
    const on = e.target as Element;
    eat = out !== null && !on.closest('.act');
    if (!on.closest('.slide.out')) out = null;
  }
  function down(e: PointerEvent, id: number) {
    sliding = false;
    start = !e.button && leavable(id) ? { id, x: e.clientX, y: e.clientY, from: offset(id), el: e.currentTarget as HTMLElement } : null;
  }
  function move(e: PointerEvent) {
    if (!start) return;
    const dx = e.clientX - start.x;
    if (!sliding) {
      if (Math.abs(dx) < 8) return;
      if (Math.abs(e.clientY - start.y) > Math.abs(dx)) { start = null; return; } // a scroll (touch-action hands it to the browser anyway)
      sliding = true;
      start.el.setPointerCapture(e.pointerId);
    }
    drag = { id: start.id, dx: Math.min(0, Math.max(-W, start.from + dx)) };
  }
  function up(e: PointerEvent) {
    if (drag) { out = drag.dx < -W * 0.4 ? drag.id : null; drag = null; eat = true; }
    else if (e.type === 'pointercancel') out = null; // a scroll that began on the open row
    start = null;
  }
  function click(e: MouseEvent) {
    if (!eat) return;
    eat = false;
    if (!sliding) out = null; // a tap on the open row itself
    e.stopPropagation();
  }
  const leave = (id: number) => { const m = leavable(id); out = null; if (m) void leaveClub(m); };
</script>

<svelte:window onpointerdowncapture={anyDown} />

<Pane {overlay} title={title ?? t('clubs.mineTitle')} icon={TAB_ICON.club}>
  <div class="list" onclickcapture={click} role="presentation"><Group>
    {#each shown as x (x.org.id)}
      {@const dx = offset(x.org.id)}
      <div class={['slide', { out: dx < 0 }]} role="presentation" onpointerdown={(e) => down(e, x.org.id)} onpointermove={move} onpointerup={up} onpointercancel={up}>
        {#if leavable(x.org.id)}<button class="act" onclick={() => leave(x.org.id)}>{t('clubs.leave')}</button>{/if}
        <div class={['front', { held: drag?.id === x.org.id }]} style:translate="{dx}px 0">
          <Row dense title={shortOf(x.org)} subtitle={x.sub} accessory="chevron" onclick={() => open(x)}>
            {#snippet lead()}<OrgLogo org={x.org} size={40} />{/snippet}
          </Row>
        </div>
      </div>
    {/each}
  </Group></div>
</Pane>

<style>
  .list :global(.st) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .slide { position: relative; overflow: hidden; touch-action: pan-y; }
  /* the wrapper parts the Rows, so their line between them is drawn here (Row's own rule, for siblings) */
  .slide + .slide :global(.body)::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 0.5px; background: var(--separator); }
  .front { position: relative; background: var(--group-bg, var(--surface)); transition: translate var(--t-base) var(--ease); }
  .front.held { transition: none; }
  /* hidden when shut, after the row has slid back: no red at the group's round corners */
  .act { position: absolute; inset: 0 0 0 auto; width: 84px; text-align: center; background: var(--danger); color: var(--on-accent); font: 600 var(--fs-body)/1 var(--font-text); visibility: hidden; transition: visibility 0s linear var(--t-base); }
  .out .act { visibility: visible; transition: none; }
</style>
