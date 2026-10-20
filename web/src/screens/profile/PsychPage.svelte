<script lang="ts">
  // The psychological service (PLAN 20, owner Oct 18 + Oct 20: "maximum wow"): a full-screen page of support, not a
  // booking flow. Behind it a live sky (one WebGL shader): night when it opens, the sun rises as you scroll down and the
  // clouds part. A breathing orb (4 s in, 2 s hold, 6 s out), warm words, KBTU's psychologist with the nearest free hour
  // (psych.py) and a link to KBTU's own booking page: nothing about the student passes through us (mental-health data
  // is special-category). The crisis lines are always on the page, never behind a tap, each checked at its source on
  // Oct 20, 2026: 150, the national line for children and youth (telephone150.kz: 24/7, free, anonymous, WhatsApp
  // +7 708 106 0810); 1303, Almaty's Mental Health Centre (cpzalmaty.kz/kontakty: crisis line, 24/7); 111 (order
  // No. 378/NK of Jun 28, 2024, adilet.zan.kz V2400034643: free, round the clock, psychological help, kk/ru); 112. Power saving or reduced motion: the sky is drawn once and stays still.
  import { onMount } from 'svelte';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import Phone from '@lucide/svelte/icons/phone';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { power } from '../../lib/state/power.svelte';
  import { api } from '../../lib/api';
  import { PSYCHOLOGIST } from '../../lib/academic';
  import { t } from '../../lib/i18n/index.svelte';
  import { whenLine } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';

  // the youth line first (owner, Oct 20), its WhatsApp for whoever can't speak; then Almaty's mental-health centre,
  // the family line, the emergency number
  const WA150 = 'https://wa.me/77081060810';
  const LINES = ['1303', '111', '112'] as const;

  let { overlay }: { overlay: Overlay } = $props();
  $effect(() => { overlay.title = t('psy.title'); overlay.icon = HeartHandshake; overlay.theme = 'dark'; });

  let next = $state<number | null>(null), full = $state(false);
  api.psych().then((r) => { next = r.next; full = !!r.full; }, () => {});

  let page: HTMLDivElement, canvas: HTMLCanvasElement;
  let flat = $state(false); // no WebGL: the CSS sky
  let gone = false;

  // ---- breathing: 4 s in, 2 s hold, 6 s out; the orb's CSS animation runs the same 12 s from the same moment ----
  const IN = 4000, HOLD = 2000, CYCLE = 12000;
  let phase = $state<'in' | 'hold' | 'out'>('in');
  let felt = $state(false); // a tap on the orb: a soft buzz at each turn
  const born = performance.now();
  function tick() {
    const p = (performance.now() - born) % CYCLE;
    const now = p < IN ? 'in' : p < IN + HOLD ? 'hold' : 'out';
    if (now !== phase) { phase = now; if (felt && now !== 'hold') haptic.soft(); }
  }

  // ---- the sky ----
  const FRAG = `precision mediump float;
uniform vec2 R; uniform float T; uniform float D;
float h(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3. - 2. * f);
  return mix(mix(h(i), h(i + vec2(1, 0)), f.x), mix(h(i + vec2(0, 1)), h(i + vec2(1, 1)), f.x), f.y); }
float fbm(vec2 p){ float v = 0., a = .5; for (int i = 0; i < 5; i++) { v += a * n(p); p = p * 2.03 + 11.7; a *= .5; } return v; }
void main(){
  vec2 uv = gl_FragCoord.xy / R; float k = R.x / R.y; vec2 q = vec2((uv.x - .5) * k, uv.y);
  vec3 top = mix(vec3(.02, .025, .07), vec3(.11, .13, .33), D);
  vec3 mid = mix(vec3(.06, .07, .19), vec3(.62, .36, .52), D);
  vec3 low = mix(vec3(.10, .09, .26), vec3(1., .62, .42), D);
  vec3 c = mix(low, mid, smoothstep(0., .45, uv.y)); c = mix(c, top, smoothstep(.4, 1., uv.y));
  vec2 sun = vec2(0., mix(-.32, .2, D)); float r = length(q - sun);
  vec3 warm = vec3(1., .78, .55);
  c += warm * (exp(-r * 3.2) * .55 + exp(-r * 14.) * .9) * (.25 + .75 * D);
  c += vec3(1., .96, .88) * smoothstep(.075, .065, r) * smoothstep(-.2, .05, sun.y);
  float s = h(floor(gl_FragCoord.xy / 2.)); float tw = .5 + .5 * sin(T * 1.7 + s * 60.);
  c += vec3(.9, .92, 1.) * step(.9965, s) * tw * smoothstep(.25, .8, uv.y) * (1. - D) * .9;
  vec2 cp = vec2(q.x * 1.3 + T * .012, uv.y * 3.2 - T * .004);
  float cl = fbm(cp * 1.6 + fbm(cp + T * .02) * .8);
  float dens = smoothstep(.36 + D * .2, .78, cl) * smoothstep(1., .3, uv.y);
  vec3 cc = mix(vec3(.2, .2, .4), mix(vec3(.95, .55, .55), warm, .5), D) + warm * exp(-r * 2.5) * D * .8;
  c = mix(c, cc, dens * .85);
  vec2 dp = gl_FragCoord.xy / R.y * 90. + vec2(T * 1.1, -T * 2.3);
  float dd = h(floor(dp)); vec2 fp = fract(dp) - .5;
  c += warm * step(.985, dd) * smoothstep(.22, 0., length(fp)) * (.15 + .5 * D) * (.5 + .5 * sin(T * 2. + dd * 40.));
  c += (h(gl_FragCoord.xy + T) - .5) / 255. * 2.;
  gl_FragColor = vec4(c, 1.);
}`;

  onMount(() => {
    haptic.soft();
    page.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 420, easing: 'ease-out' });
    const undo = hideChrome();
    const timer = setInterval(tick, 100);

    const gl = canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' });
    if (!gl) { flat = true; return () => { undo(); clearInterval(timer); }; }
    const sh = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, 'attribute vec2 p;void main(){gl_Position=vec4(p,0,1);}'));
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { flat = true; return () => { undo(); clearInterval(timer); }; }
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    const uR = gl.getUniformLocation(prog, 'R'), uT = gl.getUniformLocation(prog, 'T'), uD = gl.getUniformLocation(prog, 'D');

    // half resolution: the sky is soft anyway, and a phone's GPU stays cool
    const size = () => { const q = Math.min(devicePixelRatio, 2) * 0.5; canvas.width = Math.round(innerWidth * q); canvas.height = Math.round(innerHeight * q); gl.viewport(0, 0, canvas.width, canvas.height); };
    size();
    addEventListener('resize', size);
    const still = () => power.lite || matchMedia('(prefers-reduced-motion: reduce)').matches;
    let dawn = 0, raf = 0, last = 0;
    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      if (now - last < 33 && last) return; // ~30 fps
      last = now;
      const max = page.scrollHeight - page.clientHeight;
      // the sun starts rising on its own when the page opens, then follows the scroll
      const want = Math.max(Math.min(0.3, (now - born) / 9000), max > 0 ? page.scrollTop / max : 0);
      dawn += (want - dawn) * 0.08;
      gl.uniform2f(uR, canvas.width, canvas.height); gl.uniform1f(uT, still() ? 20 : now / 1000); gl.uniform1f(uD, dawn);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (still() && Math.abs(want - dawn) < 0.002) { cancelAnimationFrame(raf); raf = 0; } // still: draw, then rest
    };
    raf = requestAnimationFrame(draw);
    const wake = () => { if (!raf) raf = requestAnimationFrame(draw); };
    page.addEventListener('scroll', wake, { passive: true });
    return () => { undo(); clearInterval(timer); cancelAnimationFrame(raf); removeEventListener('resize', size); gl.getExtension('WEBGL_lose_context')?.loseContext(); };
  });

  function leave() {
    if (gone) return;
    gone = true;
    page.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: 'ease-in', fill: 'forwards' }).onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });

  function breathe() { felt = !felt; haptic.tap(); }
  function book() { haptic.tap(); openLink(PSYCHOLOGIST); }
</script>

<div class="page" class:flat bind:this={page}>
  <canvas class="sky" bind:this={canvas} aria-hidden="true"></canvas>
  <div class="body">
    <section class="hero">
      <button class="orb" class:felt onclick={breathe} aria-label={t('psy.breathe')}>
        <span class="glow"></span><span class="ball"><span class="iri"></span><span class="hl"></span></span>
      </button>
      {#key phase}<p class="phase">{t(`psy.${phase}`)}</p>{/key}
      <p class="hint">{felt ? t('psy.felt') : t('psy.breathe')}</p>
    </section>

    <h1>{t('psy.hello')}</h1>
    <p class="lead">{t('psy.lead')}</p>

    <div class="card">
      <span class="cap">{t('psy.kbtu')}</span>
      <p class="tx">{t('psy.kbtuText')}</p>
      {#if next}
        <p class="slot"><span>{t('psy.next')}</span><b>{whenLine(next)}</b></p>
      {:else if full}
        <p class="slot busy">{t('psy.full')}</p>
      {/if}
      <button class="book" onclick={book}>{t('psy.book')}<ArrowUpRight size={18} /></button>
    </div>

    <div class="card now">
      <span class="cap">{t('psy.now')}</span>
      <div class="main">
        <a class="line" href="tel:150" onclick={() => haptic.tap()}>
          <b>150</b><span>{t('psy.150')}</span><i><Phone size={20} /></i>
        </a>
        <button class="wa" onclick={() => { haptic.tap(); openLink(WA150); }}><MessageCircle size={17} />{t('psy.write')}</button>
      </div>
      {#each LINES as n (n)}
        <a class="line" href="tel:{n}" onclick={() => haptic.tap()}>
          <b>{n}</b><span>{t(`psy.${n}`)}</span><i><Phone size={20} /></i>
        </a>
      {/each}
    </div>
    <p class="src">{t('psy.src')}</p>
  </div>
</div>

<style>
  .page {
    position: absolute; inset: 0; z-index: var(--z-sheet); overflow-y: auto; overscroll-behavior: contain; color: #fff;
    background: #05060F; -webkit-overflow-scrolling: touch;
  }
  .page.flat { background: linear-gradient(180deg, #070A1E, #1A1B45 55%, #4A2F5E 85%, #9A5A62); background-attachment: fixed; }
  .sky { position: fixed; inset: 0; width: 100%; height: 100%; display: block; pointer-events: none; }
  .flat .sky { display: none; }
  .body { position: relative; display: flex; flex-direction: column; gap: 14px; max-width: 480px; margin: 0 auto;
    padding: calc(var(--top) + 12px) 20px calc(var(--safe-bottom) + 28px); }

  /* the breathing orb: iridescence only inside the glass sphere */
  .hero { display: flex; flex-direction: column; align-items: center; padding: 36px 0 4px; }
  .orb { position: relative; width: 180px; height: 180px; border-radius: 50%; padding: 0; background: none; border: 0;
    animation: breathe 12s cubic-bezier(.45, 0, .35, 1) infinite; -webkit-tap-highlight-color: transparent; }
  .glow { position: absolute; inset: -40%; border-radius: 50%; background: radial-gradient(circle, rgba(255, 196, 150, 0.42), rgba(160, 120, 255, 0.14) 45%, transparent 68%);
    animation: pulse 12s cubic-bezier(.45, 0, .35, 1) infinite; }
  .ball { position: absolute; inset: 0; border-radius: 50%; overflow: hidden;
    background: radial-gradient(circle at 50% 55%, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.02) 60%, rgba(255, 255, 255, 0.14));
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.28), inset 0 -18px 40px rgba(255, 170, 140, 0.25), inset 0 20px 40px rgba(140, 160, 255, 0.2), 0 30px 60px -20px rgba(0, 0, 0, 0.6); }
  .iri { position: absolute; inset: -30%; filter: blur(14px); opacity: 0.95; mix-blend-mode: screen;
    background: conic-gradient(from 0deg, #FF9EC4, #FFC79A, #FFF1B8, #9EF0E0, #9DB7FF, #C9A2FF, #FF9EC4);
    -webkit-mask: radial-gradient(circle, rgba(0,0,0,.35) 18%, #000 58%); mask: radial-gradient(circle, rgba(0,0,0,.35) 18%, #000 58%);
    animation: spin 18s linear infinite; }
  .hl { position: absolute; left: 22%; top: 12%; width: 38%; height: 24%; border-radius: 50%; background: radial-gradient(closest-side, rgba(255, 255, 255, 0.7), transparent); transform: rotate(-24deg); }
  .orb.felt .ball { box-shadow: inset 0 0 0 1.5px rgba(255, 226, 190, 0.7), inset 0 -18px 40px rgba(255, 170, 140, 0.3), inset 0 20px 40px rgba(140, 160, 255, 0.2), 0 30px 60px -20px rgba(0, 0, 0, 0.6); }
  @keyframes breathe { 0% { transform: scale(0.7); } 33.33% { transform: scale(1); } 50% { transform: scale(1); } 100% { transform: scale(0.7); } }
  @keyframes pulse { 0% { opacity: 0.45; } 33.33%, 50% { opacity: 1; } 100% { opacity: 0.45; } }
  @keyframes spin { to { transform: rotate(360deg); } }
  .phase { margin: 40px 0 0; font: 300 30px/1 var(--font-display); letter-spacing: 0.02em; animation: fade 900ms ease-out; }
  @keyframes fade { from { opacity: 0; transform: translateY(6px); filter: blur(4px); } }
  .hint { margin: 10px 0 0; font: 500 13px/1.3 var(--font-text); color: rgba(255, 255, 255, 0.55); }

  h1 { margin: 22px 0 0; font: 680 34px/1.08 var(--font-display); letter-spacing: -0.03em; text-wrap: balance; }
  .lead { margin: 0 0 10px; font: 400 17px/1.45 var(--font-text); color: rgba(255, 255, 255, 0.78); text-wrap: pretty; }

  .card { display: flex; flex-direction: column; gap: 12px; padding: 18px; border-radius: 26px;
    background: rgba(16, 18, 40, 0.42); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.16), inset 0 0 0 1px rgba(255, 255, 255, 0.08), 0 24px 48px -24px rgba(0, 0, 0, 0.6);
    -webkit-backdrop-filter: blur(22px) saturate(140%); backdrop-filter: blur(22px) saturate(140%); }
  .cap { font: 700 12px/1 var(--font-text); letter-spacing: 0.14em; text-transform: uppercase; color: rgba(255, 214, 180, 0.85); }
  .tx { margin: 0; font: 400 15px/1.45 var(--font-text); color: rgba(255, 255, 255, 0.8); }
  .slot { display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 12px 14px; border-radius: 16px; background: rgba(255, 255, 255, 0.07); }
  .slot span { font: 500 13px/1.2 var(--font-text); color: rgba(255, 255, 255, 0.6); }
  .slot b { font: 650 19px/1.2 var(--font-display); }
  .slot.busy { font: 500 15px/1.4 var(--font-text); color: rgba(255, 255, 255, 0.85); }
  .book { display: flex; align-items: center; justify-content: center; gap: 6px; height: 54px; border: 0; border-radius: 18px;
    background: linear-gradient(120deg, #FFD3A8, #FFA4B8 55%, #C9A2FF); color: #1B1430; font: 680 17px/1 var(--font-text);
    box-shadow: 0 12px 30px -10px rgba(255, 150, 160, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.6); }
  .book:active, .line:active { transform: scale(0.98); }

  .line { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 14px; padding: 12px 12px 12px 16px;
    border-radius: 18px; background: rgba(255, 255, 255, 0.08); color: #fff; text-decoration: none; transition: transform 120ms ease-out; }
  .line b { min-width: 74px; font: 720 30px/1 var(--font-display); letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .line span { font: 450 13.5px/1.35 var(--font-text); color: rgba(255, 255, 255, 0.75); }
  .line i { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 50%; background: #fff; color: #14172E; }
  .main { display: flex; flex-direction: column; gap: 8px; padding: 6px; margin: 0 -6px; border-radius: 22px;
    background: linear-gradient(120deg, rgba(255, 211, 168, 0.22), rgba(201, 162, 255, 0.18)); }
  .main .line { background: none; padding: 6px 6px 2px 10px; }
  .main .line b { font-size: 40px; }
  .wa { display: flex; align-items: center; justify-content: center; gap: 7px; height: 44px; border: 0; border-radius: 16px;
    background: rgba(255, 255, 255, 0.12); color: #fff; font: 600 15px/1 var(--font-text); }
  .src { margin: 2px 4px 0; font: 400 11.5px/1.4 var(--font-text); color: rgba(255, 255, 255, 0.42); }

  /* power saving: no endless motion, no live blur; the orb still breathes (it is the point) */
  :global(html.lowfx) .iri, :global(html.lowfx) .glow { animation: none; }
  :global(html.lowfx) .card { -webkit-backdrop-filter: none; backdrop-filter: none; background: rgba(16, 18, 40, 0.82); }
  @media (prefers-reduced-motion: reduce) { .iri, .glow { animation: none; } .orb { animation-duration: 12s; } }
</style>
