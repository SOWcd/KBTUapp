<script lang="ts">
  // The welcome for someone DMP's Student Union list has under their Telegram username, before they've signed in with
  // KBTU (PLAN 95; the way in, a celebration, not a form). Only the clubs and positions: nothing else of
  // the row shows before Microsoft says who this is. "Take your place" is the usual KBTU sign-in; after it, the row
  // joins by itself when the name matches (a toast), else the club's President confirms.
  import { onMount } from 'svelte';
  import type { RosterSpot } from '../../lib/api';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { roleName } from '../../lib/perms';
  import { nameOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import { writeSupport } from '../../lib/feedback';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  let { overlay, spots }: { overlay: Overlay; spots: RosterSpot[] } = $props();
  onMount(() => { const id = setTimeout(() => { haptic.ok(); burst(); }, 280); return () => clearTimeout(id); });
  function go() { haptic.tap(); close(overlay.id); sheets.login(); }
</script>

<Sheet {overlay} title={t('ro.hi')}>
  <div class="hero">
    <span class="glow" aria-hidden="true"></span>
    <span class="em"><Emoji name="party_popper_3d" size={92} /></span>
    <h2 class="t-h1 hi">{t('ro.hi')}</h2>
    <p class="t-callout lead">{t('ro.text')}</p>
  </div>
  <div class="spots">
    {#each spots as s, i (s.org.id + ':' + i)}
      <div class="spot surface" style:animation-delay="{120 + i * 90}ms">
        <OrgLogo org={s.org} size={48} />
        <span class="tx"><b class="ellipsis">{nameOf(s.org)}</b><i class="ellipsis">{s.title || roleName(s.role, null)}</i></span>
      </div>
    {/each}
  </div>
  <p class="t-foot note">{t('ro.signNote')}</p>
  <button class="sup" onclick={() => writeSupport(t('ro.draft', { org: spots.map((s) => s.org.name).join(', ') }))}>{t('ro.support')}</button>

  {#snippet footer()}
    <Button kind="primary" size="l" full onclick={go}>{t('ro.signIn')}</Button>
  {/snippet}
</Sheet>

<style>
  .hero { position: relative; display: flex; flex-direction: column; align-items: center; text-align: center; padding: 10px 0 6px; }
  .glow { position: absolute; top: -10px; width: 260px; height: 200px; border-radius: 50%; pointer-events: none;
    background: radial-gradient(closest-side, color-mix(in srgb, var(--accent) 38%, transparent), transparent); filter: blur(6px); }
  .em { position: relative; animation: pop 700ms cubic-bezier(.2, 1.5, .35, 1) both; }
  .hi { position: relative; margin: 10px 0 4px; }
  .lead { position: relative; color: var(--text-2); }
  .spots { display: flex; flex-direction: column; gap: 10px; margin-top: 18px; }
  .spot { display: flex; align-items: center; gap: 14px; padding: 12px 14px; border-radius: var(--r-l); animation: rise 520ms cubic-bezier(.2, .9, .25, 1) both; }
  .tx { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { font: 700 17px/1.2 var(--font-display); }
  .tx i { font: 620 13.5px/1.2 var(--font-text); font-style: normal; color: var(--accent-text); }
  .note { margin: 16px 4px 0; text-align: center; }
  .sup { display: block; margin: 10px auto 0; padding: 6px 10px; font: 560 13.5px/1.2 var(--font-text); color: var(--text-3); }
  @keyframes pop { 0% { transform: scale(0.3) rotate(-20deg); opacity: 0; } 100% { transform: none; opacity: 1; } }
  @keyframes rise { 0% { transform: translateY(14px); opacity: 0; } 100% { transform: none; opacity: 1; } }
  @media (prefers-reduced-motion: reduce) { .em, .spot { animation: none; } }
</style>
