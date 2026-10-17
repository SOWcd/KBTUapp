<script lang="ts">
  // Delete account (SPEC §4.8). First what goes for good, then a week to change your mind (owner, Oct 13): the bot
  // says when at once, the account works as usual meanwhile, and "Keep my account" on Me takes it back. The KBTU
  // password it asked before shut out whoever no longer has one; the week guards against someone holding the phone.
  // Last, quietly, KBTU's psychological service: no hints, just there.
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { PSYCHOLOGIST } from '../../lib/academic';

  let { overlay, lost }: { overlay: Overlay; lost: { awards: number; tickets: number; clubs: number } } = $props();

  let busy = $state(false);
  const items = $derived([
    [lost.awards, tn('person.awardsWord', lost.awards)], [lost.tickets, tn('del.ticketsWord', lost.tickets)], [lost.clubs, tn('person.clubsWord', lost.clubs)],
  ].filter(([n]) => n) as [number, string][]);

  async function submit() {
    if (busy) return;
    busy = true;
    try {
      const m = await api.deleteMe();
      session.me = m;
      haptic.warn();
      close(overlay.id);
      say(t('del.done', { date: dayMonth(m.deleteAt ?? 0) }), 'waving_hand_3d_default');
    } catch (e) {
      haptic.error();
      say(t(e instanceof ApiErr && e.message === 'president' ? 'del.president' : 'common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('del.title')}>
  <div class="wrap">
    <span class="ic"><TriangleAlert size={26} /></span>
    <h2 class="t-h2">{t('del.title')}</h2>
    {#if items.length}
      <div class="lost">
        <p class="t-cap">{t('del.lost')}</p>
        <p class="nums">{#each items as [n, word], i (word)}{#if i}<span class="dot">·</span>{/if}<b>{n}</b> {word}{/each}</p>
      </div>
    {/if}
    <p class="t-callout dim">{t('del.text')}</p>
    <p class="t-callout who">{t('del.confirm')}</p>
    <button class="care t-foot" onclick={() => openLink(PSYCHOLOGIST)}><HeartHandshake size={15} />{t('del.care')}</button>
  </div>
  {#snippet footer()}
    <Button kind="danger" size="l" full loading={busy} onclick={submit}>{t('del.forever')}</Button>
  {/snippet}
</Sheet>

<style>
  .wrap { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
  .ic { width: 54px; height: 54px; border-radius: 16px; display: flex; align-items: center; justify-content: center; background: var(--danger-soft); color: var(--danger-text); }
  .lost { padding: 12px 14px; border-radius: var(--r-m); background: var(--danger-soft); }
  .lost .t-cap { color: var(--danger-text); }
  .nums { margin-top: 4px; font: 560 15px/1.3 var(--font-text); }
  .nums b { font-weight: 760; }
  .dot { margin: 0 7px; color: var(--text-3); }
  .dim { color: var(--text-2); }
  .who { font-weight: 620; margin-top: 4px; }
  .care { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; padding: 6px 0; color: var(--text-3); }
</style>
