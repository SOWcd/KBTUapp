<script lang="ts">
  // The student forum, the bar's own tab (Oct 30, the owner: "one place instead of the chats"): a question, an offer,
  // "who's going to KFC", anything, anonymously too. The place to write on top, the topics to filter by, then the
  // threads newest-bumped first; a tap opens one (ThreadSheet). A gathering thread takes "I'm in" right from its card.
  // Moderators see what waits for a look, first.
  import { untrack } from 'svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import { api, type ThreadMod } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import { board, loadBoard, moreBoard } from '../../lib/state/board.svelte';
  import { ui } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { ago } from '../../lib/time';
  import { TOPICS, TOPIC_ICON, shown, noun, gathers, join, fail, type Offered } from '../../lib/forum';
  import { fitTitle, largeTitle } from '../../ui/title';
  import { TAB_ICON } from '../../ui/icons';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Card from '../../ui/Card.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Group from '../../ui/Group.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import ThreadHead from './ThreadHead.svelte';
  import Gather from './Gather.svelte';

  const student = $derived(!!session.me?.student);
  const me = $derived(session.me);
  const staff = $derived(session.me?.role === 'admin' || session.me?.role === 'moderator');
  const here = $derived(ui.tab === 'forum');
  // in view: a quiet refresh (the app asked for it at the start already); a new topic: its own list
  $effect(() => { if (here && student) untrack(() => void loadBoard()); });
  let mod = $state<ThreadMod | null>(null);
  const loadMod = () => api.threadMod().then((m) => (mod = m)).catch(() => {});
  $effect(() => { if (here && staff) untrack(loadMod); });

  function pick(topic: Offered | null, e: MouseEvent) {
    (e.currentTarget as Element).scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' }); // a chip half out of sight comes in
    if (board.topic === topic) return;
    haptic.select();
    const kept = board.topic == null ? board.list?.filter((x) => x.topic === topic) : null; // from All: the ones already here, at once
    board.topic = topic; board.list = kept?.length ? kept : null;
    void loadBoard();
  }
  function write() { asStudent(() => sheets.newThread(() => { board.topic = null; void loadBoard(); })); }

  async function decide(kind: 'thread' | 'reply', id: number, ok: boolean) {
    try { await api.threadModDecide(kind, id, ok); haptic.ok(); void loadMod(); void loadBoard(); } catch (e) { fail(e); }
  }
  const long = (s: string) => s.length > 260 || s.split('\n').length > 5;
</script>

<div class="page scroll">
  <h1 class="fs-title ttl" use:fitTitle use:largeTitle={'forum'}>{t('page.forum')}</h1>

  {#if student && me}
    <!-- where a thread starts, as in any feed: my face and a field that opens the composer -->
    <button class="prompt" onclick={write}>
      <Avatar person={{ id: me.id, name: me.name, avatar: me.avatar }} size={32} tappable={false} />
      <span class="field">{t('bd.prompt')}</span>
    </button>
    <div class="chips hscroll" role="group" aria-label={t('bd.topics')}>
      <Chip selected={board.topic == null} onclick={(e) => pick(null, e)}>{t('bd.all')}</Chip>
      {#each TOPICS as k (k)}<Chip selected={board.topic === k} icon={TOPIC_ICON[k]} onclick={(e) => pick(k, e)}>{t(`bd.topic.${k}`)}</Chip>{/each}
    </div>
  {/if}

  {#if staff && mod && (mod.threads.length || mod.replies.length)}
    <Group caption={t('bd.modTitle')}>
      {#each mod.threads as th (th.id)}
        <div class="mrow">
          <p class="mt">{th.body}</p>
          <span class="mm">{noun(th.topic)}{th.anon ? ' · ' + t('bd.anon') : ''} · {t(th.why === 'ai' ? 'bd.whyAi' : 'bd.whyCheck')}</span>
          <span class="mb"><Button kind="tinted" size="s" onclick={() => decide('thread', th.id, true)}>{t('bd.release')}</Button>
            <Button kind="gray" size="s" onclick={() => decide('thread', th.id, false)}>{t('bd.takeDown')}</Button></span>
        </div>
      {/each}
      {#each mod.replies as r (r.id)}
        <div class="mrow">
          <p class="mt">{r.body}</p>
          <span class="mm ellipsis">{t('bd.replyTo', { text: r.threadBody })}</span>
          <span class="mb"><Button kind="tinted" size="s" onclick={() => decide('reply', r.id, true)}>{t('bd.release')}</Button>
            <Button kind="gray" size="s" onclick={() => decide('reply', r.id, false)}>{t('bd.takeDown')}</Button></span>
        </div>
      {/each}
    </Group>
  {/if}

  {#if !student}
    <EmptyState icon={TAB_ICON.forum} title={t('bd.guestTitle')} text={t('bd.guestText')} action={{ label: t('bd.signIn'), onclick: () => asStudent(() => void loadBoard()) }} />
  {:else if board.list === null}
    <div class="list">{#each [0, 1, 2] as i (i)}<Card><Skeleton kind="lines" n={3} /></Card>{/each}</div>
  {:else if !board.list.length}
    <EmptyState icon={board.topic ? TOPIC_ICON[shown(board.topic)] : TAB_ICON.forum} title={t('bd.emptyTitle')}
      text={board.topic ? t(`bd.hint.${shown(board.topic)}`) : t('bd.emptyText')} action={{ label: t('bd.writeFirst'), onclick: write }} />
  {:else}
    <div class="list">
      {#each board.list as th, i (th.id)}
        <div class="in" style:--i={Math.min(i, 8)} class:held={th.status === 'held'}>
          <Card onclick={() => sheets.thread(th.id)}>
            <div class="kick"><Tag>{noun(th.topic)}</Tag><span class="when">{ago(th.bumpedAt)}</span>
              {#if th.status === 'held'}<span class="flag"><Tag tone="warning">{t('bd.held')}</Tag></span>{/if}</div>
            <p class="bd" class:fold={long(th.body)}>{th.body}</p>
            <div class="ft">
              <ThreadHead {th} small />
              {#if th.replies}<span class="cm num"><MessageCircle size={16} strokeWidth={2} />{th.replies}</span>{/if}
            </div>
            {#if gathers(th.topic) && (th.joins || !th.mine)}<div class="gw"><Gather {th} onjoin={() => join(th)} /></div>{/if}
          </Card>
        </div>
      {/each}
    </div>
    {#if board.more}<span class="more"><Button kind="gray" size="s" onclick={moreBoard}>{t('bd.more')}</Button></span>{/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: var(--s-3); }
  .page > :global(*) { flex-shrink: 0; }
  .ttl { margin: 0 var(--s-1); }
  /* the place to write: the Composer's field, a tap away from the real one */
  .prompt { display: flex; align-items: center; gap: var(--s-3); width: 100%; text-align: left; }
  .field { flex: 1; min-width: 0; height: var(--ctl-m); padding: 0 var(--s-4); border-radius: var(--r-full); background: var(--fill); color: var(--text-3);
    font: 450 var(--fs-row)/var(--ctl-m) var(--font-text); letter-spacing: -0.012em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: background-color var(--t-fast); }
  .prompt:active { transform: none; }
  .prompt:active .field { background: var(--fill-2); }
  /* the topics scroll sideways edge to edge; 4 px above and below keep the chips' 44 px hit areas whole */
  .chips { gap: var(--s-2); margin: 0 calc(-1 * var(--gutter)); padding: var(--s-1) var(--gutter); }
  .list { display: flex; flex-direction: column; gap: var(--s-3); }
  .in { animation: rise 440ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 50ms); }
  @keyframes rise { from { opacity: 0; transform: translateY(14px) scale(0.98); } }
  .held { opacity: 0.7; }
  /* a card: what it is and when, the words, who wrote it and how many answered; a gathering's own row under them */
  .kick { display: flex; align-items: center; gap: var(--s-2); min-width: 0; }
  .when { min-width: 0; font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .flag { margin-left: auto; display: inline-flex; }
  .bd { margin-top: var(--s-2); font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text); white-space: pre-line; overflow-wrap: break-word; }
  .bd.fold { display: -webkit-box; -webkit-line-clamp: 5; line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }
  .ft { display: flex; align-items: center; gap: var(--s-3); margin-top: var(--s-3); }
  .ft > :global(.who) { flex: 1; }
  .cm { flex: none; display: inline-flex; align-items: center; gap: var(--s-1); font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  .gw { margin: var(--s-3) 0 calc(-1 * var(--s-2)); padding-top: var(--s-1); border-top: 0.5px solid var(--separator); }
  .more { align-self: center; }
  /* the moderators' queue: each held text, why it waits, and the two answers */
  .mrow { position: relative; display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); }
  .mrow + .mrow::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .mt { font: 450 var(--fs-body)/1.4 var(--font-text); white-space: pre-line; overflow-wrap: break-word; }
  .mm { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .mb { display: flex; gap: var(--s-2); }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
