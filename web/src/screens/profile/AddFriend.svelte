<script lang="ts">
  // Add a friend (SPEC §4.7). My invite QR on the badge's material, the one link (Nov 2, lib/friends): a friend points
  // the camera, taps "Add as a friend" on my card and we're friends. While the sheet is open it watches for a new friend,
  // shows them and celebrates. The same invite goes out as our bot's card (a line and a button; no bare links). Or:
  // look someone up by @username and send a request they answer.
  import { onDestroy } from 'svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { api, ApiErr, type FoundStudent, type PersonRef } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { friendsChanged } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { inviteUrl, shareInvite } from '../../lib/friends';
  import { session } from '../../lib/state/session.svelte';
  import { QR_TONE } from '../../lib/awards';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import Button from '../../ui/Button.svelte';
  import Qr from '../../ui/Qr.svelte';
  import '../../lib/qrnow'; // its code in the first frame (lib/qr.svelte.ts)
  import Avatar from '../../ui/Avatar.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { schoolShort } from '../../lib/short';

  let { overlay, share = false }: { overlay: Overlay; share?: boolean } = $props();

  const code = $derived(session.me?.referrals?.code ?? null);
  let joined = $state<PersonRef | null>(null); // who has just become my friend: on the plate for a few seconds
  // svelte-ignore state_referenced_locally
  if (share) void send(); // opened to share at once (the Friends sheet's invite)

  let since: number | null = null; // the server's clock: the first round only notes my newest friend so far
  let quiet: ReturnType<typeof setTimeout> | undefined;
  const watch = setInterval(async () => {
    if (joined || document.hidden) return;
    try {
      const r = await api.friendJoined(since ?? 0), first = since === null;
      since = r.at;
      if (!r.usedBy || first) return;
      joined = r.usedBy;
      haptic.ok(); burst(); say(t('fr.accepted', { name: r.usedBy.name }), 'partying_face_3d');
      friendsChanged();
      quiet = setTimeout(() => { joined = null; }, 3200);
    } catch { /* offline for a moment: the next round asks again */ }
  }, 2500);
  onDestroy(() => { clearInterval(watch); clearTimeout(quiet); });

  async function send() {
    try { if (code) await shareInvite(code); } catch { say(t('common.error'), 'warning_3d'); }
  }

  // ---- by @username ----
  let q = $state('');
  let found = $state<FoundStudent | null>(null);
  let miss = $state('');
  let looking = $state(false);
  let asking = $state(false);
  const line = $derived(found ? [found.course ? t('person.course', { n: found.course }) : '', schoolShort(found.school)].filter(Boolean).join(' · ') : '');
  async function find(ev: Event) {
    ev.preventDefault();
    if (!q.trim()) return;
    looking = true; miss = ''; found = null;
    try { found = await api.findFriend(q.trim()); }
    catch (e) { miss = e instanceof ApiErr && e.code === 'bad_input' ? t('fr.badName') : e instanceof ApiErr && e.code === 'not_found' ? t('fr.notFound') : t('common.error'); }
    finally { looking = false; }
  }
  // the row answers first (the speed rule): friends, or the request sent; an error puts it back
  async function ask() {
    const was = found;
    if (!was || asking) return;
    asking = true;
    const incoming = was.friendship === 'incoming';
    found = { ...was, friendship: incoming ? 'friends' : 'requested' };
    haptic.tap();
    try {
      const now = incoming ? (await api.answerFriend(was.person.id, true), 'friends' as const) : (await api.askFriend(was.person.id)).friendship;
      if (found?.person.id === was.person.id) found = { ...was, friendship: now };
      if (now === 'friends') { haptic.ok(); burst(); say(t('fr.accepted', { name: was.person.name }), 'partying_face_3d'); }
      else { haptic.ok(); say(t('person.requestSent'), 'raising_hands_3d_default'); }
      friendsChanged();
    } catch (e) {
      const closed = e instanceof ApiErr && e.code === 'closed';
      if (found?.person.id === was.person.id) found = { ...was, closed };
      haptic.error(); say(e instanceof ApiErr && e.code === 'rate_limited' ? t('fr.tooMany') : closed ? t('fr.closed') : t('common.error'), 'warning_3d');
    } finally { asking = false; }
  }
</script>

<Sheet {overlay} icon={UserPlus} title={t('fr.addTitle')}>
  <div class="pass">
    <div class="plate">
      {#if joined}
        <span class="joined"><Avatar person={joined} size={72} tappable={false} /><b>{joined.name}</b><i>{t('fr.nowFriend')}</i></span>
      {:else if code}
        <span class="code"><Qr text={inviteUrl(code)} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></span>
      {:else}
        <span class="wait" aria-hidden="true"></span>
      {/if}
    </div>
    <p class="cap">{t('ref.qr')}</p>
  </div>

  <div class="acts">
    <Button kind="primary" size="l" full onclick={send}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('fr.send')}</Button>
  </div>

  <!-- engine: Field has no autocapitalize / spellcheck (a username wants both off) -->
  <form class="find" onsubmit={find}>
    <span class="fl"><Field label={t('fr.orUsername')} bind:value={q} placeholder="@username" autocomplete="off" enterkeyhint="search" maxlength={33} error={miss || undefined} /></span>
    <Button kind="secondary" size="m" type="submit" loading={looking} disabled={!q.trim()}>{t('fr.find')}</Button>
  </form>
  {#if found}
    {@const st = found.me ? t('fr.isMe') : found.friendship === 'friends' ? t('fr.already') : found.friendship === 'requested' ? t('person.requestSent') : found.closed ? t('fr.closed') : ''}
    <div class="hit"><Group>
      {#if st}<Row dense title={found.person.name} subtitle={line} value={st}>{#snippet lead()}<Avatar person={found!.person} size={40} />{/snippet}</Row>
      {:else}<Row dense title={found.person.name} subtitle={line}>{#snippet lead()}<Avatar person={found!.person} size={40} />{/snippet}
        {#snippet trailing()}<Button kind="primary" size="s" loading={asking} onclick={ask}>{found!.friendship === 'incoming' ? t('fr.accept') : t('fr.add')}</Button>{/snippet}</Row>{/if}
    </Group></div>
  {/if}
</Sheet>

<style>

  /* the badge's own material (MyQr), smaller: the code a friend scans across a table */
  .pass { position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 18px 18px 16px; border-radius: 26px; color: #fff;
    background: radial-gradient(110% 70% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(160deg, #2A4FD6, #121A3D 70%);
    box-shadow: 0 26px 46px -26px rgba(18, 26, 61, 0.9), inset 0 1px 0 rgba(255, 255, 255, 0.25); }
  .plate { width: 196px; height: 196px; padding: 12px; border-radius: 22px; background: #fff; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 16px 30px -18px rgba(0, 0, 0, 0.6); }
  .code { display: block; width: 100%; animation: turn 520ms cubic-bezier(.2, .9, .25, 1.1) backwards; }
  @keyframes turn { from { opacity: 0; transform: perspective(600px) rotateY(-80deg) scale(0.9); } }
  .wait { width: 100%; height: 100%; border-radius: 12px; background: #EEF1F8; animation: pulse 1.1s ease-in-out infinite; }
  .joined { display: flex; flex-direction: column; align-items: center; gap: 8px; color: #0B1433; text-align: center; animation: pop 560ms cubic-bezier(.2, 1.4, .4, 1) backwards; }
  .joined b { font: 700 var(--fs-row)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .joined i { font: 600 var(--fs-sub)/1.25 var(--font-text); font-style: normal; color: #13884A; }
  @keyframes pop { from { opacity: 0; transform: scale(0.6); } }
  @keyframes pulse { 50% { opacity: 0.55; } }
  .cap { margin-top: 8px; font: 600 var(--fs-body)/1.3 var(--font-text); text-align: center; text-wrap: balance; }

  .acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .acts :global(.btn.full) { flex: 1 1 140px; width: auto; min-width: 0; } /* side by side, stacked on a 320-px phone */

  /* the field and its button on one line, the button level with the box (the label sits above) */
  .find { display: flex; align-items: flex-end; gap: var(--s-2); margin-top: var(--s-6); }
  .fl { flex: 1; min-width: 0; }
  .find > :global(.btn) { margin-bottom: 3px; }
  .hit { margin-top: var(--s-3); }
</style>
