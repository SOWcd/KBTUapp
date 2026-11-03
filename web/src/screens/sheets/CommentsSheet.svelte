<script lang="ts">
  // Comments under a post or an event (SPEC §4.10): questions to the organizer ("where's the entrance?"). Oldest first,
  // the club's own answers marked; write at the bottom (as the club when I lead it); ⋯ on a comment takes it down (mine,
  // or any as the club's Head+) or reports it to the admin; the club's Head+ can turn the thread off. Someone else's
  // comment swiped left, as in Telegram (no "Reply" button), makes mine a reply (testers, Oct 5: "why
  // can't I reply"): their words quoted above it, and the bot tells them. No nested threads: a reply sits in time order.
  import { untrack } from 'svelte';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import X from '@lucide/svelte/icons/x';
  import Reply from '@lucide/svelte/icons/reply';
  import { api, ApiErr, type Comment, type CommentThread, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { data } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import Avatar from '../../ui/Avatar.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import { nameOf } from '../../lib/short';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Chip from '../../ui/Chip.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Composer from '../../ui/Composer.svelte';
  import { menu as openMenu, type MenuItem } from '../../ui/menu';

  let { overlay, kind, id, title, onchange }: { overlay: Overlay; kind: 'post' | 'event'; id: Id; title: string; onchange?: (n: number) => void } = $props();

  let th = $state<CommentThread | null>(null);
  let draft = $state('');
  let asClub = $state(false);
  let sending = $state(false);
  let replying = $state<Comment | null>(null); // the comment mine answers
  let list = $state<HTMLDivElement>();
  let compose = $state<HTMLDivElement>();

  $effect(() => {
    api.comments(kind, id).then((x) => {
      th = x;
      // read by the club's Head+: the event leaves Studio's "questions waiting" at once (the server marked it read for me)
      const e = kind === 'event' && x.asOrg ? data.studio[x.asOrg.id]?.find((c) => c.id === id) : null;
      if (e) e.questions = 0;
    })
      .catch(() => { th = { items: [], on: false, canModerate: false, asOrg: null }; say(t('common.error'), 'warning_3d'); });
  });
  // the caller's count follows; untracked, or whatever the caller reads would loop back into this effect
  $effect(() => { if (th) { const n = th.items.length; untrack(() => onchange?.(n)); } });

  async function send() {
    const body = draft.trim();
    if (!body || sending) return;
    sending = true;
    try {
      th = await api.addComment(kind, id, body, asClub, replying?.id);
      draft = ''; replying = null; haptic.ok(); say(phrase('say.commented'), 'speech_balloon_3d');
      requestAnimationFrame(() => list?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' }));
    } catch (e) {
      haptic.error();
      say(e instanceof ApiErr && e.code === 'rate_limited' ? t('cm.tooFast') : e instanceof ApiErr && e.code === 'closed' ? t('cm.off') : t('common.error'), 'warning_3d');
    } finally { sending = false; }
  }
  async function remove(c: Comment) {
    if (!(await sheets.ask({ title: t('cm.deleteAsk'), ok: t('cm.delete'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.deleteComment(c.id); if (th) th = { ...th, items: th.items.filter((x) => x.id !== c.id) }; haptic.soft(); say(t('say.cmDeleted'), 'waving_hand_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  const report = (c: Comment) => { sheets.report('comment', c.id, c.body); };
  async function toggle(on: boolean) {
    try { th = await api.setComments(kind, id, on); haptic.select(); say(on ? phrase('say.cmOn') : t('say.cmOff'), on ? 'speech_balloon_3d' : 'locked_3d'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  function reply(c: Comment) {
    replying = c; haptic.select();
    requestAnimationFrame(() => compose?.querySelector('textarea')?.focus());
  }
  /** Telegram's swipe: the comment follows the finger left, the arrow at the right grows; past 56 px it ticks and gives,
   *  and let go there it replies. A drag that starts more down than sideways is the list's scroll. */
  function swipe(node: HTMLElement, c: Comment) {
    const body = node.lastElementChild as HTMLElement, arrow = node.firstElementChild as HTMLElement, FAR = 56;
    let x0 = 0, y0 = 0, id = -1, mode = '', hit = false;
    const set = (dx: number, ease = '') => {
      body.style.transition = arrow.style.transition = ease;
      body.style.transform = dx ? `translateX(${dx}px)` : '';
      const k = Math.min(1, -dx / FAR);
      arrow.style.opacity = String(k); arrow.style.transform = `scale(${hit ? 1.1 : 0.5 + 0.5 * k})`;
    };
    const down = (e: PointerEvent) => {
      if (!th?.on || c.mine || e.button > 0 || (e.target as Element).closest('button')) return;
      x0 = e.clientX; y0 = e.clientY; id = e.pointerId; mode = ''; hit = false;
    };
    const move = (e: PointerEvent) => {
      if (e.pointerId !== id) return;
      const mx = e.clientX - x0, my = e.clientY - y0;
      if (!mode) {
        if (Math.abs(mx) < 8 && Math.abs(my) < 8) return;
        mode = mx < 0 && Math.abs(mx) > Math.abs(my) ? 'x' : 'y';
        if (mode === 'y') { id = -1; return; }
        node.setPointerCapture(id); getSelection()?.removeAllRanges();
      }
      const dx = Math.min(0, mx < -FAR ? -FAR + (mx + FAR) * 0.3 : mx); // rubber past the tick
      if (dx <= -FAR !== hit) { hit = dx <= -FAR; if (hit) haptic.select(); }
      set(dx);
    };
    const up = (e: PointerEvent) => {
      if (e.pointerId !== id) return;
      id = -1;
      if (mode !== 'x') return;
      const go = hit && e.type === 'pointerup';
      hit = false; set(0, 'transform 0.34s var(--ease-spring), opacity 0.2s ease');
      if (go) reply(c);
    };
    node.addEventListener('pointerdown', down); node.addEventListener('pointermove', move);
    node.addEventListener('pointerup', up); node.addEventListener('pointercancel', up);
    return { update: (n: Comment) => (c = n) };
  }
  // a tap on a quote brings up the comment it answers
  const jump = (to: Id) => list?.querySelector(`[data-c="${to}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  // ⋯ on a comment: the shared menu at it (take it down, report)
  function open(ev: MouseEvent, c: Comment) {
    const items: MenuItem[] = [];
    if (!c.mine) items.push({ label: t('cm.report'), onselect: () => report(c) });
    if (c.canDelete) items.push({ label: t('cm.delete'), destructive: true, onselect: () => remove(c) });
    if (items.length) openMenu(ev.currentTarget as Element, items, 'end');
  }
</script>

<Sheet {overlay} icon={MessageCircle} tall title={kind === 'event' ? t('cm.titleEvent') : t('cm.title')}>
  <p class="fs-sub dim sub ellipsis">{title}</p>

  {#if th?.canModerate}
    <div class="onoff"><Group footnote={t('cm.onNote')}><Row title={t('cm.on')} accessory="switch" checked={th.on} onchange={toggle} /></Group></div>
  {/if}

  {#if th === null}
    <Skeleton kind="rows" n={2} />
  {:else if !th.items.length}
    <EmptyState icon={MessageCircle} title={kind === 'event' ? t('cm.emptyEvent') : t('cm.empty')} />
  {:else}
    <div class="list" bind:this={list}>
      {#each th.items as c (c.id)}
        <div class="cw" use:swipe={c}>
        <span class="sw" aria-hidden="true"><Reply size={18} /></span>
        <div class="c" class:club={!!c.org} data-c={c.id}>
          {#if c.org}<OrgLogo org={c.org} size={34} />{:else if c.person}<Avatar person={c.person} size={34} />{/if}
          <div class="cb">
            <span class="ch">
              <b class="ellipsis">{c.org ? nameOf(c.org) : c.person?.name}</b>{#if c.org}<Tag tone="accent">{t('cm.club')}</Tag>{/if}<i>{ago(c.at)}</i>
              {#if c.canDelete || !c.mine}<span class="more"><IconButton icon={Ellipsis} kind="plain" size="s" label={t('common.more')} onclick={(ev) => open(ev, c)} /></span>{/if}
            </span>
            {#if c.replyTo}<button class="quote" onclick={() => jump(c.replyTo!.id)}><b>{c.replyTo.name}</b><span class="ellipsis">{c.replyTo.body}</span></button>{/if}
            <p class="selectable">{c.body}</p>
          </div>
        </div>
        </div>
      {/each}
    </div>
  {/if}

  {#snippet footer()}
    {#if th?.on}
      <div class="compose" bind:this={compose}>
        {#if th.asOrg}
          <span class="as"><Chip selected={asClub} onclick={() => { asClub = !asClub; haptic.select(); }}><OrgLogo org={th.asOrg} size={18} />{asClub ? t('cm.asClub') : t('cm.asMe')}</Chip></span>
        {/if}
        {#if replying}
          <div class="to"><span class="quote"><b>{t('cm.replyTo', { name: replying.org ? nameOf(replying.org) : replying.person?.name ?? '' })}</b><span class="ellipsis">{replying.body}</span></span>
            <IconButton icon={X} kind="plain" size="s" label={t('common.cancel')} onclick={() => (replying = null)} /></div>
        {/if}
        <Composer bind:value={draft} placeholder={kind === 'event' && !th.asOrg ? t('cm.askPh') : t('cm.ph')} maxlength={500} {sending} label={t('cm.send')} onsend={send} />
      </div>
    {:else if th}
      <p class="fs-body dim off">{t('cm.off')}</p>
    {/if}
  {/snippet}
</Sheet>

<style>
  .sub { margin: 0 var(--s-1) var(--s-4); }
  .onoff { margin-bottom: var(--s-5); }
  .list { display: flex; flex-direction: column; gap: var(--s-4); padding-bottom: var(--s-2); }
  /* a comment: chat-like content, not a list row (an avatar, the name and time, the words) */
  .c { display: flex; gap: 10px; align-items: flex-start; animation: c-in 320ms var(--ease) backwards; }
  @keyframes c-in { from { opacity: 0; transform: translateY(6px); } }
  .cb { flex: 1; min-width: 0; }
  .ch { display: flex; align-items: center; gap: 6px; min-width: 0; min-height: 26px; }
  .ch b { font: 600 var(--fs-body)/1.3 var(--font-text); min-width: 0; }
  .ch i { flex: none; font: 450 var(--fs-cap)/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .ch :global(.chip) { height: 20px; padding: 0 7px; font-size: var(--fs-micro); }
  /* the 36 px button inside a 26 px line: its hit area reaches past it */
  .more { margin: -5px -8px -5px auto; flex: none; color: var(--text-3); --plain-ink: var(--text-3); }
  .cb p { margin-top: 3px; font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .club .cb p { padding: var(--s-2) var(--s-3); margin-top: 5px; border-radius: var(--r-xs) var(--r-m) var(--r-m) var(--r-m); background: var(--accent-soft); }
  .quote { display: flex; flex-direction: column; gap: 2px; width: 100%; min-width: 0; margin-top: var(--s-1); padding: 5px 10px; border-left: 2.5px solid var(--accent);
    border-radius: var(--r-xs); background: var(--fill); text-align: left; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .quote b { font: 600 var(--fs-cap)/1.2 var(--font-text); color: var(--accent-text); }
  .to { display: flex; align-items: center; gap: 6px; }
  .to .quote { flex: 1; margin-top: 0; }
  .cw { position: relative; touch-action: pan-y; }
  .sw { position: absolute; right: 2px; top: 50%; margin-top: -16px; width: 32px; height: 32px; border-radius: var(--r-full); display: flex; align-items: center;
    justify-content: center; background: var(--fill); color: var(--text-2); opacity: 0; transform: scale(0.5); pointer-events: none; }

  .compose { display: flex; flex-direction: column; gap: var(--s-2); width: 100%; }
  .as { align-self: flex-start; }
  .off { width: 100%; padding: var(--s-3); text-align: center; }
</style>
