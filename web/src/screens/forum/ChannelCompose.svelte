<script lang="ts">
  // A new post to the forum channel (the Forum tab's composer row): first whose name it goes out under (named or the
  // mask, picked beside my face, which turns into the mask; what that means, honestly, under it), then the words. The
  // rules are checked as I type (lib/forumRules: the server's own, mirrored), said at the spot and holding Publish; the
  // count shows only near the limit. Publish closes the sheet at
  // once and the post stands at the top of the feed, "checking" while the AI looks; refused, the sheet comes back with
  // the words and why, standing above them until I edit (a toast went before it could be read, owner Nov 2).
  import { untrack } from 'svelte';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import { api, ApiErr, type ChannelFeedPost } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { channel, loadChannel, touched } from '../../lib/state/channel.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { broken, type Rule } from '../../lib/forumRules';
  import { haptic } from '../../lib/tg';
  import { nowTs } from '../../lib/time';
  import { burst } from '../../ui/burst';
  import { grow } from '../../ui/grow';
  import Sheet from '../../ui/Sheet.svelte';
  import Card from '../../ui/Card.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Segmented from '../../ui/Segmented.svelte';

  let { overlay, draft }: { overlay: Overlay; draft?: { body: string; anon: boolean; why?: string } } = $props();
  let body = $state(untrack(() => draft?.body ?? '')), anon = $state(untrack(() => draft?.anon ?? false));
  const why = $derived(draft?.why && body === draft.body ? draft.why : null);  // gone once I change the words
  const MAX = 1000;
  const rule = $derived(broken(body));
  const ready = $derived(body.trim().length >= 2 && !rule);
  const HINT: Record<Rule, Key> = { link: 'fc.noLink', mention: 'fc.noMention', phone: 'fc.noPhone', signature: 'fc.signature' };
  // the bot's signature, as the server makes it (fchannel.signature): the real first name and the last initial, a nick or
  // not (owner, Nov 2: the nick rule; the app's feed shows the nick)
  const s = $derived(session.me?.student);
  const sign = $derived(s ? `${s.firstName} ${s.lastName ? [...s.lastName][0] : ''}`.trim() : session.me?.name ?? '');

  function reason(e: unknown): string {
    const why: Key = e instanceof ApiErr ? (e.code === 'rate_limited' ? 'fc.slow' : e.message === 'links' ? 'fc.links' : e.message === 'signature' ? 'fc.signature' : e.message === 'short' ? 'fc.short' : e.message === 'duplicate' ? 'fc.dup' : e.message === 'noise' ? 'fc.noise' : e.message === 'ad' ? 'fc.ad' : 'common.error') : 'common.error';
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
  {#if why}<div class="why"><Notice tone="danger" text={why} /></div>{/if}
  <!-- who signs it, first: my face (the mask once picked) beside two buttons, not a switch (owner, Nov 1); what it means under them -->
  <div class="who">
    {#key anon || !session.me}<span class="face">{#if anon || !session.me}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
    {:else}<Avatar person={session.me} size={36} tappable={false} />{/if}</span>{/key}
    <div class="pick"><Segmented items={[{ value: 'named', label: t('fc.named') }, { value: 'anon', label: t('fc.anon') }]} value={anon ? 'anon' : 'named'} label={t('fc.anon')}
      onchange={(v) => { anon = v === 'anon'; haptic.select(); }} /></div>
  </div>
  <p class="note">{anon ? t('fc.asAnon') : t('fc.as', { name: sign })}</p>
  <Card>
    <div class="col">
      <b class="ellipsis">{anon ? anonSign(body) : sign}</b>
      <textarea class="text" bind:value={body} maxlength={MAX} rows="3" placeholder={t('fc.ph')} aria-label={t('fc.ph')} aria-invalid={!!rule} use:grow={280}></textarea>
      <!-- the rule broken, at the spot (the server's words for it); the count once it's near the limit -->
      {#if rule || body.length > MAX - 100}<div class="foot">
        {#if rule}<span class="hint" role="status">{t(HINT[rule])}</span>{/if}
        {#if body.length > MAX - 100}<span class="count" class:full={body.length >= MAX}>{MAX - body.length}</span>{/if}
      </div>{/if}
    </div>
  </Card>
  <p class="note last">{t('fc.rules')}</p>
  {#snippet footer()}<Button kind="filled" size="l" full disabled={!ready} onclick={post}>{t('fc.post')}</Button>{/snippet}
</Sheet>

<style>
  /* my face (or the mask) beside the choice; the name it goes out under above the words (Threads) */
  .who { display: flex; gap: var(--s-3); align-items: center; padding: 0 var(--s-1); }
  .face { flex: none; display: flex; animation: swap 320ms var(--ease-bounce); }
  @keyframes swap { from { transform: scale(0.6) rotate(-12deg); opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .face { animation: none; } }
  .pick { flex: 1; min-width: 0; }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--fill-2); color: var(--text); }
  .col { display: flex; flex-direction: column; gap: 2px; }
  .col b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  /* the words: no box of their own, the card is the field */
  .text { display: block; width: 100%; min-height: 84px; padding: 0; border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.4 var(--font-text); letter-spacing: -0.012em; }
  .text::placeholder { color: var(--text-3); }
  .text:focus { outline: none; }
  .why { margin-bottom: var(--s-3); }
  .note { margin: var(--s-2) var(--s-4) var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .note.last { margin-bottom: 0; }
  .foot { display: flex; align-items: baseline; gap: var(--s-2); margin-top: var(--s-2); font: 500 var(--fs-sub)/1.3 var(--font-text); }
  .hint { flex: 1; color: var(--danger-text); }
  .count { margin-left: auto; color: var(--text-3); font-variant-numeric: tabular-nums; }
  .count.full { color: var(--warning-text); }
</style>
