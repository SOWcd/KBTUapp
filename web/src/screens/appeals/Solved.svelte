<script lang="ts">
  // "Solved by your appeals" (server appeals.solved): SG's two general lines, what was raised and what changed,
  // newest first, 5 then "Show all". Never an appeal's words, never linked to one. Students get it from 3 entries (the
  // server sends nothing before); SG's people see it from the first, with that said. edit: the SG panel's own side,
  // Add (checked as typed, lib/solved) and Delete (confirmed, Undo). Loaded with my appeals, one request.
  import Trash from '@lucide/svelte/icons/trash-2';
  import { api, ApiErr, type AppealTopic, type Solved } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say } from '../../lib/state/ui.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { monthName, solvedClean, solvedWhy, type SolvedWhy } from '../../lib/solved';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import { TOPICS } from './Appeals.svelte';

  let { edit = false }: { edit?: boolean } = $props();
  const FIRST = 5, SHOWN = 3; // SHOWN: the server's SOLVED_SHOWN
  let all = $state(false), adding = $state(false);
  let raised = $state(''), changed = $state(''), topic = $state<AppealTopic | null>(null);
  const shown = $derived(all ? data.solved : data.solved.slice(0, FIRST));
  const hint = $derived(!!session.me?.appeals?.sg && data.solved.length < SHOWN ? t('apl.solvedHint') : undefined);
  const meta = (e: Solved) => [e.topic ? t(`apl.t.${e.topic}`) : '', monthName(e.month, i18n.lang)].filter(Boolean).join(' · ');
  // a line's problem said as it's typed; too short only blocks Add (the placeholders show the size)
  const said = (s: string) => { const w = s.trim() ? solvedWhy(s) : null; return w && w !== 'length' ? t(`apl.solvedWhy.${w}`) : undefined; };
  const ready = $derived(!solvedWhy(raised) && !solvedWhy(changed));

  async function add() {
    if (!ready) return;
    const was = { raised, changed, topic };
    const temp: Solved = { id: -Date.now(), raised: solvedClean(raised), changed: solvedClean(changed), topic, month: new Date().toISOString().slice(0, 7) };
    data.solved = [temp, ...data.solved];
    raised = ''; changed = ''; topic = null; adding = false;
    haptic.ok(); say(t('apl.solvedAdded'), 'raising_hands_3d_default');
    try {
      const e = await api.solvedAdd({ raised: temp.raised, changed: temp.changed, topic: temp.topic });
      data.solved = data.solved.map((x) => (x.id === temp.id ? e : x));
    } catch (err) {
      data.solved = data.solved.filter((x) => x.id !== temp.id);
      ({ raised, changed, topic } = was); adding = true; haptic.error();
      const why = err instanceof ApiErr && err.code === 'bad_input' ? (err.message as SolvedWhy) : null;
      say(err instanceof ApiErr && err.code === 'rate_limited' ? t('apl.solvedCap')
        : why && ['length', 'link', 'contact', 'number'].includes(why) ? t(`apl.solvedWhy.${why}`) : t('common.error'), 'pleading_face_3d');
    }
  }

  async function drop(e: Solved) {
    if (!(await sheets.ask({ title: t('apl.solvedDelQ'), text: t('apl.solvedDelText'), ok: t('apl.solvedDel'), cancel: t('common.cancel'), danger: true }))) return;
    const back = () => { if (!data.solved.some((x) => x.id === e.id)) data.solved = [...data.solved, e].sort((a, b) => b.id - a.id); };
    data.solved = data.solved.filter((x) => x.id !== e.id);
    const gone = api.solvedDrop(e.id);
    haptic.ok();
    say(t('apl.solvedGone'), 'waving_hand_3d_default', () => {
      back();
      gone.then(() => api.solvedRestore(e.id)).catch((err) => {
        data.solved = data.solved.filter((x) => x.id !== e.id);
        say(t(err instanceof ApiErr && err.code === 'rate_limited' ? 'apl.solvedCap' : 'common.error'), 'pleading_face_3d');
      });
    });
    try { await gone; } catch { back(); haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

{#if data.solved.length || edit}
  <Group caption={t('apl.solved')} footnote={edit ? t('apl.solvedRule') : hint}>
    {#each shown as e (e.id)}
      {#snippet del()}<IconButton icon={Trash} size="s" label={t('apl.solvedDel')} disabled={e.id < 0} onclick={() => drop(e)} />{/snippet}
      <Row dense title={e.changed} subtitle={`${e.raised} · ${meta(e)}`} trailing={edit ? del : undefined} />
    {/each}
    {#if data.solved.length > FIRST && !all}
      <Row tone="action" title={t('apl.solvedAll')} onclick={() => { haptic.tap(); all = true; }} />
    {/if}
    {#if edit}
      <Row tone="add" title={t('apl.solvedAdd')} accessory="disclosure" open={adding} onclick={() => { haptic.select(); adding = !adding; }} />
    {/if}
  </Group>
  {#if edit && hint}<p class="fs-sub faint hint">{hint}</p>{/if}
  {#if edit && adding}
    <div class="form">
      <Field label={t('apl.solvedRaised')} placeholder={t('apl.solvedRaisedPh')} bind:value={raised} multiline rows={2} maxlength={140} error={said(raised)} />
      <Field label={t('apl.solvedChanged')} placeholder={t('apl.solvedChangedPh')} bind:value={changed} multiline rows={2} maxlength={140} error={said(changed)} />
      <div class="chips" role="group" aria-label={t('apl.solvedAdd')}>
        {#each TOPICS as k (k)}
          <Chip selected={topic === k} onclick={() => { haptic.select(); topic = topic === k ? null : k; }}>{t(`apl.t.${k}`)}</Chip>
        {/each}
      </div>
      <Button kind="primary" full disabled={!ready} onclick={add}>{t('apl.solvedAdd')}</Button>
    </div>
  {/if}
{/if}

<style>
  .form { display: flex; flex-direction: column; gap: var(--s-3); }
  .chips { display: flex; gap: var(--s-2); overflow-x: auto; padding: 4px var(--s-4); margin: 0 calc(-1 * var(--s-4)); scrollbar-width: none; }
  .chips::-webkit-scrollbar { display: none; }
  .hint { margin: calc(-1 * var(--s-2)) 0 0; padding: 0 var(--s-4); }
</style>
