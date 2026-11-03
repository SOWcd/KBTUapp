<script lang="ts">
  // The app's staff seal by the name (Hero only: never in rows or lists, review Nov 3), Founder's craft in a shield:
  // a struck metal rim, a field, a five-point star struck in it. 'moderator': steel blue in silver; 'admin': the same shield in
  // gold, the star struck in black (Founder's gold coin). A tap by the name opens what it is (AwardSheet).
  // `deep` (the award sheet, owner Nov 3: "more effect"): rim, field and star are layers that slide apart with the tilt
  // glass.ts writes on an ancestor (--gx/--gy, -1..1), the star raised over its own shadow, a glint crossing the metal.
  // Still under power saving and reduced motion. The small seal by the name stays flat.
  let { size = 16, role, deep = false }: { size?: number; role: 'admin' | 'moderator'; deep?: boolean } = $props();
  const gold = $derived(role === 'admin');
  const field = $derived(gold ? ['rgb(255, 243, 200)', 'rgb(216, 167, 67)', 'rgb(122, 82, 16)'] : ['rgb(120, 156, 204)', 'rgb(46, 78, 128)', 'rgb(16, 30, 58)']);
  const rim = $derived(gold ? ['rgb(255, 246, 216)', 'rgb(138, 94, 20)', 'rgb(242, 210, 122)'] : ['rgb(250, 252, 255)', 'rgb(132, 140, 156)', 'rgb(226, 230, 238)']);
  const mark = $derived(gold ? ['rgb(42, 28, 5)', 'rgb(20, 13, 2)'] : ['rgb(255, 255, 255)', 'rgb(190, 200, 216)']);
  const id = $props.id(); // gradient ids per seal, as Founder's
  const SHIELD = 'M16 1.6 27.6 5.4V14.2C27.6 21.8 22.6 27.4 16 30.4 9.4 27.4 4.4 21.8 4.4 14.2V5.4Z';
  // a star, not a check: a check reads as "verified account" (owner, Nov 3)
  const STAR = 'M16 8.6 17.7 13.25 22.66 13.44 18.76 16.5 20.11 21.26 16 18.5 11.89 21.26 13.24 16.5 9.34 13.44 14.3 13.25Z';
</script>

<svg class="seal" class:deep width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <defs>
    <linearGradient id="{id}r" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color={rim[0]} /><stop offset="0.5" stop-color={rim[1]} /><stop offset="1" stop-color={rim[2]} /></linearGradient>
    <radialGradient id="{id}f" cx="0.34" cy="0.2" r="0.95"><stop offset="0" stop-color={field[0]} /><stop offset="0.55" stop-color={field[1]} /><stop offset="1" stop-color={field[2]} /></radialGradient>
    <linearGradient id="{id}m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color={mark[0]} /><stop offset="1" stop-color={mark[1]} /></linearGradient>
    <clipPath id="{id}c"><path d={SHIELD} /></clipPath>
    {#if deep}
      <filter id="{id}b" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="0.45" /></filter>
      <linearGradient id="{id}g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="rgb(255, 255, 255)" stop-opacity="0" /><stop offset="0.5" stop-color="rgb(255, 255, 255)" stop-opacity="0.55" /><stop offset="1" stop-color="rgb(255, 255, 255)" stop-opacity="0" /></linearGradient>
    {/if}
  </defs>
  <!-- the rim, then the field inset in it with a struck line round its edge -->
  <path d={SHIELD} fill="url(#{id}r)" />
  <g class="lyr fld"><g transform="translate(16 15.6) scale(0.84) translate(-16 -15.6)">
    <path d={SHIELD} fill="url(#{id}f)" />
    <path d={SHIELD} fill="none" stroke={gold ? 'rgb(90, 60, 6)' : 'rgb(8, 16, 34)'} stroke-opacity="0.55" stroke-width="0.6" />
  </g></g>
  {#if deep}
    <!-- the star stands off the field: its shadow falls away from the light, the star itself rides higher -->
    <g clip-path="url(#{id}c)"><path class="lyr drop" d={STAR} fill="rgb(0, 0, 0)" fill-opacity="0.45" filter="url(#{id}b)" /></g>
  {/if}
  <g class="lyr star">
    <path d={STAR} fill="url(#{id}m)" stroke={gold ? 'rgb(20, 13, 2)' : 'rgb(8, 16, 34)'} stroke-opacity="0.35" stroke-width="0.5" stroke-linejoin="round" />
    {#if deep}<path d={STAR} fill="none" stroke="rgb(255, 255, 255)" stroke-opacity={gold ? 0.35 : 0.6} stroke-width="0.25" stroke-linejoin="round" transform="translate(0 -0.2)" />{/if}
  </g>
  <!-- the light on polished metal, kept inside the shield; deep: a glint band that crosses it with the tilt -->
  <g clip-path="url(#{id}c)">
    <g class="lyr spot"><ellipse cx="11" cy="7.4" rx="7" ry="2.8" transform="rotate(-24 11 7.4)" fill="rgb(255, 255, 255)" fill-opacity={gold ? 0.22 : 0.16} /></g>
    {#if deep}<g class="lyr glint"><rect x="-4" y="-8" width="9" height="48" fill="url(#{id}g)" transform="rotate(24 0 16)" style="mix-blend-mode: soft-light" /></g>{/if}
  </g>
</svg>

<style>
  .seal { flex: none; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35)); }
  /* in the viewBox's units (32 across): a unit is ~7 px on the sheet's 220 px shield */
  .deep .fld { transform: translate(calc(var(--gx, 0) * 0.3px), calc(var(--gy, 0) * 0.3px)); }
  .deep .star { transform: translate(calc(var(--gx, 0) * 0.9px), calc(var(--gy, 0) * 0.9px - 0.15px)); }
  .deep .drop { transform: translate(calc(0.4px - var(--gx, 0) * 0.5px), calc(0.7px - var(--gy, 0) * 0.5px)); }
  .deep .spot { transform: translate(calc(var(--gx, 0) * 2.5px), calc(var(--gy, 0) * 1.5px)); }
  .deep .glint { transform: translateX(calc(14px + var(--gx, 0) * 14px + var(--gy, 0) * 4px)); }
  /* still: the layers rest where a level phone puts them (power saving freezes the gyro, reduced motion never starts it) */
  :global(html.lowfx) .deep { --gx: 0; --gy: 0; }
  @media (prefers-reduced-motion: reduce) { .deep { --gx: 0; --gy: 0; } }
</style>
