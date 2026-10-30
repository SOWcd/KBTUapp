<script lang="ts">
  // A new forum thread: the topic (it decides how long it stays and whether people can say "I'm in"), the words, and
  // "anonymously". Said plainly what anonymous means: nobody sees the name, the app's creator can, for a broken rule.
  // The AI reads it first: a held one says it waits for a look. Leaving with words typed asks first.
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import { api, ApiErr, type Topic } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import { grow } from '../../ui/grow';
  import { TOPICS, TOPIC_ICON, TOPIC_TINT } from '../../lib/forum';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, onmade }: { overlay: Overlay; onmade?: () => void } = $props();
  let topic = $state<Topic | null>(null), body = $state(''), anon = $state(false), busy = $state(false), done = false;
  const ready = $derived(!!topic && body.trim().length >= 2);
  let field = $state<HTMLTextAreaElement>();

  function pick(k: Topic) { topic = k; haptic.select(); setTimeout(() => field?.focus(), 60); }
  async function post() {
    if (!ready || busy) return;
    busy = true;
    try {
      const th = await api.newThread({ topic: topic!, body: body.trim(), anon });
      done = true; haptic.ok();
      if (th.status === 'held') say(t('bd.heldSay'), 'thinking_face_3d');
      else { burst(); say(t('bd.postedSay'), 'party_popper_3d'); }
      onmade?.(); close(overlay.id);
    } catch (e) {
      haptic.error();
      say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'bd.slowPosts' : 'common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
  let asking = false;
  async function askLeave() {
    if (asking) return;
    asking = true;
    try { if (await sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('common.cancel'), danger: true })) { done = true; close(overlay.id); } }
    finally { asking = false; }
  }
</script>

<Sheet {overlay} tall title={t('bd.newTitle')} hold={() => !done && !!body.trim()} onhold={askLeave}>
  <h2 class="t-h2 hd">{t('bd.newTitle')}</h2>
  <div class="topics">
    {#each TOPICS as k (k)}
      {@const Icon = TOPIC_ICON[k]}
      <button class:on={topic === k} aria-pressed={topic === k} style:--tint={TOPIC_TINT[k]} onclick={() => pick(k)}>
        <span class="ic"><Icon size={20} strokeWidth={2.2} /></span><b>{t(`bd.topic.${k}`)}</b>
      </button>
    {/each}
  </div>
  {#if topic}<p class="t-foot hint">{t(`bd.hint.${topic}`)}</p>{/if}
  <textarea class="text" bind:this={field} bind:value={body} maxlength="1000" rows="4" placeholder={t(topic ? `bd.ph.${topic}` : 'bd.ph.any')} use:grow={320}></textarea>
  <label class="switch">
    <span><b><VenetianMask size={16} />{t('bd.anonSwitch')}</b><i class="t-foot">{t('bd.anonNote')}</i></span>
    <input type="checkbox" role="switch" bind:checked={anon} />
  </label>
  <p class="t-foot rules">{t('bd.rules')}</p>
  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} disabled={!ready} onclick={post}>{t('bd.post')}</Button>
  {/snippet}
</Sheet>

<style>
  .hd { margin: 4px 0 14px; }
  .topics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; }
  .topics button { display: flex; flex-direction: column; align-items: center; gap: 7px; padding: 11px 2px 10px; border-radius: 16px; background: var(--surface-2);
    transition: transform var(--t-fast) var(--ease), background-color var(--t-base) var(--ease), box-shadow var(--t-base) var(--ease); }
  .topics button:active { transform: scale(0.94); }
  /* each topic's icon in its colour, no tile of paint under it (owner, Oct 30: coloured tiles look childish); the picked
     one ringed in it */
  .ic { height: 28px; display: grid; place-items: center; color: var(--tint); }
  .topics button.on { background: color-mix(in srgb, var(--tint) 12%, var(--surface-2)); box-shadow: inset 0 0 0 1.5px var(--tint); }
  .topics button.on .ic { animation: boop 420ms cubic-bezier(.2, 1.6, .4, 1); }
  @keyframes boop { 30% { transform: scale(1.18) rotate(-8deg); } }
  .topics b { font: 620 11.5px/1.15 var(--font-text); text-align: center; color: var(--text-2); overflow-wrap: anywhere; }
  .topics button.on b { color: var(--text); }
  .hint { margin: 10px 2px 0; animation: c-in 240ms ease-out; }
  @keyframes c-in { from { opacity: 0; transform: translateY(4px); } }
  .text { width: 100%; margin-top: 12px; min-height: 112px; padding: 13px 14px; border-radius: 18px; resize: none; background: var(--surface-2); color: var(--text);
    font: 450 16px/1.45 var(--font-text); }
  .text::placeholder { color: var(--text-3); }
  .switch { margin-top: 12px; }
  .switch b { display: inline-flex; align-items: center; gap: 6px; }
  .rules { margin: 12px 2px 0; }
</style>
