<script lang="ts">
  // My invite as a QR (owner, Oct 31) with my photo in the middle (Nov 1); the one link that also adds friends (Nov 2).
  // It is r_<link code>, never the lanyard's u_<id>_<badge code>: this QR is made to be posted and the badge code checks me in at the door (review, Nov 1).
  // A newcomer who scans my lanyard in person still counts for me (server refer).
  // Drawn as the back of my lanyard card (owner, Nov 3: the blue card looked weak; ui/CardBack): its art, my name and
  // number, the medallion; only the code is the invite's, with my photo in its middle.
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { inviteUrl, shareInvite } from '../../lib/friends';
  import { hero, lookOf, orgOfLook } from '../../lib/awards';
  import { data } from '../../lib/state/data.svelte';
  import CardBack from '../../ui/CardBack.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Link from '@lucide/svelte/icons/link';
  import Button from '../../ui/Button.svelte';
  import '../../lib/qrnow'; // its code in the first frame (lib/qr.svelte.ts)
  import Avatar from '../../ui/Avatar.svelte';
  import { session } from '../../lib/state/session.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';

  let { overlay, code }: { overlay: Overlay; code: string } = $props();
  const link = $derived(inviteUrl(code));
  const me = $derived(session.me);
  // my card as Profile shows it (the lanyard I wear); before it loads, the KBTU one with what the app knows
  const card = $derived(data.myCard && me ? { ...data.myCard, skin: me.skin } : null);
  const look = $derived(card ? lookOf(card) : 'kbtu');
  const h = $derived(card ? hero(card) : null);
  let busy = $state(false);
  async function send() {
    haptic.tap(); busy = true;
    try { await shareInvite(code, () => (busy = false)); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={Link} title={t('ref.title')}>
  <div class="pass">
    <CardBack {look} name={h?.name ?? me?.name ?? ''} title={h?.title ?? 'Student'} line={h?.line ?? ''} no={h?.no ?? (me?.no == null ? '—' : String(me.no).padStart(5, '0'))}
      text={link} logo={card ? orgOfLook(card, look)?.logo ?? null : null}>
      {#snippet mark()}{#if me}<span class="face"><Avatar person={me} size={48} tappable={false} /></span>{/if}{/snippet}
    </CardBack>
  </div>
  <p class="cap">{t('ref.qr')}</p>
  <div class="acts">
    <Button kind="primary" size="l" full loading={busy} onclick={send}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('fr.send')}</Button>
  </div>
</Sheet>

<style>
  .pass { margin-top: 4px; }
  /* my photo in the code's middle: a white gap, then the brand's ring, like a story */
  .face { display: flex; width: 100%; height: 100%; padding: 2px; border-radius: 50%; background: var(--grad-accent);
    box-shadow: 0 0 0 2px rgb(255, 255, 255), 0 4px 10px -4px rgba(42, 79, 214, 0.6); }
  .face :global(.av) { width: 100% !important; height: 100% !important; border-radius: 50%; box-shadow: 0 0 0 1.5px rgb(255, 255, 255); overflow: hidden; }
  .face :global(img), .face :global(.ini) { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
  .face :global(.seal) { display: none; } /* the founder's seal would cover the code */
  .cap { margin-top: 14px; font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); text-align: center; text-wrap: balance; }
  .acts { margin-top: 12px; }
</style>
