<script lang="ts" module>
  declare global {
    interface Window { kbTelegramLogin?: (user: unknown) => void }
  }
</script>

<script lang="ts">
  import { onMount } from 'svelte';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import SquareArrowUp from '@lucide/svelte/icons/square-arrow-up';
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

  async function enter() {
    await loadMe(false, true, await api.me(true));
    entered = true;
  }

  // while the session is checked the page draws nothing: index.html's boot screen (its lights, its mark) carries on
  async function check() {
    view = 'checking';
    bootOver();
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

  // the app is up and painted under the boot screen: it fades away over it
  $effect(() => { if (entered) requestAnimationFrame(() => requestAnimationFrame(bootOut)); });

  // The welcome: the boot screen's mark is ours from here. Ours starts where that one stood and glides into its place
  // (the glint carries on from the same moment), the lights stay as the ground, the words and the card rise after it.
  function land(mark: HTMLElement) {
    const from = bootUnder();
    if (!from) return;
    const to = mark.getBoundingClientRect();
    mark.animate([{ transform: `translate(${from.x - to.x}px, ${from.y - to.y}px)` }, { transform: 'none' }], { duration: 760, easing: 'cubic-bezier(.32, .72, 0, 1)' });
    const glint = mark.querySelector('i')?.getAnimations()[0];
    if (glint) glint.currentTime = from.glint;
  }

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
        <!-- .kb-mark: index.html's, the boot screen's own mark (one look, defined once) -->
        <span class="kb-mark mark" {@attach land}><KbtuMark size={48} /><i></i></span>
        {#if view === 'offline'}
          <p class="fs-body dim in" style:--i={1}>{t('common.offline')}</p>
          <div class="in" style:--i={2}><Button kind="primary" onclick={check}>{t('common.retry')}</Button></div>
        {:else}
          <h1 class="fs-title in" style:--i={1}>{t('web.hello')}</h1>
          <p class="about fs-body dim in" style:--i={2}>{t('web.about')}</p>
          <section class="card glass in" style:--i={3}>
            <i class="sweep" aria-hidden="true"></i>
            <!-- Telegram's button is an iframe we can't restyle: it sits in a glass well, clipped to the pill -->
            {#if !widgetFailed}
              {#key retry}<div class="well" class:busy><div class="widget" {@attach attachWidget} inert={busy}></div></div>{/key}
            {:else}
              <p class="fs-sub" role="alert">{t('web.widgetFailed')}</p>
              <Button kind="plain" onclick={() => { widgetFailed = false; retry++; }}>{t('common.retry')}</Button>
            {/if}
            {#if busy}<span class="spinner" role="status" aria-label={t('web.loading')}><LoaderCircle size={20} /></span>{/if}
            {#if loginFailed}<p class="fs-sub" role="alert">{t('web.signInFailed')}</p>{/if}
            <p class="fs-sub faint">{t('web.cookie')} <a href="/privacy?lang={i18n.lang}" target="_blank" rel="noopener">{t('web.policy')}</a></p>
          </section>
          {#if onIos && !installed}
            <p class="hint glass glass-pill fs-sub in" style:--i={4}><SquareArrowUp size={18} /><span>{t('web.install')}</span></p>
          {/if}
          {#if onComputer}<a class="fs-sub dim in" style:--i={4} href="/show">{t('tgo.show')}</a>{/if}
        {/if}
      </div>
    {/if}
  </main>
{/if}

<style>
  /* no ground of its own: index.html's boot screen lies under it, its lights drifting on */
  .entrance { position: absolute; inset: 0; display: flex; flex-direction: column;
    padding: calc(var(--safe-top) + var(--s-6)) var(--gutter) calc(var(--safe-bottom) + var(--s-6)); text-align: center; }
  /* margin auto, not justify-content: a short window scrolls from the top instead of cutting it */
  .col { position: relative; display: flex; flex-direction: column; align-items: center; gap: var(--s-3); width: 100%; max-width: 380px; margin: auto; }
  .mark { flex: none; margin-bottom: var(--s-3); }
  .mark i { animation-iteration-count: 1; } /* the glint it arrived with ends; a still mark from then on */
  /* the words and the card rise one after another behind the mark, all inside ~1.2 s */
  .in { animation: up 640ms var(--ease-spring) both; animation-delay: calc(240ms + var(--i) * 80ms); }
  @keyframes up { from { opacity: 0; transform: translateY(18px); } }

  .about { max-width: 30ch; text-wrap: balance; }
  .card { position: relative; display: flex; flex-direction: column; align-items: center; gap: var(--s-3); width: 100%; margin-top: var(--s-4);
    padding: var(--s-6) var(--s-5) var(--s-5); border-radius: var(--r-xl); }
  .card p { max-width: 32ch; text-wrap: balance; }
  .card a { color: var(--accent-text); }
  /* one slow glint across the glass as it settles */
  .sweep { position: absolute; inset: 0; z-index: -1; overflow: hidden; border-radius: inherit; pointer-events: none; }
  .sweep::after { content: ''; position: absolute; inset: 0 auto 0 0; width: 45%; opacity: 0;
    background: linear-gradient(100deg, transparent, var(--lg-spot), transparent); animation: glint 1100ms var(--ease) 900ms; }
  @keyframes glint { from { opacity: 1; transform: translateX(-110%); } to { opacity: 1; transform: translateX(330%); } }

  .well { display: flex; justify-content: center; min-width: 200px; max-width: 100%; padding: 6px; border-radius: var(--r-full);
    background: var(--fill); box-shadow: var(--lg-bevel), var(--lg-lift); transition: opacity var(--t-base) var(--ease); }
  .well.busy { opacity: 0.5; }
  .widget { display: flex; min-height: 40px; max-width: 100%; }
  /* color-scheme: else Chromium paints white corners behind the button in dark */
  .widget :global(iframe) { display: block; max-width: 100%; border-radius: var(--r-full); color-scheme: light; }

  .hint { position: relative; display: flex; align-items: center; gap: var(--s-2); margin-top: var(--s-2); padding: var(--s-3) var(--s-4);
    border-radius: var(--r-l); color: var(--text-2); text-align: start; }
  .hint span { text-wrap: balance; }
  .hint :global(svg) { flex: none; color: var(--accent-text); }

  .spinner { display: flex; color: var(--text-2); animation: turn 900ms linear infinite; }
  @keyframes turn { to { transform: rotate(1turn); } }
  @media (prefers-reduced-motion: reduce) { .in, .sweep::after, .spinner { animation: none; } }
</style>
