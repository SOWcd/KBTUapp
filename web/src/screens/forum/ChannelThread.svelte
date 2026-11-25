<script lang="ts">
  // A channel post's comments, written and read in the app (server fchannel.comment_*, thread): the words go to the bot,
  // which posts them under the post in the channel's discussion under my short name, after the same AI look and the same
  // moderators as an anonymous author's reply. Oldest first; mine say where they stand until they're out, each deletable.
  // Comments written in Telegram aren't here (the app never keeps other people's words): one quiet row opens them there.
  // My own anonymous post has no composer: I answer it as the mask (ChannelReply), a signed comment would pair us.
  import { untrack } from 'svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import { api, ApiErr, type ChannelComment, type Id } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { nickName } from '../../lib/i18n/nicks';
  import { broken, type Rule } from '../../lib/forumRules';
  import { haptic, openLink } from '../../lib/tg';
  import { ago, nowTs } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Composer from '../../ui/Composer.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';

  let { overlay, post }: { overlay: Overlay; post: { id: Id; body: string; mine: boolean; anon: boolean; link: string } } = $props();
  const pid = untrack(() => post.id);
  let items = $state<ChannelComment[] | null>(null);
  let draft = $state(''), sending = $state(false), why = $state<string | null>(null);
  const student = $derived(!!session.me?.student && !session.me.student.manual);
  const mayWrite = $derived(student && !(post.mine && post.anon));
  const rule = $derived(broken(draft));
  const HINT: Record<Rule, Key> = { link: 'fc.noLink', mention: 'fc.noMention', phone: 'fc.noPhone', signature: 'fc.signature' };

  // "goes out in a few seconds": looked at again until none of mine is on its way
  let again: ReturnType<typeof setTimeout> | undefined, closed = false;
  function load() {
    api.channelThread(pid).then((l) => {
      items = [...(items ?? []).filter((c) => c.id < 0), ...l];
      clearTimeout(again);
      if (closed) return; // an answer after the sheet closed: no new timer
      if (l.some((c) => c.mine && (c.state === 'soon' || c.state === 'checking'))) again = setTimeout(load, 12_000);
    }).catch(() => (items ??= []));
  }
  $effect(() => { untrack(load); return () => { closed = true; clearTimeout(again); }; });

  function reason(e: unknown): string {
    const k: Key = !(e instanceof ApiErr) ? 'common.error' : e.code === 'rate_limited' ? 'fct.slow'
      : e.message === 'links' ? 'fc.links' : e.message === 'signature' ? 'fc.signature' : 'common.error';
    return t(k);
  }

  async function send() {
    const text = draft.trim();
    if (text.length < 2 || rule || sending) return;
    const temp: ChannelComment = { id: -Date.now(), body: text, at: nowTs(), state: 'checking', mine: true, anon: false, nick: null, name: session.me?.name ?? null };
    items = [...(items ?? []), temp]; draft = ''; why = null; haptic.select();
    try {
      const r = await api.newChannelComment(pid, text);
      items = (items ?? []).map((c) => (c.id === temp.id ? { ...temp, id: r.id, state: r.state } : c));
      haptic.ok();
      if (r.state === 'held') say(t('fcr.heldSay'), 'thinking_face_3d');
      else if (!closed) { clearTimeout(again); again = setTimeout(load, 22_000); } // one timer, cleared as the sheet closes
    } catch (e) {
      items = (items ?? []).filter((c) => c.id !== temp.id);
      draft = text; why = reason(e); haptic.error();
    }
  }

  async function drop(c: ChannelComment) {
    if (!(await sheets.ask({ title: t('fcr.deleteAsk'), text: t('fct.deleteText'), ok: t('fc.delete'), cancel: t('common.cancel'), danger: true }))) return;
    const before = items;
    items = (items ?? []).filter((x) => x.id !== c.id); haptic.ok();
    try { await api.deleteChannelReply(c.id); } catch { items = before; haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} icon={MessageCircle} tall title={t('fct.title')}>
  <p class="post">{post.body}</p>
  {#if items === null}
    <Skeleton kind="rows" n={2} />
  {:else if !items.length}
    <EmptyState icon={MessageCircle} title={t('fct.empty')} />
  {:else}
    <div class="list">
      {#each items as c (c.id)}
        <div class="c">
          {#if c.anon}<span class="mask" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>
          {:else}<Avatar person={{ id: (c.name ?? '?').charCodeAt(0), name: c.name ?? '?' }} size={34} tappable={false} />{/if}
          <div class="cb">
            <span class="ch">
              <b class="ellipsis">{c.anon ? nickName(c.nick) ?? t('bd.asAnon') : c.name}</b><i>{ago(c.at)}</i>
              {#if c.mine && c.id > 0}<span class="more"><IconButton icon={Trash2} kind="plain" size="s" label={t('fc.delete')} onclick={() => drop(c)} /></span>{/if}
            </span>
            <p class="selectable">{c.body}</p>
            {#if c.mine && c.state !== 'sent'}<span class="st" class:warn={c.state === 'held' || c.state === 'maybe'}>{t(`fcr.st.${c.state}` as Key)}</span>{/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
  <div class="tg"><Button kind="plain" size="s" onclick={() => { haptic.tap(); openLink(post.link); }}>{#snippet icon()}<TelegramMark size={16} />{/snippet}{t('fct.tg')}</Button></div>

  {#snippet footer()}
    {#if mayWrite}
      <div class="compose">
        {#if why}<span class="hint" role="status">{why}</span>
        {:else if rule}<span class="hint" role="status">{t(HINT[rule])}</span>{/if}
        <Composer bind:value={draft} placeholder={t('fct.ph')} maxlength={1000} {sending} label={t('cm.send')} onsend={send} />
      </div>
    {:else if post.mine && post.anon}
      <p class="fs-sub dim off">{t('fct.own')}</p>
    {/if}
  {/snippet}
</Sheet>

<style>
  .post { margin: 0 var(--s-1) var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); white-space: pre-line;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .list { display: flex; flex-direction: column; gap: var(--s-4); padding-bottom: var(--s-2); }
  .c { display: flex; gap: 10px; align-items: flex-start; }
  .mask { flex: none; width: 34px; height: 34px; display: grid; place-items: center; border-radius: var(--r-full); background: var(--surface-3); color: var(--text); }
  .cb { flex: 1; min-width: 0; }
  .ch { display: flex; align-items: center; gap: 6px; min-width: 0; min-height: 26px; }
  .ch b { font: 600 var(--fs-body)/1.3 var(--font-text); min-width: 0; }
  .ch i { flex: none; font: 450 var(--fs-cap)/1 var(--font-text); font-style: normal; color: var(--text-3); }
  /* the 36 px button inside a 26 px line: its hit area reaches past it */
  .more { margin: -5px -8px -5px auto; flex: none; color: var(--text-3); --plain-ink: var(--text-3); }
  .cb p { margin-top: 3px; font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .st { display: block; margin-top: 2px; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .st.warn { color: var(--warning-text); }
  .tg { display: flex; justify-content: center; margin-top: var(--s-4); }
  .compose { display: flex; flex-direction: column; gap: var(--s-2); width: 100%; }
  .hint { font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--danger-text); }
  .off { width: 100%; padding: var(--s-3); text-align: center; }
</style>
