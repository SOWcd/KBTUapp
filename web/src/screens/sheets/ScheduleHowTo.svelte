<script lang="ts">
  // How the week gets into the app (PLAN 26): the portal's schedule page saved on the phone and sent to
  // the bot, which reads the whole week (server portal.py) and answers "found N classes". iPhone: Safari's Share ->
  // Options -> Web Archive -> Telegram; Android: Chrome's "Download page" (.mht). Offered right after the Microsoft
  // sign-in (`first`: "Later" says it stays on Home) and from the Home card until a schedule is there.
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink, tgTry } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, first = false }: { overlay: Overlay; first?: boolean } = $props();
  const PORTAL = 'https://uninet.kbtu.kz/student/schedule';
  const toBot = () => { haptic.tap(); openLink('https://t.me/KBTUappBot'); setTimeout(() => tgTry((w) => w.close()), 300); };
  const steps = (os: 'iphone' | 'android') => ([1, 2, 3] as const).map((i) => t(`sched.${os}${i}`));
</script>

<Sheet {overlay} title={t('sched.howTitle')} icon={CalendarDays}>
  <p class="t-callout lead">{t('sched.howLead')}</p>
  {#each ['iphone', 'android'] as const as os (os)}
    <h3 class="t-cap cap">{t(`sched.${os}`)}</h3>
    <ol class="steps surface">{#each steps(os) as s, i (i)}<li><b class="num">{i + 1}</b><span>{s}</span></li>{/each}</ol>
  {/each}
  <p class="t-foot note">{t('sched.privacy')}</p>
  <button class="portal" onclick={() => { haptic.tap(); openLink(PORTAL); }}>{t('sched.portal')}</button>
  {#snippet footer()}
    <div class="acts">
      {#if first}<Button kind="neutral" size="l" full onclick={() => close(overlay.id)}>{t('sched.later')}</Button>{/if}
      <Button kind="primary" size="l" full onclick={toBot}>{t('sched.bot')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .lead { color: var(--text-2); margin: 4px 0 6px; }
  .cap { margin: 16px 4px 8px; }
  .steps { list-style: none; margin: 0; padding: 4px 0; border-radius: var(--r-l); }
  .steps li { display: flex; align-items: center; gap: 12px; padding: 10px 14px; }
  .steps li + li { border-top: 1px solid var(--line); }
  .steps b { flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; background: var(--accent-soft); color: var(--accent-text); font: 700 13px/1 var(--font-text); }
  .steps span { font: 520 var(--fs-sub)/1.3 var(--font-text); }
  .note { margin: 14px 4px 0; }
  .portal { display: block; width: 100%; margin-top: 10px; padding: 10px; color: var(--accent-text); font: 620 var(--fs-sub)/1.2 var(--font-text); }
  .acts { display: flex; gap: 8px; }
  .acts :global(.btn.full) { flex: 1; width: auto; min-width: 0; }
</style>
