<script lang="ts">
  // A post the AI refused (no message in it, an ad): the verdict, at once: "Not published", the words, Edit (back into
  // the writing window, ChannelCompose) and Send to a moderator (fchannel.appeal, three a day) usable right away; the
  // AI's own reason, the piece it stopped at marked and what to change come in when they're ready (/why, phase 2:
  // nobody waits on it).
  import { onMount } from 'svelte';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import ShieldAlert from '@lucide/svelte/icons/shield-alert';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import { api, ApiErr, type ForumWhy, type Id } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { close, open, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Marked from './Marked.svelte';
  import Self from './ChannelRefused.svelte';
  import { compose, land, signOf, stand, unstand } from './ChannelCompose.svelte';

  type Refused = { post: Id; kind: 'noise' | 'ad'; appeal: boolean };
  let { overlay, body, anon, refused }: { overlay: Overlay; body: string; anon: boolean; refused: Refused } = $props();
  let ex = $state<ForumWhy | null>(null), asking = $state(true);

  // the verdict's reason in the AI's words, asked once the verdict is on screen; none: the template stays
  onMount(() => { api.channelPostWhy(refused.post, body).then((x) => { ex = x.explain; }).catch(() => {}).finally(() => { asking = false; }); });

  // the AI was wrong: a human decides (held, in the moderators' queue); the post stands in the feed "with a moderator"
  async function appeal() {
    const r = refused, text = body.trim(), was = anon;
    const temp = stand(text, was, true); haptic.select(); close(overlay.id);
    try {
      const p = await api.appealChannelPost(r.post, text);
      land(temp, p, true); haptic.ok(); say(t('fc.appealedSay'), 'thinking_face_3d');
    } catch (e) {
      unstand(temp); haptic.error();
      const out = e instanceof ApiErr && e.code === 'rate_limited';
      say(t(out ? 'fc.appealsOut' : 'common.error'), 'pleading_face_3d');
      open(Self, { body: text, anon: was, refused: { ...r, appeal: !out && !(e instanceof ApiErr && e.code === 'not_found') } });
    }
  }

  function edit() { haptic.tap(); close(overlay.id); compose({ body, anon }); }
</script>

<Sheet {overlay} icon={ShieldAlert} title={t('fc.refused')}>
  <!-- the verdict: at once, in plain words; the AI's own reason replaces the template once it comes -->
  <div class="verdict">
    <span class="seal" aria-hidden="true"><ShieldAlert size={22} strokeWidth={2} /></span>
    <h2>{t('fc.refused')}</h2>
    <p class="reason" aria-live="polite">{ex?.reason ?? t(refused.kind === 'ad' ? 'fc.ad' : 'fc.noise')}</p>
    {#if asking}<p class="wait">{t('fc.whyLoading')}</p>{/if}
  </div>
  <div class="card">
    <div class="from">
      <span class="face">{#if anon || !session.me}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
      {:else}<Avatar person={session.me} size={36} tappable={false} />{/if}</span>
      <span class="who"><b class="ellipsis">{anon ? t('fc.nickSoon') : signOf()}</b><span class="sub">{t('fc.toChannel')}</span></span>
    </div>
    <p class="words"><Marked text={body} quote={ex?.quote} /></p>
    {#if ex?.fix}<p class="fix"><Lightbulb size={16} strokeWidth={2} aria-hidden="true" /><span>{ex.fix}</span></p>{/if}
  </div>
  {#if refused.appeal}<p class="note">{t('fc.appealNote')}</p>{/if}
  {#snippet footer()}
    <div class="two">
      {#if refused.appeal}<Button kind="secondary" size="l" full onclick={appeal}>{t('fc.appeal')}</Button>{/if}
      <Button kind="filled" size="l" full onclick={edit}>{t('fc.edit')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .card { margin-top: var(--s-3); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card), inset 0 0 0 0.5px var(--line); }
  .from { position: relative; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); }
  .from::after { content: ''; position: absolute; left: var(--s-4); right: 0; bottom: 0; height: 0.5px; background: var(--separator); }
  .face { flex: none; display: flex; }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--fill-2); color: var(--text); }
  .who { min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .who b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); letter-spacing: -0.01em; }
  .sub { font: 450 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .note { margin: var(--s-3) var(--s-4) 0; font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }

  /* the verdict: a seal, the word, the reason; calm, centred, no alarm red */
  .verdict { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); padding: var(--s-2) var(--s-4) var(--s-2); text-align: center; }
  .seal { width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; background: var(--warning-soft); color: var(--warning-text);
    animation: seal 520ms var(--ease-bounce) backwards; }
  @keyframes seal { from { transform: scale(0.5); opacity: 0; } }
  .verdict h2 { margin-top: var(--s-1); font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.02em; color: var(--text); }
  .reason { max-width: 34ch; font: 450 var(--fs-body)/1.42 var(--font-text); color: var(--text-2); animation: fade 300ms var(--ease); }
  @keyframes fade { from { opacity: 0; } }
  .wait { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.45; } }
  @media (prefers-reduced-motion: reduce) { .seal, .wait { animation: none; } }
  .words { padding: var(--s-3) var(--s-4) var(--s-4); font: 450 var(--fs-body)/1.47 var(--font-text); color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    max-height: 40vh; overflow: auto; }
  .fix { position: relative; display: flex; gap: var(--s-2); align-items: flex-start; padding: var(--s-3) var(--s-4); font: 500 var(--fs-sub)/1.4 var(--font-text); color: var(--text);
    animation: fade 300ms var(--ease); }
  .fix::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .fix :global(svg) { flex: none; margin-top: 1px; color: var(--warning-text); }
  .two { display: flex; flex-direction: column; gap: var(--s-2); }
</style>
