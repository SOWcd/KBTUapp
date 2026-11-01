<script lang="ts">
  // The privacy policy changed (lib/legal.ts): a signed-in student agrees again before using the app (owner, Nov 1:
  // the sheet got swiped away unread). Full screen, not a Sheet: no swipe, not in the overlay stack, so Back can't
  // close it. App renders it over the tabs and holds every other overlay until it's accepted. One button (owner, Nov 1:
  // no "Delete account" here); the way out is Telegram's own close, the policy one tap away.
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Archive from '@lucide/svelte/icons/archive';
  import Users from '@lucide/svelte/icons/users';
  import Send from '@lucide/svelte/icons/send';
  import Cpu from '@lucide/svelte/icons/cpu';
  import EyeOff from '@lucide/svelte/icons/eye-off';
  import Clock from '@lucide/svelte/icons/clock';
  import ThumbsUp from '@lucide/svelte/icons/thumbs-up';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Button from '../ui/Button.svelte';
  import { glass } from '../ui/glass';
  import { burst } from '../ui/burst';
  import { api } from '../lib/api';
  import { say } from '../lib/state/ui.svelte';
  import { session } from '../lib/state/session.svelte';
  import { t, i18n, type Key } from '../lib/i18n/index.svelte';
  import { haptic, openLink } from '../lib/tg';
  import { CONSENT_BOARD, CONSENT_BOTH, CONSENT_TGC, CONSENT_VERSION } from '../lib/legal';

  let busy = $state(false), done = $state(false), seal: HTMLElement;
  // what's new in the version asked, one short line each with its mark: v3 alone, the find-people forum (v4), the
  // student forum (v7), both (v8); a text's lines and its icons go in the same order (ru, kk, en alike)
  type Tone = 'accent' | 'success' | 'warning' | 'danger';
  const PARTS: [Key, [typeof Cpu, Tone][]][] = [
    ['consent.text', [[Archive, 'accent']]],
    ['consent.textForum', [[Users, 'accent'], [Send, 'success'], [Cpu, 'warning']]],
    ['consent.textBoard', [[EyeOff, 'accent'], [Cpu, 'warning'], [Clock, 'success'], [ThumbsUp, 'danger']]],
    ['consent.textTgc', [[Send, 'accent'], [Cpu, 'warning']]],
  ];
  // the channel's comments add "+tgc1" to whichever version (server logic/account.py CONSENT_TGC): its line, on top of the base's
  const tgc = $derived(session.policy.endsWith(CONSENT_TGC));
  const p = $derived(tgc ? session.policy.slice(0, -CONSENT_TGC.length) : session.policy);
  const asked = (k: Key) => k === 'consent.textTgc' ? tgc : k === 'consent.text' ? p === CONSENT_VERSION
    : k === 'consent.textForum' ? p !== CONSENT_VERSION && p !== CONSENT_BOARD : p === CONSENT_BOARD || p === CONSENT_BOTH;
  const items = $derived(PARTS.filter(([k]) => asked(k)).flatMap(([k, marks]) =>
    t(k).split('\n').map((text, i) => ({ text, icon: marks[i]?.[0] ?? ShieldCheck, tone: marks[i]?.[1] ?? 'accent' }))));

  async function agree() {
    if (busy) return;
    busy = true;
    try {
      const me = await api.consent(session.policy);
      // the accept as a moment: the seal turns green with a burst, then the gate lifts into the app
      done = true; haptic.ok();
      const r = seal.getBoundingClientRect();
      burst(false, { x: r.left + r.width / 2, y: r.top + r.height / 2 }, 'sparkles_3d');
      setTimeout(() => (session.me = me), 750);
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); busy = false; }
  }
</script>

<div class="gate" class:done role="dialog" aria-modal="true" aria-labelledby="cg-t">
  <span class="blob b1"></span><span class="blob b2"></span><span class="blob b3"></span>
  <div class="body">
    <div class="hero">
      <span class="halo"></span><span class="ring"></span>
      <span class="seal glass" bind:this={seal} use:glass><ShieldCheck size={40} strokeWidth={1.6} /></span>
    </div>
    <h1 id="cg-t" class="t-h1 rise" style="--i:1">{t('consent.title')}</h1>
    <div class="card glass glass-sheet rise" style="--i:2" use:glass>
      <span class="sweep"></span>
      {#each items as it, i (i)}
        <div class="item rise" style="--i:{i + 3}">
          <span class="tile {it.tone}"><it.icon size={18} strokeWidth={2} /></span>
          <p class="t-callout">{it.text}</p>
        </div>
      {/each}
      <button class="item lnk" onclick={() => { haptic.tap(); openLink(`${location.origin}/privacy?lang=${i18n.lang}`); }}>
        <span class="t-callout">{t('login.consentLink')}</span><ArrowUpRight size={18} />
      </button>
    </div>
  </div>
  <div class="foot rise" style="--i:{items.length + 3}">
    <Button kind="primary" size="l" full loading={busy} onclick={agree}>{t('consent.ok')}</Button>
  </div>
</div>

<style>
  .gate { position: absolute; inset: 0; z-index: calc(var(--z-sheet) - 1); display: flex; flex-direction: column; overflow: hidden;
    padding: var(--page-top) 20px calc(var(--safe-bottom) + 16px); background: var(--bg); animation: fade var(--t-base) ease-out both; }

  /* a living ground: three soft lights drifting slowly behind the glass */
  .blob { position: absolute; width: 70vw; height: 70vw; border-radius: 50%; filter: blur(60px); opacity: 0.55; pointer-events: none; animation: drift 18s ease-in-out infinite alternate; }
  .b1 { top: -18vw; left: -20vw; background: rgba(59, 107, 255, 0.55); }
  .b2 { top: 30%; right: -30vw; background: rgba(124, 77, 255, 0.45); animation-duration: 23s; animation-delay: -6s; }
  .b3 { bottom: -25vw; left: 5vw; background: rgba(53, 208, 255, 0.3); animation-duration: 27s; animation-delay: -12s; }
  :global(html[data-theme='light']) .blob { opacity: 0.3; }
  @keyframes drift { to { transform: translate(12vw, 8vh) scale(1.15); } }
  .body { position: relative; flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: none; display: flex; flex-direction: column; align-items: center; gap: 18px; padding: 40px 0 8px; }
  .body::-webkit-scrollbar { display: none; }
  /* centred while it fits, scrolled from the top when it doesn't (a short phone): justify-content would cut the top off */
  .body > :first-child { margin-top: auto; }
  .body > :last-child { margin-bottom: auto; }
  .hero { position: relative; width: 96px; height: 96px; display: grid; place-items: center; margin-bottom: 4px; animation: pop 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) both; }
  .seal { position: relative; width: 96px; height: 96px; border-radius: var(--r-full); display: grid; place-items: center; color: var(--accent-text); }
  /* a slow turning light behind the seal, its colours the app's blue and violet (the owner liked it here, Nov 1) */
  .halo { position: absolute; inset: -34px; border-radius: 50%; filter: blur(18px); opacity: 0.8; pointer-events: none;
    background: conic-gradient(from 0deg, rgba(59, 107, 255, 0.9), rgba(124, 77, 255, 0.85), rgba(53, 208, 255, 0.7), rgba(255, 107, 214, 0.55), rgba(59, 107, 255, 0.9));
    -webkit-mask: radial-gradient(closest-side, transparent 52%, black 60%, transparent 100%); mask: radial-gradient(closest-side, transparent 52%, black 60%, transparent 100%);
    animation: turn 9s linear infinite; }
  @keyframes turn { to { transform: rotate(1turn); } }
  .done .halo { filter: blur(22px) hue-rotate(-90deg); }
  /* the shield draws itself in, then the tick */
  .seal :global(svg path) { stroke-dasharray: 80; stroke-dashoffset: 80; animation: draw 1s 0.35s cubic-bezier(0.65, 0, 0.35, 1) forwards; }
  .seal :global(svg path + path) { animation-delay: 1.05s; animation-duration: 0.45s; }
  @keyframes draw { to { stroke-dashoffset: 0; } }
  .seal { transition: color 0.3s, transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
  .done .seal { color: var(--success-text); transform: scale(1.12); }
  /* accepted: the whole gate lifts and fades into the app */
  .gate.done { animation: lift 0.45s 0.3s cubic-bezier(0.4, 0, 1, 1) forwards; }
  @keyframes lift { to { opacity: 0; transform: scale(1.04); } }
  .ring { position: absolute; inset: 0; border-radius: var(--r-full); border: 1.5px solid var(--accent); opacity: 0; animation: pulse 2.8s 0.8s ease-out infinite; }
  @keyframes pulse { 0% { transform: scale(1); opacity: 0.55; } 100% { transform: scale(1.7); opacity: 0; } }
  @keyframes pop { from { transform: scale(0.4); opacity: 0; } }
  h1 { text-align: center; text-wrap: balance; }

  .card { position: relative; width: 100%; border-radius: var(--r-xl); padding: 6px 16px; display: flex; flex-direction: column; }
  /* one pass of light over the card once it has landed */
  .sweep { position: absolute; inset: 0; border-radius: inherit; overflow: hidden; pointer-events: none; }
  .sweep::after { content: ''; position: absolute; inset: -20% -60%; background: linear-gradient(105deg, transparent 40%, rgba(255, 255, 255, 0.14) 50%, transparent 60%);
    transform: translateX(-70%); animation: pass 1.6s 0.9s cubic-bezier(0.4, 0, 0.2, 1) both; }
  @keyframes pass { to { transform: translateX(70%); } }
  .item { position: relative; display: flex; align-items: flex-start; gap: 14px; padding: 13px 0; text-align: left; }
  .item + .item { border-top: 0.5px solid var(--separator); }
  .item p { flex: 1; color: var(--text); padding-top: 3px; }
  .tile { flex: none; width: 32px; height: 32px; border-radius: var(--r-xs); display: grid; place-items: center; }
  .accent { background: var(--accent-soft); color: var(--accent-text); }
  .success { background: var(--success-soft); color: var(--success-text); }
  .warning { background: var(--warning-soft); color: var(--warning-text); }
  .danger { background: var(--danger-soft); color: var(--danger-text); }
  .lnk { align-items: center; justify-content: space-between; color: var(--accent-text); font-weight: 620; }

  .foot { position: relative; padding-top: 14px; }
  /* one after another: the title, the card, each line, the button */
  .rise { animation: rise 0.55s calc(0.15s + var(--i) * 0.07s) cubic-bezier(0.22, 1, 0.36, 1) both; }
  @keyframes rise { from { opacity: 0; transform: translateY(14px); } }
  @keyframes fade { from { opacity: 0; } }
  :global(html.lowfx) .ring, :global(html.lowfx) .halo { animation: none; }
  :global(html.lowfx) .blob { animation: none; filter: none; opacity: 0.12; }
  @media (prefers-reduced-motion: reduce) { .blob, .ring, .halo, .sweep::after { animation: none; }
    .seal :global(svg path) { animation: none; stroke-dashoffset: 0; } }
</style>
