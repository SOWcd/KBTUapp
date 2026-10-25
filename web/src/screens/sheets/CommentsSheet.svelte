<script lang="ts">
  // Comments under a post or an event (SPEC §4.10): questions to the organizer ("where's the entrance?"). Oldest first,
  // the club's own answers marked; write at the bottom (as the club when I lead it); ⋯ on a comment takes it down (mine,
  // or any as the club's Head+) or reports it to the admin; the club's Head+ can turn the thread off. Someone else's
  // comment swiped left, as in Telegram (owner, Oct 12: no "Reply" button), makes mine a reply (testers, Oct 5: "why
  // can't I reply"): their words quoted above it, and the bot tells them. No nested threads: a reply sits in time order.
  import { untrack } from 'svelte';
  import SendHorizontal from '@lucide/svelte/icons/send-horizontal';
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
  import Avatar from '../../ui/Avatar.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import { nameOf } from '../../lib/short';

  let { overlay, kind, id, title, onchange }: { overlay: Overlay; kind: 'post' | 'event'; id: Id; title: string; onchange?: (n: number) => void } = $props();

  let th = $state<CommentThread | null>(null);
  let draft = $state('');
  let asClub = $state(false);
  let sending = $state(false);
  let replying = $state<Comment | null>(null); // the comment mine answers
  let menu = $state<Id | null>(null);      // the comment whose actions are open
  let list = $state<HTMLDivElement>();
  let field = $state<HTMLTextAreaElement>();

  $effect(() => {
    api.comments(kind, id).then((x) => {
      th = x;
      // read by the club's Head+: the event leaves Studio's "questions waiting" at once (the server marked it read for me)
      const e = kind === 'event' && x.asOrg ? data.studio[x.asOrg.id]?.find((c) => c.id === id) : null;
      if (e) e.questions = 0;
    })
      .catch(() => { th = { items: [], on: false, canModerate: false, asOrg: null }; say(t('common.error'), 'pleading_face_3d'); });
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
      say(e instanceof ApiErr && e.code === 'rate_limited' ? t('cm.tooFast') : e instanceof ApiErr && e.code === 'closed' ? t('cm.off') : t('common.error'), 'pleading_face_3d');
    } finally { sending = false; }
  }
  async function remove(c: Comment) {
    if (!(await sheets.ask({ title: t('cm.deleteAsk'), ok: t('cm.delete'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.deleteComment(c.id); if (th) th = { ...th, items: th.items.filter((x) => x.id !== c.id) }; menu = null; haptic.soft(); say(t('say.cmDeleted'), 'waving_hand_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  const report = (c: Comment) => { menu = null; sheets.report('comment', c.id, c.body); };
  async function toggle(ev: Event) {
    const on = (ev.currentTarget as HTMLInputElement).checked;
    try { th = await api.setComments(kind, id, on); haptic.select(); say(on ? phrase('say.cmOn') : t('say.cmOff'), on ? 'speech_balloon_3d' : 'locked_3d'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  function reply(c: Comment) {
    replying = c; menu = null; haptic.select();
    requestAnimationFrame(() => field?.focus());
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
  const open = (c: Comment) => { menu = menu === c.id ? null : c.id; };
  // the field grows with the text, up to five lines; Enter sends, Shift+Enter breaks the line
  const grow = (el: HTMLTextAreaElement) => { const fit = () => { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 132) + 'px'; }; fit(); el.addEventListener('input', fit); };
  const key = (ev: KeyboardEvent) => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); void send(); } };
</script>

<Sheet {overlay} tall title={kind === 'event' ? t('cm.titleEvent') : t('cm.title')}>
  <h2 class="t-h2 hd">{kind === 'event' ? t('cm.titleEvent') : t('cm.title')}</h2>
  <p class="t-foot sub ellipsis">{title}</p>

  {#if th?.canModerate}
    <label class="switch onoff"><span><b>{t('cm.on')}</b><i class="t-foot">{t('cm.onNote')}</i></span><input type="checkbox" role="switch" checked={th.on} onchange={toggle} /></label>
  {/if}

  {#if th === null}
    <div class="wait" aria-hidden="true"><span></span><span></span></div>
  {:else if !th.items.length}
    <p class="empty">{kind === 'event' ? t('cm.emptyEvent') : t('cm.empty')}</p>
  {:else}
    <div class="list" bind:this={list}>
      {#each th.items as c (c.id)}
        <div class="cw" use:swipe={c}>
        <span class="sw" aria-hidden="true"><Reply size={18} /></span>
        <div class="c" class:club={!!c.org} data-c={c.id}>
          {#if c.org}<OrgLogo org={c.org} size={34} />{:else if c.person}<Avatar person={c.person} size={34} />{/if}
          <div class="cb">
            <span class="ch">
              <b class="ellipsis">{c.org ? nameOf(c.org) : c.person?.name}</b>{#if c.org}<span class="tag">{t('cm.club')}</span>{/if}<i>{ago(c.at)}</i>
              <button class="more" onclick={() => open(c)} aria-label={t('common.more')} aria-expanded={menu === c.id}><Ellipsis size={16} /></button>
            </span>
            {#if c.replyTo}<button class="quote" onclick={() => jump(c.replyTo!.id)}><b>{c.replyTo.name}</b><span class="ellipsis">{c.replyTo.body}</span></button>{/if}
            <p class="selectable">{c.body}</p>
            {#if menu === c.id}
              <div class="acts">
                {#if c.canDelete}<button class="danger" onclick={() => remove(c)}>{t('cm.delete')}</button>{/if}
                {#if !c.mine}<button onclick={() => report(c)}>{t('cm.report')}</button>{/if}
              </div>
            {/if}
          </div>
        </div>
        </div>
      {/each}
    </div>
  {/if}

  {#snippet footer()}
    {#if th?.on}
      <div class="compose">
        {#if th.asOrg}
          <button class="as" class:on={asClub} onclick={() => { asClub = !asClub; haptic.select(); }} aria-pressed={asClub}>
            <OrgLogo org={th.asOrg} size={18} />{asClub ? t('cm.asClub') : t('cm.asMe')}
          </button>
        {/if}
        {#if replying}
          <div class="to"><span class="quote"><b>{t('cm.replyTo', { name: replying.org ? nameOf(replying.org) : replying.person?.name ?? '' })}</b><span class="ellipsis">{replying.body}</span></span>
            <button class="x" onclick={() => (replying = null)} aria-label={t('common.cancel')}><X size={16} /></button></div>
        {/if}
        <div class="row">
          <textarea bind:value={draft} rows="1" maxlength="500" bind:this={field} placeholder={kind === 'event' && !th.asOrg ? t('cm.askPh') : t('cm.ph')} use:grow enterkeyhint="send" onkeydown={key}></textarea>
          <button class="send" disabled={!draft.trim() || sending} onclick={send} aria-label={t('cm.send')}><SendHorizontal size={20} /></button>
        </div>
      </div>
    {:else if th}
      <p class="off">{t('cm.off')}</p>
    {/if}
  {/snippet}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 14px; }
  .onoff { margin-bottom: 14px; }
  .empty { padding: 22px 12px; text-align: center; color: var(--text-2); font: 500 14.5px/1.45 var(--font-text); text-wrap: balance; }
  .list { display: flex; flex-direction: column; gap: 16px; padding-bottom: 8px; }
  .c { display: flex; gap: 10px; align-items: flex-start; animation: c-in 320ms cubic-bezier(.2, .9, .25, 1) backwards; }
  @keyframes c-in { from { opacity: 0; transform: translateY(6px); } }
  .cb { flex: 1; min-width: 0; }
  .ch { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .ch b { font: 650 14px/1.3 var(--font-text); min-width: 0; }
  .ch i { flex: none; font: 500 12.5px/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .tag { flex: none; padding: 3px 7px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 700 10.5px/1 var(--font-text); letter-spacing: 0.04em; text-transform: uppercase; }
  .more { margin-left: auto; flex: none; width: 30px; height: 26px; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: var(--text-3); }
  .more:active { background: var(--surface-2); }
  .cb p { margin-top: 3px; font: 450 15px/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .club .cb p { padding: 8px 12px; margin-top: 5px; border-radius: 4px 16px 16px 16px; background: var(--accent-soft); }
  .quote { display: flex; flex-direction: column; gap: 2px; width: 100%; min-width: 0; margin-top: 4px; padding: 5px 10px; border-left: 2.5px solid var(--accent);
    border-radius: 4px 10px 10px 4px; background: var(--surface-2); text-align: left; font: 500 13px/1.3 var(--font-text); color: var(--text-2); }
  .quote b { font: 650 12.5px/1.2 var(--font-text); color: var(--accent-text); }
  .to { display: flex; align-items: center; gap: 6px; }
  .to .quote { flex: 1; margin-top: 0; }
  .x { flex: none; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 50%; color: var(--text-3); }
  .cw { position: relative; touch-action: pan-y; }
  .sw { position: absolute; right: 2px; top: 50%; margin-top: -16px; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; background: var(--surface-2); color: var(--text-2); opacity: 0; transform: scale(0.5); pointer-events: none; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; animation: c-in 220ms ease-out backwards; }
  .acts button { height: 32px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); font: 620 13px/1 var(--font-text); color: var(--text); }
  .acts .danger { color: var(--danger-text); background: var(--danger-soft); }

  .compose { display: flex; flex-direction: column; gap: 8px; width: 100%; }
  .as { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px 0 5px; border-radius: var(--r-full);
    background: var(--surface-2); color: var(--text-2); font: 620 12.5px/1 var(--font-text); }
  .as.on { background: var(--accent-soft); color: var(--accent-text); box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 50%, transparent); }
  .row { display: flex; align-items: flex-end; gap: 8px; }
  .row textarea { flex: 1; min-width: 0; min-height: 44px; padding: 11px 14px; border-radius: 22px; resize: none; background: var(--surface-2); color: var(--text);
    font: 450 16px/1.4 var(--font-text); }
  .row textarea::placeholder { color: var(--text-3); }
  .send { flex: none; width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--accent); color: #fff;
    transition: opacity var(--t-fast), transform var(--t-fast); }
  .send:disabled { opacity: 0.35; }
  .send:not(:disabled):active { transform: scale(0.92); }
  .off { width: 100%; padding: 12px; text-align: center; color: var(--text-2); font: 550 14px/1.3 var(--font-text); }
  .wait { display: flex; flex-direction: column; gap: 14px; }
  .wait span { height: 54px; border-radius: var(--r-m); background: var(--surface-2); animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
</style>
