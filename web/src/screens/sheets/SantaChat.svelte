<script lang="ts">
  // Secret Santa's chat (server santa.chat): one thread of a pair. side 'to': I write as the Santa of my person (named:
  // I know them); 'from': with my own Santa, who is only ever "Secret Santa" here. The thread lives in the store
  // (data.santaChat), read again as this opens; a send shows in the same frame and is put back if it fails. A tap on
  // a received message reports: the thread is deleted and closed for both (no moderator reads a pair).
  import { tick, untrack } from 'svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import { api, ApiErr, type Id, type SantaMsg } from '../../lib/api';
  import { data, loadSantaChat } from '../../lib/state/data.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { nowTs } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Composer from '../../ui/Composer.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import { menu } from '../../ui/menu';

  let { overlay, event, side, name = '' }: { overlay: Overlay; event: Id; side: 'to' | 'from'; name?: string } = $props();
  const th = $derived(data.santaChat[event]?.[side]);
  let draft = $state('');
  let list = $state<HTMLDivElement>();
  let tmp = 0;
  const down = async () => { await tick(); list?.lastElementChild?.scrollIntoView({ block: 'end' }); };
  void loadSantaChat(untrack(() => event));
  $effect(() => { if (th?.msgs.length) void down(); });

  async function send() {
    const text = draft.split(/\s+/).filter(Boolean).join(' ');
    if (!text || !th) return;
    const mine: SantaMsg = { id: --tmp, mine: true, text, at: nowTs() };
    th.msgs.push(mine); draft = ''; haptic.tap();
    try {
      const m = await api.santaWrite(event, side, text);
      const now = data.santaChat[event]?.[side]?.msgs; // a refresh may have replaced the list meanwhile
      const i = now?.findIndex((x) => x.id === mine.id) ?? -1;
      if (i >= 0) now![i] = m; else if (now && !now.some((x) => x.id === m.id)) now.push(m);
    } catch (e) {
      const now = data.santaChat[event]?.[side];
      if (now) now.msgs = now.msgs.filter((x) => x.id !== mine.id);
      if (!draft) draft = text;
      const code = e instanceof ApiErr ? e.code : '';
      if (code === 'closed' && now) { now.closed = true; now.msgs = []; }
      haptic.error(); say(t(code === 'rate_limited' ? 'santa.chatLimit' : code === 'closed' ? 'santa.chatClosed' : 'common.error'), 'warning_3d');
    }
  }
  async function report() {
    if (!(await sheets.ask({ title: t('santa.chatReportAsk'), text: t('santa.chatReportText'), ok: t('santa.chatReportGo'), cancel: t('common.cancel'), danger: true }))) return;
    try {
      await api.santaReport(event, side);
      const now = data.santaChat[event]?.[side];
      if (now) { now.closed = true; now.msgs = []; }
      haptic.soft(); say(t('santa.chatClosed'), 'locked_3d');
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  const more = (e: MouseEvent) => menu(e.currentTarget as Element, [{ label: t('cm.report'), destructive: true, onselect: report }], 'start');
</script>

<Sheet {overlay} icon={MessageCircle} tall heading={side === 'to' ? name : t('santa.title')}>
  <p class="fs-sub sub">{t(side === 'to' ? 'santa.chatToSub' : 'santa.chatFromSub')}</p>
  {#if !th}
    <Skeleton kind="rows" n={2} />
  {:else if th.closed}
    <EmptyState icon={MessageCircle} title={t('santa.chatClosed')} />
  {:else if !th.msgs.length}
    <EmptyState icon={MessageCircle} title={t('santa.chatEmpty')} />
  {:else}
    <div class="list" bind:this={list} role="log">
      {#each th.msgs as m (m.id)}
        {#if m.mine}<p class="b mine selectable">{m.text}</p>
        {:else}<button class="b" aria-haspopup="menu" onclick={more}>{m.text}</button>{/if}
      {/each}
    </div>
  {/if}

  {#snippet footer()}
    {#if th && !th.closed}
      <div class="compose">
        <Composer bind:value={draft} placeholder={t(side === 'to' ? 'santa.chatPhTo' : 'santa.chatPhFrom')} maxlength={500} onsend={send} />
        <!-- the feature's own consent, as the wishlist's line: until my first message here -->
        {#if !th.msgs.some((m) => m.mine)}<p class="note">{t('santa.chatNote')}</p>{/if}
      </div>
    {/if}
  {/snippet}
</Sheet>

<style>
  .sub { margin: 0 var(--s-1) var(--s-4); color: var(--text-2); }
  .list { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); padding-bottom: var(--s-2); }
  .b { max-width: 86%; margin: 0; padding: 9px 14px; border-radius: var(--r-l); background: var(--fill); color: var(--text); text-align: left;
    font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; animation: b-in 320ms var(--ease) backwards; }
  .mine { align-self: flex-end; background: var(--accent-soft); }
  .compose { display: flex; flex-direction: column; gap: var(--s-2); width: 100%; }
  .note { margin: 0 var(--s-1); color: var(--text-3); font: 450 var(--fs-cap)/1.35 var(--font-text); }
  @keyframes b-in { from { opacity: 0; transform: translateY(6px); } }
  @media (prefers-reduced-motion: reduce) { .b { animation: none; } }
</style>
