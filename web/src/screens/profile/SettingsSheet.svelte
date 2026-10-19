<script lang="ts">
  // Behind the Me rows: what the bot sends (notifications), who sees what (privacy, SPEC §3), power saving (this phone's,
  // SPEC §8.2). A switch saves at once and puts itself back if the server says no; important messages can't be turned off.
  import { api } from '../../lib/api';
  import Lock from '@lucide/svelte/icons/lock';
  import Bell from '@lucide/svelte/icons/bell';
  import BatteryMedium from '@lucide/svelte/icons/battery-medium';
  import { power, setPowerMode, POWER_MODES } from '../../lib/state/power.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';

  let { overlay, kind }: { overlay: Overlay; kind: 'notify' | 'privacy' | 'power' } = $props();
  const NOW = { fps: 'power.now.fps', battery: 'power.now.battery', device: 'power.now.device' } as const;
  const now = $derived(power.mode === 'on' ? 'power.now.on' : power.mode === 'off' ? 'power.now.off' : power.why ? NOW[power.why] : 'power.now.autoOff');
  const s = $derived(session.me?.settings);

  const SWITCHES = [['nRemind', 'set.remind', 'set.remindHint'], ['nNewEvents', 'set.newEvents', 'set.newEventsHint']] as const;
  // what we keep about a student first: the sign-in sheet's "What we store" opens this (§4.1 consent)
  const SEES = [['set.portal', 'set.portalText'], ['set.allSee', 'set.allSeeText'], ['set.orgSee', 'set.orgSeeText'],
    ['set.teamSee', 'set.teamSeeText'], ['set.youSee', 'set.youSeeText'], ['set.never', 'set.neverText']] as const;

  async function set(k: 'nRemind' | 'nNewEvents', on: boolean) {
    const me = session.me;
    if (!me) return;
    haptic.tap();
    me.settings[k] = on;
    try { session.me = await api.updateMe({ [k]: on }); }
    catch { me.settings[k] = !on; say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} title={t(kind === 'notify' ? 'me.notifications' : kind === 'power' ? 'power.title' : 'me.privacy')} icon={kind === 'notify' ? Bell : kind === 'power' ? BatteryMedium : Lock}>
  {#if kind === 'power'}
    <h2 class="t-h2 hd">{t('power.title')}</h2>
    <p class="t-callout lead">{t('power.lead')}</p>
    <div class="seg modes">{#each POWER_MODES as m (m)}<button class:on={power.mode === m} onclick={() => { haptic.select(); setPowerMode(m); }}>{t(`power.${m}`)}</button>{/each}</div>
    <section class="blk now"><p class="t-callout">{t(now)}</p>
      {#if power.mode === 'auto' && power.fps}<p class="t-foot">{t('power.fps', { n: power.fps })}</p>{/if}</section>
    <p class="t-foot note">{t('power.what')}</p>
  {:else if kind === 'notify'}
    <h2 class="t-h2 hd">{t('me.notifications')}</h2>
    <p class="t-callout lead">{t('set.notifyLead')}</p>
    {#if s}
      <div class="col">
        {#each SWITCHES as [k, title, hint] (k)}
          <label class="switch"><span><b>{t(title)}</b><i class="t-foot">{t(hint)}</i></span>
            <input type="checkbox" role="switch" checked={s[k]} onchange={(e) => set(k, e.currentTarget.checked)} /></label>
        {/each}
      </div>
    {/if}
    <p class="t-foot note">{t('set.always')}</p>
  {:else}
    <h2 class="t-h2 hd">{t('me.privacy')}</h2>
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
