<script lang="ts">
  // A new post to the forum channel (the Forum tab's composer row): whose name it goes out under (my face and signature,
  // or the mask), the words, the rules, named or Anonymous and what that means, honestly. Publish closes the sheet at
  // once and the post stands at the top of the feed, "checking" while the AI looks; refused, the sheet comes back with
  // the words and why, standing above them until I edit (a toast went before it could be read, owner Nov 2).
  import { untrack } from 'svelte';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import CircleAlert from '@lucide/svelte/icons/circle-alert';
  import { api, ApiErr, type ChannelFeedPost } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { channel, loadChannel, touched } from '../../lib/state/channel.svelte';
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
  import Avatar from '../../ui/Avatar.svelte';

  let { overlay, draft }: { overlay: Overlay; draft?: { body: string; anon: boolean; why?: string } } = $props();
  let body = $state(untrack(() => draft?.body ?? '')), anon = $state(untrack(() => draft?.anon ?? false));
  const why = $derived(draft?.why && body === draft.body ? draft.why : null);  // gone once I change the words
  const ready = $derived(body.trim().length >= 2);
  // the bot's signature, as the server makes it (fchannel.signature): the real first name and the last initial, a nick or
  // not (owner, Nov 2: the nick rule; the app's feed shows the nick)
  const s = $derived(session.me?.student);
  const sign = $derived(s ? `${s.firstName} ${s.lastName ? [...s.lastName][0] : ''}`.trim() : session.me?.name ?? '');

  function reason(e: unknown): string {
    const why: Key = e instanceof ApiErr ? (e.code === 'rate_limited' ? 'fc.slow' : e.message === 'links' ? 'fc.links' : e.message === 'signature' ? 'fc.signature' : e.message === 'short' ? 'fc.short' : e.message === 'duplicate' ? 'fc.dup' : e.message === 'noise' ? 'fc.noise' : 'common.error') : 'common.error';
    return t(why);
  }

  // as the channel signs an anonymous post (fchannel.anon_sign): "Anon" for any Cyrillic, else English
  const anonSign = (text: string) => (/[\u0400-\u04ff]/.test(text) ? '\u0410\u043d\u043e\u043d\u0438\u043c' : 'Anonymous');

  async function post() {
    if (!ready) return;
    const text = body.trim(), was = anon;
    const temp: ChannelFeedPost = { id: -Date.now(), body: text, status: 'held', at: nowTs(), msg: null, anon: was, sign: was ? anonSign(text) : sign, mine: true,
      person: !was && session.me ? { id: session.me.id, name: session.me.name, avatar: session.me.avatar, founder: false } : null, comments: 0, thread: null, faces: [], reactions: [], hot: false };
    channel.feed = [temp, ...(channel.feed ?? [])]; haptic.select(); close(overlay.id);
    try {
      const p = await api.newChannelPost(text, was);
      // a refresh may have brought the real one already (Channel's poll): then the stand-in just goes (no twin keys)
      const feed = channel.feed ?? []; touched();
      channel.feed = feed.some((x) => x.id === p.id) ? feed.filter((x) => x.id !== temp.id)
        : feed.map((x) => (x.id === temp.id ? { ...x, id: p.id, status: p.status, at: p.at } : x));
      haptic.ok();
      if (p.status === 'live') { burst(); say(t('fc.postedSay'), 'party_popper_3d'); setTimeout(loadChannel, 5000); } // the bot sends it within seconds: its link then
      else say(t('fc.heldSay'), 'thinking_face_3d');
    } catch (e) {
      channel.feed = (channel.feed ?? []).filter((x) => x.id !== temp.id);
      haptic.error(); sheets.channelPost({ body: text, anon: was, why: reason(e) });
    }
  }
</script>

<!-- the title is the capsule's, with the pen (a heading of its own said it twice) -->
<Sheet {overlay} icon={SquarePen} title={t('fc.new')}>
  {#if why}<p class="why" role="alert"><CircleAlert size={18} strokeWidth={2.2} />{why}</p>{/if}
  <Card>
    <div class="write">
      {#if anon || !session.me}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
      {:else}<Avatar person={session.me} size={36} tappable={false} />{/if}
      <div class="col">
        <b class="ellipsis">{anon ? anonSign(body) : sign}</b>
        <textarea class="text" bind:value={body} maxlength="1000" rows="3" placeholder={t('fc.ph')} aria-label={t('fc.ph')} use:grow={280}></textarea>
      </div>
    </div>
  </Card>
  <p class="note">{t('fc.rules')}</p>
  <!-- who signs it: two buttons, not a switch (owner, Nov 1); under them what that means -->
  <div class="seg wide who" role="radiogroup" aria-label={t('fc.anon')}>
    <button type="button" role="radio" aria-checked={!anon} class:on={!anon} onclick={() => { anon = false; haptic.select(); }}>{t('fc.named')}</button>
    <button type="button" role="radio" aria-checked={anon} class:on={anon} onclick={() => { anon = true; haptic.select(); }}><VenetianMask size={15} />{t('fc.anon')}</button>
  </div>
  <p class="note last">{anon ? t('fc.asAnon') : t('fc.as', { name: sign })}</p>
  {#snippet footer()}<Button kind="filled" size="l" full disabled={!ready} onclick={post}>{t('fc.post')}</Button>{/snippet}
</Sheet>

<style>
  /* my face (or the mask) and the name it goes out under, the words under the name (Threads) */
  .write { display: flex; gap: var(--s-3); align-items: flex-start; }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-2); }
  .col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .col b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  /* the words: no box of their own, the card is the field */
  .text { display: block; width: 100%; min-height: 84px; padding: 0; border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.4 var(--font-text); letter-spacing: -0.012em; }
  .text::placeholder { color: var(--text-3); }
  .text:focus { outline: none; }
  .why { display: flex; gap: var(--s-2); align-items: flex-start; margin: 0 0 var(--s-3); padding: var(--s-3); border-radius: var(--r-m);
    background: var(--danger-soft); color: var(--text); font: 500 var(--fs-sub)/1.35 var(--font-text); }
  .why :global(svg) { flex: none; margin-top: 1px; color: var(--danger); }
  .note { margin: var(--s-2) var(--s-2) var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .note.last { margin-bottom: 0; }
  .who { display: flex; width: 100%; }
  .who button { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 40px; font-size: var(--fs-body); }
</style>
