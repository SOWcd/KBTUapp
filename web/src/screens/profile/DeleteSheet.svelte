<script lang="ts">
  // Delete account (SPEC §4.8). First what goes for good, then a week to change your mind: the bot
  // says when at once, the account works as usual meanwhile, and "Keep my account" on Me takes it back. The KBTU
  // password it asked before shut out whoever no longer has one; the week guards against someone holding the phone.
  // Last, quietly, KBTU's psychological service: no hints, just there. What stays without the name (H2): the album photos
  // added (a switch takes them too), a paid ticket ahead makes it wait, a President's club passes on.
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import Sheet from '../../ui/Sheet.svelte';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import Button from '../../ui/Button.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import { api } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { PSYCHOLOGIST } from '../../lib/academic';

  let { overlay, lost }: { overlay: Overlay; lost: { awards: number; tickets: number; clubs: number } } = $props();

  let busy = $state(false);
  let info = $state<{ photos: number; paid: boolean } | null>(null);
  let photos = $state(false);
  api.deleteInfo().then((i) => (info = i)).catch(() => {});
  const president = session.me?.memberships.some((m) => m.role === 'president') ?? false;
  const items = $derived([
    [lost.awards, tn('person.awardsWord', lost.awards)], [lost.tickets, tn('del.ticketsWord', lost.tickets)], [lost.clubs, tn('person.clubsWord', lost.clubs)],
  ].filter(([n]) => n) as [number, string][]);

  async function submit() {
    if (busy) return;
    busy = true;
    try {
      const m = await api.deleteMe(photos);
      session.me = m;
      haptic.warn();
      close(overlay.id);
      say(t('del.done', { date: dayMonth(m.deleteAt ?? 0) }), 'waving_hand_3d_default');
    } catch (e) {
      haptic.error();
      say(t('common.error'), 'warning_3d');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={Trash2} title={t('del.title')}>
  <div class="wrap">
    <span class="ic"><TriangleAlert size={26} /></span>
    <h2 class="t-h2">{t('del.title')}</h2>
    {#if items.length}<Notice tone="danger" title={t('del.lost')} text={items.map(([n, word]) => `${n} ${word}`).join(' · ')} />{/if}
    <p class="t-callout dim">{t('del.text')}</p>
    <p class="t-callout dim">{t('del.stays')}</p>
    {#if info?.photos}
      <Group><Row title={t('del.photos')} subtitle={tn('del.photosN', info.photos)} accessory="switch" checked={photos} onchange={(on) => { photos = on; haptic.select(); }} /></Group>
    {/if}
    {#if president}<Notice tone="warning" text={t('del.president')} />{/if}
    {#if info?.paid}<Notice tone="warning" text={t('del.paid')} />{/if}
    <p class="t-callout who">{t('del.confirm')}</p>
    <span class="care"><Button kind="plain" size="s" onclick={() => openLink(PSYCHOLOGIST)}>{#snippet icon()}<HeartHandshake size={15} />{/snippet}{t('del.care')}</Button></span>
  </div>
  {#snippet footer()}
    <Button kind="danger" size="l" full loading={busy} onclick={submit}>{t('del.forever')}</Button>
  {/snippet}
</Sheet>

<style>
  .wrap { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
  .ic { width: 54px; height: 54px; border-radius: var(--r-m); display: flex; align-items: center; justify-content: center; background: var(--danger-soft); color: var(--danger-text); }
  .dim { color: var(--text-2); }
  .who { font-weight: 600; margin-top: 4px; }
  /* quietly there: grey, not the accent of an action */
  .care { align-self: flex-start; margin: 8px 0 0 calc(-1 * var(--s-2)); --plain-ink: var(--text-3); }
</style>
