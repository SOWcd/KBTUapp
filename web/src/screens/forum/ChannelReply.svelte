<script lang="ts">
  // A reply in my anonymous post's comments, sent by the bot so it doesn't carry my Telegram account (server
  // fchannel.reply_*). ChannelCompose's language: the mask and the mark it goes out under, the words, the rules; then
  // the comment's link (optional: empty, the reply goes to the discussion) and one honest line about what can still
  // give me away. Under it, my replies and where each stands, each deletable. No comments are listed here: the app
  // never keeps other people's words (review). Sending answers at once: the reply stands at the top "checking".
  import { untrack } from 'svelte';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Link2 from '@lucide/svelte/icons/link-2';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import { api, ApiErr, type ChannelReply, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { broken, type Rule } from '../../lib/forumRules';
  import { haptic } from '../../lib/tg';
  import { ago, nowTs } from '../../lib/time';
  import { grow } from '../../ui/grow';
  import Sheet from '../../ui/Sheet.svelte';
  import Card from '../../ui/Card.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Group from '../../ui/Group.svelte';

  let { overlay, post }: { overlay: Overlay; post: { id: Id; body: string } } = $props();
  const pid = untrack(() => post.id);
  let body = $state(''), link = $state(''), why = $state<string | null>(null);
  let mine = $state<ChannelReply[] | null>(null);
  // the post's rules as I type (lib/forumRules), said at the spot as in ChannelCompose
  const rule = $derived(broken(body));
  const ready = $derived(body.trim().length >= 2 && !rule);
  const HINT: Record<Rule, Key> = { link: 'fc.noLink', mention: 'fc.noMention', phone: 'fc.noPhone', signature: 'fc.signature' };
  const SIGN = '\u{1F3AD} \u0410\u0432\u0442\u043e\u0440 \u043f\u043e\u0441\u0442\u0430'; // the bot's mark (server texts.FCH_REPLY_SIGN)

  // "goes out in a few seconds": looked at again once that's surely over
  let again: ReturnType<typeof setTimeout> | undefined;
  function load() {
    api.channelReplies(pid).then((l) => {
      mine = [...(mine ?? []).filter((r) => r.id < 0), ...l];
      clearTimeout(again);
      if (l.some((r) => r.state === 'soon' || r.state === 'checking')) again = setTimeout(load, 12_000);
    }).catch(() => (mine ??= []));
  }
  $effect(() => { untrack(load); return () => clearTimeout(again); });

  function reason(e: unknown): string {
    const k: Key = !(e instanceof ApiErr) ? 'common.error' : e.code === 'rate_limited' ? 'fcr.slow' : e.message === 'comment' ? 'fcr.badLink'
      : e.message === 'links' ? 'fc.links' : e.message === 'signature' ? 'fc.signature' : 'common.error';
    return t(k);
  }

  async function send() {
    if (!ready) return;
    const text = body.trim(), to = link.trim();
    const temp: ChannelReply = { id: -Date.now(), body: text, comment: to ? 0 : null, state: 'checking', at: nowTs() };
    mine = [temp, ...(mine ?? [])]; body = ''; link = ''; why = null; haptic.select();
    try {
      const r = await api.newChannelReply(pid, text, to);
      mine = (mine ?? []).map((x) => (x.id === temp.id ? r : x));
      haptic.ok();
      if (r.state === 'held') say(t('fcr.heldSay'), 'thinking_face_3d');
      else setTimeout(load, 22_000);
    } catch (e) {
      mine = (mine ?? []).filter((x) => x.id !== temp.id);
      body = text; link = to; why = reason(e); haptic.error();
    }
  }

  async function drop(r: ChannelReply) {
    if (!(await sheets.ask({ title: t('fcr.deleteAsk'), text: t('fcr.deleteText'), ok: t('fc.delete'), cancel: t('common.cancel'), danger: true }))) return;
    const before = mine;
    mine = (mine ?? []).filter((x) => x.id !== r.id); haptic.ok();
    try { await api.deleteChannelReply(r.id); } catch { mine = before; haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }

  const tone = (r: ChannelReply) => r.state === 'held' || r.state === 'maybe' ? 'warning' : r.state === 'sent' ? 'accent' : 'quiet';
</script>

<Sheet {overlay} icon={VenetianMask} title={t('fcr.entry')}>
  <!-- what I'm answering under: my post, quietly -->
  <p class="post">{post.body}</p>
  {#if why}<div class="why"><Notice tone="danger" text={why} /></div>{/if}
  <Card>
    <div class="write">
      <span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
      <div class="col">
        <b class="ellipsis">{SIGN}</b>
        <textarea class="text" bind:value={body} maxlength="1000" rows="3" placeholder={t('fcr.ph')} aria-label={t('fcr.ph')} aria-invalid={!!rule} use:grow={240}></textarea>
        {#if rule}<span class="hint" role="status">{t(HINT[rule])}</span>{/if}
      </div>
    </div>
    <label class="link">
      <Link2 size={17} strokeWidth={2} aria-hidden="true" />
      <input bind:value={link} inputmode="url" autocapitalize="none" autocomplete="off" spellcheck="false" aria-label={t('fcr.link')} placeholder={t('fcr.link')} />
    </label>
  </Card>
  <p class="note">{t('fcr.rules')}</p>
  <p class="note warn">{t('fcr.warn')}</p>

  {#if mine?.length}
    <!-- my replies and where each stands: content rows in a Group (AdminForum's grammar), the bin at the end -->
    <div class="mine">
      <Group caption={t('fcr.mine')}>
        {#each mine as r (r.id)}
          <div class="row">
            <div class="main">
              <p class="rb">{r.body || '—'}</p>
              <span class="meta">{t(r.comment == null ? 'fcr.toThread' : 'fcr.toComment')} · <i class={tone(r)}>{t(`fcr.st.${r.state}` as Key)}</i> · {ago(r.at)}</span>
            </div>
            {#if r.id > 0 && r.state !== 'missing'}<IconButton kind="plain" size="s" icon={Trash2} label={t('fc.delete')} onclick={() => drop(r)} />{/if}
          </div>
        {/each}
      </Group>
    </div>
  {/if}
  {#snippet footer()}<Button kind="filled" size="l" full disabled={!ready} onclick={send}>{t('fcr.send')}</Button>{/snippet}
</Sheet>

<style>
  .post { margin: 0 var(--s-4) var(--s-3); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); white-space: pre-line;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .write { display: flex; gap: var(--s-3); align-items: flex-start; }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--fill-2); color: var(--text); }
  .col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .col b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  .text { display: block; width: 100%; min-height: 64px; padding: 0; border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.4 var(--font-text); letter-spacing: -0.012em; }
  .text::placeholder, .link input::placeholder { color: var(--text-3); }
  .text:focus, .link input:focus { outline: none; }
  /* the comment's link: one quiet line under the words, a hairline above it */
  .link { position: relative; display: flex; align-items: center; gap: var(--s-2); margin-top: var(--s-3); padding-top: var(--s-3); color: var(--text-3); }
  .link::before { content: ''; position: absolute; top: 0; left: calc(36px + var(--s-3)); right: 0; height: 0.5px; background: var(--separator); }
  .link :global(svg) { flex: none; width: 36px; }
  .link input { flex: 1; min-width: 0; height: 28px; padding: 0; border: 0; background: none; color: var(--text); font: 450 var(--fs-sub)/1.3 var(--font-text); text-overflow: ellipsis; }
  .why { margin-bottom: var(--s-3); }
  .hint { margin-top: var(--s-2); font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--danger-text); }
  .note { margin: var(--s-2) var(--s-4) 0; font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .note.warn { color: var(--warning-text); }
  .mine { margin-top: var(--gap-group); }
  .row { position: relative; display: flex; align-items: flex-start; gap: var(--s-2); padding: var(--s-3) var(--s-2) var(--s-3) var(--s-4); }
  .row + .row::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .main { flex: 1; min-width: 0; }
  .rb { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .meta { display: block; margin-top: 2px; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .meta i { font-style: normal; }
  .meta .accent { color: var(--accent-text); }
  .meta .warning { color: var(--warning-text); }
  .row > :global(.ib) { margin: -4px 0; }
</style>
