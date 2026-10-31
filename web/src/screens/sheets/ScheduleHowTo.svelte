<script lang="ts">
  // How the week gets into the app (PLAN 26): the portal's schedule page saved on the phone and sent to
  // the bot, which reads the whole week (server portal.py) and answers "found N classes". iPhone: Safari's Share ->
  // Options -> Web Archive -> Telegram; Android: Chrome's "Download page" (.mht). Offered from Today's card until a
  // schedule is there (no longer right after the sign-in: one thing at a time, the onboarding plan of Oct 31).
  // Oct 30 (owner): the portal is the first big button, and the iPhone way is shown as his own screen recording
  // (public/howto: his face, his classes' teachers and his contacts blurred, the upload sped up, 14 s, no sound).
  // This phone's own steps come first. `addLang` (the Week sheet's "Add a language"): the lead says to switch the
  // portal's language first; the same page sent again adds that language's names (Oct 30).
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, onAndroid, openLink, tgTry } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, addLang = false }: { overlay: Overlay; addLang?: boolean } = $props();
  const PORTAL = 'https://uninet.kbtu.kz/student/schedule';
  const toBot = () => { haptic.tap(); openLink('https://t.me/KBTUappBot'); setTimeout(() => tgTry((w) => w.close()), 300); };
  const toPortal = () => { haptic.tap(); openLink(PORTAL); };
  const steps = (os: 'iphone' | 'android') => ([1, 2, 3] as const).map((i) => t(`sched.${os}${i}`));
  const order = onAndroid ? (['android', 'iphone'] as const) : (['iphone', 'android'] as const);
</script>

<Sheet {overlay} title={t(addLang ? 'sched.addLang' : 'sched.howTitle')} icon={CalendarDays}>
  <p class="t-callout lead">{t(addLang ? 'sched.langLead' : 'sched.howLead')}</p>
  <Button kind="secondary" size="l" full onclick={toPortal}>{#snippet icon()}<ExternalLink size={18} />{/snippet}{t('sched.portal')}</Button>
  {#each order as os (os)}
    <h3 class="t-cap cap">{t(`sched.${os}`)}</h3>
    {#if os === 'iphone'}
      <div class="how">
        <!-- muted + playsinline: iOS plays it in place, on its own, in a loop -->
        <video class="phone" src="howto/schedule-iphone.mp4" poster="howto/schedule-iphone.jpg" autoplay muted loop playsinline preload="metadata"
          aria-label={t('sched.video')}></video>
        <ol class="steps">{#each steps(os) as s, i (i)}<li><b class="num">{i + 1}</b><span>{s}</span></li>{/each}</ol>
      </div>
    {:else}
      <ol class="steps surface">{#each steps(os) as s, i (i)}<li><b class="num">{i + 1}</b><span>{s}</span></li>{/each}</ol>
    {/if}
  {/each}
  <p class="t-foot note">{t('sched.privacy')}</p>
  {#snippet footer()}
    <div class="acts btns">
      <Button kind="primary" size="l" full onclick={toBot}>{t('sched.bot')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .lead { color: var(--text-2); margin: 4px 0 14px; }
  .cap { margin: 20px 4px 8px; }
  .how { display: grid; grid-template-columns: minmax(0, 132px) 1fr; gap: 14px; align-items: center; padding: 12px; border-radius: var(--r-l);
    background: var(--surface); }
  /* the recording in a phone's outline: rounded like the screen it came from */
  .phone { width: 100%; aspect-ratio: 590 / 1278; border-radius: 18px; background: #000; object-fit: cover;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--text) 14%, transparent), 0 10px 30px rgba(0, 0, 0, 0.35); }
  .steps { list-style: none; margin: 0; padding: 4px 0; border-radius: var(--r-l); }
  .how .steps { padding: 0; }
  .steps li { display: flex; align-items: center; gap: 12px; padding: 10px 14px; }
  .how .steps li { padding: 9px 0; }
  .steps li + li { border-top: 1px solid var(--line); }
  .steps b { flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; background: var(--accent-soft); color: var(--accent-text); font: 700 13px/1 var(--font-text); }
  .steps span { font: 520 var(--fs-sub)/1.3 var(--font-text); }
  .note { margin: 14px 4px 0; }
  .acts { display: flex; gap: 8px; }
</style>
