<script lang="ts">
  // A forum thread (server logic/threads.py): the whole text, who's in on a gathering one (the author sees them with a
  // way to write), the replies oldest first, a reply of mine at the bottom, anonymous or not. An anonymous writer is
  // "Author" (the thread's own) or "Anonymous N", the same number all through the thread. ⋯ reports someone else's
  // words, deletes my own; the admin alone can reveal an anonymous writer (the server logs it).
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import SendHorizontal from '@lucide/svelte/icons/send-horizontal';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import { api, ApiErr, type Joiner, type PersonRef, type ThreadFull, type ThreadReply } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { putThread } from '../../lib/state/board.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago, dayMonth } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { gathers } from '../../lib/forum';
  import { grow } from '../../ui/grow';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import ThreadHead from './ThreadHead.svelte';
  import TopicTag from './TopicTag.svelte';

  let { overlay, id }: { overlay: Overlay; id: number } = $props();
  let th = $state<ThreadFull | null>(null);
  let gone = $state(false);
  let joiners = $state<Joiner[] | null>(null);
  let draft = $state(''), anon = $state(false), sending = $state(false);
  let menu = $state<string | null>(null); // 't' the thread's, 'r<id>' a reply's
  let revealed = $state<Record<string, PersonRef>>({});
  // the app's owner alone (the founder admin), as the anonymous switch promises
  const owner = $derived(session.me?.role === 'admin' && !!session.me?.founder);
  const me = $derived(session.me);

  const load = () => api.thread(id).then((x) => {
    if (!th) anon = x.mine && x.anon; // once: an anonymous author stays anonymous in their replies; a switch flipped by hand stays
    th = x;
    if (x.mine && gathers(x.topic) && x.joins) api.threadJoiners(id).then((l) => (joiners = l)).catch(() => {});
  }).catch(() => (gone = true));
  $effect(() => { void load(); });

  const fail = (e: unknown) => {
    haptic.error();
    say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'bd.slow' : e instanceof ApiErr && e.code === 'not_found' ? 'bd.gone' : 'common.error'), 'pleading_face_3d');
  };
  async function send() {
    const body = draft.trim();
    if (!th || !body || sending) return;
    sending = true;
    try {
      const x = await api.replyThread(id, body, anon);
      const mine = x.thread.filter((r) => r.mine).at(-1);
      th = x; draft = ''; putThread(id, x); haptic.ok();
      if (mine?.status === 'held') say(t('bd.replyHeld'), 'thinking_face_3d');
    } catch (e) { fail(e); } finally { sending = false; }
  }
  const key = (ev: KeyboardEvent) => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); void send(); } };

  async function join() {
    if (!th) return;
    const on = !th.joined;
    haptic.select();
    try { th = { ...th, ...(await api.joinThread(id, on)) }; putThread(id, th); if (on) say(t('bd.inSay'), 'raising_hands_3d_default'); }
    catch (e) { fail(e); }
  }
  async function removeThread() {
    menu = null;
    if (!(await sheets.ask({ title: t('bd.deleteAsk'), text: t('bd.deleteText'), ok: t('bd.delete'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.deleteThread(id); putThread(id, null); haptic.ok(); say(t('bd.deleted'), 'waving_hand_3d_default'); close(overlay.id); } catch (e) { fail(e); }
  }
  async function removeReply(r: ThreadReply) {
    menu = null;
    try { await api.deleteReply(r.id); th = th && { ...th, thread: th.thread.filter((x) => x.id !== r.id), replies: th.replies - (r.status === 'held' ? 0 : 1) }; if (th) putThread(id, th); haptic.ok(); }
    catch (e) { fail(e); }
  }
  async function reveal(kind: 'thread' | 'reply', xid: number) {
    menu = null;
    if (!(await sheets.ask({ title: t('bd.revealAsk'), text: t('bd.revealText'), ok: t('bd.reveal'), cancel: t('common.cancel') }))) return;
    try { revealed = { ...revealed, [`${kind}${xid}`]: await api.revealAnon(kind, xid) }; haptic.ok(); } catch (e) { fail(e); }
  }
  // a named writer by name (the author's tag beside); "Author" is the anonymous author only
  const replyName = (r: ThreadReply) => r.person && !r.anon ? r.person.name : r.op ? t('bd.author') : t('bd.anonN', { n: r.n ?? 0 });
</script>

<Sheet {overlay} tall title={t('page.forum')}>
  {#if gone}
    <p class="empty">{t('bd.gone')}</p>
  {:else if !th}
    <div class="wait" aria-hidden="true"><span class="tall"></span><span></span><span></span></div>
  {:else}
    <div class="top">
      <div class="head"><ThreadHead {th} tappable /></div>
      <TopicTag topic={th.topic} />
      <button class="more" onclick={() => (menu = menu === 't' ? null : 't')} aria-label={t('common.more')} aria-expanded={menu === 't'}><Ellipsis size={18} /></button>
    </div>
    {#if menu === 't'}
      <div class="acts">
        {#if th.mine}<button class="danger" onclick={removeThread}>{t('bd.delete')}</button>
        {:else}<button onclick={() => { menu = null; sheets.report('thread', id, th!.body.slice(0, 60)); }}>{t('cm.report')}</button>{/if}
        {#if owner && th.anon && !revealed[`thread${id}`]}<button onclick={() => reveal('thread', id)}>{t('bd.reveal')}</button>{/if}
      </div>
    {/if}
    {#if revealed[`thread${id}`]}<p class="who-was">{t('bd.wrote', { name: revealed[`thread${id}`].name })}</p>{/if}
    <p class="body selectable">{th.body}</p>
    <p class="t-foot life">{th.status === 'held' ? t('bd.heldLong') : t('bd.until', { date: dayMonth(th.expiresAt) })}</p>

    {#if gathers(th.topic)}
      <section class="gather surface">
        <div class="gh">
          {#if th.joiners?.length}<span class="faces">{#each th.joiners as p (p.id)}<Avatar person={p} size={28} />{/each}</span>{/if}
          <b>{t(th.mine ? 'bd.inCount' : 'bd.inOthers', { n: th.joins ?? 0 })}</b>
          {#if !th.mine}<button class="in-btn" class:on={th.joined} aria-pressed={th.joined} onclick={join}>{th.joined ? t('bd.inOn') : t('bd.inOff')}</button>{/if}
        </div>
        {#if th.mine && joiners?.length}
          <div class="jl">
            {#each joiners as p (p.id)}
              <div class="jr"><Avatar person={p} size={32} /><b class="ellipsis">{p.name}</b>
                {#if p.telegram}<button class="tg" onclick={() => openLink(p.telegram!)}>{t('bd.writeTg')}</button>{/if}</div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    <h3 class="t-cap cap">{th.replies ? t('bd.replies', { n: th.replies }) : t('bd.noReplies')}</h3>
    <div class="list">
      {#each th.thread as r (r.id)}
        <div class="r" class:held={r.status === 'held'}>
          {#if r.person && !r.anon}<Avatar person={r.person} size={32} />{:else}<span class="mask" aria-hidden="true"><VenetianMask size={17} /></span>{/if}
          <div class="rb">
            <span class="rh"><b class="ellipsis">{replyName(r)}</b>{#if r.op}<span class="tag">{t('bd.authorTag')}</span>{/if}<i>{ago(r.at)}</i>
              <button class="more sm" onclick={() => (menu = menu === `r${r.id}` ? null : `r${r.id}`)} aria-label={t('common.more')}><Ellipsis size={16} /></button></span>
            {#if revealed[`reply${r.id}`]}<span class="who-was">{t('bd.wrote', { name: revealed[`reply${r.id}`].name })}</span>{/if}
            <p class="selectable">{r.body}</p>
            {#if r.status === 'held'}<span class="t-foot">{t('bd.replyHeld')}</span>{/if}
            {#if menu === `r${r.id}`}
              <div class="acts">
                {#if r.mine}<button class="danger" onclick={() => removeReply(r)}>{t('cm.delete')}</button>
                {:else}<button onclick={() => { menu = null; sheets.report('reply', r.id, r.body.slice(0, 60)); }}>{t('cm.report')}</button>{/if}
                {#if owner && r.anon && !revealed[`reply${r.id}`]}<button onclick={() => reveal('reply', r.id)}>{t('bd.reveal')}</button>{/if}
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}

  {#snippet footer()}
    {#if th && th.status === 'live'}
      <!-- who I answer as, Telegram's "send as" way: my face, or the mask, beside the field -->
      <div class="row">
        <button class="as" class:on={anon} aria-pressed={anon} aria-label={anon ? t('bd.asAnon') : t('bd.asMe')} onclick={() => { anon = !anon; haptic.select(); }}>
          {#if anon || !me}<VenetianMask size={20} />{:else}<Avatar person={{ id: me.id, name: me.name, avatar: me.avatar }} size={36} tappable={false} />{/if}
        </button>
        <textarea bind:value={draft} rows="1" maxlength="500" placeholder={t(anon ? 'bd.anonPh' : 'bd.replyPh')} use:grow={132} enterkeyhint="send" onkeydown={key}></textarea>
        <button class="send" disabled={!draft.trim() || sending} onclick={send} aria-label={t('cm.send')}><SendHorizontal size={20} /></button>
      </div>
    {/if}
  {/snippet}
</Sheet>

<style>
  .empty { padding: 28px 12px; text-align: center; color: var(--text-2); font: 500 15px/1.45 var(--font-text); }
  .top { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
  .head { flex: 1; min-width: 0; }
  .more { flex: none; width: 34px; height: 30px; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: var(--text-3); }
  .more:active { background: var(--surface-2); }
  .more.sm { width: 30px; height: 26px; margin-left: auto; }
  .body { margin-top: 14px; font: 470 18px/1.45 var(--font-text); letter-spacing: -0.005em; white-space: pre-wrap; overflow-wrap: anywhere; }
  .life { margin-top: 8px; }
  .who-was { display: inline-block; margin-top: 6px; padding: 4px 9px; border-radius: var(--r-full); background: var(--danger-soft); color: var(--danger-text); font: 650 12px/1.2 var(--font-text); }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; animation: c-in 220ms ease-out backwards; }
  .acts button { height: 32px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); font: 620 13px/1 var(--font-text); color: var(--text); }
  .acts .danger { color: var(--danger-text); background: var(--danger-soft); }
  .gather { margin-top: 14px; padding: 12px 14px; border-radius: var(--r-l); display: flex; flex-direction: column; gap: 10px; }
  .gh { display: flex; align-items: center; gap: 10px; }
  .gh b { flex: 1; font: 650 14.5px/1.2 var(--font-text); }
  .faces { display: inline-flex; }
  .faces > :global(*) + :global(*) { margin-left: -8px; }
  .in-btn { flex: none; height: 36px; padding: 0 16px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 14px/1 var(--font-text);
    transition: transform var(--t-fast) var(--ease), background-color var(--t-base) var(--ease); }
  .in-btn:active { transform: scale(0.93); }
  .in-btn.on { background: var(--accent); color: #fff; }
  .jl { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--line); padding-top: 10px; }
  .jr { display: flex; align-items: center; gap: 10px; }
  .jr b { flex: 1; min-width: 0; font: 600 14px/1.2 var(--font-text); }
  .tg { flex: none; height: 30px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); color: var(--accent-text); font: 650 13px/1 var(--font-text); }
  .cap { margin: 22px 2px 2px; }
  .list { display: flex; flex-direction: column; padding-bottom: 8px; }
  .list > .r { padding: 12px 0; }
  .list > .r + .r { border-top: 1px solid var(--line); }
  .r { display: flex; gap: 10px; align-items: flex-start; animation: c-in 320ms cubic-bezier(.2, .9, .25, 1) backwards; }
  .r.held { opacity: 0.65; }
  @keyframes c-in { from { opacity: 0; transform: translateY(6px); } }
  .mask { flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-2); }
  .rb { flex: 1; min-width: 0; }
  .rh { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .rh b { font: 650 14px/1.3 var(--font-text); min-width: 0; }
  .rh i { flex: none; font: 500 12.5px/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .tag { flex: none; padding: 3px 7px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 700 10.5px/1 var(--font-text); letter-spacing: 0.04em; text-transform: uppercase; }
  .rb p { margin-top: 3px; font: 450 15px/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .row { display: flex; align-items: flex-end; gap: 8px; width: 100%; }
  .as { flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-2);
    transition: transform var(--t-fast) var(--ease), background-color var(--t-base) var(--ease); }
  .as:active { transform: scale(0.92); }
  .as.on { background: var(--accent-soft); color: var(--accent-text); box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 55%, transparent); }
  .row textarea { flex: 1; min-width: 0; min-height: 44px; padding: 11px 14px; border-radius: 22px; resize: none; background: var(--surface-2); color: var(--text);
    font: 450 16px/1.4 var(--font-text); }
  .row textarea::placeholder { color: var(--text-3); }
  .send { flex: none; width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--accent); color: #fff;
    transition: opacity var(--t-fast), transform var(--t-fast); }
  .send:disabled { opacity: 0.35; }
  .send:not(:disabled):active { transform: scale(0.92); }
  .wait { display: flex; flex-direction: column; gap: 14px; margin-top: 8px; }
  .wait span { height: 54px; border-radius: var(--r-m); background: var(--surface-2); animation: pulse 1.1s ease-in-out infinite; }
  .wait .tall { height: 120px; }
  @keyframes pulse { 50% { opacity: 0.5; } }
</style>
