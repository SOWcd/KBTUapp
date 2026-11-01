<script lang="ts">
  // A new forum thread: what it's for first, as a verb (ask, offer, invite, discuss: it decides how long the thread
  // stays and whether people can say "I'm in"; Discuss, or the topic the feed was filtered by), the words, and "anonymously" with
  // what it means in one line: nobody sees the name, the app's creator can, for a broken rule. The AI reads it first:
  // a held one says it waits for a look. Leaving with words typed asks first.
  import { untrack } from 'svelte';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import { grow } from '../../ui/grow';
  import { TOPICS, TOPIC_ICON, type Offered } from '../../lib/forum';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { overlay, onmade, topic: first = 'talk' }: { overlay: Overlay; onmade?: (topic: Offered) => void; topic?: Offered } = $props();
  let topic = $state<Offered>(untrack(() => first)), body = $state(''), anon = $state(false), busy = $state(false), done = false;
  const ready = $derived(body.trim().length >= 2);
  let field = $state<HTMLTextAreaElement>();

  function pick(k: Offered) { topic = k; haptic.select(); setTimeout(() => field?.focus(), 60); }
  async function post() {
    if (!ready || busy) return;
    busy = true;
    try {
      const th = await api.newThread({ topic, body: body.trim(), anon });
      done = true; haptic.ok();
      if (th.status === 'held') say(t('bd.heldSay'), 'thinking_face_3d');
      else { burst(); say(t('bd.postedSay'), 'party_popper_3d'); }
      onmade?.(topic); close(overlay.id);
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

<Sheet {overlay} tall heading={t('bd.newTitle')} icon={SquarePen} hold={() => !done && !!body.trim()} onhold={askLeave}>
  <div class="topics" role="group" aria-label={t('bd.topics')}>
    {#each TOPICS as k (k)}<Chip full selected={topic === k} icon={TOPIC_ICON[k]} onclick={() => pick(k)}>{t(`bd.do.${k}`)}</Chip>{/each}
  </div>
  <textarea class="text" bind:this={field} bind:value={body} maxlength="1000" rows="4" placeholder={t(`bd.ph.${topic}`)} aria-label={t('bd.newTitle')}
    use:grow={320}></textarea>
  <div class="anon">
    <Group footnote={t('bd.anonNote')}>
      <Row title={t('bd.asAnon')} icon={VenetianMask} tile="gray" accessory="switch" checked={anon} onchange={(v) => (anon = v)} />
    </Group>
  </div>
  <p class="foot">{t('bd.rules')}</p>
  {#snippet footer()}
    <Button kind="filled" size="l" full loading={busy} disabled={!ready} onclick={post}>{t('bd.post')}</Button>
  {/snippet}
</Sheet>

<style>
  /* the four as equal tiles, two by two: a verb fits whole in every language at 320 px */
  .topics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-2); padding: var(--s-1) 0; }
  .foot { margin: var(--s-2) var(--s-4) 0; font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  /* the words: a Field's box (Field itself has no way to take the focus after a pick) */
  .text { display: block; width: 100%; margin-top: var(--s-4); min-height: 120px; padding: 13px var(--s-4); border-radius: var(--r-m); resize: none;
    background: var(--fill); color: var(--text); font: 450 var(--fs-row)/1.4 var(--font-text); letter-spacing: -0.012em; transition: box-shadow var(--t-fast); }
  .text::placeholder { color: var(--text-3); }
  .text:focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
  .anon { margin-top: var(--s-5); }
</style>
