<script lang="ts">
  // What people told the creator from inside the app (server logic/helpus.py), newest first: the signed offers to help
  // (the creator's alone; a tap: their Telegram, or their page without a username) and the anonymous lines of the days
  // already over (nobody's: the day alone, shuffled, no ids). Opening it marks read what it showed; what was new this
  // time keeps its dot until the sheet closes.
  import MessageSquareHeart from '@lucide/svelte/icons/message-square-heart';
  import { staffOnly } from '../../lib/state/staffGate.svelte';
  import { api } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago, dayMonth } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  staffOnly(() => overlay);
  let list = $state<Awaited<ReturnType<typeof api.helpList>> | null>(null);
  api.helpList().then((l) => {
    list = l;
    if ([...l.anon, ...l.offers].some((x) => x.new)) void api.helpSeen(l.anon[0]?.day ?? 0, l.offers[0]?.id ?? 0).then(() => { if (data.inbox) data.inbox.voices = 0; }).catch(() => {});
  }).catch(() => (list = { anon: [], offers: [] }));
  const reach = (o: NonNullable<typeof list>['offers'][number]) => { haptic.tap(); if (o.username) openLink(`https://t.me/${o.username}`); else sheets.person(o.person.id); };
</script>

<Sheet {overlay} icon={MessageSquareHeart} full title={t('vo.title')}>
  {#if list && !list.anon.length && !list.offers.length}<p class="t-foot">{t('vo.none')}</p>{/if}
  {#if list?.offers.length}
    <h3 class="t-h3 cap">{t('vo.offers')}</h3>
    {#each list.offers as o (o.id)}
      <button class="line who surface" onclick={() => reach(o)}>
        <Avatar person={o.person} size={36} tappable={false} />
        <span class="col">
          <b>{o.person.realName ?? o.person.name}</b>
          <span class="kinds">{o.kinds.map((k) => t(`help.k.${k}`)).join(', ')}</span>
          {#if o.note}<span class="tx">{o.note}</span>{/if}
          <i class="t-foot">{#if o.new}<b class="dot" aria-label={t('vo.new')}></b>{/if}<span>{ago(o.at)}{#if o.username} · @{o.username}{/if}</span></i>
        </span>
      </button>
    {/each}
  {/if}
  {#if list?.anon.length}
    <h3 class="t-h3 cap">{t('vo.anon')}</h3>
    {#each list.anon as a, i (i)}
      <div class="line surface"><p class="tx">{a.body}</p><i class="t-foot">{#if a.new}<b class="dot" aria-label={t('vo.new')}></b>{/if}{dayMonth(a.day * 86400)}</i></div>
    {/each}
  {/if}
</Sheet>

<style>
  .cap { margin: var(--s-4) 0 var(--s-3); }
  .line { display: flex; flex-direction: column; gap: var(--s-1); width: 100%; padding: var(--s-3) var(--s-4); border-radius: var(--r-l); margin-bottom: var(--s-2); text-align: start; }
  .who { flex-direction: row; align-items: flex-start; gap: var(--s-3); }
  .col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--s-1); }
  .col > b { font: 600 var(--fs-row)/1.25 var(--font-text); overflow-wrap: anywhere; }
  .kinds { font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .tx { margin: 0; font: 450 var(--fs-body)/1.4 var(--font-text); overflow-wrap: anywhere; white-space: pre-wrap; }
  .line i { display: flex; align-items: center; gap: var(--s-2); font-style: normal; color: var(--text-3); }
  .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
</style>
