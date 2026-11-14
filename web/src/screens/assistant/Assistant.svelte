<script lang="ts">
  // The students' assistant (server logic/assistant.py; owner, Oct 30: "where is my dean's office?" and the app knows
  // the school, the year, the timetable, the campus, what's on). A chat: suggestions to start, the answer with up to
  // three buttons (a room on the map, an event, a club, my classes, a Settings page, the Gallery, the news), checked by
  // the server against what it told the model. Under an answer 👍/👎 (on 👎, the student may send that one question
  // and answer); when the server sees distress, its fixed help card with the helplines (review, Oct 31: nothing of
  // it is kept or sent by us; the student calls or writes themselves).
  import { untrack } from 'svelte';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import Users from '@lucide/svelte/icons/users';
  import CalendarClock from '@lucide/svelte/icons/calendar-clock';
  import Settings from '@lucide/svelte/icons/settings';
  import Images from '@lucide/svelte/icons/images';
  import Newspaper from '@lucide/svelte/icons/newspaper';
  import ThumbsUp from '@lucide/svelte/icons/thumbs-up';
  import ThumbsDown from '@lucide/svelte/icons/thumbs-down';
  import Phone from '@lucide/svelte/icons/phone';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import { api, ApiErr } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { data, eventById } from '../../lib/state/data.svelte';
  import { chat, type AskCtx, type Turn } from '../../lib/state/assistant.svelte';
  import type { AssistAction } from '../../lib/api/types';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { PSYCHOLOGIST } from '../../lib/academic';
  import Sheet from '../../ui/Sheet.svelte';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Emoji from '../../ui/Emoji.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Composer from '../../ui/Composer.svelte';

  // ctx: opened from a card's "Ask AI" (an event, a club); another card, or none, starts a fresh conversation
  let { overlay, ctx }: { overlay: Overlay; ctx?: AskCtx } = $props();
  untrack(() => {
    if (chat.ctx?.kind === ctx?.kind && chat.ctx?.id === ctx?.id) return;
    chat.turns = []; chat.ctx = ctx ?? null;
  });
  let draft = $state(''), busy = $state(false);
  let list = $state<HTMLDivElement>();
  const SUGGEST = $derived(chat.ctx?.kind === 'event' ? ['as.e1', 'as.e2', 'as.e3'] as const
    : chat.ctx?.kind === 'club' ? ['as.c1', 'as.c2'] as const : ['as.s1', 'as.s2', 'as.s3', 'as.s4'] as const);
  const down = () => setTimeout(() => list?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' }), 30);
  $effect(() => { void chat.turns.length; untrack(down); });

  async function ask(q: string) {
    q = q.trim();
    if (!q || busy) return;
    const history = chat.turns.filter((m) => m.text).slice(-6).map(({ role, text }) => ({ role, text }));
    chat.turns.push({ role: 'user', text: q });
    draft = ''; busy = true;
    try {
      const a = await api.assistant(q, history, chat.ctx ? { kind: chat.ctx.kind, id: chat.ctx.id } : undefined);
      chat.turns.push({ role: 'assistant', ...a, q });
      haptic.soft();
    } catch (e) {
      const why = e instanceof ApiErr ? e.code : '';
      chat.turns.push({ role: 'assistant', text: t(why === 'rate_limited' ? 'as.limit' : why === 'unavailable' ? 'as.busy' : why === 'forbidden' ? 'as.consent' : 'common.error') });
      haptic.error();
      if (why === 'forbidden') sheets.consent(); // the new policy first: here it is
    } finally { busy = false; }
  }
  // labels from our own strings and store, never the model's words
  const SET = { school: 'look.school', course: 'pd.course', notify: 'me.notifications' } as const;
  const label = (a: AssistAction) => a.type === 'map' ? t('as.onMap', { room: a.room })
    : a.type === 'event' ? eventById(a.id)?.title ?? t('as.event')
    : a.type === 'club' ? [...data.orgs, ...data.small].find((o) => o.id === a.id)?.name ?? t('as.club')
    : a.type === 'settings' ? t(SET[a.kind]) : t(a.type === 'timetable' ? 'list.classes' : a.type === 'gallery' ? 'gallery.title' : 'page.news');
  const ICON = { map: MapPin, event: CalendarDays, club: Users, timetable: CalendarClock, settings: Settings, gallery: Images, news: Newspaper };
  function go(a: AssistAction) {
    if (a.type === 'map') sheets.map(a.room);
    else if (a.type === 'event') sheets.event(a.id);
    else if (a.type === 'club') sheets.club(a.id);
    else if (a.type === 'settings') sheets.settings(a.kind);
    else if (a.type === 'timetable') sheets.week();
    else if (a.type === 'gallery') sheets.gallery();
    else sheets.news();
  }
  // optimistic: the tap shows at once; a failed call quietly takes it back
  function vote(m: Turn, v: 'up' | 'down') {
    if (m.vote || !m.mark) return;
    m.vote = v;
    api.assistantVote(m.mark, v).catch((e) => { if (!(e instanceof ApiErr && e.code === 'conflict')) m.vote = undefined; }); // conflict: counted already
  }
  function send(m: Turn) {
    if (m.sent || !m.q || !m.mark || !m.pair) return;
    m.sent = true;
    api.assistantSend(m.mark, m.pair, m.q, m.text).catch((e) => {
      m.sent = false; haptic.error();
      say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'as.sendFull' : 'common.error'), 'pleading_face_3d'); // past the day's cap: not kept, said so
    });
  }
</script>

<Sheet {overlay} icon={Sparkles} tall title={t('as.title')}>
  <div class="list" bind:this={list}>
    {#if !chat.turns.length}
      <div class="hello">
        <span class="orb" aria-hidden="true"><Emoji name="sparkles_3d" size={44} /></span>
        {#if chat.ctx}<h2 class="t-h2 clamp-2">{t('as.about', { title: chat.ctx.title })}</h2>
        {:else}<h2 class="t-h2">{t('as.hello')}</h2><p class="hi">{t('as.helloText')}</p>{/if}
        <div class="sugg">{#each SUGGEST as k (k)}<Chip selected={false} onclick={() => { haptic.tap(); void ask(t(k)); }}>{t(k)}</Chip>{/each}</div>
      </div>
    {:else if chat.ctx}
      <!-- engine: ui/Tag could truncate a long label with "…" (an event's title); till then this pill is local -->
      <p class="ctx"><Sparkles size={13} strokeWidth={2.2} /><span class="ellipsis">{chat.ctx.title}</span></p>
    {/if}
    {#each chat.turns as m, i (i)}
      {#if m.text}
        <div class="b {m.role}">
          <p class="selectable">{m.text}</p>
          {#if m.actions?.length}
            <div class="acts">{#each m.actions as a, k (k)}
              <Button kind="tinted" size="s" onclick={() => go(a)}>
                {#snippet icon()}{@const Icon = ICON[a.type]}<Icon size={15} />{/snippet}
                {label(a)}
              </Button>
            {/each}</div>
          {/if}
        </div>
      {/if}
      {#if m.mark && !m.care}
        <div class="rate">
          <IconButton kind="plain" size="s" icon={ThumbsUp} label={t('as.good')} on={m.vote === 'up'} disabled={!!m.vote} onclick={() => vote(m, 'up')} />
          <IconButton kind="plain" size="s" icon={ThumbsDown} label={t('as.bad')} on={m.vote === 'down'} disabled={!!m.vote} onclick={() => vote(m, 'down')} />
        </div>
        {#if m.vote === 'down'}
          <div class="offer">{#if m.sent}<p>{t('as.sent')}</p>{:else}
            <Button kind="plain" size="s" onclick={() => send(m)}>{t('as.sendQ')}</Button><p>{t('as.sendNote')}</p>{/if}</div>
        {/if}
      {/if}
      {#if m.care && m.help}
        <div class="b assistant help">
          <p class="selectable">{m.help}</p>
          <div class="lines">
            <!-- ponytail: a tel: link; Telegram's openLink takes http(s) only. If a client won't dial, the number is in the text above -->
            <!-- engine: Button href (a link drawn as a primary Button); till then this one link is styled here -->
            <a class="first" href="tel:1303" onclick={() => haptic.tap()}><Phone size={16} />{t('as.call1303')}</a>
            <Button kind="secondary" full onclick={() => openLink('https://wa.me/77081060810')}>{#snippet icon()}<MessageCircle size={16} />{/snippet}{t('as.write150')}</Button>
            <Button kind="secondary" full onclick={() => openLink(PSYCHOLOGIST)}>{#snippet icon()}<HeartHandshake size={16} />{/snippet}{t('as.psych')}</Button>
          </div>
        </div>
      {/if}
    {/each}
    {#if busy}<div class="b assistant typing" aria-label={t('as.thinking')}><i></i><i></i><i></i></div>{/if}
  </div>
  <p class="note">{t('as.note')}</p>

  {#snippet footer()}
    <div class="row"><Composer bind:value={draft} placeholder={t('as.ph')} maxlength={300} sending={busy} label={t('cm.send')} onsend={() => ask(draft)} /></div>
  {/snippet}
</Sheet>

<style>
  .list { display: flex; flex-direction: column; gap: 10px; padding: 6px 0 4px; }
  .hello { display: flex; flex-direction: column; align-items: center; text-align: center; gap: var(--s-2); padding: 14px 6px 8px; }
  .hi { max-width: 320px; font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text-2); }
  .orb { display: grid; place-items: center; width: 76px; height: 76px; border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, var(--accent-soft), transparent 70%), var(--surface-2);
    animation: orb 3.2s ease-in-out infinite; }
  @keyframes orb { 50% { transform: translateY(-4px) scale(1.04); } }
  .sugg { display: flex; flex-wrap: wrap; justify-content: center; gap: var(--s-2); margin-top: var(--s-2); padding: 4px 0;
    animation: pop 380ms cubic-bezier(.2, 1.3, .4, 1) 120ms backwards; }
  @keyframes pop { from { opacity: 0; transform: translateY(8px) scale(0.96); } }
  .ctx { align-self: center; display: inline-flex; align-items: center; gap: 6px; max-width: 86%; height: 28px; padding: 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 600 var(--fs-cap)/1 var(--font-text); }
  /* the chat's bubbles: bespoke content (no ui/ part draws a message), on the tokens */
  .b { max-width: 86%; padding: 10px 14px; border-radius: var(--r-l); animation: in 300ms cubic-bezier(.2, .9, .25, 1) backwards; }
  @keyframes in { from { opacity: 0; transform: translateY(8px) scale(0.98); } }
  .b p { font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .b.user { align-self: flex-end; background: var(--accent); color: var(--on-accent); border-bottom-right-radius: var(--r-xs); }
  .b.assistant { align-self: flex-start; background: var(--surface-2); border-bottom-left-radius: var(--r-xs); }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: var(--s-2); }
  .acts :global(.btn) { max-width: 100%; }
  .rate { display: flex; gap: 2px; margin: -4px 0 0 0; --plain-ink: var(--text-3); }
  .rate :global(.btn[aria-pressed='true']) { color: var(--accent-text); opacity: 1; }
  .offer { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; max-width: 86%; margin: -2px 0 0 0; animation: in 300ms cubic-bezier(.2, .9, .25, 1) backwards; }
  .offer p { padding: 0 var(--s-2); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .help { max-width: 92%; }
  .lines { display: flex; flex-direction: column; gap: 6px; margin-top: var(--s-3); }
  .lines a { display: flex; align-items: center; justify-content: center; gap: var(--s-2); height: var(--ctl-m); padding: 0 var(--s-5); border-radius: var(--r-full);
    background: var(--accent); color: var(--on-accent); font: 600 var(--fs-body)/1 var(--font-text); text-decoration: none; }
  .lines a:active { opacity: 0.8; }
  .typing { display: flex; gap: 5px; padding: 14px 16px; }
  .typing i { width: 7px; height: 7px; border-radius: 50%; background: var(--text-3); animation: dot 1s ease-in-out infinite; }
  .typing i:nth-child(2) { animation-delay: 150ms; } .typing i:nth-child(3) { animation-delay: 300ms; }
  @keyframes dot { 30% { transform: translateY(-4px); opacity: 1; } 0%, 60%, 100% { opacity: 0.4; } }
  .note { margin: var(--s-2) 0 2px; text-align: center; font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .row { width: 100%; }
  :global(html.lowfx) .orb { animation: none; }
</style>
