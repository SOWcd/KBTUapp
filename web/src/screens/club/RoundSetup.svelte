<script lang="ts">
  // Opening a recruitment round, or changing the live one (PLAN "Casting"; the "casting" right). About three minutes:
  // departments (optional: none is a round for the whole club) are the club's tags (a new one right here), each with a line about it and maybe places; how many a
  // student may pick; up to six questions of the club's own, from templates or written (in any one language: the screen
  // around them is in the student's language already); the deadline and "results by"; "what's next" (in-person
  // auditions: dates, place) shown under the student's steps; the club's own words for a no; the group's invite for the
  // accepted (https://t.me/... only: the app shows it to them, the bot never posts it).
  // Once someone has applied the questions stay as they are (answers would stop matching them).
  import { untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import Plus from '@lucide/svelte/icons/plus';
  import { api, type ClubTag, type Id, type Round, type RoundQuestion } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, studioChanged } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { dateInput, fromInputs, nowTs, time } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import { TEAM_COLORS } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import QuestionsEditor, { toSave, unfinished } from './QuestionsEditor.svelte';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import ClipboardPen from '@lucide/svelte/icons/clipboard-pen';
  import { phrase } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { may } from '../../lib/perms';

  let { overlay, org, round = null, onsaved }: { overlay: Overlay; org: Id; round?: Round | null; onsaved?: () => void } = $props();

  // "Always open" (any-time applications, the team right) sits on top here: Studio's Recruiting opens this form directly (owner, Nov 14)
  const o = $derived(data.orgs.find((x) => x.id === org));
  const team = $derived(may(session.me?.memberships.find((x) => x.org.id === org), 'team'));
  async function setOpen(on: boolean) {
    if (!o) return;
    o.recruiting = on;
    try { Object.assign(o, await api.setRecruiting(org, on)); say(phrase(on ? 'say.recruitOn' : 'say.recruitOff'), on ? 'raising_hands_3d_default' : 'sparkles_3d'); studioChanged(); }
    catch { o.recruiting = !on; say(t('common.error'), 'warning_3d'); }
  }

  let tags = $state<ClubTag[]>([]);
  // a picked department deleted in Team setup leaves the round too
  const readTags = () => api.teamSetup(org).then((s) => { tags = s.tags; deps = deps.filter((d) => s.tags.some((x) => x.id === d.tagId)); }).catch(() => {});
  $effect(() => { void readTags(); });

  const r0 = untrack(() => round); // the form starts from it once
  let title = $state(r0?.title ?? t('cast.defTitle', { club: data.orgs.find((o) => o.id === org)?.name ?? '' }));
  let picks = $state(r0?.picks ?? 2);
  let closeDate = $state(dateInput(r0?.closesAt ?? nowTs() + 7 * 86400)), closeTime = $state(r0 ? time(r0.closesAt) : '23:59');
  let resultsDate = $state(r0?.resultsBy ? dateInput(r0.resultsBy) : '');
  let deps = $state<{ tagId: Id; about: string; places: string }[]>(r0?.departments.map((d) => ({ tagId: d.tagId, about: d.about, places: d.places ? String(d.places) : '' })) ?? []);
  let qs = $state<RoundQuestion[]>(r0?.questions.map((q) => ({ ...q })) ?? []);
  let decline = $state(r0?.declineText ?? '');
  let next = $state(r0?.nextText ?? '');
  let group = $state(r0?.groupLink ?? '');
  // the server takes https://t.me/... only; a bare t.me/... gets its https here
  const groupUrl = $derived(group.trim() && !/^https?:\/\//.test(group.trim()) ? 'https://' + group.trim() : group.trim());
  const locked = $derived(!!r0 && Object.values(r0.counts ?? {}).some((n) => (n ?? 0) > 0)); // someone applied: the questions stay
  let busy = $state(false), tried = $state(false);

  function toggleDep(id: Id) {
    haptic.select();
    deps = deps.some((d) => d.tagId === id) ? deps.filter((d) => d.tagId !== id) : [...deps, { tagId: id, about: '', places: '' }];
  }
  let newTag = $state('');
  async function makeTag() {
    const name = newTag.trim();
    if (!name) return;
    try {
      const s = await api.saveTag(org, { name, color: TEAM_COLORS[tags.length % TEAM_COLORS.length] });
      tags = s.tags; newTag = '';
      const made = s.tags.find((x) => x.name === name);
      if (made && !deps.some((d) => d.tagId === made.id)) deps = [...deps, { tagId: made.id, about: '', places: '' }];
    } catch { say(t('common.error'), 'warning_3d'); }
  }
  const tagName = (id: Id) => tags.find((x) => x.id === id)?.name ?? '';

  const closes = $derived(fromInputs(closeDate, closeTime));
  const results = $derived(resultsDate ? fromInputs(resultsDate, '20:00') : null);
  const err = $derived(!title.trim() ? 'title' : !Number.isFinite(closes) || closes <= nowTs() ? 'when' : results != null && results < closes ? 'results'
    : unfinished(qs) ? 'qs' : groupUrl && !/^https:\/\/t\.me\/[\w+/-]{2,120}$/.test(groupUrl) ? 'group' : '');

  async function save() {
    tried = true;
    if (err) { haptic.error(); return; }
    busy = true;
    const input = { title: title.trim(), picks: Math.min(picks, Math.max(1, deps.length)), closesAt: closes, resultsBy: results, declineText: decline.trim(), nextText: next.trim(), groupLink: groupUrl || null,
      departments: deps.map((d) => ({ tagId: d.tagId, about: d.about.trim(), places: +d.places > 0 ? +d.places : null })),
      questions: toSave(qs) };
    try {
      if (r0) await api.updateRound(r0.id, input); else await api.openRound(org, input);
      haptic.ok(); say(r0 ? t('cast.updated') : t('cast.opened'), 'party_popper_3d');
      studioChanged(); onsaved?.(); close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={Megaphone} full title={r0 ? t('cast.edit') : t('cast.open')}>
  <div class="stack">
    {#if team && o}
      <Group footnote={t('jr.openHint')}>
        <Row icon={UserPlus} title={t('jr.open')} accessory="switch" checked={o.recruiting} onchange={(on) => { haptic.tap(); void setOpen(on); }} />
        {#if o.recruiting}<Row icon={ClipboardPen} title={t('cast.questions')} value={o.joinQuestions?.length ? String(o.joinQuestions.length) : t('jr.qsNone')} accessory="chevron" onclick={() => sheets.joinQuestions(org)} />{/if}
      </Group>
    {/if}
    <p class="hint">{t('cast.openSub')}</p>

    <Field label={t('cast.name')} bind:value={title} maxlength={80} error={tried && err === 'title' ? t('ed.need') : undefined} />

    <h3 class="cap">{t('cast.deps')}</h3>
    <p class="hint">{t('cast.depsHint')}</p>
    {#if tags.length}
      <div class="wrap">
        {#each tags as g (g.id)}<Chip selected={deps.some((d) => d.tagId === g.id)} onclick={() => toggleDep(g.id)}><i class="dot" style:--c={g.color}></i>{g.name}</Chip>{/each}
      </div>
    {/if}
    <div class="newtag"><Field label={t('cast.newTag')} bind:value={newTag} maxlength={30} />
      <IconButton icon={Plus} kind="tinted" label={t('cast.newTag')} disabled={!newTag.trim()} onclick={makeTag} /></div>
    <Group><Row dense title={t('cast.manageDeps')} accessory="chevron" onclick={() => sheets.teamSetup(org, readTags)} /></Group>
    {#each deps as d (d.tagId)}
      {@const g = tags.find((x) => x.id === d.tagId)}
      <div class="dep" style:--c={g?.color ?? 'var(--accent)'}>
        <b>{g?.name ?? '…'}</b>
        <div class="two">
          <Field label={t('cast.about')} bind:value={d.about} maxlength={200} placeholder={t('cast.aboutPh')} />
          <Field label={t('cast.places')} bind:value={d.places} type="number" inputmode="numeric" placeholder="—" />
        </div>
      </div>
    {/each}
    {#if deps.length > 1}
      <span class="lbl">{t('cast.picks')}</span>
      <Segmented items={[1, 2, 3].slice(0, deps.length).map((n) => ({ value: n, label: String(n) }))} bind:value={picks} label={t('cast.picks')} />
    {/if}

    <h3 class="cap">{t('cast.questions')}</h3>
    <p class="hint">{locked ? t('cast.qsLocked') : t('cast.qsHint')}</p>
    <QuestionsEditor bind:qs {locked} deps={deps.map((d) => d.tagId)} {tagName} error={tried && err === 'qs'} />

    <h3 class="cap">{t('cast.dates')}</h3>
    <!-- engine: Field has no date/time type: by hand, in Field's look (.fl) -->
    <div class="two">
      <label class="fl" class:bad={tried && err === 'when'}><span>{t('cast.closes')}</span><input type="date" bind:value={closeDate} /></label>
      <label class="fl" class:bad={tried && err === 'when'}><span>{t('ed.regTime')}</span><input type="time" bind:value={closeTime} /></label>
    </div>
    <label class="fl" class:bad={tried && err === 'results'}><span>{t('cast.resultsBy')}</span><input type="date" bind:value={resultsDate} /></label>
    <p class="hint">{t('cast.resultsHint')}</p>

    <Field label={t('cast.next')} multiline rows={3} maxlength={300} bind:value={next} placeholder={t('cast.nextPh')} />
    <Field label={t('cast.decline')} multiline rows={3} maxlength={500} bind:value={decline} placeholder={t('cast.declinePh')} />
    <Field label={t('cast.group')} bind:value={group} maxlength={140} inputmode="url" placeholder="https://t.me/+…"
      error={tried && err === 'group' ? t('cast.groupBad') : undefined} />
    <p class="hint">{t('cast.groupHint')}</p>
  </div>

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={save}>{r0 ? t('common.save') : t('cast.openGo')}</Button>
  {/snippet}
</Sheet>

<style>
  .stack { display: flex; flex-direction: column; gap: var(--s-3); }
  .hint { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  .cap + .hint { margin-top: -6px; }
  /* a heading in Group's caption style, over what isn't a list */
  .cap { margin: var(--s-4) var(--s-1) 0; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .lbl { margin: 0 var(--s-4) -6px; font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .wrap { display: flex; flex-wrap: wrap; gap: var(--s-2); padding-block: var(--s-1); }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--c); }
  .newtag { display: flex; align-items: flex-end; gap: var(--s-2); }
  .newtag > :global(:first-child) { flex: 1; min-width: 0; }
  .newtag > :global(:last-child) { margin-bottom: 3px; }
  .dep { display: flex; flex-direction: column; gap: var(--s-2); padding-left: var(--s-3); border-left: 3px solid var(--c); }
  .dep b { font: 600 var(--fs-body)/1.2 var(--font-text); }
  .two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-2); align-items: end; }
  .dep .two { grid-template-columns: minmax(0, 1fr) 96px; }
  /* Field's look for the date and time inputs it can't take yet */
  .fl { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .fl > span { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .fl > input { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
  .fl.bad > input { box-shadow: inset 0 0 0 1.5px var(--danger); }
</style>
