<script lang="ts">
  // The app's staff seal by the name (Hero only: never in rows or lists, review Nov 3), Founder's craft in a shield:
  // a struck metal rim, a field, a check struck in it. 'moderator': steel blue in silver; 'admin': the same shield in
  // gold, the check struck in black (Founder's gold coin). A tap by the name opens what it is (AwardSheet).
  let { size = 16, role }: { size?: number; role: 'admin' | 'moderator' } = $props();
  const gold = $derived(role === 'admin');
  const field = $derived(gold ? ['rgb(255, 243, 200)', 'rgb(216, 167, 67)', 'rgb(122, 82, 16)'] : ['rgb(120, 156, 204)', 'rgb(46, 78, 128)', 'rgb(16, 30, 58)']);
  const rim = $derived(gold ? ['rgb(255, 246, 216)', 'rgb(138, 94, 20)', 'rgb(242, 210, 122)'] : ['rgb(250, 252, 255)', 'rgb(132, 140, 156)', 'rgb(226, 230, 238)']);
  const mark = $derived(gold ? ['rgb(42, 28, 5)', 'rgb(20, 13, 2)'] : ['rgb(255, 255, 255)', 'rgb(190, 200, 216)']);
  const id = $props.id(); // gradient ids per seal, as Founder's
  const SHIELD = 'M16 1.6 27.6 5.4V14.2C27.6 21.8 22.6 27.4 16 30.4 9.4 27.4 4.4 21.8 4.4 14.2V5.4Z';
</script>

<svg class="seal" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <defs>
    <linearGradient id="{id}r" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color={rim[0]} /><stop offset="0.5" stop-color={rim[1]} /><stop offset="1" stop-color={rim[2]} /></linearGradient>
    <radialGradient id="{id}f" cx="0.34" cy="0.2" r="0.95"><stop offset="0" stop-color={field[0]} /><stop offset="0.55" stop-color={field[1]} /><stop offset="1" stop-color={field[2]} /></radialGradient>
    <linearGradient id="{id}m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color={mark[0]} /><stop offset="1" stop-color={mark[1]} /></linearGradient>
    <clipPath id="{id}c"><path d={SHIELD} /></clipPath>
  </defs>
  <!-- the rim, then the field inset in it with a struck line round its edge -->
  <path d={SHIELD} fill="url(#{id}r)" />
  <g transform="translate(16 15.6) scale(0.84) translate(-16 -15.6)">
    <path d={SHIELD} fill="url(#{id}f)" />
    <path d={SHIELD} fill="none" stroke={gold ? 'rgb(90, 60, 6)' : 'rgb(8, 16, 34)'} stroke-opacity="0.55" stroke-width="0.6" />
  </g>
  <path d="M10.6 15.6 14.6 19.6 21.6 11.8" fill="none" stroke="url(#{id}m)" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round" />
  <!-- the light on polished metal, kept inside the shield -->
  <g clip-path="url(#{id}c)"><ellipse cx="11" cy="7.4" rx="7" ry="2.8" transform="rotate(-24 11 7.4)" fill="rgb(255, 255, 255)" fill-opacity={gold ? 0.22 : 0.16} /></g>
</svg>

<style>
  .seal { flex: none; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35)); }
</style>
