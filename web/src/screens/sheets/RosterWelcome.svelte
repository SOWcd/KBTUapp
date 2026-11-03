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
  import Hand from '@lucide/svelte/icons/hand';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  let { overlay, spots }: { overlay: Overlay; spots: RosterSpot[] } = $props();
  onMount(() => { const id = setTimeout(() => { haptic.ok(); burst(); }, 280); return () => clearTimeout(id); });
  function go() { haptic.tap(); close(overlay.id); sheets.login(); }
</script>

<Sheet {overlay} icon={Hand} title={t('ro.hi')}>
  <div class="hero">
    <span class="glow" aria-hidden="true"></span>
    <span class="em"><Emoji name="party_popper_3d" size={92} /></span>
    <h2 class="t-h1 hi">{t('ro.hi')}</h2>
    <p class="t-callout lead">{t('ro.text')}</p>
  </div>
  <div class="spots">
    <Group footnote={t('ro.signNote')}>
      {#each spots as s, i (s.org.id + ':' + i)}
        <Row title={nameOf(s.org)} subtitle={s.title || roleName(s.role, null)}>{#snippet lead()}<OrgLogo org={s.org} size={40} />{/snippet}</Row>
      {/each}
    </Group>
  </div>
  <div class="sup"><Button kind="plain" size="s" onclick={() => writeSupport(t('ro.draft', { org: spots.map((s) => s.org.name).join(', ') }))}>{t('ro.support')}</Button></div>

  {#snippet footer()}
    <Button kind="primary" size="l" full onclick={go}>{t('ro.signIn')}</Button>
  {/snippet}
</Sheet>

<style>
  .hero { position: relative; display: flex; flex-direction: column; align-items: center; text-align: center; padding: 10px 0 6px; }
  .glow { position: absolute; top: -10px; width: 260px; height: 200px; border-radius: 50%; pointer-events: none;
    background: radial-gradient(closest-side, var(--accent-soft), transparent); filter: blur(6px); }
  .em { position: relative; animation: pop 700ms cubic-bezier(.2, 1.5, .35, 1) both; }
  .hi { position: relative; margin: 10px 0 var(--s-1); }
  .lead { position: relative; color: var(--text-2); }
  .spots { margin-top: var(--s-5); }
  .sup { display: flex; justify-content: center; margin-top: var(--s-3); --plain-ink: var(--text-3); }
  @keyframes pop { 0% { transform: scale(0.3) rotate(-20deg); opacity: 0; } 100% { transform: none; opacity: 1; } }
  @media (prefers-reduced-motion: reduce) { .em { animation: none; } }
</style>
