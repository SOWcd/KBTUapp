<script lang="ts" module>
  declare global {
    interface Window { kbTelegramLogin?: (user: unknown) => void }
  }
</script>

<script lang="ts">
  import { onMount } from 'svelte';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import SquareArrowUp from '@lucide/svelte/icons/square-arrow-up';
  import LockKeyhole from '@lucide/svelte/icons/lock-keyhole';
  import App from '../App.svelte';
  import Button from '../ui/Button.svelte';
  import KbtuMark from '../ui/KbtuMark.svelte';
  import { api, ApiErr } from '../lib/api';
  import { WEB_SESSION_CHANGE } from '../lib/api/client';
  import { i18n, t } from '../lib/i18n/index.svelte';
  import { loadMe } from '../lib/state/session.svelte';
  import { onComputer, onIos } from '../lib/tg';
  import { bootOut, bootOver, bootUnder } from '../lib/boot';

  const installed = matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone;
  let view = $state<'checking' | 'signin' | 'offline'>('checking');
  let entered = $state(false);
  let busy = $state(false), loginFailed = $state(false), widgetFailed = $state(false);
  let retry = $state(0);

  // limit: the first check gives up after it and shows Retry (a captive portal holds a request for the API's 100 s)
  async function enter(limit = 0) {
    const me = api.me(true);
    await loadMe(false, true, await (limit ? Promise.race([me, new Promise<never>((_, no) => setTimeout(() => no(new Error('timeout')), limit))]) : me));
    entered = true;
  }

  // while the session is checked the page draws nothing: index.html's boot screen (its emblem) carries on
  async function check() {
    view = 'checking';
    bootOver();
    try { await enter(8000); }
    catch (e) { view = e instanceof ApiErr && e.code === 'unauthorized' ? 'signin' : 'offline'; }
  }

  async function login(user: unknown) {
    if (busy) return;
    busy = true;
    loginFailed = false;
    try { await api.webLogin(user); await enter(); }
    catch { loginFailed = true; }
    finally { busy = false; }
  }

  onMount(() => {
    void check();
    const ended = () => { if (entered) location.reload(); };
    const switched = (e: StorageEvent) => { if (e.key === WEB_SESSION_CHANGE) location.reload(); };
    addEventListener('kb:web-session-ended', ended);
    addEventListener('storage', switched);
    return () => { removeEventListener('kb:web-session-ended', ended); removeEventListener('storage', switched); };
  });

  // the app is up and painted under the boot screen: it fades away over it
  $effect(() => { if (entered) requestAnimationFrame(() => requestAnimationFrame(bootOut)); });

  // The welcome: the boot screen's emblem lets go of its mark. Ours starts where that one stood and glides into its
  // place; the lights wake under the page, the words rise after it.
  function land(mark: HTMLElement) {
    const from = bootUnder();
    if (!from) return;
    const to = mark.getBoundingClientRect();
    mark.animate([{ transform: `translate(${from.x - to.x}px, ${from.y - to.y}px)` }, { transform: 'none' }], { duration: 820, easing: 'cubic-bezier(.32, .72, 0, 1)' });
  }

  // the sign-in, start to end: people are wary of typing a phone number into a window
  const STEPS = ['web.step1', 'web.step2', 'web.step3', 'web.step4'] as const;

  function attachWidget(widget: HTMLElement) {
    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.async = true;
    script.dataset.telegramLogin = 'KBTUappBot';
    script.dataset.size = 'large';
    script.dataset.onauth = 'kbTelegramLogin(user)';
    script.dataset.requestAccess = 'write';
    script.dataset.lang = i18n.lang === 'en' ? 'en' : 'ru'; // the widget has no Kazakh: Russian reads closer than English
    script.onerror = () => { widgetFailed = true; };
    window.kbTelegramLogin = (user) => void login(user);
    widget.append(script);
    return () => { delete window.kbTelegramLogin; script.remove(); };
  }
</script>

{#if entered}
  <App />
{:else}
  <main class="entrance scroll" aria-busy={view === 'checking'}>
    {#if view !== 'checking'}
      <div class="col">
        <span class="mark" {@attach land}><KbtuMark size={56} /></span>
        {#if view === 'offline'}
          <p class="fs-body dim in" style:--i={1}>{t('common.offline')}</p>
          <div class="enter in" style:--i={2}><Button kind="primary" onclick={check}>{t('common.retry')}</Button></div>
        {:else}
          <h1 class="fs-title in" style:--i={1}>{t('web.hello')}</h1>
          <p class="about fs-body dim in" style:--i={2}>{t('web.about')}</p>
          <!-- Telegram's button is an iframe we can't restyle: bare, clipped to its own pill, nothing drawn round it -->
          <div class="enter in" style:--i={3}>
            {#if !widgetFailed}
              {#key retry}<div class="widget" class:busy {@attach attachWidget} inert={busy}></div>{/key}
            {:else}
              <p class="fs-sub" role="alert">{t('web.widgetFailed')}</p>
              <Button kind="plain" onclick={() => { widgetFailed = false; retry++; }}>{t('common.retry')}</Button>
            {/if}
            {#if busy}<span class="spinner" role="status" aria-label={t('web.loading')}><LoaderCircle size={20} /></span>{/if}
            {#if loginFailed}<p class="fs-sub" role="alert">{t('web.signInFailed')}</p>{/if}
          </div>
          <ol class="steps fs-sub in" style:--i={4}>
            {#each STEPS as key, n (key)}<li><b class="num">{n + 1}</b><span>{t(key)}</span></li>{/each}
          </ol>
          <p class="private fs-sub in" style:--i={5}><LockKeyhole size={14} /><span>{t('web.private')}</span></p>
          <p class="fine fs-sub in" style:--i={6}>{t('web.cookie')} <a href="/privacy?lang={i18n.lang}" target="_blank" rel="noopener">{t('web.policy')}</a></p>
          {#if onIos && !installed}<p class="fine hint fs-sub in" style:--i={7}><SquareArrowUp size={15} /><span>{t('web.install')}</span></p>{/if}
          {#if onComputer}<a class="fine fs-sub in" style:--i={7} href="/show">{t('tgo.show')}</a>{/if}
        {/if}
      </div>
    {/if}
  </main>
{/if}

<style>
  /* no ground of its own: index.html's boot screen lies under it, its lights awake. No cards, no boxes: type on the
     ground, hairlines between the steps, Telegram's own button the one filled thing */
  .entrance { position: absolute; inset: 0; display: flex; flex-direction: column;
    padding: calc(var(--safe-top) + var(--s-8)) var(--s-6) calc(var(--safe-bottom) + var(--s-6)); text-align: center; }
  /* margin auto, not justify-content: a short window scrolls from the top instead of cutting it */
  .col { display: flex; flex-direction: column; align-items: center; width: 100%; max-width: 320px; margin: auto; }
  .mark { display: flex; flex: none; margin-bottom: var(--s-6); color: var(--text); }
  /* the words rise one after another behind the mark, all inside ~1.3 s */
  .in { animation: up 640ms var(--ease-spring) both; animation-delay: calc(200ms + var(--i) * 70ms); }
  @keyframes up { from { opacity: 0; transform: translateY(16px); } }

  .about { max-width: 28ch; margin-top: var(--s-3); text-wrap: balance; }
  .enter { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); margin-top: var(--s-8); }
  .enter p { max-width: 30ch; text-wrap: balance; }
  .widget { display: flex; justify-content: center; min-height: 40px; max-width: 100%; border-radius: var(--r-full); transition: opacity var(--t-base) var(--ease); }
  .widget:not(:has(:global(iframe))) { width: 224px; background: var(--fill); } /* its place while Telegram's script loads */
  .widget.busy { opacity: 0.5; }
  /* color-scheme: else Chromium paints white corners behind the button in dark */
  .widget :global(iframe) { display: block; max-width: 100%; border-radius: var(--r-full); color-scheme: light; }

  .steps { width: 100%; margin-top: var(--s-8); list-style: none; text-align: start; color: var(--text-2); }
  .steps li { display: flex; gap: var(--s-3); padding-block: 10px; }
  .steps li + li { border-top: 0.5px solid var(--separator); }
  .steps b { flex: none; width: 1.1em; font-weight: 600; color: var(--text-3); }
  .private { display: flex; gap: var(--s-2); width: 100%; margin-top: var(--s-3); padding-top: var(--s-4); border-top: 0.5px solid var(--separator);
    text-align: start; color: var(--text-3); }
  .private :global(svg) { flex: none; margin-top: 2px; }
  .fine { max-width: 34ch; margin-top: var(--s-6); color: var(--text-3); text-wrap: balance; }
  .fine a, a.fine { color: var(--text-2); text-decoration: underline; text-decoration-color: var(--line-2); text-underline-offset: 3px; }
  .hint { display: flex; gap: var(--s-2); margin-top: var(--s-4); text-align: start; }
  .hint :global(svg) { flex: none; margin-top: 1px; }

  .spinner { display: flex; color: var(--text-2); animation: turn 900ms linear infinite; }
  @keyframes turn { to { transform: rotate(1turn); } }
  @media (prefers-reduced-motion: reduce) { .in, .spinner { animation: none; } }
</style>
