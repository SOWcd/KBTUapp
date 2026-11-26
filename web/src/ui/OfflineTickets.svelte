<script lang="ts">
  // My kept tickets for the door without the network (lib/offlineTickets): each QR at once, no tap, under a small
  // "offline" note. A lazy chunk the service worker keeps (lib/shell LAZY): the QR encoder never weighs on the first
  // paint. On the Afisha when its events didn't reach the server, and outside Telegram on WebEntrance's offline page.
  import WifiOff from '@lucide/svelte/icons/wifi-off';
  import type { OfflineTicket } from '../lib/offlineTickets';
  import { lookVars, QR_LOOK } from '../lib/awards';
  import { t, placeOf } from '../lib/i18n/index.svelte';
  import { relDay, time } from '../lib/time';
  import '../lib/qrnow'; // the encoder in this chunk: offline, there is no other to fetch
  import Qr from './Qr.svelte';
  import LookMark from './LookMark.svelte';

  let { tickets }: { tickets: OfflineTicket[] } = $props();
</script>

<section class="tickets" aria-label={t('as.tickets')}>
  <p class="note fs-sub" role="status"><WifiOff size={15} /><span>{t('tk.offlineNote')}</span></p>
  {#each tickets as k (k.id)}
    <article class="pass">
      <div class="plate" style={lookVars(k.look)}><Qr text={'KBTU' + k.code} minVersion={4} tone={QR_LOOK[k.look]}><LookMark look={k.look} logo={k.logo} /></Qr></div>
      <b class="ttl">{k.title}</b>
      <span class="when fs-sub">{relDay(k.startsAt)} · {time(k.startsAt)} · {placeOf(k.place, k.online)}</span>
      <span class="code fs-cap"><i>{t('tk.code')}</i><b class="num">{k.code.replace(/^(\w{2})(\w{2})$/, '$1 $2')}</b></span>
    </article>
  {/each}
</section>

<style>
  .tickets { display: flex; flex-direction: column; gap: var(--s-3); width: 100%; }
  /* the note: quiet, the theme's own warning tone, never an alarm over the ticket */
  .note { display: inline-flex; align-items: center; gap: var(--s-2); align-self: flex-start; padding: var(--s-1) var(--s-3);
    border-radius: var(--r-full); background: var(--warning-soft); color: var(--warning-text); font-weight: 600; text-align: start; }
  .note :global(svg) { flex: none; }
  .pass { display: flex; flex-direction: column; align-items: center; gap: var(--s-1); padding: var(--s-4); border-radius: var(--r-l);
    background: var(--surface); box-shadow: var(--card-rim, var(--shadow-card)); text-align: center; }
  /* white in both themes: the door's scanner reads dark on light (as the ticket's own plate) */
  .plate { width: min(232px, 100%); padding: var(--s-3); margin-bottom: var(--s-2); border-radius: var(--r-m); background: white; }
  .ttl { max-width: 100%; color: var(--text); font: 600 var(--fs-body)/1.3 var(--font-text); overflow-wrap: anywhere; }
  .when { color: var(--text-2); }
  .code { display: inline-flex; gap: var(--s-2); color: var(--text-3); }
  .code i { font-style: normal; }
  .code b { color: var(--text); letter-spacing: 0.08em; }
</style>
