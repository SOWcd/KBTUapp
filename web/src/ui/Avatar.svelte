<script lang="ts">
  // Avatar: the person's own photo or Telegram's (never the portal photo, SPEC §3). Tapping it opens the universal profile card.
  import Founder from './Founder.svelte';
  import { sheets } from '../lib/state/sheets';
  import { prefetchPerson } from '../lib/state/data.svelte';
  import { haptic } from '../lib/tg';

  type P = { id?: number; name: string; avatar?: string | null; founder?: boolean; mark?: 'idea' | null };
  let { person, size = 40, tappable = true, ring = false }: { person: P; size?: number; tappable?: boolean; ring?: boolean } = $props();

  const TONES = ['#3B6BFF', '#7C4DFF', '#F2542D', '#2FBF71', '#FFB23D', '#18A9DB', '#FF4FA3'];
  const initials = $derived(person.name.split(/\s+/).map((w) => w[0] ?? '').join('').slice(0, 2).toUpperCase());
  const tone = $derived(TONES[(person.id ?? person.name.length) % TONES.length]);
  let broken = $state(false);
  const can = $derived(tappable && person.id != null);

  function tap(e: MouseEvent) {
    if (!can) return;
    e.stopPropagation();
    haptic.tap();
    sheets.person(person.id!);
  }
</script>

{#snippet face()}
  {#if person.avatar && !broken}
    <!-- the person's tone under the photo while it loads (his own profile showed a white square first) -->
    <img src={person.avatar} alt="" width={size} height={size} decoding="async" loading={size >= 64 ? 'eager' : 'lazy'} style="background:{tone}"
      onerror={() => (broken = true)} />
  {:else}
    <span class="ini" style="background:{tone};font-size:{Math.round(size * 0.38)}px">{initials}</span>
  {/if}
  {#if (person.founder || person.mark === 'idea') && size >= 28}<span class="seal"><Founder size={Math.max(14, Math.round(size * 0.36))} idea={!person.founder} /></span>{/if}
{/snippet}

{#if can}
  <button class="av" class:ring style="width:{size}px;height:{size}px" onclick={tap} onpointerdown={() => prefetchPerson(person.id!)} aria-label={person.name}>{@render face()}</button>
{:else}
  <span class="av" class:ring style="width:{size}px;height:{size}px">{@render face()}</span>
{/if}

<style>
  .av { position: relative; display: inline-flex; flex: none; border-radius: 50%; }
  .av img, .ini { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; background: var(--surface-2); }
  .ini { display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; letter-spacing: -0.02em; }
  .ring { box-shadow: 0 0 0 2px var(--bg), 0 0 0 3.5px var(--accent); }
  .seal { position: absolute; right: -3px; bottom: -3px; }
  button.av { transition: transform var(--t-fast) var(--ease); }
  button.av:active { transform: scale(0.94); }
</style>
