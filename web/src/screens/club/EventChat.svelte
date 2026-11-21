<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import { api, ApiErr, type Id } from '../../lib/api';
  import { nextQuestion, updateDraft, type ChatFill } from '../../lib/eventFill';
  import { keyboard } from '../../lib/state/keyboard.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { teamSize } from '../../lib/teams';
  import { haptic } from '../../lib/tg';
  import Composer from '../../ui/Composer.svelte';
  import Poster from '../../ui/Poster.svelte';
  import Button from '../../ui/Button.svelte';
  import ChatMessage from '../assistant/ChatMessage.svelte';

  let { org, draft = $bindable(), dirty = $bindable(false), canPrice, emoji, color, onhand, onpublish }:
    { org: Id; draft: ChatFill; dirty?: boolean; canPrice: boolean; emoji: string; color: string; onhand: () => void; onpublish: () => void } = $props();
  let message = $state('');
  let turns = $state<{ mine: boolean; text: string }[]>([]);
  let busy = $state(false), started = $state(false);
  let list: HTMLDivElement | undefined;
  let active = true;
  onDestroy(() => { active = false; });
  const next = $derived(nextQuestion(draft, canPrice));
  const question = $derived(started ? next : 'event');
  const seats = $derived(draft.paid && draft.teams && draft.teamCap && draft.teamMax
    ? Math.min(draft.seats || Infinity, draft.teamCap * draft.teamMax) : draft.seats);
  const facts = $derived([
    [draft.date, draft.start, draft.endDate, draft.end].filter(Boolean).join(' · '),
    draft.online ? t('event.online') : draft.tba ? t('ed.tba') : draft.place,
    draft.paid ? [draft.price ? t('ex.tenge', { n: draft.price }) : t('ed.chatPaid'), draft.payTo, draft.payPhone].filter(Boolean).join(' · ')
      : draft.paid === false ? t('ex.free') : '',
    draft.visibility ? t(draft.visibility === 'leaders' ? 'ed.whoLeaders' : draft.visibility === 'members' ? 'ed.whoTeam' : 'ed.whoAll') : '',
    draft.department, draft.forBoard ? t('ed.meetingBoard') : '', draft.cohost ? t('co.invite') + ' · ' + draft.cohost : '',
    draft.memo ? t('studio.memoShort') : '', draft.partner ? draft.guestHost || t('ed.partner') : '',
    seats !== undefined ? t('ed.seats') + ' · ' + (seats || t('ex.unlimited')) : '',
    draft.registration ? t('ex.regUntil') + ' · ' + (draft.registration === 'date' ? [draft.regDate, draft.regTime].filter(Boolean).join(' ') : t(draft.registration === 'end' ? 'ex.untilEnd' : 'ex.untilStart')) : '',
    draft.teams === undefined ? '' : t('ed.teams') + ' · ' + (draft.teams ? [draft.teamMin && draft.teamMax ? teamSize(draft.teamMin, draft.teamMax) : '', draft.teamCap ? t('ed.teamCapN', { n: draft.teamCap }) : ''].filter(Boolean).join(' · ') || t('ed.teams') : t('ex.no')),
    draft.meeting ? t('ed.meeting') : '', draft.santa ? t('santa.title') : '',
    draft.needsPhone ? t('ed.formPhone') : '', draft.form?.map(q => q.label).join(' · '),
  ].filter(Boolean));
  async function down() { await tick(); if (active && list) list.scrollTop = list.scrollHeight; }
  function typeMessage(value: string) {
    message = value;
    dirty = !!value.trim() || turns.length > 0;
  }

  async function send() {
    const text = message.trim();
    if (!text || busy) return;
    const asked = question;
    haptic.tap();
    busy = true; message = '';
    if (started) turns.push({ mine: false, text: t(`ed.chat.${asked}`) });
    turns.push({ mine: true, text });
    void down();
    try {
      // Only the latest message and event facts. Never send payment contacts or the assistant's ordinary chat history.
      const { title, date, endDate, start, end, place, description, paid, price, seats, registration, regDate, regTime, teams, teamMin, teamMax, teamCap,
        online, tba, visibility, meeting, partner } = draft;
      const patch = await api.eventFill(org, text, { title, date, endDate, start, end, place, description, paid, price, seats, registration, regDate, regTime, teams,
        teamMin, teamMax, teamCap, online, tba, visibility, meeting, partner }, asked);
      if (!active) return;
      draft = updateDraft(draft, patch);
      started = true;
    } catch (error) {
      if (!active) return;
      const code = error instanceof ApiErr ? error.code : '';
      turns.push({ mine: false, text: t(code === 'rate_limited' ? 'as.limit' : code === 'unavailable' ? 'as.busy' : 'common.error') });
      if (!message) message = text;
    } finally { busy = false; void down(); }
  }
</script>

<div class="chat" style:margin-bottom={keyboard.h + 'px'}>
  <div class="top">
    <b><Sparkles size={18} />{t('as.title')}</b>
    <Button kind="secondary" size="s" onclick={onhand}>{t('ed.byHand')}</Button>
  </div>
  <div class="thread scroll" {@attach (el) => { list = el; return () => { list = undefined; }; }} role="log" aria-live="polite">
    <ChatMessage text={t('ed.chat.event')} />
    {#each turns as turn, i (i)}<ChatMessage mine={turn.mine} text={turn.text} fresh />{/each}
    {#if Object.keys(draft).length}
      <article class="preview" aria-label={t('ed.preview')}>
        <Poster item={{ cover: null, emoji: draft.emoji ?? emoji, color: draft.color ?? color }} size={52} />
        <div><b>{draft.title || t('ed.new')}</b>
          {#each facts as fact, i (i)}<p>{fact}</p>{/each}
          {#if draft.description}<p class="clamp-2">{draft.description}</p>{/if}
        </div>
      </article>
    {/if}
    {#if busy}<p class="hint" role="status">{t('as.thinking')}</p>
    {:else if started}<ChatMessage text={t(`ed.chat.${question}`)} fresh />{/if}
  </div>
  {#if next === 'ready'}<Button kind="filled" full disabled={busy || !!message.trim()} onclick={onpublish}>{t('ed.chatPublish')}</Button>{/if}
  <Composer bind:value={() => message, typeMessage} placeholder={t(question === 'payTo' ? 'ed.payTo' : question === 'payPhone' ? 'ed.payPhone' : 'ed.chatPh')}
    maxlength={4000} sending={busy} onsend={send} pill />
</div>

<style>
  .chat { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; gap: var(--s-3);
    padding: calc(max(48px, var(--top)) + var(--s-2)) var(--gutter) max(var(--safe-bottom), var(--s-3)); }
  .top, .top b { display: flex; align-items: center; gap: var(--s-2); }
  .top { justify-content: space-between; }
  .thread { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-2) 0; }
  .thread > :global(*) { flex: none; }
  .preview { display: flex; align-items: flex-start; gap: var(--s-3); padding: var(--s-3); background: var(--pill); border-radius: var(--r-l); overflow-wrap: anywhere; }
  .preview div { min-width: 0; }
  .preview p, .hint { margin-top: var(--s-1); color: var(--text-2); font: 450 var(--fs-sub)/1.4 var(--font-text); }
</style>
