<script lang="ts" module>
  import type { AkoKey } from '../../lib/i18n/ako';
  /** An ApiErr read without knowing its field names: its code, its detail ('phone', 'full', 'ako_consent'…), its data. */
  export function errOf(e: unknown): { code: string; msg: string; data: Record<string, unknown> } {
    const x = (e ?? {}) as Record<string, unknown>;
    const data = (x.data ?? {}) as Record<string, unknown>;
    return { code: String(x.code ?? x.error ?? 'unavailable'), msg: String(x.message ?? data.message ?? data.detail ?? ''), data };
  }
  /** The general message for an error (each step maps its own special cases first). */
  export function errKey(e: unknown): AkoKey {
    const { code } = errOf(e);
    return code === 'unavailable' ? 'ako.err.network' : code === 'not_found' ? 'ako.err.gone' : code === 'conflict' ? 'ako.err.closed'
      : code === 'rate_limited' ? 'ako.err.tooMany' : 'ako.err.generic';
  }
</script>

<script lang="ts">
  // The documents: the consent card, then "now / later / optional". A page is a tile (kind, size, a check): never a
  // preview, the applicant can't read a page back. only='later': the status page's list of what's still without a page.
  import { fly } from 'svelte/transition';
  import Check from '@lucide/svelte/icons/check';
  import Camera from '@lucide/svelte/icons/camera';
  import Paperclip from '@lucide/svelte/icons/paperclip';
  import FileText from '@lucide/svelte/icons/file-text';
  import ImageIcon from '@lucide/svelte/icons/image';
  import X from '@lucide/svelte/icons/x';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Button from '../../ui/Button.svelte';
  import { ako } from '../../lib/api/ako';
  import type { AkoDoc, AkoFile, AkoView } from '../../lib/api/types';
  import { i18n } from '../../lib/i18n/index.svelte';
  import { aw, awn } from '../../lib/i18n/ako';
  import { shrink } from '../../lib/photo';

  type Up = { id: number; doc: AkoDoc; pdf: boolean; bytes: number; p: number; err: AkoKey | ''; again: boolean; src: Blob };
  let { view, token, onchange, only }: { view: AkoView; token: string; onchange: (v: AkoView) => void; only?: 'later' } = $props();

  let ups = $state<Up[]>([]);
  let open = $state<AkoDoc[]>([]);
  let touched = $state<AkoDoc[]>([]);
  let ask = $state<AkoFile['id'] | null>(null);
  let nudge = $state(false);
  let note = $state<AkoKey | ''>('');
  let cam: HTMLInputElement | undefined = $state();
  let any: HTMLInputElement | undefined = $state();
  let consentEl: HTMLElement | undefined = $state();
  let target: AkoDoc = 'cv';
  let seq = 0;
  const dur = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 220;
  const LOC = { ru: 'ru-RU', kk: 'kk-KZ', en: 'en-GB' } as const;

  const program = $derived(view.programs.find((p) => p.key === view.program));
  const has = (d: AkoDoc) => view.files.some((f) => f.doc === d);
  const groups = $derived.by(() => {
    if (!program) return [];
    const left = (a: AkoDoc[]) => (only ? a.filter((d) => !has(d) || touched.includes(d)) : a);
    return ([['first', only ? [] : program.first], ['later', left(program.later)], ['optional', left(program.optional)]] as const).filter((g) => g[1].length);
  });
  const k = (s: string) => s as AkoKey;
  const opt = (s: string) => { const v = aw(k(s)); return v === s ? '' : v; };
  function size(b: number): string {
    const mb = b >= 1e6;
    try { return new Intl.NumberFormat(LOC[i18n.lang], { style: 'unit', unit: mb ? 'megabyte' : 'kilobyte', maximumFractionDigits: mb ? 1 : 0 }).format(mb ? b / 1e6 : Math.max(1, b / 1e3)); }
    catch { return ''; }
  }

  function pick(doc: AkoDoc, how: 'cam' | 'any') {
    note = '';
    if (!view.consent) { nudge = true; requestAnimationFrame(() => consentEl?.scrollIntoView({ block: 'center', behavior: dur ? 'smooth' : 'auto' })); return; }
    target = doc;
    (how === 'cam' ? cam : any)?.click();
  }
  function picked(e: Event) {
    const el = e.currentTarget as HTMLInputElement;
    for (const f of Array.from(el.files ?? [])) {
      ups.push({ id: ++seq, doc: target, pdf: f.type === 'application/pdf' || /\.pdf$/i.test(f.name), bytes: f.size, p: 0, err: '', again: true, src: f });
      void run(ups[ups.length - 1]);
    }
    if (!touched.includes(target)) touched.push(target);
    el.value = '';
  }
  const forget = (u: Up) => (ups = ups.filter((x) => x.id !== u.id));
  async function run(u: Up) {
    u.err = ''; u.p = 0;
    if (u.pdf && u.src.size > view.maxBytes) { u.again = false; u.err = 'ako.err.big'; return; }
    try {
      const body = u.pdf ? u.src : await shrink(u.src, 2400, 0.86);
      const f = await ako.upload(token, u.doc, body, (p) => (u.p = p));
      forget(u);
      onchange({ ...view, files: [...view.files, f] });
    } catch (e) {
      const { code, msg } = errOf(e);
      if (code === 'forbidden' && msg.includes('ako_consent')) { forget(u); nudge = true; onchange({ ...view, consent: false }); return; }
      u.again = code !== 'bad_input' && code !== 'rate_limited';
      u.err = code === 'bad_input' ? 'ako.err.file' : errKey(e);
    }
  }
  async function drop(f: AkoFile) {
    ask = null; note = '';
    onchange({ ...view, files: view.files.filter((x) => x.id !== f.id) });
    try { await ako.dropFile(token, f.id); }
    catch (e) { onchange({ ...view, files: [...view.files, f] }); note = errKey(e); }
  }
  async function agree() {
    nudge = false; note = '';
    onchange({ ...view, consent: true });
    try { await ako.patch(token, { consent: true }); }
    catch (e) { onchange({ ...view, consent: false }); note = errKey(e); }
  }
  const toggle = (d: AkoDoc) => (open = open.includes(d) ? open.filter((x) => x !== d) : [...open, d]);
</script>

{#snippet head(d: AkoDoc, n: number)}
  <span class="dot" class:ok={n > 0}>{#if n}<Check size={16} strokeWidth={3} />{/if}</span>
  <span class="ttl"><b>{aw(k('ako.doc.' + d))}</b><span class="a-sub">{n ? awn('ako.pages', n) : opt('ako.docHint.' + d)}</span></span>
{/snippet}

{#snippet card(d: AkoDoc, fold: boolean)}
  {@const files = view.files.filter((f) => f.doc === d)}
  {@const mine = ups.filter((u) => u.doc === d)}
  {@const shown = !fold || open.includes(d) || mine.length > 0}
  {@const how = opt('ako.docHow.' + d)}
  {@const url = opt('ako.docUrl.' + d)}
  <article class="a-card doc">
    {#if fold}
      <button type="button" class="head" aria-expanded={shown} onclick={() => toggle(d)}>
        {@render head(d, files.length)}<span class="chev" class:up={shown}><ChevronDown size={22} /></span>
      </button>
    {:else}<div class="head">{@render head(d, files.length)}</div>{/if}
    {#if shown}
      <div class="body">
        {#if how}
          <p class="a-sub">{how}</p>
          {#if url}<a class="a-quiet" href={url} target="_blank" rel="noopener noreferrer">{aw('ako.openLink')}<ArrowUpRight size={18} /></a>{/if}
        {/if}
        {#each files as f (f.id)}
          <div class="page">
            <span class="pi">{#if f.mime === 'application/pdf'}<FileText size={22} />{:else}<ImageIcon size={22} />{/if}</span>
            <span class="ptx"><b>{aw(f.mime === 'application/pdf' ? 'ako.pdf' : 'ako.photoPage')}</b><span class="a-sub">{size(f.bytes)}</span></span>
            <span class="okm" title={aw('ako.uploaded')}><Check size={20} strokeWidth={2.6} /></span>
            <button type="button" class="ib" aria-label={aw('ako.removePage')} onclick={() => (ask = ask === f.id ? null : f.id)}><X size={20} /></button>
          </div>
          {#if ask === f.id}
            <div class="ask">
              <p class="a-sub">{aw('ako.removeAsk')}</p>
              <div class="a-two">
                <Button kind="destructive" size="l" full onclick={() => drop(f)}>{aw('ako.removePage')}</Button>
                <Button kind="gray" size="l" full onclick={() => (ask = null)}>{aw('ako.keep')}</Button>
              </div>
            </div>
          {/if}
        {/each}
        {#each mine as u (u.id)}
          <div class="page" class:bad={!!u.err} role={u.err ? 'alert' : undefined}>
            <span class="pi">{#if u.pdf}<FileText size={22} />{:else}<ImageIcon size={22} />{/if}</span>
            <span class="ptx">
              <b>{aw(u.pdf ? 'ako.pdf' : 'ako.photoPage')}</b>
              <span class="a-sub">{u.err ? aw(u.err) : aw('ako.uploading', { p: Math.round(u.p * 100) })}</span>
            </span>
            {#if !u.err}<span class="bar" style:transform="scaleX({Math.max(0.04, u.p)})"></span>{/if}
          </div>
          {#if u.err}
            <div class="fix">
              {#if u.again}<button type="button" class="a-quiet" onclick={() => run(u)}>{aw('ako.retry')}</button>{/if}
              <button type="button" class="a-quiet red" onclick={() => forget(u)}>{aw('ako.removePage')}</button>
            </div>
          {/if}
        {/each}
        <div class="a-two add">
          <Button kind="gray" size="l" full onclick={() => pick(d, 'cam')}>{#snippet icon()}<Camera size={20} />{/snippet}{aw('ako.camera')}</Button>
          <Button kind="gray" size="l" full onclick={() => pick(d, 'any')}>{#snippet icon()}<Paperclip size={20} />{/snippet}{aw('ako.file')}</Button>
        </div>
      </div>
    {/if}
  </article>
{/snippet}

<div class="docs">
  {#if !only}
    <h1 class="a-h1">{aw('ako.docsTitle')}</h1>
    <p class="a-lead">{aw(program?.first.length ? 'ako.docsLead' : 'ako.docsLeadNone')}</p>
  {/if}

  {#if !view.consent && (!only || nudge)}
    <section class="a-card consent" class:nudge bind:this={consentEl} out:fly={{ y: -12, duration: dur }}>
      <span class="shield"><ShieldCheck size={26} /></span>
      <h2 class="a-h2">{aw('ako.consentTitle')}</h2>
      <p class="a-sub">{aw('ako.consentText')}</p>
      <a class="a-quiet" href="/privacy?lang={i18n.lang}" target="_blank" rel="noopener">{aw('ako.policy')}<ArrowUpRight size={18} /></a>
      <Button size="l" full onclick={agree}>{aw('ako.consentOk')}</Button>
    </section>
  {/if}
  {#if note}<p class="a-note bad top" role="alert">{aw(note)}</p>{/if}

  {#each groups as [g, list] (g)}
    <h2 class="a-sec">{aw(k(`ako.${g}Group`))}</h2>
    {#each list as d (d)}{@render card(d, g !== 'first')}{/each}
  {/each}

  <input bind:this={cam} class="in" type="file" accept="image/*" capture="environment" tabindex="-1" aria-hidden="true" onchange={picked} />
  <input bind:this={any} class="in" type="file" accept="image/*,application/pdf" multiple tabindex="-1" aria-hidden="true" onchange={picked} />
</div>

<style>
  .in { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
  .consent { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-3); margin-top: var(--s-6); transition: box-shadow var(--t-base) var(--ease); }
  .consent.nudge { box-shadow: inset 0 0 0 2px var(--accent); animation: nudge var(--t-slow) var(--ease-bounce); }
  @keyframes nudge { 50% { transform: scale(1.015); } }
  .shield { display: grid; place-items: center; width: 52px; height: 52px; border-radius: var(--r-full); background: var(--success-soft); color: var(--success-text); }
  .top { margin-top: var(--s-4); }

  .doc { padding: 0; }
  .head { display: flex; align-items: center; gap: var(--s-3); width: 100%; min-height: 76px; padding: var(--s-4) var(--s-5); text-align: left; color: inherit;
    border-radius: var(--r-l); -webkit-tap-highlight-color: transparent; }
  .ttl { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .ttl b { font: 600 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.012em; }
  .dot { flex: none; display: grid; place-items: center; width: 28px; height: 28px; border-radius: var(--r-full); box-shadow: inset 0 0 0 2px var(--line-2); color: var(--on-accent); }
  .dot.ok { background: var(--success); box-shadow: none; animation: pop var(--t-slow) var(--ease-bounce); }
  @keyframes pop { from { transform: scale(0.5); opacity: 0; } }
  .chev { flex: none; display: inline-flex; color: var(--text-3); transition: transform var(--t-base) var(--ease); }
  .chev.up { transform: rotate(180deg); }

  .body { display: flex; flex-direction: column; gap: var(--s-2); padding: 0 var(--s-5) var(--s-5); animation: rise var(--t-base) var(--ease) both; }
  @keyframes rise { from { opacity: 0; transform: translateY(-6px); } }
  .page { position: relative; display: flex; align-items: center; gap: var(--s-3); min-height: 60px; padding: var(--s-2) var(--s-1) var(--s-2) var(--s-4);
    border-radius: var(--r-m); background: var(--fill); overflow: hidden; animation: rise var(--t-base) var(--ease) both; }
  .page.bad { background: var(--danger-soft); padding-right: var(--s-4); }
  .page.bad .a-sub, .page.bad .pi { color: var(--danger-text); }
  .pi { flex: none; display: inline-flex; color: var(--text-2); }
  .ptx { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .ptx b { font: 600 var(--fs-row)/1.25 var(--font-text); }
  .okm { flex: none; display: inline-flex; color: var(--success-text); }
  .ib { flex: none; display: grid; place-items: center; width: 48px; height: 48px; border-radius: var(--r-full); color: var(--text-3); -webkit-tap-highlight-color: transparent; }
  .ib:active { opacity: 0.5; }
  .bar { position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: var(--accent); transform-origin: left center; transition: transform var(--t-base) linear; }
  .ask { display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-2) 0 var(--s-3); animation: rise var(--t-base) var(--ease) both; }
  .fix { display: flex; gap: var(--s-6); padding: 0 var(--s-1); }
  .add { margin-top: var(--s-2); }
  .add :global(.btn), .ask :global(.btn) { padding-inline: var(--s-3); }

  @media (prefers-reduced-motion: reduce) {
    .consent.nudge, .dot.ok, .body, .page, .ask { animation: none; }
    .chev, .bar { transition: none; }
  }
</style>
