<script lang="ts">
  // A club's links (Oct 5 and Oct 24): a network's button asks for that username (or a pasted link), any site
  // too; six at most. The caller turns the drafts into links with linkUrl.
  import { tick } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import { social, linkUrl, isHandle, NETS, type LinkDraft } from '../lib/social';
  import { t } from '../lib/i18n/index.svelte';
  import SocialIcon from './SocialIcon.svelte';

  let { links = $bindable() }: { links: LinkDraft[] } = $props();
  const urls = $derived(links.map(linkUrl));
  let inputs = $state<HTMLInputElement[]>([]);
  async function add(kind: LinkDraft['kind']) {
    links.push({ kind, v: '' });
    await tick();
    inputs[links.length - 1]?.focus();
  }
</script>

{#each links as d, i (i)}
  <div class="link" class:bad={!!d.v.trim() && !urls[i]}>
    <SocialIcon kind={urls[i] ? social(urls[i]!).kind : d.kind} size={18} />
    {#if d.kind !== 'web' && (!d.v.trim() || isHandle(d))}<span class="at">@</span>{/if}
    <input bind:this={inputs[i]} bind:value={d.v} oninput={() => { if (d.kind !== 'web') d.v = d.v.replace(/^@+/, ''); }} maxlength="200"
      placeholder={d.kind === 'web' ? 'site.kz' : 'username'} autocapitalize="none" autocomplete="off" spellcheck="false" inputmode={d.kind === 'web' ? 'url' : 'text'} />
    <button class="rm" onclick={() => links.splice(i, 1)} aria-label={t('cm.delete')}><X size={16} /></button>
  </div>
{/each}
{#if links.length < 6}
  <div class="nets">
    {#each [...NETS, { kind: 'web' as const, label: t('ce.site') }] as n (n.kind)}
      <button class="addl" onclick={() => add(n.kind)}><SocialIcon kind={n.kind} size={16} />{n.label}</button>
    {/each}
  </div>
{/if}

<style>
  .link { display: flex; align-items: center; gap: 10px; height: 48px; padding: 0 6px 0 14px; margin-bottom: 8px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-2); }
  .link.bad { box-shadow: inset 0 0 0 1.5px var(--danger); }
  .link input { flex: 1; min-width: 0; font: 550 15px/1.3 var(--font-text); color: var(--text); }
  .link input::placeholder { color: var(--text-3); }
  .at { margin-right: -9px; font: 550 15px/1.3 var(--font-text); color: var(--text-3); }
  .rm { flex: none; width: 36px; height: 36px; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: var(--text-3); }
  .rm:active { background: var(--surface); }
  .nets { display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0 8px; }
  .addl { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 11px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 620 13.5px/1 var(--font-text); }
</style>
