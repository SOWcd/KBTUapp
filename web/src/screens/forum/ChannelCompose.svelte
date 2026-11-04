<script lang="ts">
  // A new post to the forum channel (the Forum tab's composer row). Whose name it goes out under first (named or the
  // mask: two parts, not a switch, owner Nov 1), then one card that is the post as it will stand: the face and the
  // name it goes out under on top, the words under them (owner, Nov 4: the old sheet "looked shabby"). The rules are
  // checked as I type (lib/forumRules, the server's own), said at the spot, holding Publish; the count only near the
  // limit. Publish closes the sheet at once and the post stands at the top of the feed, "checking" while the AI looks.
  // Refused by the AI (no message in it, an ad): the sheet comes back as the verdict, at once: "Not published", the
  // words, Edit, and Send to a moderator (fchannel.appeal, three a day) usable right away; the AI's own reason, the
  // piece it stopped at marked and what to change come in when they're ready (/why, phase 2: nobody waits on it).
  // Held for a moderator: the feed shows the reason under my post (channel.why). A refusal by the rules (a link, the
  // pace) brings the editor back with the words and why above them until I edit.
  import { untrack } from 'svelte';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import ShieldAlert from '@lucide/svelte/icons/shield-alert';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import { api, ApiErr, type ChannelFeedPost, type ForumWhy, type Id } from '../../lib/api';
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
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import Marked from './Marked.svelte';

  type Refused = { post: Id; kind: 'noise' | 'ad'; appeal: boolean };
  type Draft = { body: string; anon: boolean; why?: string; refused?: Refused };
  let { overlay, draft }: { overlay: Overlay; draft?: Draft } = $props();
  let body = $state(untrack(() => draft?.body ?? '')), anon = $state(untrack(() => draft?.anon ?? false));
  let refused = $state<Refused | null>(untrack(() => draft?.refused ?? null));
  let ex = $state<ForumWhy | null>(null), asking = $state(false);
  const why = $derived(draft?.why && body === draft.body ? draft.why : null);  // gone once I change the words
  const MAX = 1000;
  const rule = $derived(broken(body));
  const ready = $derived(body.trim().length >= 2 && !rule);
  const HINT: Record<Rule, Key> = { link: 'fc.noLink', mention: 'fc.noMention', phone: 'fc.noPhone', signature: 'fc.signature' };
  // the bot's signature, as the server makes it (fchannel.signature): the real first name and the last initial, a nick or
  // not (owner, Nov 2: the nick rule; the app's feed shows the nick)
  const s = $derived(session.me?.student);
  const sign = $derived(s ? `${s.firstName} ${s.lastName ? [...s.lastName][0] : ''}`.trim() : session.me?.name ?? '');

  // the verdict's reason in the AI's words, asked once the verdict is on screen; none: the template stays
  $effect(() => {
    const r = untrack(() => refused);
    if (!r) return;
    asking = true;
    api.channelPostWhy(r.post, untrack(() => body)).then((x) => { ex = x.explain; }).catch(() => {}).finally(() => { asking = false; });
  });

  function reason(e: unknown): string {
    const why: Key = e instanceof ApiErr ? (e.code === 'rate_limited' ? 'fc.slow' : e.message === 'links' ? 'fc.links' : e.message === 'signature' ? 'fc.signature' : e.message === 'short' ? 'fc.short' : e.message === 'duplicate' ? 'fc.dup' : 'common.error') : 'common.error';
    return t(why);
  }

  // a stand-in on top of the feed while the server answers (a tap answers in the same frame)
  function stand(text: string, was: boolean, human = false): ChannelFeedPost {
    const temp: ChannelFeedPost = { id: -Date.now(), body: text, status: 'held', human, at: nowTs(), msg: null, anon: was, nick: null, sign: was ? t('fc.nickSoon') : sign, mine: true,
      person: !was && session.me ? { id: session.me.id, name: session.me.name, avatar: session.me.avatar, founder: false } : null, comments: 0, thread: null, faces: [], reactions: [], hot: false };
    channel.feed = [temp, ...(channel.feed ?? [])];
    return temp;
  }
  // the stand-in becomes the real one (or just goes, if a refresh brought the real one already: no twin keys)
  function land(temp: ChannelFeedPost, p: { id: Id; status: ChannelFeedPost['status']; at: number; nick: ChannelFeedPost['nick'] }, human = false) {
    const feed = channel.feed ?? []; touched();
    channel.feed = feed.some((x) => x.id === p.id) ? feed.filter((x) => x.id !== temp.id)
      : feed.map((x) => (x.id === temp.id ? { ...x, id: p.id, status: p.status, at: p.at, nick: p.nick, human } : x));
  }
  const unstand = (temp: ChannelFeedPost) => { channel.feed = (channel.feed ?? []).filter((x) => x.id !== temp.id); };

  async function post() {
    if (!ready) return;
    const text = body.trim(), was = anon;
    const temp = stand(text, was); haptic.select(); close(overlay.id);
    try {
      const p = await api.newChannelPost(text, was);
      land(temp, p, p.status === 'held' && !!p.ai);
      haptic.ok();
      if (p.status === 'live') { burst(); say(t('fc.postedSay'), 'party_popper_3d'); setTimeout(loadChannel, 5000); } // the bot sends it within seconds: its link then
      else {
        say(t('fc.heldSay'), 'thinking_face_3d');
        if (p.ai) api.channelPostWhy(p.id, text).then((x) => { if (x.explain) channel.why[p.id] = x.explain; }).catch(() => {});
      }
    } catch (e) {
      unstand(temp); haptic.error();
      const d = e instanceof ApiErr ? e.data : {};
      if (e instanceof ApiErr && (e.message === 'noise' || e.message === 'ad') && typeof d.post === 'number')
        sheets.channelPost({ body: text, anon: was, refused: { post: d.post, kind: e.message === 'ad' ? 'ad' : 'noise', appeal: d.appeal === true } });
      else sheets.channelPost({ body: text, anon: was, why: reason(e) });
    }
  }

  // the AI was wrong: a human decides (held, in the moderators' queue); the post stands in the feed "with a moderator"
  async function appeal() {
    const r = refused, text = body.trim(), was = anon;
    if (!r) return;
    const temp = stand(text, was, true); haptic.select(); close(overlay.id);
    try {
      const p = await api.appealChannelPost(r.post, text);
      land(temp, p, true); haptic.ok(); say(t('fc.appealedSay'), 'thinking_face_3d');
    } catch (e) {
      unstand(temp); haptic.error();
      const out = e instanceof ApiErr && e.code === 'rate_limited';
      say(t(out ? 'fc.appealsOut' : 'common.error'), 'pleading_face_3d');
      sheets.channelPost({ body: text, anon: was, refused: { ...r, appeal: !out && !(e instanceof ApiErr && e.code === 'not_found') } });
    }
  }

  function edit() { haptic.tap(); refused = null; }
</script>

<Sheet {overlay} icon={refused ? ShieldAlert : SquarePen} title={t(refused ? 'fc.refused' : 'fc.new')}>
  {#if refused}
    <!-- the verdict: at once, in plain words; the AI's own reason replaces the template once it comes -->
    <div class="verdict">
      <span class="seal" aria-hidden="true"><ShieldAlert size={22} strokeWidth={2} /></span>
      <h2>{t('fc.refused')}</h2>
      <p class="reason" aria-live="polite">{ex?.reason ?? t(refused.kind === 'ad' ? 'fc.ad' : 'fc.noise')}</p>
      {#if asking}<p class="wait">{t('fc.whyLoading')}</p>{/if}
    </div>
    <div class="card">
      <div class="from">
        {@render face()}
        <span class="who"><b class="ellipsis">{anon ? t('fc.nickSoon') : sign}</b><span class="sub">{t('fc.toChannel')}</span></span>
      </div>
      <p class="words"><Marked text={body} quote={ex?.quote} /></p>
      {#if ex?.fix}<p class="fix"><Lightbulb size={16} strokeWidth={2} aria-hidden="true" /><span>{ex.fix}</span></p>{/if}
    </div>
    {#if refused.appeal}<p class="note">{t('fc.appealNote')}</p>{/if}
  {:else}
    {#if why}<div class="why"><Notice tone="danger" text={why} /></div>{/if}
    <!-- whose name first; the card below is the post as it will stand -->
    <Segmented items={[{ value: 'named', label: t('fc.named') }, { value: 'anon', label: t('fc.anon') }]} value={anon ? 'anon' : 'named'} label={t('fc.anon')}
      onchange={(v) => { anon = v === 'anon'; haptic.select(); }} />
    <div class="card edit" class:bad={!!rule}>
      <div class="from">
        {@render face()}
        <span class="who"><b class="ellipsis">{anon ? t('fc.nickSoon') : sign}</b><span class="sub">{t('fc.toChannel')}</span></span>
      </div>
      <textarea class="text" bind:value={body} maxlength={MAX} rows="4" placeholder={t('fc.ph')} aria-label={t('fc.ph')} aria-invalid={!!rule} use:grow={300}></textarea>
      <!-- the rule broken, at the spot (the server's words for it); the count once it's near the limit -->
      {#if rule || body.length > MAX - 100}<div class="foot">
        {#if rule}<span class="hint" role="status">{t(HINT[rule])}</span>{/if}
        {#if body.length > MAX - 100}<span class="count" class:full={body.length >= MAX}>{MAX - body.length}</span>{/if}
      </div>{/if}
    </div>
    <p class="note">{anon ? t('fc.asAnon') : t('fc.rules')}</p>
  {/if}
  {#snippet footer()}
    {#if refused}
      <div class="two">
        {#if refused.appeal}<Button kind="secondary" size="l" full onclick={appeal}>{t('fc.appeal')}</Button>{/if}
        <Button kind="filled" size="l" full onclick={edit}>{t('fc.edit')}</Button>
      </div>
    {:else}<Button kind="filled" size="l" full disabled={!ready} onclick={post}>{t('fc.post')}</Button>{/if}
  {/snippet}
</Sheet>

{#snippet face()}
  {#key anon || !session.me}<span class="face">{#if anon || !session.me}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
  {:else}<Avatar person={session.me} size={36} tappable={false} />{/if}</span>{/key}
{/snippet}

<style>
  /* the post as it will stand: one card, the face and name on top, a hairline, the words; focus lifts it in the accent */
  .card { margin-top: var(--s-3); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card), inset 0 0 0 0.5px var(--line);
    transition: box-shadow var(--t-base) var(--ease); }
  .card.edit:focus-within { box-shadow: var(--shadow-card), inset 0 0 0 1px var(--accent), 0 0 0 4px var(--accent-soft); }
  .card.edit.bad:focus-within { box-shadow: var(--shadow-card), inset 0 0 0 1px var(--danger), 0 0 0 4px var(--danger-soft); }
  .from { position: relative; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); }
  .from::after { content: ''; position: absolute; left: var(--s-4); right: 0; bottom: 0; height: 0.5px; background: var(--separator); }
  .face { flex: none; display: flex; animation: swap 320ms var(--ease-bounce); }
  @keyframes swap { from { transform: scale(0.6) rotate(-12deg); opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .face { animation: none; } }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--fill-2); color: var(--text); }
  .who { min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .who b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); letter-spacing: -0.01em; }
  .sub { font: 450 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  /* the words: no box of their own, the card is the field */
  .text { display: block; width: 100%; min-height: 112px; padding: var(--s-3) var(--s-4) var(--s-4); border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.42 var(--font-text); letter-spacing: -0.012em; }
  .text::placeholder { color: var(--text-3); }
  .text:focus { outline: none; }
  .foot { display: flex; align-items: baseline; gap: var(--s-2); padding: 0 var(--s-4) var(--s-3); font: 500 var(--fs-sub)/1.3 var(--font-text); }
  .hint { flex: 1; color: var(--danger-text); }
  .count { margin-left: auto; color: var(--text-3); font-variant-numeric: tabular-nums; }
  .count.full { color: var(--warning-text); }
  .why { margin-bottom: var(--s-3); }
  .note { margin: var(--s-3) var(--s-4) 0; font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }

  /* the verdict: a seal, the word, the reason; calm, centred, no alarm red */
  .verdict { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); padding: var(--s-2) var(--s-4) var(--s-2); text-align: center; }
  .seal { width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; background: var(--warning-soft); color: var(--warning-text);
    animation: seal 520ms var(--ease-bounce) backwards; }
  @keyframes seal { from { transform: scale(0.5); opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .seal { animation: none; } }
  .verdict h2 { margin-top: var(--s-1); font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.02em; color: var(--text); }
  .reason { max-width: 34ch; font: 450 var(--fs-body)/1.42 var(--font-text); color: var(--text-2); animation: fade 300ms var(--ease); }
  @keyframes fade { from { opacity: 0; } }
  .wait { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.45; } }
  @media (prefers-reduced-motion: reduce) { .wait { animation: none; } }
  .words { padding: var(--s-3) var(--s-4) var(--s-4); font: 450 var(--fs-body)/1.47 var(--font-text); color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    max-height: 40vh; overflow: auto; }
  .fix { position: relative; display: flex; gap: var(--s-2); align-items: flex-start; padding: var(--s-3) var(--s-4); font: 500 var(--fs-sub)/1.4 var(--font-text); color: var(--text);
    animation: fade 300ms var(--ease); }
  .fix::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .fix :global(svg) { flex: none; margin-top: 1px; color: var(--warning-text); }
  .two { display: flex; flex-direction: column; gap: var(--s-2); }
</style>
