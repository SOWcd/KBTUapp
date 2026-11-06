<script lang="ts">
  // How the week gets into the app (PLAN 26): the portal's schedule page saved on the phone and sent to
  // the bot, which reads the whole week (server portal.py) and answers "found N classes". iPhone: Safari's Share ->
  // Options -> Web Archive -> Telegram; Android: Chrome's "Download page" (.mht). Offered from Today's card until a
  // schedule is there (no longer right after the sign-in: one thing at a time, the onboarding plan of Oct 31).
  // Oct 30 (owner): the portal is the big button (Nov 2: the pinned one; no "open the bot", the steps say it), and
  // the iPhone way is shown as his own screen recording (public/howto: his face, his classes' teachers and his contacts blurred, the upload sped up, 14 s, no sound).
  // Nov 6 (owner): only this phone's own steps (a computer still sees both), and the recording is an animated WebP:
  // an <img> loops by itself where Telegram's iOS webview never played the mp4, muted and play() or not.
  // `addLang` (the Week sheet's "Add a language"): the lead says to switch the portal's language first; the same page
  // sent again adds that language's names (Oct 30).
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, onAndroid, onIos, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { overlay, addLang = false }: { overlay: Overlay; addLang?: boolean } = $props();
  const PORTAL = 'https://uninet.kbtu.kz/student/schedule';
  const toPortal = () => { haptic.tap(); openLink(PORTAL); };
  const steps = (os: 'iphone' | 'android') => ([1, 2, 3] as const).map((i) => t(`sched.${os}${i}`));
  const oss = onIos ? (['iphone'] as const) : onAndroid ? (['android'] as const) : (['iphone', 'android'] as const);
</script>

<Sheet {overlay} title={t(addLang ? 'sched.addLang' : 'sched.howTitle')} icon={CalendarDays}>
  <p class="t-callout lead">{t(addLang ? 'sched.langLead' : 'sched.howLead')}</p>
  <div class="oss">
    {#each oss as os (os)}
      {#if os === 'iphone'}
        <img class="phone" src="howto/schedule-iphone.webp" width="360" height="780" alt={t('sched.video')} />
      {/if}
      <Group caption={t(`sched.${os}`)}>
        {#each steps(os) as s, i (i)}<Row dense title={s}>{#snippet lead()}<b class="n num">{i + 1}</b>{/snippet}</Row>{/each}
      </Group>
    {/each}
  </div>
  <p class="t-foot note">{t('sched.privacy')}</p>
  {#snippet footer()}
    <div class="acts btns">
      <Button kind="primary" size="l" full onclick={toPortal}>{#snippet icon()}<ExternalLink size={18} />{/snippet}{t('sched.portal')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .lead { color: var(--text-2); margin: var(--s-1) 0 0; text-align: center; }
  .oss { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-5); }
  /* the recording in a phone's outline: rounded like the screen it came from */
  .phone { display: block; width: min(42vw, 156px); height: auto; aspect-ratio: 360 / 780; margin: 0 auto;
    border-radius: var(--r-xl); background: var(--line-2); object-fit: cover;
    box-shadow: 0 0 0 4px var(--line-2), var(--shadow-thumb); }
  .n { flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; background: var(--accent-soft); color: var(--accent-text); font: 700 var(--fs-sub)/1 var(--font-text); }
  .note { margin: 14px var(--s-1) 0; text-align: center; }
  .acts { display: flex; }
</style>
