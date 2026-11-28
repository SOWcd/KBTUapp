<script lang="ts">
  // The applicant's page (/ako#<secret>, /ako/o/<slug>, /ako for slug ako): its own root outside the app's shell, in
  // the app's look: glass pills floating on top (Back, the step, the language), content on grouped surface cards, the
  // one action a glass island with a calm ink capsule (the event sheet's). The program step is here; the other steps
  // and the status page are components. Shared looks live here under :global(.ako .a-*).
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import Check from '@lucide/svelte/icons/check';
  import Video from '@lucide/svelte/icons/video';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import Link2Off from '@lucide/svelte/icons/link-2-off';
  import WifiOff from '@lucide/svelte/icons/wifi-off';
  import Button from '../../ui/Button.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { ako } from '../../lib/api/ako';
  import type { AkoStart, AkoView } from '../../lib/api/types';
  import { i18n, setLang, loadLang } from '../../lib/i18n/index.svelte';
  import { aw, type AkoKey } from '../../lib/i18n/ako';
  import { time, weekday, dayMonth } from '../../lib/time';
  import AkoDocs, { errOf, errKey } from './AkoDocs.svelte';
  import AkoSlots from './AkoSlots.svelte';
  import AkoSend from './AkoSend.svelte';
  import AkoStatus from './AkoStatus.svelte';

  type Lang = 'ru' | 'kk' | 'en';
  type Step = 'program' | 'docs' | 'slot' | 'send';
  const LANGS: [Lang, AkoKey][] = [['ru', 'ako.lang.ru'], ['kk', 'ako.lang.kk'], ['en', 'ako.lang.en']];

  // the secret rides in the fragment (/ako#<secret>): a browser never sends it, so no server or proxy log holds it
  const path = location.pathname;
  const pub = /^\/ako\/o\/([^/]+)\/?$/.exec(path);
  // plain /ako (no fragment): the Academy's own start page, the short link for its website
  const slug = pub ? decodeURIComponent(pub[1]) : /^\/ako\/?$/.test(path) && !location.hash ? 'ako' : '';
  let token = $state(pub ? '' : (/^#([A-Za-z0-9_-]{43})$/.exec(location.hash)?.[1] ?? ''));
  // another link pasted into this tab changes only the fragment: the page starts over with it
  addEventListener('hashchange', () => location.reload());

  let phase = $state<'loading' | 'gone' | 'offline' | 'ready'>('loading');
  let start = $state<AkoStart | null>(null);
  let view = $state<AkoView | null>(null);
  let step = $state<Step>('program');
  let dir = $state(1);
  let pick = $state<string | null>(null);
  let busy = $state(false);
  let note = $state('');
  let fresh = $state(false);
  let want = $state<Lang | ''>('');
  let scroller: HTMLDivElement | undefined = $state();

  const data = $derived(view ?? start);
  const orgName = $derived(data ? (data.org.name[i18n.lang] ?? data.org.name.ru) : '');
  const program = $derived(view?.programs.find((p) => p.key === view?.program) ?? null);
  const steps = $derived<Step[]>(['docs', ...(program?.interview ? (['slot'] as const) : []), 'send']);
  const idx = $derived(steps.indexOf(step));
  const wizard = $derived(phase === 'ready' && (!view || view.status === 'draft'));
  const canBack = $derived(wizard && (step === 'program' ? !!view?.program : idx > 0));
  const kinds = $derived((['degree', 'short'] as const)
    .map((k) => ({ k, list: (data?.programs ?? []).filter((p) => p.kind === k) })).filter((g) => g.list.length));
  const k = (s: string) => s as AkoKey;

  async function open() {
    const v = await ako.view(token);
    if (v.lang && v.lang !== i18n.lang) { await loadLang(v.lang); setLang(v.lang); }
    view = v; pick = v.program; step = v.program ? 'docs' : 'program';
  }
  async function boot() {
    phase = 'loading';
    try {
      if (token) await open();
      else if (slug) { start = await ako.start(slug); step = 'program'; }
      else { phase = 'gone'; return; }
      phase = 'ready';
    } catch (e) { phase = errOf(e).code === 'not_found' ? 'gone' : 'offline'; }
  }
  boot();

  async function lang(l: Lang) {
    if (l === i18n.lang) return;
    want = l;
    try { await loadLang(l); setLang(l); if (token) ako.patch(token, { lang: l }).catch(() => {}); }
    finally { want = ''; }
  }
  function go(s: Step, d: number) { dir = d; step = s; note = ''; scroller?.scrollTo(0, 0); }
  function back() {
    if (step === 'program') { pick = view?.program ?? null; go('docs', -1); }
    else if (idx > 0) go(steps[idx - 1], -1);
  }
  async function next() {
    note = '';
    if (step === 'program') {
      if (!pick) return; // the island shows only with a program picked
      busy = true;
      try {
        if (!token) {
          const r = await ako.begin(slug, pick, i18n.lang);
          token = r.token; history.replaceState(null, '', '/ako#' + token);
          await open();
        } else if (view && pick !== view.program) { await ako.patch(token, { program: pick }); view = await ako.view(token); }
        go('docs', 1);
      } catch (e) { note = aw(errKey(e)); } finally { busy = false; }
      return;
    }
    if (!view || !program) return;
    if (step === 'docs') {
      const miss = program.first.filter((d) => !view!.files.some((f) => f.doc === d));
      if (miss.length) { note = aw('ako.missing', { list: miss.map((d) => aw(k('ako.doc.' + d))).join(', ') }); return; }
    }
    if (step === 'slot' && !view.slot && view.slots.length) { note = aw('ako.needSlot'); return; }
    go(steps[idx + 1], 1);
  }
  function changed(v: AkoView) { view = v; note = ''; }
</script>

<div class="ako" bind:this={scroller}>
  <div class="col">
    <header class="top">
      {#if canBack}<button type="button" class="glass glass-pill pill rnd" aria-label={aw('ako.back')} onclick={back}><ChevronLeft size={20} strokeWidth={2.4} /></button>{/if}
      <div class="glass glass-pill pill cap" class:stepped={wizard && idx >= 0}>
        <span class="mark"><KbtuMark size={20} /></span>
        {#if wizard && idx >= 0}<span>{aw('ako.stepOf', { n: idx + 1, all: steps.length })}</span>{/if}
      </div>
      <nav class="glass glass-pill pill lang">
        {#each LANGS as [l, name] (l)}
          <button type="button" class:on={(want || i18n.lang) === l} aria-pressed={(want || i18n.lang) === l} onclick={() => lang(l)}>{aw(name)}</button>
        {/each}
      </nav>
    </header>

    <main>
      {#if phase === 'loading'}
        <div class="sk" aria-busy="true" aria-hidden="true">
          <i class="b t"></i><i class="b l"></i><i class="b l s"></i>
          <i class="b c"></i><i class="b c"></i>
        </div>
      {:else if phase === 'gone' || phase === 'offline'}
        <section class="state">
          <span class="ico">{#if phase === 'gone'}<Link2Off size={30} />{:else}<WifiOff size={30} />{/if}</span>
          <p class="a-h2">{aw(phase === 'gone' ? 'ako.err.gone' : 'ako.err.network')}</p>
          {#if phase === 'offline'}<Button size="l" onclick={boot}>{aw('ako.retry')}</Button>{/if}
        </section>
      {:else if view && view.status !== 'draft'}
        {#if orgName}<p class="org">{orgName}</p>{/if}
        <AkoStatus {view} {token} {fresh} onchange={changed} />
      {:else}
        {#key step}
          <section class="step" style:--dx={dir}>
            {#if step === 'program' || !view || !program}
              {#if orgName}<p class="org">{orgName}</p>{/if}
              <h1 class="a-h1">{aw(view ? 'ako.step.program' : 'ako.title')}</h1>
              {#if !view}<p class="a-lead">{aw(data?.programs.some((p) => p.interview) ? 'ako.introInterview' : 'ako.intro')}</p>{/if}
              <div class="kinds" role="radiogroup" aria-label={aw('ako.step.program')}>
                {#each kinds as g (g.k)}
                  <section class="a-grp">
                    <header class="a-head"><h2>{aw(g.k === 'degree' ? 'ako.degree' : 'ako.short')}</h2><span>{g.list.length}</span></header>
                    {#each g.list as p (p.key)}
                      {@const info = p.info[i18n.lang] ?? p.info.ru}
                      <div class="a-row prog" class:on={pick === p.key}>
                        <button type="button" class="pk" role="radio" aria-checked={pick === p.key} onclick={() => { pick = p.key; note = ''; }}>
                          <span class="ptx">
                            <b class="pt">{info.title}</b>
                            {#if info.sub}<span class="ps">{info.sub}</span>{/if}
                            <span class="a-sub">{[info.length, info.format].filter(Boolean).join(' · ')}</span>
                            {#if info.price}<span class="pp">{info.price}</span>{/if}
                            <span class="a-sub pi">{#if p.interview}<Video size={18} />{/if}{aw(p.interview ? 'ako.interviewYes' : 'ako.interviewNo')}</span>
                          </span>
                          <span class="radio">{#if pick === p.key}<Check size={16} strokeWidth={3} />{/if}</span>
                        </button>
                        {#if p.url}<a class="more" href={p.url} target="_blank" rel="noopener noreferrer">{aw('ako.source')}<ArrowUpRight size={16} /></a>{/if}
                      </div>
                    {/each}
                  </section>
                {/each}
              </div>
            {:else if step === 'docs'}
              {@const info = program.info[i18n.lang] ?? program.info.ru}
              <div class="a-card mine">
                <span class="mtx"><span class="a-sub">{aw('ako.yourProgram')}</span><b>{info.title}</b></span>
                <Button kind="gray" size="s" onclick={() => go('program', -1)}>{aw('ako.changeProgram')}</Button>
              </div>
              <AkoDocs {view} {token} onchange={changed} />
            {:else if step === 'slot'}
              <AkoSlots {view} {token} onchange={changed} />
            {:else}
              <AkoSend {view} {token} onsent={(v) => { fresh = true; view = v; scroller?.scrollTo(0, 0); }} />
            {/if}
          </section>
        {/key}

        <!-- the one action: an island over the content, there only once it can be taken (a program is picked) -->
        {#if step !== 'send' && (step !== 'program' || pick)}
          <div class="a-bar">
            <div class="glass glass-pill a-island">
              {#if note}<p class="tnote bad" role="alert">{note}</p>
              {:else if step === 'slot' && view?.slot}
                <p class="tnote got" role="status"><Check size={18} strokeWidth={2.6} />{aw('ako.slotPicked', { when: `${weekday(view.slot.at)}, ${dayMonth(view.slot.at)}, ${time(view.slot.at)}` })}</p>
              {/if}
              <Button size="l" full loading={busy} onclick={next}>{aw('ako.next')}{#snippet icon()}<ArrowRight size={20} />{/snippet}</Button>
            </div>
          </div>
        {/if}
      {/if}
    </main>

    <footer class="foot">
      <span>{aw('ako.on')}</span>
      <a href="/privacy?lang={i18n.lang}" target="_blank" rel="noopener">{aw('ako.policy')}</a>
    </footer>
  </div>
</div>

<style>
  /* the app's calm ink in place of the accent's blue (the owner: never a saturated button): the main button, the
     radios, the picked time and the links all take the text colour, as the event sheet's island does */
  .ako { --accent: var(--text); --on-accent: var(--bg); --accent-text: var(--text); --accent-soft: var(--fill);
    position: fixed; inset: 0; overflow-x: hidden; overflow-y: auto; -webkit-overflow-scrolling: touch; background: var(--bg); color: var(--text);
    font: 450 var(--fs-row)/1.45 var(--font-text); letter-spacing: -0.011em; -webkit-text-size-adjust: 100%; }
  .col { display: flex; flex-direction: column; min-height: 100%; max-width: 560px; margin: 0 auto; padding: 0 var(--s-4); }
  main { flex: 1; display: flex; flex-direction: column; }

  /* glass pills over the content, the web app's bar (ui/StandaloneBar): Back, the mark with the step, the language */
  .top { position: sticky; top: 0; z-index: var(--z-nav); display: flex; align-items: center; gap: var(--s-2);
    padding: calc(var(--safe-top) + var(--s-2)) 0 var(--s-3); pointer-events: none; }
  @media (min-width: 700px) { .top { padding-top: var(--s-6); } }
  /* what scrolls under the pills fades into the ground: words never run through them */
  .top::before { content: ''; position: absolute; inset: 0 calc(-1 * var(--s-4)) calc(-1 * var(--s-3)); z-index: -1; background: linear-gradient(var(--bg) 55%, transparent); }
  .pill { flex: none; display: flex; align-items: center; height: 44px; border-radius: var(--r-full); color: var(--text); pointer-events: auto;
    font: 600 var(--fs-sub)/1 var(--font-text); letter-spacing: -0.005em; }
  .rnd { justify-content: center; width: 44px; -webkit-tap-highlight-color: transparent; transition: transform var(--t-base) var(--ease-bounce); }
  .rnd:active { transform: scale(0.92); }
  .cap { gap: var(--s-2); padding: 0 var(--s-4); }
  .mark { display: inline-flex; }
  @media (max-width: 350px) { .stepped .mark { display: none; } }
  .lang { margin-left: auto; padding: 3px; }
  .lang button { position: relative; min-width: 40px; height: 38px; padding: 0 var(--s-2); -webkit-tap-highlight-color: transparent; border-radius: var(--r-full); font: inherit; letter-spacing: 0.02em;
    color: var(--text-2); transition: color var(--t-base) var(--ease), background-color var(--t-base) var(--ease); }
  .lang button::after { content: ''; position: absolute; inset: -3px 0; } /* 38 seen, 44 to the finger */
  .lang button.on { color: var(--text); background: var(--lens); box-shadow: var(--lens-shadow); } /* the tab bar's lens */

  .org { margin-bottom: var(--s-3); max-width: 24em; text-wrap: balance; font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }

  .step { flex: 1; padding: var(--s-2) 0 var(--s-6); animation: slide var(--t-slow) var(--ease) both; }
  @keyframes slide { from { opacity: 0; transform: translateX(calc(var(--dx, 1) * 28px)); } }

  .kinds { margin-top: var(--s-5); }
  .prog { transition: background-color var(--t-base) var(--ease); }
  .prog.on { background: var(--fill); }
  .pk { display: flex; align-items: flex-start; gap: var(--s-3); width: 100%; padding: var(--s-4) var(--s-5); text-align: left; color: inherit;
    -webkit-tap-highlight-color: transparent; }
  .ptx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--s-1); }
  .pt { font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .ps { color: var(--text-2); line-height: 1.35; }
  .pp { margin-top: var(--s-1); font-weight: 600; }
  .pi { display: inline-flex; align-items: center; gap: var(--s-2); }
  .radio { flex: none; display: grid; place-items: center; width: 26px; height: 26px; border-radius: var(--r-full);
    box-shadow: inset 0 0 0 1.5px var(--line-2); color: var(--on-accent); transition: background var(--t-fast); }
  .on .radio { background: var(--accent); box-shadow: none; animation: pop var(--t-base) var(--ease-bounce); }
  @keyframes pop { from { transform: scale(0.6); } }
  /* the university's own page about the program: a quiet grey link, never the accent */
  .more { display: inline-flex; align-items: center; gap: var(--s-1); min-height: 44px; margin: calc(-1 * var(--s-3)) var(--s-5) var(--s-1);
    font: 450 var(--fs-body)/1.2 var(--font-text); color: var(--text-3); text-decoration: none; -webkit-tap-highlight-color: transparent; }
  .more:active { opacity: 0.5; }
  .mine { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); padding: var(--s-3) var(--s-4) var(--s-3) var(--s-5); margin-bottom: var(--s-6); }
  .mtx { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .mtx b { font: 600 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.012em; }

  .state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s-6);
    padding: var(--s-10) 0; text-align: center; }
  .ico { display: grid; place-items: center; width: 72px; height: 72px; border-radius: var(--r-full); background: var(--fill); color: var(--text-2); }

  .sk { display: flex; flex-direction: column; gap: var(--s-3); padding-top: var(--s-4); }
  .b { display: block; border-radius: var(--r-full); background: var(--fill); animation: breathe 1.4s ease-in-out infinite alternate; }
  .b.t { width: 60%; height: 26px; border-radius: var(--r-s); }
  .b.l { width: 92%; height: 14px; }
  .b.s { width: 55%; margin-bottom: var(--s-4); }
  .b.c { height: 220px; border-radius: var(--r-group); }
  @keyframes breathe { from { opacity: 1; } to { opacity: 0.45; } }

  .foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 0 var(--s-4);
    padding: var(--s-4) 0 calc(var(--safe-bottom) + var(--s-4)); font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .foot a { display: inline-flex; align-items: center; min-height: 48px; color: inherit; text-decoration: underline; text-underline-offset: 3px; }

  /* ---- shared with the other AKO components ---- */
  :global(.ako h1), :global(.ako h2), :global(.ako p) { margin: 0; }
  /* a step's name at a section's size: no web-style giant page title */
  :global(.ako .a-h1) { font: 700 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.025em; text-wrap: balance; }
  :global(.ako .a-h2) { font: 700 var(--fs-t3)/1.22 var(--font-display); letter-spacing: -0.02em; text-wrap: balance; }
  :global(.ako .a-lead) { margin-top: var(--s-2); font: 450 var(--fs-body)/1.45 var(--font-text); color: var(--text-2); }
  /* :where: a component's own class must win over the shared look (padding: 0 on a card lost to it and doubled) */
  :global(:where(.ako) .a-sub) { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); }
  :global(:where(.ako) .a-card) { padding: var(--s-5); border-radius: var(--r-group); background: var(--surface); box-shadow: var(--card-rim); }
  :global(.ako .a-card + .a-card) { margin-top: var(--s-3); }
  /* Profile's card: its own head (the name left, a count right), then rows parted by hairlines */
  :global(.ako .a-grp) { overflow: hidden; border-radius: var(--r-group); background: var(--surface); box-shadow: var(--card-rim); }
  :global(.ako .a-grp + .a-grp) { margin-top: var(--s-4); }
  :global(.ako .a-head) { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-3); padding: var(--s-4) var(--s-5) var(--s-1); }
  :global(.ako .a-head h2) { min-width: 0; font: 700 var(--fs-card)/1.25 var(--font-display); letter-spacing: -0.016em; }
  :global(.ako .a-head span) { flex: none; font: 450 var(--fs-body)/1.25 var(--font-text); color: var(--text-3); font-variant-numeric: tabular-nums; }
  :global(.ako .a-row) { position: relative; }
  :global(.ako .a-row + .a-row::before) { content: ''; position: absolute; top: 0; left: var(--s-5); right: var(--s-5); height: 0.5px; background: var(--separator); }
  :global(.ako .a-quiet) { display: inline-flex; align-items: center; gap: var(--s-1); min-height: 48px; font: 600 var(--fs-body)/1.2 var(--font-text);
    color: var(--text-2); text-decoration: none; -webkit-tap-highlight-color: transparent; transition: opacity var(--t-fast); }
  :global(.ako .a-quiet:active) { opacity: 0.5; }
  :global(.ako .a-quiet.red) { color: var(--danger-text); }
  :global(.ako .a-note) { padding: var(--s-3) var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 500 var(--fs-body)/1.4 var(--font-text); }
  :global(.ako .a-note.bad) { background: var(--danger-soft); color: var(--danger-text); }
  :global(.ako .a-note.warn) { background: var(--warning-soft); color: var(--warning-text); }
  :global(.ako .a-note.ok) { background: var(--success-soft); color: var(--success-text); }
  :global(.ako .a-two) { display: grid; grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); gap: var(--s-3); } /* a narrow phone stacks them */
  :global(.ako :focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }

  /* the island: floats over the content at the bottom, as wide as its words need (never a bar across the screen) */
  .a-bar { position: sticky; bottom: calc(var(--safe-bottom) + var(--s-4)); z-index: var(--z-sticky); display: flex; justify-content: center;
    pointer-events: none; }
  .a-island { display: flex; flex-direction: column; min-width: 208px; max-width: 100%; padding: 5px; border-radius: var(--r-xl); pointer-events: auto;
    animation: grow 400ms var(--ease-bounce) both; }
  @keyframes grow { from { opacity: 0; transform: translateY(12px) scale(0.86); } }
  .tnote { display: flex; align-items: center; justify-content: center; gap: var(--s-2); margin: var(--s-2) var(--s-4); text-align: center;
    font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .tnote :global(svg) { flex: none; }
  .tnote.bad { color: var(--danger-text); }
  .tnote.got { color: var(--success-text); }
  .a-island :global(.btn .ic) { order: 1; margin: 0 -2px 0 0; } /* the arrow after the word */

  @media (prefers-reduced-motion: reduce) {
    .step, .b, .on .radio, .a-island { animation: none; }
  }
</style>
