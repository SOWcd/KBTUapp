<script lang="ts">
  // A new post to the forum channel (the Forum tab's plus): the words, the rules, Anonymous, and whose name it goes out
  // under. Publish closes the sheet at once and the post stands at the top of the feed, "checking" while the AI looks;
  // refused, the sheet comes back with the words.
  import { untrack } from 'svelte';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import { api, ApiErr, type ChannelFeedPost } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { channel, loadChannel } from '../../lib/state/channel.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { nowTs } from '../../lib/time';
  import { burst } from '../../ui/burst';
  import { grow } from '../../ui/grow';
  import Sheet from '../../ui/Sheet.svelte';
  import Card from '../../ui/Card.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, draft }: { overlay: Overlay; draft?: { body: string; anon: boolean } } = $props();
  let body = $state(untrack(() => draft?.body ?? '')), anon = $state(untrack(() => draft?.anon ?? false));
  const ready = $derived(body.trim().length >= 2);
  // the bot's signature, as the server makes it (fchannel.signature): my nick if I have one, else the real first name
  // and the last initial (ponytail: a nick the server reads as a link signs with the name there; clean_nick refuses most)
  const s = $derived(session.me?.student);
  const sign = $derived(session.me?.nick || (s ? `${s.firstName} ${s.lastName ? [...s.lastName][0] + '.' : ''}`.trim() : ''));

  function fail(e: unknown) {
    haptic.error();
    const why: Key = e instanceof ApiErr ? (e.code === 'rate_limited' ? 'fc.slow' : e.message === 'links' ? 'fc.links' : e.message === 'signature' ? 'fc.signature' : 'common.error') : 'common.error';
    say(t(why), 'pleading_face_3d');
  }

  async function post() {
    if (!ready) return;
    const text = body.trim(), was = anon;
    const temp: ChannelFeedPost = { id: -Date.now(), body: text, status: 'held', at: nowTs(), msg: null, anon: was, sign: was ? t('fc.anonSign') : sign, mine: true,
      person: !was && session.me ? { id: session.me.id, name: session.me.name, avatar: session.me.avatar, founder: false } : null, comments: 0, thread: null };
    channel.feed = [temp, ...(channel.feed ?? [])]; haptic.select(); close(overlay.id);
    try {
      const p = await api.newChannelPost(text, was);
      channel.feed = (channel.feed ?? []).map((x) => (x.id === temp.id ? { ...x, id: p.id, status: p.status, at: p.at } : x));
      haptic.ok();
      if (p.status === 'live') { burst(); say(t('fc.postedSay'), 'party_popper_3d'); setTimeout(loadChannel, 5000); } // the bot sends it within seconds: its link then
      else say(t('fc.heldSay'), 'thinking_face_3d');
    } catch (e) {
      channel.feed = (channel.feed ?? []).filter((x) => x.id !== temp.id);
      fail(e); sheets.channelPost({ body: text, anon: was });
    }
  }
</script>

<Sheet {overlay} icon={SquarePen} heading={t('fc.new')}>
  <Card>
    <textarea class="text" bind:value={body} maxlength="1000" rows="4" placeholder={t('fc.ph')} aria-label={t('fc.ph')} use:grow={280}></textarea>
    <p class="rules">{t('fc.rules')}</p>
  </Card>
  <div class="gap"></div>
  <!-- who signs it: two buttons, not a switch (owner, Nov 1) -->
  <div class="seg wide who" role="radiogroup" aria-label={t('fc.anon')}>
    <button type="button" role="radio" aria-checked={!anon} class:on={!anon} onclick={() => { anon = false; haptic.select(); }}>{sign}</button>
    <button type="button" role="radio" aria-checked={anon} class:on={anon} onclick={() => { anon = true; haptic.select(); }}><VenetianMask size={15} />{t('fc.anon')}</button>
  </div>
  <p class="as">{anon ? t('fc.asAnon') : t('fc.as', { name: sign })}</p>
  {#snippet footer()}<Button kind="filled" size="l" full disabled={!ready} onclick={post}>{t('fc.post')}</Button>{/snippet}
</Sheet>

<style>
  /* the words: no box of their own inside the card, the card is the field */
  .text { display: block; width: 100%; min-height: 104px; padding: 0; border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.4 var(--font-text); letter-spacing: -0.012em; }
  .text::placeholder { color: var(--text-3); }
  .text:focus { outline: none; }
  .rules { margin-top: var(--s-3); padding-top: var(--s-3); border-top: 0.5px solid var(--separator); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .gap { height: var(--s-4); }
  .who { display: flex; width: 100%; }
  .who button { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 40px; font-size: var(--fs-body); }
  .as { margin: var(--s-2) var(--s-2) 0; font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
</style>
