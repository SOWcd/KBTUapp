<script lang="ts">
  // A subject's card: its name and codes, "Looking for study partners" (my one switch, an optional note under it), and
  // who else chose to be listed: face, name, year, school, their note; "Study together" sends the find-people offer they
  // accept in the bot (then each gets the other's Telegram: "Write"). Nobody here is shown for merely taking the
  // subject. Every tap answers at once and comes back on a refusal; the name shows before the people come.
  import BookOpen from '@lucide/svelte/icons/book-open';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Flag from '@lucide/svelte/icons/flag';
  import { ApiErr, api, type SubjectCard, type SubjectPerson } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { subj, subjectCard, keepCard } from '../../lib/state/subjects.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { schoolShort } from '../../lib/short';
  import { dayMonth } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { menu } from '../../ui/menu';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, id }: { overlay: Overlay; id: string } = $props();
  let card = $state<SubjectCard | null>(null), note = $state(''), saving = $state(false);
  const base = $derived(card ?? subj.all?.subjects.find((s) => s.id === id) ?? null);
  const mine = $derived(card?.mine ?? null);
  const set = (c: SubjectCard) => { card = c; keepCard(c); note = c.mine?.note ?? ''; };
  $effect(() => { subjectCard(id).then(set, () => say(t('common.error'), 'pleading_face_3d')); });

  function fail(e: unknown) {
    if (e instanceof ApiErr && e.code === 'forbidden') return; // the policy's gate asks in place (api client)
    haptic.error();
    say(t(e instanceof ApiErr && e.message === 'link' ? 'sj.linkErr' : e instanceof ApiErr && e.message === 'subjects' ? 'sj.many' : 'common.error'), 'pleading_face_3d');
  }
  // my mark in the list's "mine" too
  function listed(on: boolean) { if (subj.all) subj.all.mine = on ? [...new Set([...subj.all.mine, id])] : subj.all.mine.filter((x) => x !== id); }

  async function toggle(on: boolean) {
    if (!card) return;
    const before = card;
    haptic.tap();
    card = { ...card, mine: on ? { note: '', status: 'live', why: null, until: 0 } : null };
    if (!on) note = '';
    listed(on);
    try { if (on) set(await api.joinSubject(id, '')); else { await api.leaveSubject(id); keepCard(card); } }
    catch (e) { card = before; note = before.mine?.note ?? ''; listed(!on); fail(e); }
  }
  async function save() {
    saving = true;
    try { set(await api.joinSubject(id, note.trim())); haptic.ok(); } catch (e) { fail(e); } finally { saving = false; }
  }
  async function offer(p: SubjectPerson) {
    haptic.tap();
    p.offered = 'pending';
    try { await api.subjectOffer(p.ask); haptic.ok(); say(t('sj.sentSay'), 'raising_hands_3d_default'); if (card) keepCard(card); }
    catch (e) { p.offered = null; fail(e); }
  }
  const more = (e: MouseEvent, p: SubjectPerson) => menu(e.currentTarget as Element,
    [{ label: t('cm.report'), icon: Flag, destructive: true, onselect: () => sheets.report('ask', p.ask, p.note ?? p.name) }], 'end');
  const status = $derived(mine?.status === 'held' ? t('sj.held') : mine?.status === 'hidden' ? t('sj.hidden') : null);
</script>

<Sheet {overlay} tall heading={base?.name ?? t('sj.title')} icon={BookOpen}>
  <div class="col">
    {#if base?.codes.length}<p class="codes num">{base.codes.join(' · ')}</p>{/if}

    <Group footnote={status ?? (mine?.until ? t('sj.listNote', { when: dayMonth(mine.until) }) : t('sj.listOff'))}>
      <Row title={t('sj.listMe')} accessory="switch" checked={!!mine} disabled={!card} onchange={toggle} />
    </Group>
    {#if mine}
      <div class="note">
        <Field label={t('sj.note')} bind:value={note} placeholder={t('sj.notePh')} maxlength={140} multiline rows={2} />
        {#if note.trim() !== (mine.note ?? '')}<Button kind="tinted" size="s" loading={saving} onclick={save}>{t('sj.save')}</Button>{/if}
      </div>
    {/if}

    {#if card}
      <Group caption={t('sj.people')}>
        {#each card.people as p (p.ask)}
          <div class="p">
            <Avatar person={p.person} size={40} />
            <span class="tx">
              <b class="ellipsis">{p.name}</b>
              <span class="meta ellipsis">{[p.course ? t('fo.course', { n: p.course }) : '', schoolShort(p.school)].filter(Boolean).join(' · ')}</span>
            </span>
            <IconButton kind="plain" size="s" icon={Ellipsis} label={t('common.more')} onclick={(e) => more(e, p)} />
            <!-- their note, then the one way to them: under the name, the whole width (a 320 px phone keeps the name) -->
            {#if p.note}<p class="nt">{p.note}</p>{/if}
            <span class="act">
              {#if p.telegram}<Button kind="tinted" size="s" onclick={() => openLink(p.telegram!)}>{t('sj.write')}</Button>
              {:else if p.offered}<span class="sent">{t('sj.sent')}</span>
              {:else}<Button kind="tinted" size="s" onclick={() => offer(p)}>{t('sj.together')}</Button>{/if}
            </span>
          </div>
        {:else}
          <EmptyState inline text={t('sj.none')} />
        {/each}
      </Group>
    {/if}
  </div>
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--gap-group); padding-bottom: var(--s-6); }
  .codes { margin: calc(var(--s-2) * -1) var(--s-1) 0; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .note { display: flex; flex-direction: column; align-items: flex-end; gap: var(--s-2); margin-top: calc(var(--gap-group) / -2); }
  .note > :global(*:first-child) { align-self: stretch; }
  .p { position: relative; display: grid; grid-template-columns: 40px minmax(0, 1fr) auto; align-items: center; column-gap: var(--s-3); padding: var(--s-3) var(--s-2) var(--s-3) var(--s-4); }
  .p + .p::before { content: ''; position: absolute; top: 0; left: calc(var(--s-4) + 40px + var(--s-3)); right: 0; height: 0.5px; background: var(--separator); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  .meta { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .nt { grid-column: 2 / -1; margin: var(--s-1) var(--s-2) 0 0; font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-2); overflow-wrap: anywhere; }
  .act { grid-column: 2 / -1; display: flex; margin-top: var(--s-2); }
  .sent { font: 500 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
</style>
