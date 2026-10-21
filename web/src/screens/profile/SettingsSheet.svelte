<script lang="ts">
  // Behind Settings' rows: power saving (this phone's, SPEC §8.2) and About the app (who sees what, SPEC §3; the rules,
  // the code, a contact). The notification switches sit on the Settings page itself since Oct 21.
  import Lock from '@lucide/svelte/icons/lock';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import { power, setPowerMode, POWER_MODES } from '../../lib/state/power.svelte';
  import { type Overlay } from '../../lib/state/ui.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';

  let { overlay, kind }: { overlay: Overlay; kind: 'privacy' | 'power' } = $props();
  const NOW = { fps: 'power.now.fps', battery: 'power.now.battery', device: 'power.now.device' } as const;
  const now = $derived(power.mode === 'on' ? 'power.now.on' : power.mode === 'off' ? 'power.now.off' : power.why ? NOW[power.why] : 'power.now.autoOff');
  // what we keep about a student first: the sign-in sheet's "What we store" opens this (§4.1 consent)
  const SEES = [['set.portal', 'set.portalText'], ['set.allSee', 'set.allSeeText'], ['set.orgSee', 'set.orgSeeText'],
    ['set.teamSee', 'set.teamSeeText'], ['set.youSee', 'set.youSeeText'], ['set.never', 'set.neverText']] as const;
</script>

<Sheet {overlay} title={t(kind === 'power' ? 'power.title' : 'set.about')} icon={kind === 'power' ? BatteryMedium : Lock}>
  {#if kind === 'power'}
    <h2 class="t-h2 hd">{t('power.title')}</h2>
    <p class="t-callout lead">{t('power.lead')}</p>
    <div class="seg modes">{#each POWER_MODES as m (m)}<button class:on={power.mode === m} onclick={() => { haptic.select(); setPowerMode(m); }}>{t(`power.${m}`)}</button>{/each}</div>
    <section class="blk now"><p class="t-callout">{t(now)}</p>
      {#if power.mode === 'auto' && power.fps}<p class="t-foot">{t('power.fps', { n: power.fps })}</p>{/if}</section>
    <p class="t-foot note">{t('power.what')}</p>
  {:else}
    <h2 class="t-h2 hd">{t('set.about')}</h2>
    <div class="col">
      {#each SEES as [h, text] (h)}
        <section class="blk"><h3 class="t-cap">{t(h)}</h3><p class="t-callout">{t(text)}</p></section>
      {/each}
    </div>
    <p class="t-foot note"><button class="link" onclick={() => openLink(`${location.origin}/privacy?lang=${i18n.lang}`)}>{t('login.consentLink')}</button> · <button class="link" onclick={() => openLink(`${location.origin}/terms?lang=${i18n.lang}`)}>{t('login.terms')}</button></p>
    <p class="t-foot note">{t('set.contact')} <button class="link" onclick={() => openLink('https://t.me/Sowers')}>@Sowers</button></p>
    <p class="t-foot note">{t('set.source')} <button class="link" onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}>GitHub</button></p>
  {/if}
</Sheet>

<style>
  .hd { margin: 4px 0 8px; }
  .lead { color: var(--text-2); margin-bottom: 14px; }
  .col { display: flex; flex-direction: column; gap: 8px; }
  .blk { padding: 12px 14px; border-radius: var(--r-m); background: var(--surface-2); }
  .blk h3 { margin-bottom: 4px; color: var(--text-2); }
  .note { margin-top: 14px; padding: 0 2px; }
  .link { color: var(--accent-text); font-weight: 620; }
  .modes { display: flex; width: 100%; }
  .modes button { flex: 1; height: 38px; font-size: 14px; text-align: center; }
  .now { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
</style>
