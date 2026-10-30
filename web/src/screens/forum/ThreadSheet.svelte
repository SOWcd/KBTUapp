<script lang="ts">
  // A forum thread (server logic/threads.py): the whole text, who's in on a gathering one (the author sees them with a
  // way to write), the replies oldest first, and my reply at the bottom, as me or masked (the Composer's "send as": a
  // Menu on my face, the placeholder says which). An anonymous writer is "Author" (the thread's own) or "Anonymous N",
  // the same number all through the thread. ⋯ (a Menu) reports someone else's words and deletes my own, asked first;
  // the app's owner alone can reveal an anonymous writer (the server logs it).
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Flag from '@lucide/svelte/icons/flag';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import Eye from '@lucide/svelte/icons/eye';
  import { api, type Joiner, type PersonRef, type ThreadFull, type ThreadReply } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { putThread } from '../../lib/state/board.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { ago, dayMonth } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { gathers, join, fail } from '../../lib/forum';
  import { menu, type MenuItem } from '../../ui/menu';
  import { TAB_ICON } from '../../ui/icons';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Composer from '../../ui/Composer.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Toolbar from '../../ui/Toolbar.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import ThreadHead from './ThreadHead.svelte';
  import Gather from './Gather.svelte';
  import Mask from './Mask.svelte';

  let { overlay, id }: { overlay: Overlay; id: number } = $props();
  let th = $state<ThreadFull | null>(null);
  let gone = $state(false);
  let joiners = $state<Joiner[] | null>(null);
  let draft = $state(''), anon = $state(false), sending = $state(false);
  let revealed = $state<Record<string, PersonRef>>({});
  // the app's owner alone (the founder admin), as the anonymous switch promises
  const owner = $derived(session.me?.role === 'admin' && !!session.me?.founder);
  const me = $derived(session.me);

  const load = () => api.thread(id).then((x) => {
    if (!th) anon = x.mine && x.anon; // once: an anonymous author stays anonymous in their replies; a pick by hand stays
    th = x;
    if (x.mine && gathers(x.topic) && x.joins) api.threadJoiners(id).then((l) => (joiners = l)).catch(() => {});
  }).catch(() => (gone = true));
  $effect(() => { void load(); });

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

  async function removeThread() {
    if (!(await sheets.ask({ title: t('bd.deleteAsk'), text: t('bd.deleteText'), ok: t('bd.delete'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.deleteThread(id); putThread(id, null); haptic.ok(); say(t('bd.deleted'), 'waving_hand_3d_default'); close(overlay.id); } catch (e) { fail(e); }
  }
  async function removeReply(r: ThreadReply) {
    if (!(await sheets.ask({ title: t('bd.deleteReplyAsk'), ok: t('cm.delete'), cancel: t('common.cancel'), danger: true }))) return;
    try {
      await api.deleteReply(r.id);
      if (th) { th.thread = th.thread.filter((x) => x.id !== r.id); if (r.status !== 'held') th.replies--; putThread(id, th); }
      haptic.ok();
    } catch (e) { fail(e); }
  }
  async function reveal(kind: 'thread' | 'reply', xid: number) {
    if (!(await sheets.ask({ title: t('bd.revealAsk'), text: t('bd.revealText'), ok: t('bd.reveal'), cancel: t('common.cancel') }))) return;
    try { revealed = { ...revealed, [`${kind}${xid}`]: await api.revealAnon(kind, xid) }; haptic.ok(); } catch (e) { fail(e); }
  }
  // ⋯ on the thread or a reply: someone else's words reported, my own deleted (red, last); the owner may reveal a mask
  function more(e: MouseEvent, kind: 'thread' | 'reply', x: { id: number; mine: boolean; anon: boolean; body: string }, remove: () => void) {
    const items: MenuItem[] = [];
    if (!x.mine) items.push({ label: t('cm.report'), icon: Flag, onselect: () => sheets.report(kind, x.id, x.body.slice(0, 60)) });
    if (owner && x.anon && !revealed[`${kind}${x.id}`]) items.push({ label: t('bd.reveal'), icon: Eye, onselect: () => void reveal(kind, x.id) });
    if (x.mine) items.push({ label: t(kind === 'thread' ? 'bd.delete' : 'cm.delete'), icon: Trash2, destructive: true, onselect: remove });
    menu(e.currentTarget as Element, items, 'end');
  }
  // a named writer by name (the author's mark beside); "Author" is the anonymous author only
  const replyName = (r: ThreadReply) => r.person && !r.anon ? r.person.name : r.op ? t('bd.author') : t('bd.anonN', { n: r.n ?? 0 });
  const tg = (p: PersonRef | Joiner) => ('telegram' in p ? p.telegram : null);
</script>

<Sheet {overlay} tall title={t('page.forum')} icon={TAB_ICON.forum}>
  {#if gone}
    <EmptyState icon={TAB_ICON.forum} title={t('bd.gone')} />
  {:else if !th}
    <div class="wait"><Skeleton kind="lines" n={4} /></div>
  {:else}
    {@const x = th}
    <div class="top">
      <ThreadHead th={x} tappable />
      <Toolbar items={[{ icon: Ellipsis, label: t('common.more'), onclick: (e) => more(e, 'thread', x, () => void removeThread()) }]} />
    </div>
    {#if revealed[`thread${id}`]}<p class="who-was"><Tag tone="danger">{t('bd.wrote', { name: revealed[`thread${id}`].name })}</Tag></p>{/if}
    <p class="body selectable">{x.body}</p>
    <p class="life">{x.status === 'held' ? t('bd.heldLong') : t('bd.until', { date: dayMonth(x.expiresAt) })}</p>

    {#if gathers(x.topic)}
      {#if x.mine}
        <!-- the author: who's in, each with a way to write to them (they offered it by joining) -->
        {@const people = joiners ?? x.joiners ?? []}
        {#if people.length}
          <div class="gather"><Group caption={tn('bd.going', x.joins ?? people.length)}>
            {#each people as p (p.id)}
              {@const link = tg(p)}
              <Row dense title={p.name} value={link ? t('bd.writeTg') : undefined} accessory={link ? 'external' : 'none'} onclick={link ? () => openLink(link) : undefined}>
                {#snippet lead()}<Avatar person={p} size={32} tappable={false} />{/snippet}
              </Row>
            {/each}
          </Group></div>
        {/if}
      {:else}
        <div class="gather"><Group><span class="gr"><Gather th={x} tappable onjoin={() => join(x)} /></span></Group></div>
      {/if}
    {/if}

    {#if x.thread.length}
      <div class="replies"><Section title={t('bd.replies')} count={x.replies}>
        <div class="list">
          {#each x.thread as r (r.id)}
            <div class="r" class:held={r.status === 'held'}>
              {#if r.person && !r.anon}<Avatar person={r.person} size={32} />{:else}<Mask size={32} />{/if}
              <div class="rb">
                <span class="rh"><b class="ellipsis">{replyName(r)}</b>{#if r.op}<i class="op">{t('bd.authorTag')}</i>{/if}<i>{ago(r.at)}</i>
                  <span class="rm"><IconButton kind="plain" icon={Ellipsis} label={t('common.more')} onclick={(e) => more(e, 'reply', r, () => void removeReply(r))} /></span></span>
                {#if revealed[`reply${r.id}`]}<span class="who-was"><Tag tone="danger">{t('bd.wrote', { name: revealed[`reply${r.id}`].name })}</Tag></span>{/if}
                <p class="selectable">{r.body}</p>
                {#if r.status === 'held'}<span class="note">{t('bd.replyHeld')}</span>{/if}
              </div>
            </div>
          {/each}
        </div>
      </Section></div>
    {/if}
  {/if}

  {#snippet footer()}
    <!-- status comes only to the author and moderators; anyone else can open only a live thread -->
    {#if th && (th.status ?? 'live') === 'live'}
      <Composer bind:value={draft} placeholder={t(anon ? 'bd.anonPh' : 'bd.replyPh')} {sending} onsend={send}
        as={me ? { me: { id: me.id, name: me.name, avatar: me.avatar }, anon, onchange: (v) => { anon = v; } } : undefined} />
    {/if}
  {/snippet}
</Sheet>

<style>
  .wait { margin-top: var(--s-2); }
  .top { display: flex; align-items: center; gap: var(--s-3); margin-top: var(--s-1); }
  .top > :global(.who) { flex: 1; }
  .who-was { display: block; margin-top: var(--s-2); }
  .body { margin-top: var(--s-4); font: 450 var(--fs-row)/1.45 var(--font-text); letter-spacing: -0.012em; white-space: pre-wrap; overflow-wrap: break-word; }
  .life { margin-top: var(--s-2); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .gather { margin-top: var(--s-5); }
  .gr { padding: var(--s-1) var(--s-4); }
  .replies { margin-top: var(--s-7); }
  .list { display: flex; flex-direction: column; padding-bottom: var(--s-2); }
  .r { display: flex; gap: var(--s-3); align-items: flex-start; padding: var(--s-3) 0; animation: c-in 320ms cubic-bezier(.2, .9, .25, 1) backwards; }
  .r + .r { border-top: 0.5px solid var(--separator); }
  .r.held { opacity: 0.65; }
  @keyframes c-in { from { opacity: 0; transform: translateY(6px); } }
  .rb { flex: 1; min-width: 0; }
  .rh { display: flex; align-items: center; gap: 0.4em; min-width: 0; min-height: 20px; font: 600 var(--fs-body)/1.3 var(--font-text); }
  .rh b { min-width: 0; font-weight: inherit; }
  .rh i { flex: none; font: 450 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-3); }
  .rh .op { font-weight: 600; color: var(--accent-text); }
  /* ⋯ draws a glyph in grey but takes the finger's 44 px around it, without making the line taller */
  .rm { margin: -12px -12px -12px auto; --plain-ink: var(--text-3); }
  .rb p { margin-top: 2px; font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: break-word; }
  .note { display: block; margin-top: var(--s-1); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
</style>
