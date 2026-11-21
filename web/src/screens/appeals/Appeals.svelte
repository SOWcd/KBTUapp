<script module lang="ts">
  import type { Appeal, AppealTopic } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';

  export const TOPICS: AppealTopic[] = ['study', 'dorm', 'food', 'campus', 'events', 'money', 'other'];
  export const CONSENT = 'apl1'; // the policy's appeals section (server appeals.CONSENT)
  export const ASK_CONSENT = 'ask1'; // the help desk's own (server appeals.ASK_CONSENT)
  export type Desk = 'sg' | 'help';
  /** a list row's grey line: the status (or overdue) and the day it was sent */
  export const statusOf = (a: Appeal): string => (a.overdue && a.status !== 'closed' ? t('apl.overdue') : t(`apl.st.${a.status}`));
  export const lineOf = (a: Appeal): string => `${a.topic ? t(`apl.t.${a.topic}`) + ' · ' : ''}${dayMonth(a.at)}`;
  export const headOf = (a: Appeal): string => { const s = a.text.split('\n')[0]; return s.length > 70 ? s.slice(0, 68) + '…' : s; };
</script>

<script lang="ts">
  // An appeal to the Student Government (server logic/appeals.py): an optional topic, the words as they are, Anonymous,
  // "Help me clarify" (2-3 tips from the AI, never a rewrite, never a block), Send (always sends). The draft stays on
  // this phone only (localStorage), never on the server. My appeals under it. The section's consent: asked once, on the
  // first send. AI tips ask separately before sending each draft abroad. The funnel counts taps (lib/stats), never a word.
  // desk 'help': KRI's "Ask a person": the same composer with the question in it (q, editable, sent only on the tap),
  // its own consent, no topics, no AI tips (KRI tried), no Solved feed, no funnel; my questions under it.
  import { onMount, untrack } from 'svelte';
  import { accountDraft } from '../../lib/draft';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import MessageCircleQuestion from '@lucide/svelte/icons/message-circle-question-mark';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import { api, ApiErr } from '../../lib/api';
  import { data, loadAppeals, loadAsks } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { i18n } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Solved from './Solved.svelte';

  let { overlay, desk = 'sg', q }: { overlay: Overlay; desk?: Desk; q?: string } = $props();
  const sg = untrack(() => desk === 'sg');
  const k = (key: 'text' | 'ph' | 'anonOn' | 'anonOff' | 'who' | 'sent' | 'consentT' | 'consentText' | 'mine') => t(sg ? `apl.${key}` : `ask.${key}`);

  const draft = untrack(() => accountDraft(sg ? 'kb-appeal' : 'kb-ask', session.me?.tg.id));
  type Draft = { text: string; topic: AppealTopic | null; anon: boolean };
  function readDraft(): Draft {
    try { const j = JSON.parse(draft.read() || 'null'); if (j && typeof j.text === 'string') return j; } catch { /* blocked */ }
    return { text: '', topic: null, anon: false };
  }
  const first = untrack(() => (q?.trim() ? { text: q.trim(), topic: null, anon: false } : readDraft()));
  let text = $state(first.text), topic = $state<AppealTopic | null>(first.topic), anon = $state(first.anon);
  let tips = $state<string[]>([]), care = $state<string | null>(null), helping = $state(false), down = $state(false);
  let typed = !!first.text, sending = $state(false);

  function saveDraft() {
    const d: Draft = { text, topic, anon };
    draft.save(d.text.trim() ? JSON.stringify(d) : null);
    if (text && !typed) { typed = true; if (sg) count('apl.typed'); }
  }
  $effect(saveDraft);
  onMount(() => {
    if (!sg) { void loadAsks(); return; }
    count('apl.open');
    void loadAppeals();
    return () => { if (typed && !sending && text.trim()) count('apl.drop'); };
  });

  /** undefined: agreed before; the version: just agreed; null: said no */
  async function agree(): Promise<string | undefined | null> {
    if (sg ? session.me?.appeals?.consent : session.me?.ask?.consent) return undefined;
    const yes = await sheets.ask({ title: k('consentT'), text: k('consentText'), ok: t('apl.consentOk'), cancel: t('common.cancel') });
    return yes ? (sg ? CONSENT : ASK_CONSENT) : null;
  }
  const agreed = () => { const m = sg ? session.me?.appeals : session.me?.ask; if (m) m.consent = true; };
  const list = () => (sg ? data.appeals : data.asks) ?? [];
  const mine = $derived(list());
  const setList = (xs: Appeal[]) => { if (sg) data.appeals = xs; else data.asks = xs; };

  async function help() {
    const body = text.trim();
    if (!body) { say(t('apl.helpShort'), 'pleading_face_3d'); return; }
    const yes = await sheets.ask({ title: t('apl.aiConsentT'), text: t('apl.aiConsentText'), ok: t('apl.aiConsentOk'), cancel: t('common.cancel') });
    if (!yes) return;
    helping = true; down = false; care = null; count('apl.ai');
    try {
      const r = await api.appealHelp(body, i18n.lang, 'apl-ai1');
      tips = r.tips; care = r.help ?? null;
      haptic.ok();
    } catch { down = true; } finally { helping = false; }
  }

  // the button spins at once; the draft goes and "Received" shows only once the server has it: a failure keeps every word
  async function send() {
    const body = text.trim();
    if (!body || sending) return;
    const consent = await agree();
    if (consent === null) return;
    sending = true;
    const key = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      const a = sg ? await api.sendAppeal({ text: body, topic, anon, key, consent })
        : await api.sendAsk({ text: body, anon, key, consent });
      agreed(); if (sg) count('apl.sent');
      setList([a, ...list()]);
      if (text.trim() === body) { text = ''; topic = null; } // words typed while it went stay
      tips = []; care = null; down = false; typed = false;
      haptic.ok(); say(k('sent'), 'raising_hands_3d_default');
    } catch (e) {
      haptic.error();
      say(t(e instanceof ApiErr && e.code === 'rate_limited' ? (sg ? 'apl.slow' : 'ask.slow') : e instanceof ApiErr && e.code === 'unavailable' ? 'common.offline' : 'common.error'), 'pleading_face_3d');
    } finally { sending = false; }
  }
</script>

<Sheet {overlay} title={t(sg ? 'apl.row' : 'ask.button')} icon={sg ? Megaphone : MessageCircleQuestion} full>
  <div class="page">
    <Field label={k('text')} placeholder={k('ph')} bind:value={text} multiline rows={5} maxlength={4000} />
    {#if sg}
      <div class="chips" role="group" aria-label={t('apl.row')}>
        {#each TOPICS as c (c)}
          <Chip selected={topic === c} onclick={() => { haptic.select(); topic = topic === c ? null : c; }}>{t(`apl.t.${c}`)}</Chip>
        {/each}
      </div>
    {/if}
    <Group footnote={anon ? k('anonOn') : k('anonOff')}>
      <Row title={t('apl.anon')} accessory="switch" checked={anon} onchange={(on) => { haptic.select(); anon = on; }} />
    </Group>

    {#if care}<Notice tone="danger" title={t('apl.careT')}><p class="selectable pre">{care}</p></Notice>{/if}
    {#if tips.length}
      <Notice tone="accent" title={t('apl.tips')}><ul class="tips">{#each tips as tip, i (i)}<li>{tip}</li>{/each}</ul></Notice>
    {/if}
    {#if down}<Notice text={t('apl.helpDown')} />{/if}
    {#if sg}<Button kind="secondary" full loading={helping} onclick={help}>{#snippet icon()}<Sparkles size={18} />{/snippet}{t('apl.help')}</Button>{/if}
    <p class={['fs-sub faint fine', { alone: !sg }]}>{k('who')}</p>

    {#if mine.length}
      <Group caption={k('mine')}>
        {#each mine as a (a.id)}
          <Row dense title={headOf(a)} subtitle={`${statusOf(a)} · ${lineOf(a)}`} accessory="chevron"
            onclick={() => { if (a.id > 0) { haptic.tap(); if (sg) sheets.myAppeal(a.id); else sheets.myAsk(a.id); } }} />
        {/each}
      </Group>
    {/if}
    {#if sg}<Solved />{/if}
  </div>

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={sending} disabled={!text.trim()} onclick={send}>{t('apl.send')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  .chips { display: flex; gap: var(--s-2); overflow-x: auto; padding: 4px 0; margin: 0 calc(-1 * var(--s-4)); padding-inline: var(--s-4); scrollbar-width: none; }
  .chips::-webkit-scrollbar { display: none; }
  .tips { margin: var(--s-1) 0 0; padding-left: 1.1em; display: flex; flex-direction: column; gap: 4px; }
  .pre { white-space: pre-line; margin: var(--s-1) 0 0; }
  .fine { margin-top: calc(-1 * var(--s-2)); padding: 0 var(--s-4); }
  .fine.alone { margin-top: 0; }
</style>
