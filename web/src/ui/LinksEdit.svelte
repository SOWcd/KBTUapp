<script lang="ts">
  // A club's links (Oct 5 and Oct 24), Settings' group: a row per link (a network's username or a pasted link, any
  // site too), "Add" at the end picks the network; six at most. The caller turns the drafts into links with linkUrl.
  import { tick } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import { social, linkUrl, isHandle, NETS, TG_LINK, type LinkDraft } from '../lib/social';
  import { t } from '../lib/i18n/index.svelte';
  import SocialIcon from './SocialIcon.svelte';
  import Group from './Group.svelte';
  import Row from './Row.svelte';
  import IconButton from './IconButton.svelte';
  import { menu } from './menu';

  let { links = $bindable(), caption }: { links: LinkDraft[]; caption?: string } = $props();
  const urls = $derived(links.map(linkUrl));
  const tg = $derived(links.some((d) => TG_LINK.test(d.v.trim())));
  let inputs = $state<HTMLInputElement[]>([]);
  async function add(kind: LinkDraft['kind']) {
    links.push({ kind, v: '' });
    await tick();
    inputs[links.length - 1]?.focus();
  }
  const pick = (e: MouseEvent) => menu(e.currentTarget as Element, [...NETS, { kind: 'web' as const, label: t('ce.site') }].map((n) => ({ label: n.label, onselect: () => add(n.kind) })), 'start');
</script>

<Group {caption} footnote={tg ? t('ce.noTg') : undefined}>
  {#each links as d, i (i)}
    <div class="link kb-row" class:bad={!!d.v.trim() && !urls[i]}>
      <span class="ic"><SocialIcon kind={urls[i] ? social(urls[i]!).kind : d.kind} size={20} /></span>
      {#if d.kind !== 'web' && (!d.v.trim() || isHandle(d))}<span class="at">@</span>{/if}
      <input bind:this={inputs[i]} bind:value={d.v} oninput={() => { if (d.kind !== 'web') d.v = d.v.replace(/^@+/, ''); }} maxlength="200"
        placeholder={d.kind === 'web' ? 'site.kz' : 'username'} autocapitalize="none" autocomplete="off" spellcheck="false" inputmode={d.kind === 'web' ? 'url' : 'text'} />
      <IconButton icon={X} size="s" kind="plain" label={t('cm.delete')} onclick={() => links.splice(i, 1)} />
    </div>
  {/each}
  {#if links.length < 6}<Row tone="add" title={t('ce.addLink')} onclick={pick} />{/if}
</Group>

<style>
  .link { position: relative; display: flex; align-items: center; min-height: var(--row-h); padding: 0 var(--s-2) 0 var(--s-4); color: var(--text); font: var(--fw-row) var(--fs-row)/1.25 var(--font-text); }
  .link + .link::before { content: ''; position: absolute; top: 0; left: calc(var(--s-4) + 30px + var(--s-3)); right: 0; height: 0.5px; background: var(--separator); }
  .ic { flex: none; width: 30px; margin-right: var(--s-3); display: grid; place-items: center; color: var(--text-2); }
  .at { color: var(--text-3); }
  input { flex: 1; min-width: 0; font: inherit; color: inherit; }
  input::placeholder { color: var(--text-3); }
  .bad input { color: var(--danger-text); }
</style>
