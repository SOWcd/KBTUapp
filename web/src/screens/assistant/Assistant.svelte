<script lang="ts">
  // The students' assistant (server logic/assistant.py; owner, Oct 30: "where is my dean's office?" and the app knows
  // the school, the year, the timetable, the campus, what's on). A chat: suggestions to start, the answer with up to
  // three buttons (a room on the map, an event), checked by the server against what it told the model. Under an answer
  // 👍/👎 (on 👎, the student may send that one question and answer); when the server sees distress, its fixed help card
  // with the helplines (review, Oct 31: nothing of it is kept or sent by us; the student calls or writes themselves).
  import { untrack } from 'svelte';
  import SendHorizontal from '@lucide/svelte/icons/send-horizontal';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import ThumbsUp from '@lucide/svelte/icons/thumbs-up';
  import ThumbsDown from '@lucide/svelte/icons/thumbs-down';
  import Phone from '@lucide/svelte/icons/phone';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import { api, ApiErr } from '../../lib/api';
  import { type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { eventById } from '../../lib/state/data.svelte';
  import { chat, type Turn } from '../../lib/state/assistant.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { PSYCHOLOGIST } from '../../lib/academic';
  import { grow } from '../../ui/grow';
  import Sheet from '../../ui/Sheet.svelte';
  import Emoji from '../../ui/Emoji.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let draft = $state(''), busy = $state(false);
  let list = $state<HTMLDivElement>();
  const SUGGEST = ['as.s1', 'as.s2', 'as.s3', 'as.s4'] as const;
  const down = () => setTimeout(() => list?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' }), 30);
  $effect(() => { void chat.turns.length; untrack(down); });

  async function ask(q: string) {
    q = q.trim();
    if (!q || busy) return;
    haptic.tap();
    const history = chat.turns.filter((m) => m.text).slice(-6).map(({ role, text }) => ({ role, text }));
    chat.turns.push({ role: 'user', text: q });
    draft = ''; busy = true;
    try {
      const a = await api.assistant(q, history);
      chat.turns.push({ role: 'assistant', ...a, q });
      haptic.soft();
    } catch (e) {
      const why = e instanceof ApiErr ? e.code : '';
      chat.turns.push({ role: 'assistant', text: t(why === 'rate_limited' ? 'as.limit' : why === 'unavailable' ? 'as.busy' : why === 'forbidden' ? 'as.consent' : 'common.error') });
      haptic.error();
      if (why === 'forbidden') sheets.consent(); // the new policy first: here it is
    } finally { busy = false; }
  }
  const key = (ev: KeyboardEvent) => { if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); void ask(draft); } };
  const label = (a: NonNullable<Turn['actions']>[number]) => a.type === 'map' ? t('as.onMap', { room: a.room }) : eventById(a.id)?.title ?? t('as.event');
  const go = (a: NonNullable<Turn['actions']>[number]) => { haptic.tap(); if (a.type === 'map') sheets.map(a.room); else sheets.event(a.id); };
  // optimistic: the tap shows at once; a failed call quietly takes it back
  function vote(m: Turn, v: 'up' | 'down') {
    if (m.vote || !m.mark) return;
    haptic.select(); m.vote = v;
    api.assistantVote(m.mark, v).catch(() => (m.vote = undefined));
  }
  function send(m: Turn) {
    if (m.sent || !m.q) return;
    haptic.tap(); m.sent = true;
    api.assistantSend(m.q, m.text).catch(() => { m.sent = false; haptic.error(); });
  }
</script>

<Sheet {overlay} tall title={t('as.title')}>
  <div class="list" bind:this={list}>
    {#if !chat.turns.length}
      <div class="hello">
        <span class="orb" aria-hidden="true"><Emoji name="sparkles_3d" size={44} /></span>
        <h2 class="t-h2">{t('as.hello')}</h2>
        <p class="t-callout">{t('as.helloText')}</p>
        <div class="sugg">{#each SUGGEST as k, i (k)}<button style="--i:{i}" onclick={() => ask(t(k))}>{t(k)}</button>{/each}</div>
      </div>
    {/if}
    {#each chat.turns as m, i (i)}
      {#if m.text}
        <div class="b {m.role}">
          <p class="selectable">{m.text}</p>
          {#if m.actions?.length}
            <div class="acts">{#each m.actions as a, k (k)}
              <button onclick={() => go(a)}>{#if a.type === 'map'}<MapPin size={15} />{:else}<CalendarDays size={15} />{/if}<span class="ellipsis">{label(a)}</span></button>
            {/each}</div>
          {/if}
        </div>
      {/if}
      {#if m.mark && !m.care}
        <div class="rate">
          <button class:on={m.vote === 'up'} disabled={!!m.vote} aria-label={t('as.good')} onclick={() => vote(m, 'up')}><ThumbsUp size={15} /></button>
          <button class:on={m.vote === 'down'} disabled={!!m.vote} aria-label={t('as.bad')} onclick={() => vote(m, 'down')}><ThumbsDown size={15} /></button>
        </div>
        {#if m.vote === 'down'}
          <div class="offer">{#if m.sent}<p class="t-foot">{t('as.sent')}</p>{:else}
            <button onclick={() => send(m)}>{t('as.sendQ')}</button><p class="t-foot">{t('as.sendNote')}</p>{/if}</div>
        {/if}
      {/if}
      {#if m.care && m.help}
        <div class="b assistant help">
          <p class="selectable">{m.help}</p>
          <div class="lines">
            <!-- ponytail: a tel: link; Telegram's openLink takes http(s) only. If a client won't dial, the number is in the text above -->
            <a class="first" href="tel:1303" onclick={() => haptic.tap()}><Phone size={16} />{t('as.call1303')}</a>
            <button onclick={() => { haptic.tap(); openLink('https://wa.me/77081060810'); }}><MessageCircle size={16} />{t('as.write150')}</button>
            <button onclick={() => { haptic.tap(); openLink(PSYCHOLOGIST); }}><HeartHandshake size={16} />{t('as.psych')}</button>
          </div>
        </div>
      {/if}
    {/each}
    {#if busy}<div class="b assistant typing" aria-label={t('as.thinking')}><i></i><i></i><i></i></div>{/if}
  </div>
  <p class="t-foot note">{t('as.note')}</p>

  {#snippet footer()}
    <div class="row">
      <textarea bind:value={draft} rows="1" maxlength="300" placeholder={t('as.ph')} use:grow={132} enterkeyhint="send" onkeydown={key}></textarea>
      <button class="send" disabled={!draft.trim() || busy} onclick={() => ask(draft)} aria-label={t('cm.send')}><SendHorizontal size={20} /></button>
    </div>
  {/snippet}
</Sheet>

<style>
  .list { display: flex; flex-direction: column; gap: 10px; padding: 6px 0 4px; }
  .hello { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 8px; padding: 14px 6px 8px; }
  .hello p { color: var(--text-2); max-width: 320px; }
  .orb { display: grid; place-items: center; width: 76px; height: 76px; border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, color-mix(in srgb, var(--accent) 45%, transparent), transparent 70%), var(--surface-2);
    animation: orb 3.2s ease-in-out infinite; }
  @keyframes orb { 50% { transform: translateY(-4px) scale(1.04); box-shadow: 0 10px 30px -10px color-mix(in srgb, var(--accent) 60%, transparent); } }
  .sugg { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: 8px; }
  .sugg button { padding: 9px 14px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text); font: 600 14px/1.2 var(--font-text);
    animation: pop 380ms cubic-bezier(.2, 1.3, .4, 1) backwards; animation-delay: calc(120ms + var(--i) * 60ms); transition: transform var(--t-fast) var(--ease); }
  .sugg button:active { transform: scale(0.95); }
  @keyframes pop { from { opacity: 0; transform: translateY(8px) scale(0.92); } }
  .b { max-width: 86%; padding: 10px 14px; border-radius: 20px; animation: in 300ms cubic-bezier(.2, .9, .25, 1) backwards; }
  @keyframes in { from { opacity: 0; transform: translateY(8px) scale(0.98); } }
  .b p { font: 450 15.5px/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .b.user { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 6px; }
  .b.assistant { align-self: flex-start; background: var(--surface-2); border-bottom-left-radius: 6px; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .acts button { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; height: 32px; padding: 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 13px/1 var(--font-text); }
  .rate { display: flex; gap: 2px; margin: -4px 0 0 4px; }
  .rate button { display: grid; place-items: center; width: 32px; height: 28px; border-radius: var(--r-full); color: var(--text-3);
    transition: color var(--t-fast), transform var(--t-fast); }
  .rate button:not(:disabled):active { transform: scale(0.88); }
  .rate button.on { color: var(--accent-text); }
  .rate button:disabled:not(.on) { opacity: 0.35; }
  .offer { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; max-width: 86%; margin: -2px 0 0 8px; animation: in 300ms cubic-bezier(.2, .9, .25, 1) backwards; }
  .offer button { padding: 6px 0; color: var(--accent-text); font: 650 var(--fs-body)/1.2 var(--font-text); }
  .offer p { color: var(--text-3); }
  .help { max-width: 92%; }
  .lines { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
  .lines a, .lines button { display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 14px; border-radius: var(--r-full);
    background: var(--surface); color: var(--text); font: 650 var(--fs-body)/1 var(--font-text); text-decoration: none; }
  .lines .first { background: var(--accent); color: var(--on-accent); }
  .typing { display: flex; gap: 5px; padding: 14px 16px; }
  .typing i { width: 7px; height: 7px; border-radius: 50%; background: var(--text-3); animation: dot 1s ease-in-out infinite; }
  .typing i:nth-child(2) { animation-delay: 150ms; } .typing i:nth-child(3) { animation-delay: 300ms; }
  @keyframes dot { 30% { transform: translateY(-4px); opacity: 1; } 0%, 60%, 100% { opacity: 0.4; } }
  .note { text-align: center; margin: 8px 0 2px; }
  .row { display: flex; align-items: flex-end; gap: 8px; width: 100%; }
  .row textarea { flex: 1; min-width: 0; min-height: 44px; padding: 11px 14px; border-radius: 22px; resize: none; background: var(--surface-2); color: var(--text);
    font: 450 16px/1.4 var(--font-text); }
  .row textarea::placeholder { color: var(--text-3); }
  .send { flex: none; width: 44px; height: 44px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--accent); color: #fff;
    transition: opacity var(--t-fast), transform var(--t-fast); }
  .send:disabled { opacity: 0.35; }
  .send:not(:disabled):active { transform: scale(0.92); }
  :global(html.lowfx) .orb { animation: none; }
</style>
