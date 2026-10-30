<script lang="ts">
  // The student forum, the bar's own tab (Oct 30, the owner: "one place instead of the chats": a charger to borrow,
  // "who's going to KFC", a question, "two people needed now", anything, anonymously too). The topics on top, the
  // threads newest-bumped first, a tap opens one (ThreadSheet), "Write" makes one (NewThread). A gathering thread
  // shows who's in and takes "I'm in" right from the card. Moderators see what the AI held, first.
  import { untrack } from 'svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import PenLine from '@lucide/svelte/icons/pen-line';
  import { api, type Thread, type ThreadMod } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import { board, loadBoard, moreBoard, putThread } from '../../lib/state/board.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { ago } from '../../lib/time';
  import { TOPICS, TOPIC_ICON, TOPIC_TINT, gathers } from '../../lib/forum';
  import Avatar from '../../ui/Avatar.svelte';
  import { fitTitle, largeTitle } from '../../ui/title';
  import ThreadHead from './ThreadHead.svelte';
  import TopicTag from './TopicTag.svelte';
  import Emoji from '../../ui/Emoji.svelte';

  const student = $derived(!!session.me?.student);
  const me = $derived(session.me);
  const staff = $derived(session.me?.role === 'admin' || session.me?.role === 'moderator');
  const here = $derived(ui.tab === 'forum');
  // in view: a quiet refresh (the app asked for it at the start already); a new topic: its own list
  $effect(() => { if (here && student) untrack(() => void loadBoard()); });
  let mod = $state<ThreadMod | null>(null);
  const loadMod = () => api.threadMod().then((m) => (mod = m)).catch(() => {});
  $effect(() => { if (here && staff) untrack(loadMod); });

  function pick(topic: typeof board.topic) {
    if (board.topic === topic) return;
    haptic.select();
    board.topic = topic; board.list = null;
    void loadBoard();
  }
  function write() { asStudent(() => sheets.newThread(() => { board.topic = null; void loadBoard(); })); }

  const Hint = $derived(board.topic ? TOPIC_ICON[board.topic] : null);
  // "I'm in" from the card: at once, the server's answer settles it
  async function join(e: Event, th: Thread) {
    e.stopPropagation();
    const on = !th.joined;
    th.joined = on; th.joins = (th.joins ?? 0) + (on ? 1 : -1);
    haptic.select();
    try { putThread(th.id, await api.joinThread(th.id, on)); if (on) say(t('bd.inSay'), 'raising_hands_3d_default'); }
    catch { th.joined = !on; th.joins = (th.joins ?? 0) + (on ? -1 : 1); haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function decide(kind: 'thread' | 'reply', id: number, ok: boolean) {
    try { await api.threadModDecide(kind, id, ok); haptic.ok(); void loadMod(); void loadBoard(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  const long = (s: string) => s.length > 260 || s.split('\n').length > 5;
</script>


<div class="page scroll">
  <header class="hd">
    <h1 class="t-h1" use:fitTitle use:largeTitle={'forum'}>{t('page.forum')}</h1>
    <p class="t-foot">{t('bd.sub')}</p>
  </header>

  <!-- where a thread starts: the place to write, as in any feed (it was a floating button over the cards and the bar) -->
  {#if student && me}
    <button class="prompt surface" onclick={write}>
      <Avatar person={{ id: me.id, name: me.name, avatar: me.avatar }} size={34} tappable={false} />
      <span class="ph-tx">{t('bd.prompt')}</span>
      <span class="pen" aria-hidden="true"><PenLine size={17} /></span>
    </button>
  {/if}

  <div class="topics hscroll" role="tablist" aria-label={t('bd.topics')}>
    <button role="tab" class:on={board.topic == null} aria-selected={board.topic == null} onclick={() => pick(null)}>{t('bd.all')}</button>
    {#each TOPICS as k (k)}
      {@const Icon = TOPIC_ICON[k]}
      <button role="tab" class:on={board.topic === k} aria-selected={board.topic === k} style:--tint={TOPIC_TINT[k]} onclick={() => pick(k)}><Icon size={16} strokeWidth={2.3} />{t(`bd.topic.${k}`)}</button>
    {/each}
  </div>

  {#if staff && mod && (mod.threads.length || mod.replies.length)}
    <section class="mod surface">
      <h2 class="t-cap">{t('bd.modTitle')}</h2>
      {#each mod.threads as th (th.id)}
        <div class="mrow"><p>{th.body}</p><span class="t-foot">{t(`bd.topic.${th.topic}`)}{th.anon ? ' · ' + t('bd.anon') : ''} · {t(th.why === 'ai' ? 'bd.whyAi' : 'bd.whyCheck')}</span>
          <div class="macts"><button class="ok" onclick={() => decide('thread', th.id, true)}>{t('bd.release')}</button><button onclick={() => decide('thread', th.id, false)}>{t('bd.takeDown')}</button></div></div>
      {/each}
      {#each mod.replies as r (r.id)}
        <div class="mrow"><p>{r.body}</p><span class="t-foot ellipsis">{t('bd.replyTo', { text: r.threadBody })}</span>
          <div class="macts"><button class="ok" onclick={() => decide('reply', r.id, true)}>{t('bd.release')}</button><button onclick={() => decide('reply', r.id, false)}>{t('bd.takeDown')}</button></div></div>
      {/each}
    </section>
  {/if}

  {#if !student}
    <section class="empty">
      <Emoji name="speech_balloon_3d" size={64} />
      <h2 class="t-h2">{t('bd.guestTitle')}</h2>
      <p class="t-callout">{t('bd.guestText')}</p>
      <button class="cta" onclick={() => asStudent(() => void loadBoard())}>{t('bd.signIn')}</button>
    </section>
  {:else if board.list === null}
    <div class="skel" aria-hidden="true">{#each [0, 1, 2] as i (i)}<span class="sk"><i class="a"></i><i class="b"></i><i class="c"></i><i class="d"></i></span>{/each}</div>
  {:else if !board.list.length}
    <section class="empty">
      {#if Hint && board.topic}<span class="big" style:--tint={TOPIC_TINT[board.topic]}><Hint size={30} strokeWidth={2} /></span>
      {:else}<Emoji name="sparkles_3d" size={64} />{/if}
      <h2 class="t-h2">{t('bd.emptyTitle')}</h2>
      <p class="t-callout">{t(board.topic ? `bd.hint.${board.topic}` : 'bd.emptyText')}</p>
      <button class="cta" onclick={write}>{t('bd.writeFirst')}</button>
    </section>
  {:else}
    <div class="list">
      {#each board.list as th, i (th.id)}
        <article class="th surface in" style="--i:{Math.min(i, 8)}" class:held={th.status === 'held'}>
          <button class="open" onclick={() => sheets.thread(th.id)} aria-label={t('bd.open')}></button>
          <div class="kick"><TopicTag topic={th.topic} /><span class="when">{ago(th.bumpedAt)}</span>{#if th.status === 'held'}<span class="flag">{t('bd.held')}</span>{/if}</div>
          <p class="bd" class:fold={long(th.body)}>{th.body}</p>
          <footer class="ft">
            <ThreadHead {th} small />
            {#if th.replies}<span class="cm"><MessageCircle size={15} strokeWidth={2.2} />{th.replies}</span>{/if}
            {#if gathers(th.topic)}
              {#if th.joiners?.length}<span class="faces">{#each th.joiners.slice(0, 3) as p (p.id)}<Avatar person={p} size={22} tappable={false} />{/each}</span>{/if}
              {#if th.mine}<span class="cnt">{t('bd.inCount', { n: th.joins ?? 0 })}</span>
              {:else}<button class="in-btn" class:on={th.joined} aria-pressed={th.joined} onclick={(e) => join(e, th)}>{th.joined ? t('bd.inOn') : t('bd.inOff')}{th.joins ? ` · ${th.joins}` : ''}</button>{/if}
            {/if}
          </footer>
        </article>
      {/each}
    </div>
    {#if board.more}<button class="more" onclick={moreBoard}>{t('bd.more')}</button>{/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: 12px; }
  .page > :global(*) { flex-shrink: 0; }
  .hd p { margin-top: 6px; max-width: 32ch; }
  /* the place to write: my face and an invitation, like a feed's "what's new" */
  .prompt { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 10px 10px 12px; text-align: left;
    box-shadow: inset 0 0 0 1px var(--line); transition: transform var(--t-fast) var(--ease); }
  .prompt:active { transform: scale(0.985); }
  .ph-tx { flex: 1; min-width: 0; color: var(--text-3); font: 500 15px/1.3 var(--font-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pen { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--accent); color: #fff; }
  /* the topics scroll sideways under the thumb, edge to edge; each one's icon in its colour */
  .topics { gap: 8px; margin: 2px calc(-1 * var(--gutter)) 0; padding: 2px var(--gutter); }
  .topics button { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px; border-radius: var(--r-full);
    background: var(--surface-2); color: var(--text-2); font: 620 14px/1 var(--font-text); white-space: nowrap;
    transition: background-color var(--t-base) var(--ease), color var(--t-base) var(--ease), transform var(--t-fast) var(--ease); }
  .topics button :global(svg) { color: var(--tint); margin-left: -2px; }
  .topics button:active { transform: scale(0.95); }
  .topics button.on { background: var(--text); color: var(--bg); }
  .topics button.on :global(svg) { color: inherit; }
  .list { display: flex; flex-direction: column; gap: 10px; }
  .in { animation: rise 440ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 50ms); }
  @keyframes rise { from { opacity: 0; transform: translateY(14px) scale(0.98); } }
  @keyframes pulse { 50% { opacity: 0.5; } }
  /* a card: what it's about and when, the words first, then who and the actions */
  .th { position: relative; display: flex; flex-direction: column; gap: 8px; padding: 13px 14px 11px; box-shadow: inset 0 0 0 1px var(--line);
    transition: transform var(--t-fast) var(--ease); }
  .th:has(.open:active) { transform: scale(0.985); }
  .th.held { opacity: 0.7; }
  /* the whole card opens the thread; the buttons on it sit above this */
  .open { position: absolute; inset: 0; border-radius: inherit; }
  .kick, .bd, .ft { pointer-events: none; }
  .kick { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .when { font: 500 12.5px/1 var(--font-text); color: var(--text-3); }
  .when::before { content: '·'; margin-right: 8px; }
  .bd { font: 470 16px/1.42 var(--font-text); color: var(--text); white-space: pre-line; overflow-wrap: anywhere; }
  .bd.fold { display: -webkit-box; -webkit-line-clamp: 5; line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }
  .ft { position: relative; display: flex; align-items: center; gap: 10px; min-height: 32px; margin-top: 2px; }
  .ft > :global(.ph) { flex: 1; }
  .ft button { pointer-events: auto; }
  .cm { flex: none; display: inline-flex; align-items: center; gap: 5px; color: var(--text-3); font: 620 13px/1 var(--font-text); }
  .faces { flex: none; display: inline-flex; }
  .faces > :global(*) { box-shadow: 0 0 0 2px var(--surface-solid); border-radius: 50%; }
  .faces > :global(*) + :global(*) { margin-left: -7px; }
  .cnt { flex: none; font: 600 13px/1 var(--font-text); color: var(--text-2); }
  .flag { margin-left: auto; padding: 4px 8px; border-radius: var(--r-full); background: var(--warning-soft); color: var(--warning-text); font: 650 11.5px/1 var(--font-text); }
  .in-btn { flex: none; height: 32px; padding: 0 13px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 13px/1 var(--font-text);
    transition: transform var(--t-fast) var(--ease), background-color var(--t-base) var(--ease); }
  .in-btn:active { transform: scale(0.93); }
  .in-btn.on { background: var(--accent); color: #fff; }
  .more { align-self: center; height: 36px; padding: 0 16px; border-radius: var(--r-full); background: var(--surface-2); font: 620 14px/1 var(--font-text); color: var(--text-2); }
  .mod { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; box-shadow: inset 0 0 0 1.5px var(--warning-soft); }
  .mrow { display: flex; flex-direction: column; gap: 6px; }
  .mrow + .mrow { border-top: 1px solid var(--line); padding-top: 10px; }
  .mrow p { font: 450 14.5px/1.4 var(--font-text); white-space: pre-line; overflow-wrap: anywhere; }
  .macts { display: flex; gap: 8px; }
  .macts button { height: 32px; padding: 0 14px; border-radius: var(--r-full); background: var(--surface-2); font: 620 13px/1 var(--font-text); }
  .macts .ok { background: var(--accent); color: #fff; }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; padding: 36px 12px; }
  .empty p { color: var(--text-2); max-width: 300px; }
  .big { width: 64px; height: 64px; border-radius: 20px; display: grid; place-items: center; color: var(--tint); background: color-mix(in srgb, var(--tint) 14%, transparent); }
  .cta { margin-top: 6px; height: 44px; padding: 0 22px; border-radius: var(--r-full); background: var(--accent); color: #fff; font: 650 15px/1 var(--font-text); }
  /* the skeleton has the card's own lines */
  .skel { display: flex; flex-direction: column; gap: 10px; }
  .sk { display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: var(--r-l); background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
  .sk i { height: 12px; border-radius: 6px; background: var(--surface-2); animation: pulse 1.2s ease-in-out infinite; }
  .sk .a { width: 38%; }
  .sk .b { height: 15px; width: 92%; }
  .sk .c { height: 15px; width: 70%; }
  .sk .d { width: 30%; height: 20px; border-radius: 10px; }
  .tail { height: calc(var(--safe-bottom) + 110px); }
</style>
