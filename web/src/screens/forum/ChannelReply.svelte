<script lang="ts">
  // A reply in my anonymous post's comments, sent by the bot so it doesn't carry my Telegram account (server
  // fchannel.reply_*). How it works, in three short steps with their icons (copy the comment's link in Telegram, come
  // back and Paste, write), shown in full until I once send a reply to a comment, then folded to one small line (owner,
  // Nov 4). Then one card in the order of the steps: the comment's link with a one-tap Paste (Telegram's clipboard where
  // it may read it, else the browser's; neither: pasted by hand), a hairline, the words under the mask. One honest line
  // about what can still give me away. Under it, my replies and where each stands, each deletable; one the AI held says
  // why in its words once they come (/why, to me alone). No comments are listed here: the app never keeps other
  // people's words (review). Sending answers at once: the reply stands at the top "checking".
  import { untrack } from 'svelte';
  import { slide } from 'svelte/transition';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Link2 from '@lucide/svelte/icons/link-2';
  import Copy from '@lucide/svelte/icons/copy';
  import ClipboardPaste from '@lucide/svelte/icons/clipboard-paste';
  import PenLine from '@lucide/svelte/icons/pen-line';
  import CircleHelp from '@lucide/svelte/icons/circle-help';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import { api, ApiErr, type ChannelReply, type ForumWhy, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { broken, type Rule } from '../../lib/forumRules';
  import { haptic, readClipboard } from '../../lib/tg';
  import { ago, nowTs } from '../../lib/time';
  import { grow } from '../../ui/grow';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Group from '../../ui/Group.svelte';
  import Marked from './Marked.svelte';

  let { overlay, post }: { overlay: Overlay; post: { id: Id; body: string } } = $props();
  const pid = untrack(() => post.id);
  let body = $state(''), link = $state(''), why = $state<string | null>(null);
  let mine = $state<ChannelReply[] | null>(null);
  const said = $state<Record<number, ForumWhy>>({});  // the AI's reasons for my held replies, this visit
  // the post's rules as I type (lib/forumRules), said at the spot as in ChannelCompose
  const rule = $derived(broken(body));
  const ready = $derived(body.trim().length >= 2 && !rule);
  const HINT: Record<Rule, Key> = { link: 'fc.noLink', mention: 'fc.noMention', phone: 'fc.noPhone', signature: 'fc.signature' };
  const SIGN = '\u{1F3AD} \u0410\u0432\u0442\u043e\u0440 \u043f\u043e\u0441\u0442\u0430'; // the bot's mark (server texts.FCH_REPLY_SIGN)
  // a comment link as Telegram copies it (server COMMENT_LINK, loosely: the server checks it for real)
  const LINK = /(?:https?:\/\/)?(?:t|telegram)\.me\/\S+comment=\d+\S*/i;

  // the steps, until I once answered a comment: this browser remembers (a convenience: lost storage shows them again)
  const HOWTO = 'kb-fcr-howto';
  let learned = $state(untrack(() => { try { return localStorage.getItem(HOWTO) === '1'; } catch { return false; } }));
  let howOpen = $state(false);
  const steps = $derived(!learned || howOpen);
  function learn() { learned = true; try { localStorage.setItem(HOWTO, '1'); } catch { /* private mode: the steps stay */ } }
  const STEPS = [{ icon: Copy, key: 'fcr.step1' }, { icon: ClipboardPaste, key: 'fcr.step2' }, { icon: PenLine, key: 'fcr.step3' }] as const;

  // "goes out in a few seconds": looked at again once that's surely over
  let again: ReturnType<typeof setTimeout> | undefined;
  function load() {
    api.channelReplies(pid).then((l) => {
      mine = [...(mine ?? []).filter((r) => r.id < 0), ...l];
      if (l.some((r) => r.comment != null)) learn();
      clearTimeout(again);
      if (l.some((r) => r.state === 'soon' || r.state === 'checking')) again = setTimeout(load, 12_000);
    }).catch(() => (mine ??= []));
  }
  $effect(() => { untrack(load); return () => clearTimeout(again); });

  async function paste() {
    haptic.tap();
    const got = await readClipboard();
    const m = got?.match(LINK)?.[0];
    if (m) { link = m; haptic.ok(); }
    else { haptic.error(); say(t(got ? 'fcr.pasteBad' : 'fcr.pasteNo'), 'pleading_face_3d'); }
  }

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
      if (to) learn();
      if (r.state === 'held') {
        say(t('fcr.heldSay'), 'thinking_face_3d');
        if (r.ai) api.channelReplyWhy(r.id).then((x) => { if (x.explain) said[r.id] = x.explain; }).catch(() => {});
      } else setTimeout(load, 22_000);
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
  <!-- how: three steps in full until I've answered a comment once; then one small line that opens them -->
  {#if steps}
    <ol class="steps" transition:slide={{ duration: 260 }}>
      {#each STEPS as s, i (s.key)}<li><span class="si" aria-hidden="true"><s.icon size={16} strokeWidth={2} /></span><span class="sn">{i + 1}</span><span>{t(s.key)}</span></li>{/each}
    </ol>
  {:else}
    <button class="how" onclick={() => { haptic.tap(); howOpen = true; }}><CircleHelp size={15} strokeWidth={2} aria-hidden="true" />{t('fcr.how')}</button>
  {/if}
  {#if why}<div class="why"><Notice tone="danger" text={why} /></div>{/if}
  <div class="card">
    <!-- the comment's link, with a one-tap Paste -->
    <div class="link">
      <span class="li" aria-hidden="true"><Link2 size={17} strokeWidth={2} /></span>
      <input bind:value={link} inputmode="url" autocapitalize="none" autocomplete="off" spellcheck="false" aria-label={t('fcr.link')} placeholder={t('fcr.link')} />
      <Button kind="tinted" size="s" onclick={paste}>{#snippet icon()}<ClipboardPaste size={15} strokeWidth={2} />{/snippet}{t('fcr.paste')}</Button>
    </div>
    <div class="write">
      <span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
      <div class="col">
        <b class="ellipsis">{SIGN}</b>
        <textarea class="text" bind:value={body} maxlength="1000" rows="3" placeholder={t('fcr.ph')} aria-label={t('fcr.ph')} aria-invalid={!!rule} use:grow={240}></textarea>
        {#if rule}<span class="hint" role="status">{t(HINT[rule])}</span>{/if}
      </div>
    </div>
  </div>
  <p class="note">{t('fcr.rules')}</p>
  <p class="note warn">{t('fcr.warn')}</p>

  {#if mine?.length}
    <!-- my replies and where each stands: content rows in a Group (AdminForum's grammar), the bin at the end -->
    <div class="mine">
      <Group caption={t('fcr.mine')}>
        {#each mine as r (r.id)}
          {@const w = r.state === 'held' ? said[r.id] : undefined}
          <div class="row">
            <div class="main">
              <p class="rb"><Marked text={r.body || '—'} quote={w?.quote} /></p>
              <span class="meta">{t(r.comment == null ? 'fcr.toThread' : 'fcr.toComment')} · <i class={tone(r)}>{t(`fcr.st.${r.state}` as Key)}</i> · {ago(r.at)}</span>
              {#if w}<p class="said">{w.reason}</p>{#if w.fix}<p class="said fix"><Lightbulb size={14} strokeWidth={2} aria-hidden="true" /><span>{w.fix}</span></p>{/if}{/if}
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
  /* the steps: one line each, the icon in a soft circle, the number quiet */
  .steps { display: flex; flex-direction: column; gap: var(--s-2); margin: 0 0 var(--s-3); padding: var(--s-3) var(--s-4); border-radius: var(--r-l);
    background: var(--accent-soft); list-style: none; }
  .steps li { display: flex; align-items: center; gap: var(--s-2); font: 500 var(--fs-sub)/1.35 var(--font-text); color: var(--text); }
  .si { flex: none; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-solid); color: var(--accent-text); }
  .sn { flex: none; width: 1ch; font-weight: 700; color: var(--accent-text); font-variant-numeric: tabular-nums; }
  .how { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; margin: 0 var(--s-4) var(--s-2); color: var(--accent-text);
    font: 500 var(--fs-sub)/1.2 var(--font-text); }
  .how:active { opacity: 0.6; }
  /* one card: the link (with Paste), a hairline, the words under the mask; focus lifts it in the accent */
  .card { border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card), inset 0 0 0 0.5px var(--line); transition: box-shadow var(--t-base) var(--ease); }
  .card:focus-within { box-shadow: var(--shadow-card), inset 0 0 0 1px var(--accent), 0 0 0 4px var(--accent-soft); }
  .link { position: relative; display: flex; align-items: center; gap: var(--s-2); padding: var(--s-2) var(--s-2) var(--s-2) var(--s-4); color: var(--text-3); }
  .link::after { content: ''; position: absolute; bottom: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .li { flex: none; width: 36px; display: grid; place-items: center; }
  .link input { flex: 1; min-width: 0; height: 36px; padding: 0; border: 0; background: none; color: var(--text); font: 450 var(--fs-sub)/1.3 var(--font-text); text-overflow: ellipsis; }
  .write { display: flex; gap: var(--s-3); align-items: flex-start; padding: var(--s-3) var(--s-4) var(--s-4); }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--fill-2); color: var(--text); }
  .col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .col b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  .text { display: block; width: 100%; min-height: 64px; padding: 0; border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.4 var(--font-text); letter-spacing: -0.012em; }
  .text::placeholder, .link input::placeholder { color: var(--text-3); }
  .text:focus, .link input:focus { outline: none; }
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
  .said { margin-top: var(--s-1); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-2); }
  .said.fix { display: flex; gap: 6px; color: var(--text); }
  .said.fix :global(svg) { flex: none; margin-top: 2px; color: var(--warning-text); }
  .row > :global(.ib) { margin: -4px 0; }
</style>
