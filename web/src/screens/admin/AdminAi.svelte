<script lang="ts">
  // Admin → AI (owner, Oct 21: "where is the AI section?"): the translator of event and club texts (PLAN 9, ai.py on
  // Cloudflare Workers AI): on or off, what it did today (Cloudflare's day, UTC), its last error, how much is done,
  // waits or failed three times; the failed can get three more tries.
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import { api, type AdminAi } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let ai = $state<AdminAi | null>(null), busy = $state(false);
  const load = () => api.adminAi().then((x) => (ai = x)).catch(() => say(t('common.error'), 'pleading_face_3d'));
  $effect(() => { void load(); });
  async function retry() {
    busy = true;
    try { await api.aiRetry(); haptic.ok(); say(t('ai.retried'), 'sparkles_3d'); await load(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('ai.title')} icon={Sparkles}>
  {#if ai}
    <section class="top surface">
      <span class="st" class:on={ai.on}><i></i>{ai.on ? t('ai.on') : t('ai.off')}</span>
      <b class="num">{ai.today}</b><span class="t-foot">{t('ai.today')}</span>
      <p class="t-foot model">{ai.model}</p>
    </section>
    <div class="nums">
      <span class="surface"><b class="num">{ai.events.done}</b><i>{t('ai.events')}</i>{#if ai.events.waiting}<em>{t('ai.waiting', { n: ai.events.waiting })}</em>{/if}</span>
      <span class="surface"><b class="num">{ai.clubs.done}</b><i>{t('ai.clubs')}</i>{#if ai.clubs.waiting}<em>{t('ai.waiting', { n: ai.clubs.waiting })}</em>{/if}</span>
    </div>
    {#if ai.error}<p class="err surface"><b>{t('ai.lastError')}</b><span class="selectable">{ai.error}</span></p>{/if}
    {#if ai.failed.length}
      <h3 class="sec">{t('ai.failed')}</h3>
      <div class="rows surface">
        {#each ai.failed as f (f.kind + f.id)}
          <button class="r" onclick={() => (f.kind === 'event' ? sheets.event(f.id) : sheets.club(f.id))}><span class="ellipsis">{f.title}</span><i>{f.kind === 'event' ? t('ai.event') : t('ai.club')}</i></button>
        {/each}
      </div>
      <div class="go"><Button kind="secondary" size="m" full loading={busy} onclick={retry}>{t('ai.retry')}</Button></div>
    {/if}
    <p class="t-foot note">{t('ai.note')}</p>
  {/if}
</Sheet>

<style>
  .top { display: flex; flex-direction: column; gap: 2px; padding: 16px; border-radius: var(--r-l); }
  .top b { font: 800 40px/1 var(--font-display); letter-spacing: -0.03em; margin-top: 10px; }
  .st { display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; height: 26px; padding: 0 10px; border-radius: var(--r-full);
    background: var(--danger-soft); color: var(--danger-text); font: 650 var(--fs-sub)/1 var(--font-text); }
  .st i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .st.on { background: var(--success-soft); color: var(--success-text); }
  .model { margin-top: 8px; font-family: ui-monospace, monospace; }
  .nums { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
  .nums span { display: flex; flex-direction: column; gap: 2px; padding: 14px; border-radius: var(--r-l); }
  .nums b { font: 750 26px/1 var(--font-display); }
  .nums i { font: 500 var(--fs-sub)/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  .nums em { font: 600 var(--fs-cap)/1.2 var(--font-text); font-style: normal; color: var(--warning-text); }
  .err { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; padding: 12px 14px; border-radius: var(--r-l); font: 500 var(--fs-sub)/1.35 var(--font-text); }
  .err b { color: var(--danger-text); }
  .sec { margin: 22px 4px 10px; font: 760 var(--fs-sec)/1.1 var(--font-display); letter-spacing: -0.025em; }
  .rows { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .r { display: flex; align-items: center; gap: 10px; min-height: 48px; padding: 0 14px; text-align: left; font: 600 var(--fs-body)/1.2 var(--font-text); }
  .r + .r { box-shadow: inset 0 1px 0 var(--line); }
  .r span { flex: 1; min-width: 0; }
  .r i { flex: none; font: 500 var(--fs-cap)/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .go { margin-top: 10px; }
  .note { margin: 16px 4px 0; }
</style>
