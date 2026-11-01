<script lang="ts">
  // The privacy policy changed (lib/legal.ts): a signed-in student agrees again before using the app (owner, Nov 1:
  // the sheet got swiped away unread). Full screen, not a Sheet: no swipe, not in the overlay stack, so Back can't
  // close it. App renders it over the tabs and holds every other overlay but the delete sheet until it's accepted.
  // The ways out: read the policy, delete the account (the week's wait lifts the gate), Telegram's own close.
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Button from '../ui/Button.svelte';
  import { api } from '../lib/api';
  import { say } from '../lib/state/ui.svelte';
  import { session } from '../lib/state/session.svelte';
  import { data } from '../lib/state/data.svelte';
  import { sheets } from '../lib/state/sheets';
  import { inner } from '../lib/perms';
  import { t, i18n } from '../lib/i18n/index.svelte';
  import { haptic, openLink } from '../lib/tg';
  import { CONSENT_BOARD, CONSENT_BOTH, CONSENT_VERSION } from '../lib/legal';

  let busy = $state(false);
  // what's new in the version asked, one short line each: v3 alone, the find-people forum (v4), the student forum (v7), both (v8)
  const p = $derived(session.policy);
  const lines = $derived([
    ...(p === CONSENT_VERSION ? [t('consent.text')] : []),
    ...(p !== CONSENT_VERSION && p !== CONSENT_BOARD ? [t('consent.textForum')] : []),
    ...(p === CONSENT_BOARD || p === CONSENT_BOTH ? [t('consent.textBoard')] : []),
  ].flatMap((x) => x.split('\n')));

  async function agree() {
    if (busy) return;
    busy = true;
    try { session.me = await api.consent(session.policy); haptic.ok(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); } finally { busy = false; }
  }
  // the same counts Settings shows before a deletion
  function del() {
    haptic.tap();
    const a = data.myCard?.awards;
    sheets.deleteAccount({ awards: a ? a.achievements.filter((x) => x.level > 0).length + a.badges.length : 0,
      tickets: data.events.filter((e) => e.my && e.my.status !== 'cancelled' && !inner(e)).length, clubs: session.me?.memberships.length ?? 0 });
  }
</script>

<div class="gate" role="dialog" aria-modal="true" aria-labelledby="cg-t">
  <div class="body">
    <span class="ic"><ShieldCheck size={30} /></span>
    <h2 id="cg-t" class="t-h2">{t('consent.title')}</h2>
    <ul>{#each lines as l, i (i)}<li class="t-callout">{l}</li>{/each}</ul>
    <button class="lnk t-callout" onclick={() => { haptic.tap(); openLink(`${location.origin}/privacy?lang=${i18n.lang}`); }}>{t('login.consentLink')}</button>
  </div>
  <div class="foot">
    <Button kind="primary" size="l" full loading={busy} onclick={agree}>{t('consent.ok')}</Button>
    <button class="del t-foot" onclick={del}>{t('del.title')}</button>
  </div>
</div>

<style>
  .gate { position: absolute; inset: 0; z-index: calc(var(--z-sheet) - 1); display: flex; flex-direction: column;
    padding: var(--page-top) 20px calc(var(--safe-bottom) + 12px); background: var(--glow), var(--bg); animation: in var(--t-base) ease-out both; }
  .body { flex: 1; overflow-y: auto; display: flex; flex-direction: column; justify-content: center; gap: 14px; min-height: 0; }
  .ic { width: 56px; height: 56px; border-radius: var(--r-full); display: grid; place-items: center; background: var(--accent-soft); color: var(--accent-text); }
  ul { display: flex; flex-direction: column; gap: 10px; padding-left: 18px; }
  li { color: var(--text-2); }
  .lnk { align-self: flex-start; color: var(--accent-text); font-weight: 620; }
  .foot { display: flex; flex-direction: column; align-items: center; gap: 4px; padding-top: 12px; }
  .del { height: 44px; padding: 0 16px; color: var(--text-3); }
  @keyframes in { from { opacity: 0; } }
</style>
