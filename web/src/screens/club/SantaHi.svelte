<script lang="ts">
  // Secret Santa's welcome (owner, Nov 18: the bot's announcement "just opened Studio with a Santa row"): over the club's
  // Studio, from the bot's sn_<club> and from Studio's row, the one place to start it. How it works in three lines and
  // one Start (santa.start: the game published, the team told by the bot); a game running: its count and the way in.
  import Gift from '@lucide/svelte/icons/gift';
  import PenLine from '@lucide/svelte/icons/pen-line';
  import Shuffle from '@lucide/svelte/icons/shuffle';
  import EyeOff from '@lucide/svelte/icons/eye-off';
  import { api, type Id } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { data, loadStudio } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { nowTs, dayMonth, parts, at as tsAt } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import SantaTerms, { defaultUntil, readTerms, termsFrom } from './SantaTerms.svelte';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  const name = $derived(session.me?.memberships.find((x) => x.org.id === org)?.org.name ?? '');
  const running = $derived((data.studio[org] ?? []).find((e) => e.santa && e.status === 'published' && (e.endsAt ?? e.startsAt) > nowTs()));
  // the gifts day the editor changes later: Dec 25 (months from 0), or two weeks on when that is too close or past
  const dec25 = tsAt(parts(nowTs()).y, 11, 25, 18, 0);
  const when = dec25 - nowTs() > 3 * 86400 ? dec25 : nowTs() + 14 * 86400;
  const LINES = [[PenLine, 'santa.hi1'], [Shuffle, 'santa.hi2'], [EyeOff, 'santa.hi3']] as const;
  // the two settings (server santa.start): no budget, wishlists until a week before the gifts day
  let terms = $state(termsFrom(null, defaultUntil(when)));
  let tried = $state(false);

  let busy = $state(false);
  async function go() {
    if (running) { close(overlay.id); sheets.manage(running.id); return; }
    if (busy) return;
    const r = readTerms(terms, when);
    if (r.badBudget || r.badUntil) { tried = true; haptic.error(); return; }
    busy = true;
    try {
      const e = await api.santaStart(org, t('santa.title'), when, r.budget, r.until);
      void loadStudio(org); haptic.ok();
      close(overlay.id); say(t(e.santaTold === 0 ? 'santa.toldNot' : 'santa.told'), 'party_popper_3d'); sheets.manage(e.id);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={Gift} title={t('santa.title')}>
  <div class="hi">
    <span class="art"><Emoji name="party_popper_3d" size={84} /></span>
    <h2 class="t-h2 hd">{t('santa.hiTitle', { org: name })}</h2>
    {#if running}
      <p class="t-body dim">{t('santa.hiOn')} · {tn('santa.playing', running.taken)}</p>
    {:else}
      <ul>
        {#each LINES as [Icon, key], i (key)}
          <li style:--i={i}><Icon size={22} /><span class="t-body">{t(key)}</span></li>
        {/each}
      </ul>
      <p class="t-foot dim day">{t('santa.hiDay', { day: dayMonth(when) })}</p>
      <SantaTerms bind:f={terms} starts={when} {tried} />
    {/if}
  </div>

  {#snippet footer()}
    <div class="acts">
      <Button kind="primary" size="l" full lit loading={busy} onclick={go}>{t(running ? 'santa.hiOpen' : 'santa.hiGo')}</Button>
      <Button kind="plain" size="m" full onclick={() => close(overlay.id)}>{t('santa.hiLater')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .hi { display: flex; flex-direction: column; align-items: center; text-align: center; padding: var(--s-2) 0 var(--s-2); }
  .art { display: block; margin-bottom: var(--s-3); animation: arrive 560ms var(--ease-spring) both; }
  .hd { margin: 0 0 var(--s-5); text-wrap: balance; overflow-wrap: anywhere; }
  .dim { margin: 0; color: var(--text-2); }
  ul { display: flex; flex-direction: column; gap: var(--s-4); width: 100%; margin: 0; padding: 0; list-style: none; text-align: left; }
  li { display: flex; align-items: center; gap: var(--s-3); animation: rise 420ms var(--ease) both; animation-delay: calc(140ms + var(--i) * 80ms); }
  li :global(svg) { flex: none; color: var(--accent); }
  li span { text-wrap: pretty; }
  .day { margin: var(--s-5) 0 var(--s-4); }
  .acts { display: flex; flex-direction: column; gap: var(--s-1); }
  @keyframes arrive { from { opacity: 0; transform: translateY(12px) scale(0.86); } }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  @media (prefers-reduced-motion: reduce) { .art, li { animation: none; } }
</style>
