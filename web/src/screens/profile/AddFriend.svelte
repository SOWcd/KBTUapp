<script lang="ts">
  // Add a friend (SPEC §4.7). My one-time QR on the badge's material: a friend points the camera and you're friends at
  // once. While the sheet is open it watches the link, shows who just joined, celebrates and turns over to the next
  // code. The same invite goes out as our bot's card (a line and a button; no bare links). Or: look
  // someone up by @username and send a request they answer.
  import { onDestroy } from 'svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { api, ApiErr, type FoundStudent, type PersonRef } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { friendsChanged } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { friendUrl, shareFriendLink } from '../../lib/friends';
  import { QR_TONE } from '../../lib/awards';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Qr from '../../ui/Qr.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { schoolShort } from '../../lib/short';

  let { overlay, share = false }: { overlay: Overlay; share?: boolean } = $props();

  let token = $state<string | null>(null);
  let joined = $state<PersonRef | null>(null); // who has just used the code: on the plate for a few seconds
  const fresh = () => api.friendLink().then((l) => { token = l.token; }).catch(() => say(t('common.error'), 'pleading_face_3d'));
  void fresh().then(() => { if (share) void send(); });

  let quiet: ReturnType<typeof setTimeout> | undefined;
  const watch = setInterval(async () => {
    if (!token || joined || document.hidden) return;
    try {
      const { usedBy } = await api.friendLinkUsed(token);
      if (!usedBy) return;
      joined = usedBy;
      haptic.ok(); burst(); say(t('fr.accepted', { name: usedBy.name }), 'partying_face_3d');
      friendsChanged();
      quiet = setTimeout(() => { joined = null; void fresh(); }, 3200);
    } catch { /* offline for a moment: the next round asks again */ }
  }, 2500);
  onDestroy(() => { clearInterval(watch); clearTimeout(quiet); });

  async function send() {
    try { await shareFriendLink(); } catch { say(t('common.error'), 'pleading_face_3d'); }
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
  async function ask() {
    if (!found) return;
    asking = true;
    try {
      if (found.friendship === 'incoming') { await api.answerFriend(found.person.id, true); found = { ...found, friendship: 'friends' }; }
      else found = { ...found, friendship: (await api.askFriend(found.person.id)).friendship };
      if (found.friendship === 'friends') { haptic.ok(); burst(); say(t('fr.accepted', { name: found.person.name }), 'partying_face_3d'); }
      else { haptic.ok(); say(t('person.requestSent'), 'raising_hands_3d_default'); }
      friendsChanged();
    } catch (e) { haptic.error(); say(e instanceof ApiErr && e.code === 'rate_limited' ? t('fr.tooMany') : t('common.error'), 'pleading_face_3d'); }
    finally { asking = false; }
  }
</script>

<Sheet {overlay} title={t('fr.addTitle')}>
  <h2 class="t-h2 hd">{t('fr.addTitle')}</h2>

  <div class="pass">
    <div class="plate">
      {#if joined}
        <span class="joined"><Avatar person={joined} size={72} tappable={false} /><b>{joined.name}</b><i>{t('fr.nowFriend')}</i></span>
      {:else if token}
        {#key token}<span class="code"><Qr text={friendUrl(token)} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></span>{/key}
      {:else}
        <span class="wait" aria-hidden="true"></span>
      {/if}
    </div>
    <p class="cap">{t('fr.qrCaption')}</p>
    <p class="note">{t('fr.qrNote')}</p>
  </div>

  <div class="acts">
    <Button kind="primary" size="l" full onclick={send}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('fr.send')}</Button>
  </div>

  <p class="or"><span>{t('fr.orUsername')}</span></p>
  <form class="find" onsubmit={find}>
    <label class="uname"><span class="at">@</span><input bind:value={q} placeholder="username" autocapitalize="none" autocomplete="off" spellcheck="false" enterkeyhint="search" maxlength="33" aria-label="@username" /></label>
    <Button kind="secondary" size="m" type="submit" loading={looking} disabled={!q.trim()}>{t('fr.find')}</Button>
  </form>
  {#if miss}<p class="miss">{miss}</p>{/if}
  {#if found}
    <div class="hit">
      <Avatar person={found.person} size={44} />
      <span class="tx"><b class="ellipsis">{found.person.name}</b><i class="ellipsis">{line}</i></span>
      {#if found.me}<span class="st">{t('fr.isMe')}</span>
      {:else if found.friendship === 'friends'}<span class="st ok">{t('fr.already')}</span>
      {:else if found.friendship === 'requested'}<span class="st">{t('person.requestSent')}</span>
      {:else}<Button kind="primary" size="s" loading={asking} onclick={ask}>{found.friendship === 'incoming' ? t('fr.accept') : t('fr.add')}</Button>{/if}
    </div>
  {/if}
</Sheet>

<style>
  .hd { margin: 4px 0 14px; }

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
  .joined b { font: 760 17px/1.2 var(--font-display); letter-spacing: -0.02em; }
  .joined i { font: 600 13px/1.25 var(--font-text); font-style: normal; color: #13884A; }
  @keyframes pop { from { opacity: 0; transform: scale(0.6); } }
  @keyframes pulse { 50% { opacity: 0.55; } }
  .cap { margin-top: 8px; font: 650 15px/1.3 var(--font-text); text-align: center; text-wrap: balance; }
  .note { font: 500 12.5px/1.3 var(--font-text); color: rgba(255, 255, 255, 0.7); text-align: center; }

  .acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .acts :global(.btn.full) { flex: 1 1 140px; width: auto; min-width: 0; } /* side by side, stacked on a 320-px phone */

  .or { display: flex; align-items: center; gap: 10px; margin: 18px 0 10px; color: var(--text-3); font: 600 12.5px/1 var(--font-text); }
  .or::before, .or::after { content: ''; flex: 1; height: 1px; background: var(--line-2); }
  .find { display: flex; gap: 8px; }
  .uname { flex: 1; min-width: 0; display: flex; align-items: center; height: 44px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface-2); }
  .at { color: var(--text-3); font: 650 16px/1 var(--font-text); }
  .uname input { flex: 1; min-width: 0; height: 100%; padding-left: 2px; background: none; color: var(--text); font: 560 16px/1 var(--font-text); }
  .miss { margin-top: 8px; font: 550 13.5px/1.3 var(--font-text); color: var(--text-2); }
  .hit { display: flex; align-items: center; gap: 10px; margin-top: 10px; padding: 10px 10px 10px 12px; border-radius: var(--r-l); background: var(--surface-2); animation: pop 420ms cubic-bezier(.2, 1.2, .4, 1) backwards; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 650 15px/1.25 var(--font-text); }
  .tx i { font: 500 12.5px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .st { flex: none; font: 620 13px/1 var(--font-text); color: var(--text-2); }
  .st.ok { color: var(--success-text); }
</style>
