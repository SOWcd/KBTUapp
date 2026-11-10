<script module lang="ts">
  import type { Appeal, AppealTopic } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';

  export const TOPICS: AppealTopic[] = ['study', 'dorm', 'food', 'campus', 'events', 'money', 'other'];
  export const CONSENT = 'apl1'; // the policy's appeals section (server appeals.CONSENT)
  /** a list row's grey line: the status (or overdue) and the day it was sent */
  export const statusOf = (a: Appeal): string => (a.overdue && a.status !== 'closed' ? t('apl.overdue') : t(`apl.st.${a.status}`));
  export const lineOf = (a: Appeal): string => `${a.topic ? t(`apl.t.${a.topic}`) + ' · ' : ''}${dayMonth(a.at)}`;
  export const headOf = (a: Appeal): string => { const s = a.text.split('\n')[0]; return s.length > 70 ? s.slice(0, 68) + '…' : s; };
</script>

<script lang="ts">
  // An appeal to the Student Government (server logic/appeals.py): an optional topic, the words as they are, Anonymous,
  // "Help me clarify" (2-3 tips from the AI, never a rewrite, never a block), Send (always sends). The draft stays on
  // this phone only (localStorage), never on the server. My appeals under it. The section's consent: asked once, on the
  // first send or AI help. The funnel counts taps (lib/stats), never a word.
  import { onMount } from 'svelte';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import { api, ApiErr } from '../../lib/api';
  import { data, loadAppeals } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { i18n } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import { nowTs } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Notice from '../../ui/Notice.svelte';

  let { overlay }: { overlay: Overlay } = $props();

  const DRAFT = 'kb-appeal';
  type Draft = { text: string; topic: AppealTopic | null; anon: boolean };
  function readDraft(): Draft {
    try { const j = JSON.parse(localStorage.getItem(DRAFT) || 'null'); if (j && typeof j.text === 'string') return j; } catch { /* blocked */ }
    return { text: '', topic: null, anon: false };
  }
  const first = readDraft();
  let text = $state(first.text), topic = $state<AppealTopic | null>(first.topic), anon = $state(first.anon);
  let tips = $state<string[]>([]), care = $state<string | null>(null), helping = $state(false), down = $state(false);
  let typed = !!first.text, sent = false;

  $effect(() => {
    const d: Draft = { text, topic, anon };
    try { if (d.text.trim()) localStorage.setItem(DRAFT, JSON.stringify(d)); else localStorage.removeItem(DRAFT); } catch { /* blocked: in memory only */ }
    if (text && !typed) { typed = true; count('apl.typed'); }
  });
  onMount(() => {
    count('apl.open');
    void loadAppeals();
    return () => { if (typed && !sent && text.trim()) count('apl.drop'); };
  });

  /** undefined: agreed before; the version: just agreed; null: said no */
  async function agree(): Promise<string | undefined | null> {
    if (session.me?.appeals?.consent) return undefined;
    const yes = await sheets.ask({ title: t('apl.consentT'), text: t('apl.consentText'), ok: t('apl.consentOk'), cancel: t('common.cancel') });
    return yes ? CONSENT : null;
  }
  const agreed = () => { if (session.me?.appeals) session.me.appeals.consent = true; };

  async function help() {
    const body = text.trim();
    if (!body) { say(t('apl.helpShort'), 'pleading_face_3d'); return; }
    const consent = await agree();
    if (consent === null) return;
    helping = true; down = false; care = null; count('apl.ai');
    try {
      const r = await api.appealHelp(body, i18n.lang, consent);
      agreed(); tips = r.tips; care = r.help ?? null;
      haptic.ok();
    } catch { down = true; } finally { helping = false; }
  }

  async function send() {
    const body = text.trim();
    if (!body || sent) return;
    const consent = await agree();
    if (consent === null) return;
    sent = true;
    const was = { topic, anon }, key = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const temp: Appeal = { id: -Date.now(), topic, text: body, anon, status: 'new', answer: null, at: nowTs(), due: nowTs() + 7 * 86400, answeredAt: null, closedAt: null, overdue: false };
    data.appeals = [temp, ...(data.appeals ?? [])];
    text = ''; topic = null; tips = []; care = null; down = false;
    haptic.ok(); say(t('apl.sent'), 'raising_hands_3d_default');
    try {
      const a = await api.sendAppeal({ text: body, topic: was.topic, anon: was.anon, key, consent });
      agreed(); count('apl.sent');
      data.appeals = (data.appeals ?? []).map((x) => (x.id === temp.id ? a : x));
    } catch (e) {
      data.appeals = (data.appeals ?? []).filter((x) => x.id !== temp.id);
      text = body; topic = was.topic; sent = false; haptic.error();
      say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'apl.slow' : e instanceof ApiErr && e.code === 'unavailable' ? 'common.offline' : 'common.error'), 'pleading_face_3d');
      return;
    }
    sent = false; typed = false;
  }
</script>

<Sheet {overlay} title={t('apl.row')} icon={Megaphone} full>
  <div class="page">
    <div class="chips" role="group" aria-label={t('apl.row')}>
      {#each TOPICS as k (k)}
        <Chip selected={topic === k} onclick={() => { haptic.select(); topic = topic === k ? null : k; }}>{t(`apl.t.${k}`)}</Chip>
      {/each}
    </div>
    <Field label={t('apl.text')} placeholder={t('apl.ph')} bind:value={text} multiline rows={5} maxlength={4000} />
    <Group footnote={anon ? t('apl.anonOn') : t('apl.anonOff')}>
      <Row title={t('apl.anon')} accessory="switch" checked={anon} onchange={(on) => { haptic.select(); anon = on; }} />
    </Group>

    {#if care}<Notice tone="danger" title={t('apl.careT')}><p class="selectable pre">{care}</p></Notice>{/if}
    {#if tips.length}
      <Notice tone="accent" title={t('apl.tips')}><ul class="tips">{#each tips as tip, i (i)}<li>{tip}</li>{/each}</ul></Notice>
    {/if}
    {#if down}<Notice text={t('apl.helpDown')} />{/if}
    <Button kind="secondary" full loading={helping} onclick={help}>{#snippet icon()}<Sparkles size={18} />{/snippet}{t('apl.help')}</Button>
    <p class="fs-sub faint fine">{t('apl.who')}</p>

    {#if data.appeals?.length}
      <Group caption={t('apl.mine')}>
        {#each data.appeals as a (a.id)}
          <Row dense title={headOf(a)} subtitle={`${statusOf(a)} · ${lineOf(a)}`} accessory="chevron"
            onclick={() => { if (a.id > 0) { haptic.tap(); sheets.myAppeal(a.id); } }} />
        {/each}
      </Group>
    {/if}
  </div>

  {#snippet footer()}
    <Button kind="primary" size="l" full disabled={!text.trim()} onclick={send}>{t('apl.send')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  .chips { display: flex; gap: var(--s-2); overflow-x: auto; padding: 4px 0; margin: 0 calc(-1 * var(--s-4)); padding-inline: var(--s-4); scrollbar-width: none; }
  .chips::-webkit-scrollbar { display: none; }
  .tips { margin: var(--s-1) 0 0; padding-left: 1.1em; display: flex; flex-direction: column; gap: 4px; }
  .pre { white-space: pre-line; margin: var(--s-1) 0 0; }
  .fine { margin-top: calc(-1 * var(--s-2)); padding: 0 var(--s-4); }
</style>
