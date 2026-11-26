<script lang="ts">
  // "Become a tester": the Android app's closed test on Google Play. Opened once on entry on Android (App.svelte)
  // and by the link ?startapp=android. Honest about the effort (3 steps, about 10 minutes, most of it Google's
  // waiting), then the button opens /android.html in the phone's own browser, where the Google account lives:
  // that page leads through the steps one at a time.
  import { untrack } from 'svelte';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { openLink } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Bot from '@lucide/svelte/icons/bot';
  import ListChecks from '@lucide/svelte/icons/list-checks';
  import Timer from '@lucide/svelte/icons/timer';
  import CircleUser from '@lucide/svelte/icons/circle-user';

  let { overlay }: { overlay: Overlay } = $props();
  const facts = [[ListChecks, 'andr.steps'], [Timer, 'andr.time'], [CircleUser, 'andr.account']] as const;

  // once, when the sheet mounts
  $effect(() => {
    untrack(() => count('andr.sheet'));
  });

  function go() {
    count('andr.go');
    openLink('https://kbtu.sow.kz/android.html?lang=' + i18n.lang, true);
    close(overlay.id);
  }
</script>

<Sheet {overlay} icon={Bot} title={t('andr.cap')}>
  <div class="andr">
    <img class="mark" src="/icon-192.png" alt="" width="84" height="84" />
    <h2 class="t-h2">{t('andr.title')}</h2>
    <p class="t-callout">{t('andr.text')}</p>
    <ul class="facts">
      {#each facts as [Icon, key] (key)}
        <li><span class="ic"><Icon size={18} strokeWidth={2} /></span><span class="t-foot">{t(key)}</span></li>
      {/each}
    </ul>
  </div>
  {#snippet footer()}
    <div class="acts">
      <Button size="l" full lit onclick={go}>{t('andr.go')}</Button>
      <Button kind="plain" full onclick={() => close(overlay.id)}>{t('andr.later')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .andr { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--s-1) var(--s-1) var(--s-2); text-align: center; }
  .andr h2 { text-wrap: balance; }
  .andr p { color: var(--text-2); text-wrap: pretty; }
  /* the app's own icon, lifted off the glass as it sits on a home screen */
  .mark { display: block; width: 84px; height: 84px; margin: var(--s-2) 0; border-radius: var(--r-l); box-shadow: 0 0 0 0.5px var(--line-2), var(--lg-lift), 0 22px 36px -22px var(--accent); animation: rise 620ms var(--ease-spring) 180ms backwards; }
  /* three honest facts on one inset plate, hairlines between */
  .facts { width: 100%; margin: var(--s-2) 0 0; padding: 0 var(--s-4); list-style: none; border-radius: var(--r-l); background: var(--fill); text-align: left; }
  .facts li { display: flex; align-items: center; gap: var(--s-3); min-height: 48px; padding: var(--s-2) 0; }
  .facts li + li { box-shadow: inset 0 0.5px 0 var(--line-2); }
  .facts .t-foot { color: var(--text); text-wrap: pretty; }
  .ic { flex: none; display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; background: var(--accent-soft); color: var(--accent-text); }
  .acts { display: flex; flex-direction: column; gap: var(--s-1); }
  @keyframes rise { from { opacity: 0; transform: translate3d(0, 14px, 0) scale(0.96); } }
  /* a short screen: a smaller icon, so the facts and both buttons show without a scroll */
  @media (max-height: 640px) { .mark { width: 64px; height: 64px; margin: 0; border-radius: var(--r-m); } }
  @media (prefers-reduced-motion: reduce) { .mark { animation: none; } }
</style>
