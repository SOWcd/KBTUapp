<script lang="ts">
  // Opening a recruitment round, or changing the live one (PLAN "Casting"; the "casting" right). About three minutes:
  // departments are the club's tags (a new one right here), each with a line about it and maybe places; how many a
  // student may pick; up to six questions of the club's own, from templates or written (in any one language: the screen
  // around them is in the student's language already); the deadline and "results by"; the club's own words for a no.
  // Once someone has applied the questions stay as they are (answers would stop matching them).
  import { untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import Plus from '@lucide/svelte/icons/plus';
  import { api, type ClubTag, type Id, type Round, type RoundKind, type RoundQuestion } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { studioChanged } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { dateInput, fromInputs, nowTs, time } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import { TEAM_COLORS } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, org, round = null, onsaved }: { overlay: Overlay; org: Id; round?: Round | null; onsaved?: () => void } = $props();

  let tags = $state<ClubTag[]>([]);
  $effect(() => { api.teamSetup(org).then((s) => (tags = s.tags)).catch(() => {}); });

  const r0 = untrack(() => round); // the form starts from it once
  let title = $state(r0?.title ?? t('cast.defTitle', { year: new Date().getFullYear() }));
  let picks = $state(r0?.picks ?? 2);
  let closeDate = $state(dateInput(r0?.closesAt ?? nowTs() + 7 * 86400)), closeTime = $state(r0 ? time(r0.closesAt) : '23:59');
  let resultsDate = $state(r0?.resultsBy ? dateInput(r0.resultsBy) : '');
  let deps = $state<{ tagId: Id; about: string; places: string }[]>(r0?.departments.map((d) => ({ tagId: d.tagId, about: d.about, places: d.places ? String(d.places) : '' })) ?? []);
  let qs = $state<RoundQuestion[]>(r0?.questions.map((q) => ({ ...q })) ?? []);
  let decline = $state(r0?.declineText ?? '');
  const locked = $derived(!!r0 && Object.values(r0.counts ?? {}).some((n) => (n ?? 0) > 0)); // someone applied: the questions stay
  let busy = $state(false), tried = $state(false);

  const KINDS: RoundKind[] = ['short', 'long', 'one', 'many', 'link'];
  const TEMPLATES: (RoundQuestion & { key: string })[] = [
    { key: 'hours', kind: 'one', text: t('cast.tplHours'), options: ['1-4', '5-8', '9-12', '13+'], required: true },
    { key: 'why', kind: 'long', text: t('cast.tplWhy'), required: true },
    { key: 'about', kind: 'long', text: t('cast.tplAbout'), required: false },
    { key: 'portfolio', kind: 'link', text: t('cast.tplPortfolio'), required: false },
    { key: 'exp', kind: 'long', text: t('cast.tplExp'), required: false },
    { key: 'insta', kind: 'short', text: t('cast.tplInsta'), required: false },
  ];
  const used = (txt: string) => qs.some((q) => q.text === txt);
  function addQ(q: RoundQuestion) { if (qs.length < 6) qs = [...qs, { ...q, options: q.options ? [...q.options] : null, tagId: null }]; }

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
    } catch { say(t('common.error'), 'pleading_face_3d'); }
  }

  const closes = $derived(fromInputs(closeDate, closeTime));
  const results = $derived(resultsDate ? fromInputs(resultsDate, '20:00') : null);
  const err = $derived(!title.trim() ? 'title' : !Number.isFinite(closes) || closes <= nowTs() ? 'when' : results != null && results < closes ? 'results'
    : !deps.length ? 'deps' : qs.some((q) => !q.text.trim() || ((q.kind === 'one' || q.kind === 'many') && (q.options ?? []).filter((o) => o.trim()).length < 2)) ? 'qs' : '');

  async function save() {
    tried = true;
    if (err) { haptic.error(); return; }
    busy = true;
    const input = { title: title.trim(), picks, closesAt: closes, resultsBy: results, declineText: decline.trim(),
      departments: deps.map((d) => ({ tagId: d.tagId, about: d.about.trim(), places: +d.places > 0 ? +d.places : null })),
      questions: qs.map((q) => ({ kind: q.kind, text: q.text.trim(), options: q.kind === 'one' || q.kind === 'many' ? (q.options ?? []).map((o) => o.trim()).filter(Boolean) : null,
        required: q.required, tagId: q.tagId ?? null })) };
    try {
      if (r0) await api.updateRound(r0.id, input); else await api.openRound(org, input);
      haptic.ok(); say(r0 ? t('cast.updated') : t('cast.opened'), 'party_popper_3d');
      studioChanged(); onsaved?.(); close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} full title={r0 ? t('cast.edit') : t('cast.open')}>
  <h2 class="t-h2">{r0 ? t('cast.edit') : t('cast.open')}</h2>
  <p class="t-foot sub">{t('cast.openSub')}</p>

  <label class="field" class:bad={tried && err === 'title'}><span class="t-cap">{t('cast.name')}</span><input bind:value={title} maxlength="80" /></label>

  <h3 class="t-cap sec">{t('cast.deps')}</h3>
  <p class="hint">{t('cast.depsHint')}</p>
  <div class="tags">
    {#each tags as g (g.id)}<button class:on={deps.some((d) => d.tagId === g.id)} style="--c:{g.color}" onclick={() => toggleDep(g.id)}><i></i>{g.name}</button>{/each}
  </div>
  <div class="newtag"><input class="field" bind:value={newTag} maxlength="30" placeholder={t('cast.newTag')} /><button onclick={makeTag} disabled={!newTag.trim()}><Plus size={18} /></button></div>
  {#each deps as d (d.tagId)}
    {@const g = tags.find((x) => x.id === d.tagId)}
    <div class="dep" style="--c:{g?.color ?? 'var(--accent)'}">
      <b>{g?.name ?? '…'}</b>
      <div class="two">
        <label class="field"><span class="t-cap">{t('cast.about')}</span><input bind:value={d.about} maxlength="200" placeholder={t('cast.aboutPh')} /></label>
        <label class="field small"><span class="t-cap">{t('cast.places')}</span><input bind:value={d.places} type="number" inputmode="numeric" min="1" placeholder="—" /></label>
      </div>
    </div>
  {/each}
  {#if tried && err === 'deps'}<p class="err">{t('cast.needDeps')}</p>{/if}
  {#if deps.length > 1}
    <span class="t-cap lbl">{t('cast.picks')}</span>
    <div class="seg">{#each [1, 2, 3] as n (n)}<button class:on={picks === n} onclick={() => (picks = n)} disabled={n > deps.length}>{n}</button>{/each}</div>
  {/if}

  <h3 class="t-cap sec">{t('cast.questions')}</h3>
  <p class="hint">{locked ? t('cast.qsLocked') : t('cast.qsHint')}</p>
  {#each qs as q, i (i)}
    <div class="qcard surface">
      <div class="qtop">
        <select bind:value={q.kind} disabled={locked}>{#each KINDS as k (k)}<option value={k}>{t(`cast.kind.${k}`)}</option>{/each}</select>
        {#if !locked}<button class="x" onclick={() => (qs = qs.filter((_, j) => j !== i))} aria-label={t('memo.drop')}><X size={16} /></button>{/if}
      </div>
      <label class="field"><input bind:value={q.text} maxlength="200" placeholder={t('cast.qText')} disabled={locked} /></label>
      {#if q.kind === 'one' || q.kind === 'many'}
        <label class="field"><span class="t-cap">{t('cast.options')}</span>
          <textarea rows="3" disabled={locked} value={(q.options ?? []).join('\n')} oninput={(e) => (q.options = (e.currentTarget as HTMLTextAreaElement).value.split('\n'))}></textarea></label>
      {/if}
      <div class="qbot">
        <label class="chk"><input type="checkbox" bind:checked={q.required} disabled={locked} />{t('cast.required')}</label>
        {#if deps.length > 1}
          <select bind:value={q.tagId} disabled={locked}><option value={null}>{t('cast.forAll')}</option>
            {#each deps as d (d.tagId)}<option value={d.tagId}>{t('cast.onlyFor', { name: tags.find((x) => x.id === d.tagId)?.name ?? '' })}</option>{/each}</select>
        {/if}
      </div>
    </div>
  {/each}
  {#if tried && err === 'qs'}<p class="err">{t('cast.needQs')}</p>{/if}
  {#if !locked && qs.length < 6}
    <div class="tpls">
      {#each TEMPLATES.filter((x) => !used(x.text)) as x (x.key)}<button onclick={() => addQ(x)}><Plus size={14} />{x.text}</button>{/each}
      <button onclick={() => addQ({ kind: 'short', text: '', required: true })}><Plus size={14} />{t('cast.ownQ')}</button>
    </div>
  {/if}

  <h3 class="t-cap sec">{t('cast.dates')}</h3>
  <div class="two">
    <label class="field" class:bad={tried && err === 'when'}><span class="t-cap">{t('cast.closes')}</span><input type="date" bind:value={closeDate} /></label>
    <label class="field" class:bad={tried && err === 'when'}><span class="t-cap">{t('ed.regTime')}</span><input type="time" bind:value={closeTime} /></label>
  </div>
  <label class="field" class:bad={tried && err === 'results'}><span class="t-cap">{t('cast.resultsBy')}</span><input type="date" bind:value={resultsDate} /></label>
  <p class="hint">{t('cast.resultsHint')}</p>

  <label class="field"><span class="t-cap">{t('cast.decline')}</span><textarea rows="3" maxlength="500" bind:value={decline} placeholder={t('cast.declinePh')}></textarea></label>

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={save}>{r0 ? t('common.save') : t('cast.openGo')}</Button>
  {/snippet}
</Sheet>

<style>
  .sub { margin: 2px 0 14px; }
  .sec { margin: 22px 2px 6px; }
  .lbl { display: block; margin: 12px 2px 6px; }
  .hint { margin: 0 4px 8px; font: 500 12.5px/1.35 var(--font-text); color: var(--text-3); }
  .tags { display: flex; flex-wrap: wrap; gap: 6px; }
  .tags button { display: flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2);
    font: 600 14px/1 var(--font-text); color: var(--text-2); }
  .tags button.on { background: var(--text); color: var(--bg); }
  .tags i { width: 9px; height: 9px; border-radius: 50%; background: var(--c); }
  .newtag { display: flex; gap: 8px; margin-top: 8px; }
  .newtag input { flex: 1; min-width: 0; font: 550 15px/1.3 var(--font-text); }
  .newtag button { flex: none; width: 44px; border-radius: var(--r-m); background: var(--accent-soft); color: var(--accent-text); display: flex; align-items: center; justify-content: center; }
  .dep { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; padding-left: 12px; border-left: 3px solid var(--c); }
  .dep b { font: 650 15px/1.2 var(--font-text); }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .dep .two { grid-template-columns: 1fr 96px; }
  .qcard { display: flex; flex-direction: column; gap: 8px; margin-bottom: 8px; padding: 10px; }
  .qtop, .qbot { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  select { height: 34px; padding: 0 10px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text); font: 600 13.5px/1 var(--font-text); max-width: 60%; }
  .x { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: var(--text-2); background: var(--surface-2); }
  .chk { display: flex; align-items: center; gap: 8px; font: 550 14px/1.2 var(--font-text); }
  .chk input { width: 18px; height: 18px; accent-color: var(--accent); }
  .tpls { display: flex; flex-wrap: wrap; gap: 6px; }
  .tpls button { display: inline-flex; align-items: center; gap: 5px; height: 34px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft);
    color: var(--accent-text); font: 620 13.5px/1 var(--font-text); }
  .err { margin: 6px 4px 0; font: 600 12.5px/1.3 var(--font-text); color: var(--danger-text); }
</style>
