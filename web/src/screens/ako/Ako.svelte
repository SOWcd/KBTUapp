<script lang="ts">
  // The applicant's page (/ako#<secret>, /ako/o/<slug>): its own root outside the app's shell. Header, the wizard's
  // frame (progress, slide, sticky main button), the program step; the other steps and the status page are components.
  // Shared looks live here under :global(.ako .a-*) (see "Design language").
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import Check from '@lucide/svelte/icons/check';
  import Video from '@lucide/svelte/icons/video';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
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
  const slug = pub ? decodeURIComponent(pub[1]) : '';
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
  const canBack = $derived(step === 'program' ? !!view?.program : idx > 0);
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
      if (!pick) { note = aw('ako.needProgram'); return; }
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
      <div class="brand">
        <span class="mark"><KbtuMark size={32} /></span>
        <nav class="lang">
          {#each LANGS as [l, name] (l)}
            <button type="button" class:on={(want || i18n.lang) === l} aria-pressed={(want || i18n.lang) === l} onclick={() => lang(l)}>{aw(name)}</button>
          {/each}
        </nav>
      </div>
      {#if orgName}<p class="org">{orgName}</p>{/if}
    </header>

    <main>
      {#if phase === 'loading'}
        <div class="sk" aria-busy="true" aria-hidden="true">
          <i class="b t"></i><i class="b l"></i><i class="b l s"></i>
          <i class="b c"></i><i class="b c"></i><i class="b c"></i>
        </div>
      {:else if phase === 'gone' || phase === 'offline'}
        <section class="state">
          <span class="ico">{#if phase === 'gone'}<Link2Off size={30} />{:else}<WifiOff size={30} />{/if}</span>
          <p class="a-h2">{aw(phase === 'gone' ? 'ako.err.gone' : 'ako.err.network')}</p>
          {#if phase === 'offline'}<Button size="l" full onclick={boot}>{aw('ako.retry')}</Button>{/if}
        </section>
      {:else if view && view.status !== 'draft'}
        <AkoStatus {view} {token} {fresh} onchange={changed} />
      {:else}
        {#if step !== 'program' || view?.program}
          <div class="way">
            <div class="wrow">
              {#if canBack}<button type="button" class="a-quiet" onclick={back}><ChevronLeft size={20} />{aw('ako.back')}</button>{:else}<span></span>{/if}
              {#if idx >= 0}<span class="a-sub">{aw('ako.stepOf', { n: idx + 1, all: steps.length })}</span>{/if}
            </div>
            {#if idx >= 0}<div class="line"><i style:transform="scaleX({(idx + 1) / steps.length})"></i></div>{/if}
          </div>
        {/if}

        {#key step}
          <section class="step" style:--dx={dir}>
            {#if step === 'program' || !view || !program}
              <h1 class="a-h1">{aw(view ? 'ako.step.program' : 'ako.title')}</h1>
              {#if !view}<p class="a-lead">{aw(data?.programs.some((p) => p.interview) ? 'ako.introInterview' : 'ako.intro')}</p>{/if}
              <div role="radiogroup" aria-label={aw('ako.step.program')}>
                {#each kinds as g (g.k)}
                  <h2 class="a-sec">{aw(g.k === 'degree' ? 'ako.degree' : 'ako.short')}</h2>
                  {#each g.list as p (p.key)}
                    {@const info = p.info[i18n.lang] ?? p.info.ru}
                    <div class="a-card prog" class:on={pick === p.key}>
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
                      {#if p.url}<a class="a-quiet more" href={p.url} target="_blank" rel="noopener noreferrer">{aw('ako.source')}<ArrowUpRight size={18} /></a>{/if}
                    </div>
                  {/each}
                {/each}
              </div>
            {:else if step === 'docs'}
              {@const info = program.info[i18n.lang] ?? program.info.ru}
              <div class="a-card mine">
                <span class="mtx"><span class="a-sub">{aw('ako.yourProgram')}</span><b>{info.title}</b></span>
                <button type="button" class="a-quiet" onclick={() => go('program', -1)}>{aw('ako.changeProgram')}</button>
              </div>
              <AkoDocs {view} {token} onchange={changed} />
            {:else if step === 'slot'}
              <AkoSlots {view} {token} onchange={changed} />
            {:else}
              <AkoSend {view} {token} onsent={(v) => { fresh = true; view = v; scroller?.scrollTo(0, 0); }} />
            {/if}
          </section>
        {/key}

        {#if step !== 'send'}
          <div class="a-bar">
            {#if note}<p class="a-note bad" role="alert">{note}</p>
            {:else if step === 'slot' && view?.slot}
              <p class="got" role="status"><Check size={20} strokeWidth={2.6} />{aw('ako.slotPicked', { when: `${weekday(view.slot.at)}, ${dayMonth(view.slot.at)}, ${time(view.slot.at)}` })}</p>
            {/if}
            <Button size="l" full loading={busy} onclick={next}>{aw('ako.next')}</Button>
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
  .ako { position: fixed; inset: 0; overflow-x: hidden; overflow-y: auto; -webkit-overflow-scrolling: touch; background: var(--bg); color: var(--text);
    font: 450 var(--fs-row)/1.45 var(--font-text); letter-spacing: -0.011em; -webkit-text-size-adjust: 100%; }
  .col { display: flex; flex-direction: column; min-height: 100%; max-width: 560px; margin: 0 auto;
    padding: calc(var(--safe-top) + var(--s-2)) var(--s-5) 0; }
  @media (min-width: 700px) { .col { padding-top: var(--s-10); } }
  main { flex: 1; display: flex; flex-direction: column; }

  .top { padding-bottom: var(--s-5); }
  .brand { display: flex; align-items: center; justify-content: space-between; min-height: 48px; }
  .mark { display: inline-flex; color: var(--text); }
  .org { margin-top: var(--s-1); max-width: 22em; text-wrap: balance; font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .lang { display: flex; margin-right: calc(-1 * var(--s-3)); }
  .lang button { min-width: 52px; height: 48px; padding: 0 var(--s-3); font: 600 var(--fs-body)/1 var(--font-text); letter-spacing: 0.02em;
    color: var(--text-3); transition: color var(--t-base) var(--ease); -webkit-tap-highlight-color: transparent; }
  .lang button.on { color: var(--text); }

  .way { margin-bottom: var(--s-5); }
  .wrow { display: flex; align-items: center; justify-content: space-between; min-height: 48px; }
  .wrow :global(.a-quiet svg) { margin-left: -6px; } /* the chevron's own side bearing: its stroke starts at the page edge */
  .line { height: 3px; border-radius: var(--r-full); background: var(--fill); overflow: hidden; }
  .line i { display: block; height: 100%; border-radius: var(--r-full); background: var(--accent); transform-origin: left center;
    transition: transform var(--t-slow) var(--ease-spring); }

  .step { flex: 1; padding-bottom: var(--s-6); animation: slide var(--t-slow) var(--ease) both; }
  @keyframes slide { from { opacity: 0; transform: translateX(calc(var(--dx, 1) * 28px)); } }

  .prog { padding: 0; transition: box-shadow var(--t-base) var(--ease); }
  .prog.on { box-shadow: inset 0 0 0 2px var(--accent); }
  .pk { display: flex; align-items: flex-start; gap: var(--s-3); width: 100%; padding: var(--s-5); text-align: left; color: inherit;
    border-radius: var(--r-l); -webkit-tap-highlight-color: transparent; }
  .ptx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--s-1); }
  .pt { font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .ps { color: var(--text-2); line-height: 1.35; }
  .pp { margin-top: var(--s-1); font-weight: 600; }
  .pi { display: inline-flex; align-items: center; gap: var(--s-2); margin-top: var(--s-1); }
  .radio { flex: none; display: grid; place-items: center; width: 28px; height: 28px; border-radius: var(--r-full);
    box-shadow: inset 0 0 0 2px var(--line-2); color: var(--on-accent); transition: background var(--t-fast); }
  .on .radio { background: var(--accent); box-shadow: none; animation: pop var(--t-base) var(--ease-bounce); }
  @keyframes pop { from { transform: scale(0.6); } }
  .more { margin: calc(-1 * var(--s-3)) var(--s-5) var(--s-2); }
  .mine { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); padding: var(--s-3) var(--s-5); margin-bottom: var(--s-7); }
  .mine .a-quiet { flex: none; }
  .mtx { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .mtx b { font: 600 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.012em; }
  .got { display: flex; align-items: center; justify-content: center; gap: var(--s-2); text-align: center;
    font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--success-text); }
  .got :global(svg) { flex: none; }

  .state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s-6);
    padding: var(--s-10) 0; text-align: center; }
  .ico { display: grid; place-items: center; width: 72px; height: 72px; border-radius: var(--r-full); background: var(--fill); color: var(--text-2); }

  .sk { display: flex; flex-direction: column; gap: var(--s-3); padding-top: var(--s-4); }
  .b { display: block; border-radius: var(--r-full); background: var(--fill); animation: breathe 1.4s ease-in-out infinite alternate; }
  .b.t { width: 70%; height: 34px; border-radius: var(--r-s); }
  .b.l { width: 92%; height: 14px; }
  .b.s { width: 55%; margin-bottom: var(--s-6); }
  .b.c { height: 148px; border-radius: var(--r-l); }
  @keyframes breathe { from { opacity: 1; } to { opacity: 0.45; } }

  .foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 0 var(--s-4);
    padding: var(--s-4) 0 calc(var(--safe-bottom) + var(--s-4)); font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .foot a { display: inline-flex; align-items: center; min-height: 48px; color: inherit; text-decoration: underline; text-underline-offset: 3px; }

  /* ---- shared with the other AKO components (part 2 uses these as they are) ---- */
  :global(.ako h1), :global(.ako h2), :global(.ako p) { margin: 0; }
  :global(.ako .a-h1) { font: 700 var(--fs-title)/1.08 var(--font-display); letter-spacing: -0.03em; text-wrap: balance; }
  :global(.ako .a-h2) { font: 700 var(--fs-sec)/1.22 var(--font-display); letter-spacing: -0.02em; text-wrap: balance; }
  :global(.ako .a-lead) { margin-top: var(--s-3); font: 450 var(--fs-row)/1.45 var(--font-text); color: var(--text-2); }
  :global(.ako .a-sec) { margin: var(--s-8) 0 var(--s-3); font: 600 var(--fs-body)/1.2 var(--font-text); color: var(--text-3); }
  /* :where: a component's own class must win over the shared look (padding: 0 on a card lost to it and doubled) */
  :global(:where(.ako) .a-sub) { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); }
  :global(:where(.ako) .a-card) { padding: var(--s-5); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim); }
  :global(.ako .a-card + .a-card) { margin-top: var(--s-3); }
  :global(.ako .a-quiet) { display: inline-flex; align-items: center; gap: var(--s-1); min-height: 48px; font: 600 var(--fs-row)/1.2 var(--font-text);
    color: var(--accent-text); text-decoration: none; -webkit-tap-highlight-color: transparent; transition: opacity var(--t-fast); }
  :global(.ako .a-quiet:active) { opacity: 0.5; }
  :global(.ako .a-quiet.red) { color: var(--danger-text); }
  :global(.ako .a-note) { padding: var(--s-3) var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 500 var(--fs-body)/1.4 var(--font-text); }
  :global(.ako .a-note.bad) { background: var(--danger-soft); color: var(--danger-text); }
  :global(.ako .a-note.warn) { background: var(--warning-soft); color: var(--warning-text); }
  :global(.ako .a-note.ok) { background: var(--success-soft); color: var(--success-text); }
  :global(.ako .a-two) { display: grid; grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); gap: var(--s-3); } /* a narrow phone stacks them */
  :global(.ako .a-bar) { position: sticky; bottom: 0; z-index: var(--z-sticky); display: flex; flex-direction: column; gap: var(--s-3);
    margin: 0 calc(-1 * var(--s-5)); padding: var(--s-6) var(--s-5) calc(var(--safe-bottom) + var(--s-4));
    background: linear-gradient(transparent, var(--bg) var(--s-6)); }
  :global(.ako :focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }

  @media (prefers-reduced-motion: reduce) {
    .step, .b, .on .radio { animation: none; }
    .line i { transition: none; }
  }
</style>
