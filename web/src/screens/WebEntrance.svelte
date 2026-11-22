<script lang="ts" module>
  declare global {
    interface Window { kbTelegramLogin?: (user: unknown) => void }
  }
</script>

<script lang="ts">
  import { onMount } from 'svelte';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import App from '../App.svelte';
  import Button from '../ui/Button.svelte';
  import KbtuMark from '../ui/KbtuMark.svelte';
  import { api, ApiErr } from '../lib/api';
  import { WEB_SESSION_CHANGE } from '../lib/api/client';
  import { i18n, t } from '../lib/i18n/index.svelte';
  import { loadMe } from '../lib/state/session.svelte';
  import { onComputer, onIos } from '../lib/tg';

  const installed = matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone;
  let view = $state<'checking' | 'signin' | 'offline'>('checking');
  let entered = $state(false);
  let busy = $state(false), loginFailed = $state(false), widgetFailed = $state(false);
  let retry = $state(0);

  async function enter() {
    await loadMe(false, true, await api.me(true));
    entered = true;
  }

  async function check() {
    view = 'checking';
    try { await enter(); }
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
  <main class="entrance scroll">
    <span class="appmark mark"><KbtuMark size={42} /></span>
    <h1 class="t-h1">KBTU</h1>
    {#if view === 'checking'}
      <span class="spinner" role="status" aria-label={t('web.loading')}><LoaderCircle size={24} /></span>
    {:else if view === 'offline'}
      <p class="t-body">{t('common.offline')}</p>
      <Button kind="primary" onclick={check}>{t('common.retry')}</Button>
    {:else}
      {#key retry}<div class="widget" {@attach attachWidget} inert={busy}></div>{/key}
      {#if widgetFailed}
        <p class="t-callout" role="alert">{t('web.widgetFailed')}</p>
        <Button kind="plain" onclick={() => { widgetFailed = false; retry++; }}>{t('common.retry')}</Button>
      {/if}
      {#if busy}<span class="spinner" role="status" aria-label={t('web.loading')}><LoaderCircle size={20} /></span>{/if}
      {#if loginFailed}<p class="t-callout" role="alert">{t('web.signInFailed')}</p>{/if}
      <p class="t-foot">{t('web.cookie')} <a href="/privacy?lang={i18n.lang}" target="_blank" rel="noopener">{t('web.policy')}</a></p>
      {#if onIos && !installed}<p class="t-foot">{t('web.install')}</p>{/if}
      {#if onComputer}<a class="t-foot" href="/show">{t('tgo.show')}</a>{/if}
    {/if}
  </main>
{/if}

<style>
  .entrance { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: var(--s-3); padding: calc(var(--safe-top) + var(--s-6)) var(--gutter) calc(var(--safe-bottom) + var(--s-6)); text-align: center; }
  .mark { width: 76px; height: 76px; flex: none; box-shadow: none; }
  p { max-width: 30ch; }
  .widget { min-height: 40px; max-width: 100%; margin-block: var(--s-2); }
  /* the widget paints a square box behind its pill (white or black by theme): clip the frame to the pill */
  .widget :global(iframe) { max-width: 100%; color-scheme: light; border-radius: var(--r-full); }
  .spinner { display: flex; color: var(--text-2); animation: turn 900ms linear infinite; }
  @keyframes turn { to { transform: rotate(1turn); } }
  @media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }
</style>
