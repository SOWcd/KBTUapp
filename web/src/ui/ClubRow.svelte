<script lang="ts">
  // A club or school as one compact row (the Clubs tab's lists and "All clubs"): its mark, its name with
  // the ✓ and the Student Government mark, one line under it, and the bell (or what the list puts there instead).
  import type { Snippet } from 'svelte';
  import BadgeCheck from '@lucide/svelte/icons/badge-check';
  import Bell from '@lucide/svelte/icons/bell';
  import BellCheck from '@lucide/svelte/icons/bell-check';
  import type { Org } from '../lib/api';
  import { t } from '../lib/i18n/index.svelte';
  import { toggleSub } from '../lib/state/data.svelte';
  import { sheets } from '../lib/state/sheets';
  import OrgLogo from './OrgLogo.svelte';
  import GovMark from './GovMark.svelte';

  let { org: o, name, sub = '', hot = false, end }: { org: Org; name?: string; sub?: string; hot?: boolean; end?: Snippet } = $props();
</script>

<div class="row">
  <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
  <OrgLogo org={o} size={40} />
  <span class="txt">
    <span class="nm"><b class="ellipsis">{name ?? o.name}</b>{#if o.official}<span class="ok" title={t('clubs.official')}><BadgeCheck size={14} /></span>{/if}</span>
    {#if o.gov}<GovMark />{/if}
    {#if sub}<small class="ellipsis" class:hot>{#if hot}<i></i>{/if}{sub}</small>{/if}
  </span>
  <span class="end">
    {#if end}{@render end()}
    {:else}
      <button class="bell" class:on={o.subscribed} onclick={() => toggleSub(o.id)} aria-label={t(o.subscribed ? 'clubs.subscribed' : 'clubs.subscribe')} aria-pressed={o.subscribed}>
        {#if o.subscribed}<BellCheck size={17} />{:else}<Bell size={17} />{/if}</button>
    {/if}
  </span>
</div>

<style>
  .row { position: relative; display: flex; align-items: center; gap: 12px; min-height: 60px; padding: 8px 12px 8px 10px; }
  .row:active:not(:has(.end :active)) { background: var(--surface-2); }
  .row:not(:first-child) { box-shadow: inset 0 1px 0 var(--line); }
  .open { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 3px; pointer-events: none; }
  .nm { display: flex; align-items: center; gap: 4px; min-width: 0; max-width: 100%; }
  .nm b { font: 650 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .ok { display: inline-flex; flex: none; color: var(--accent-text); }
  small { display: block; max-width: 100%; font: 500 var(--fs-sub)/1.25 var(--font-text); color: var(--text-3); }
  small.hot { font-weight: 650; color: var(--accent-text); }
  small.hot i { display: inline-block; width: 6px; height: 6px; margin: 0 6px 1px 0; border-radius: 50%; background: #46D6FF; vertical-align: middle; }
  .end { position: relative; z-index: 2; flex: none; }
  .bell { position: relative; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-2); }
  .bell::after { content: ''; position: absolute; inset: -5px; } /* a 44 px target, the circle stays 34 */
  .bell.on { background: var(--success-soft); color: var(--success-text); }
</style>
