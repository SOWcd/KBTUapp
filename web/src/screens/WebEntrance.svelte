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
  let busy = $state(false), loginFailed = $state(false), widgetFailed = $state(false), ready = $state(false);
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

  // The welcome: the boot screen's emblem lets go of its mark. Ours starts where that one stood, at that one's size,
  // and glides into its tile; the lights wake under the page, the words rise after it.
  const MARK = 44;
  function land(mark: HTMLElement) {
    const from = bootUnder();
    if (!from) return;
    const to = mark.getBoundingClientRect();
    mark.animate([{ transform: `translate(${from.x - to.x}px, ${from.y - to.y}px) scale(${from.width / to.width})` }, { transform: 'none' }],
      { duration: 820, easing: 'cubic-bezier(.32, .72, 0, 1)' });
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
    // Telegram's script puts its iframe in at once, empty and see-through: the slot's pill stays until the button is in it
    ready = false;
    script.onload = () => {
      const frame = widget.querySelector('iframe');
      if (frame) frame.addEventListener('load', () => { ready = true; }, { once: true });
      else ready = true;
    };
    // no button after 15 s (a held connection): the Retry, never an empty place
    const late = setTimeout(() => { if (!ready) widgetFailed = true; }, 15000);
    window.kbTelegramLogin = (user) => void login(user);
    widget.append(script);
    return () => { clearTimeout(late); delete window.kbTelegramLogin; script.remove(); };
  }
</script>

{#if entered}
  <App />
{:else}
  <main class="entrance scroll" aria-busy={view === 'checking'}>
    {#if view !== 'checking'}
      <div class="col" class:alone={view === 'offline'}>
        <!-- the tile's glass fades in on its own layer: the mark above it is already gliding in from the boot screen -->
        <span class="tile"><span class="pane glass in" style:--i={0}></span><span class="mark" {@attach land}><KbtuMark size={MARK} /></span></span>
        {#if view === 'offline'}
          <p class="fs-body dim in" style:--i={1}>{t('common.offline')}</p>
          <div class="retry in" style:--i={2}><Button kind="primary" onclick={check}>{t('common.retry')}</Button></div>
        {:else}
          <h1 class="fs-title in" style:--i={1}>{t('web.hello')}</h1>
          <p class="about fs-body dim in" style:--i={2}>{t('web.about')}</p>
          <ol class="steps fs-body">
            {#each STEPS as key, n (key)}<li class="in" style:--i={n + 3}><b class="num fs-cap">{n + 1}</b><span>{t(key)}</span></li>{/each}
          </ol>
          <p class="private fs-sub in" style:--i={7}><LockKeyhole size={16} /><span>{t('web.private')}</span></p>
          <!-- Telegram's button is an iframe we can't restyle: it sits in a glass dock of its own shape. The dock is
               its slot too: one size before, while and after the button loads, so nothing under it moves. It floats
               (sticky) at the bottom of a short window, the page passing under it: the way in is always in sight -->
          <div class="enter in" style:--i={8}>
            {#if !widgetFailed}
              <div class="dock glass glass-pill">
                {#key retry}<div class="widget" class:ready class:busy {@attach attachWidget} inert={busy}></div>{/key}
                {#if busy}<span class="spinner" role="status" aria-label={t('web.loading')}><LoaderCircle size={20} /></span>{/if}
              </div>
            {:else}
              <p class="fs-sub" role="alert">{t('web.widgetFailed')}</p>
              <Button kind="plain" onclick={() => { widgetFailed = false; retry++; }}>{t('common.retry')}</Button>
            {/if}
            {#if loginFailed}<p class="fs-sub" role="alert">{t('web.signInFailed')}</p>{/if}
          </div>
          <p class="fine fs-cap in" style:--i={9}>{t('web.cookie')} <a href="/privacy?lang={i18n.lang}" target="_blank" rel="noopener">{t('web.policy')}</a></p>
          {#if onIos && !installed}<p class="fine hint fs-cap in" style:--i={10}><SquareArrowUp size={14} /><span>{t('web.install')}</span></p>{/if}
          {#if onComputer}<a class="fine fs-cap in" style:--i={10} href="/show">{t('tgo.show')}</a>{/if}
        {/if}
      </div>
    {/if}
  </main>
{/if}

<style>
  /* No ground of its own: index.html's boot screen lies under it, its lights awake. Apple's welcome sheet: the mark in
     a glass app tile, the words, the steps as one quiet timeline, and the action at the bottom under the thumb with its
     privacy note above it and the fine print below. Glass only on the two floating things: the tile and the dock. */
  .entrance { position: absolute; inset: 0; display: flex; flex-direction: column;
    padding: calc(var(--safe-top) + var(--s-10)) var(--s-6) calc(var(--safe-bottom) + var(--s-6)); text-align: center; }
  /* margin auto, not justify-content: a short window scrolls from the top instead of cutting it. As tall as the
     phone: the action rests at the bottom there; a computer's window doesn't pull the page apart */
  .col { display: flex; flex-direction: column; align-items: center; flex: none; width: 100%; max-width: 336px; min-height: 100%; margin: auto; }
  @media (min-width: 600px) { .col { min-height: min(100%, 720px); } }
  .col.alone { min-height: 0; }
  .tile { position: relative; display: grid; place-items: center; flex: none; width: 84px; height: 84px; margin-bottom: var(--s-6); color: var(--text); }
  .pane { position: absolute; inset: 0; border-radius: var(--r-l); }
  .mark { position: relative; display: flex; transform-origin: 0 0; }
  /* the words rise one after another behind the mark, all inside ~1.4 s */
  .in { animation: up 640ms var(--ease-spring) both; animation-delay: calc(200ms + var(--i) * 60ms); }
  @keyframes up { from { opacity: 0; transform: translateY(16px); } }

  .about { max-width: 28ch; margin-top: var(--s-3); text-wrap: balance; }
  .retry { margin-top: var(--s-6); }

  /* the sign-in as a timeline: a numeral in a small disc, a hairline rail running through them */
  .steps { width: 100%; margin-top: var(--s-8); list-style: none; text-align: start; color: var(--text-2); }
  .steps li { position: relative; display: flex; align-items: flex-start; gap: var(--s-3); padding-bottom: var(--s-5); }
  .steps li:last-child { padding-bottom: 0; }
  .steps li:not(:last-child)::before { content: ''; position: absolute; left: 12.5px; top: 31px; bottom: 5px; width: 1px; background: var(--line-2); }
  .num { display: grid; place-items: center; flex: none; width: 26px; height: 26px; border-radius: var(--r-full); background: var(--fill);
    color: var(--text); font-variant-numeric: tabular-nums; }
  .steps span { padding-top: 3px; }

  .private { margin-top: auto; padding-top: var(--s-8); display: flex; flex-direction: column; align-items: center; gap: var(--s-2); max-width: 34ch; color: var(--text-3); text-wrap: balance; }
  .private :global(svg) { flex: none; color: var(--text-2); }
  .enter { position: sticky; bottom: calc(var(--safe-bottom) + var(--s-3)); z-index: 1; display: flex; flex-direction: column; align-items: center; gap: var(--s-3); margin-top: var(--s-5); }
  .enter p { max-width: 30ch; text-wrap: balance; }
  .dock { position: relative; display: grid; place-items: center; padding: var(--s-2); border-radius: var(--r-full); }
  /* the button's slot, the size Telegram draws it (large: 238 x 40 at most): a quiet pill breathes there until the
     button has loaded, so the place is never empty and nothing jumps when it comes */
  .widget { position: relative; display: flex; justify-content: center; align-items: center; width: 238px; max-width: 100%; height: 40px;
    border-radius: var(--r-full); transition: opacity var(--t-base) var(--ease); }
  .widget::before { content: ''; position: absolute; inset: 0; border-radius: inherit; background: var(--fill); animation: breathe 1400ms ease-in-out infinite alternate; }
  .widget.ready::before { display: none; }
  .widget.busy { opacity: 0.35; }
  /* color-scheme: else Chromium paints white corners behind the button in dark */
  .widget :global(iframe) { position: relative; display: block; max-width: 100%; border-radius: var(--r-full); color-scheme: light;
    opacity: 0; transition: opacity var(--t-slow) var(--ease); }
  .widget.ready :global(iframe) { opacity: 1; }
  @keyframes breathe { from { opacity: 0.45; } to { opacity: 1; } }

  .fine { max-width: 36ch; margin-top: var(--s-4); color: var(--text-3); font-weight: 450; line-height: 1.4; text-wrap: balance; }
  .fine a, a.fine { color: var(--text-2); text-decoration: underline; text-decoration-color: var(--line-2); text-underline-offset: 3px; }
  .hint { margin-top: var(--s-3); }
  .hint :global(svg) { display: inline; margin-inline-end: var(--s-1); vertical-align: -2px; }

  .spinner { position: absolute; display: flex; color: var(--text); animation: turn 900ms linear infinite; }
  @keyframes turn { to { transform: rotate(1turn); } }
  @media (prefers-reduced-motion: reduce) { .in, .spinner, .widget::before { animation: none; } }
</style>
