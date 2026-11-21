<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import ListTree from '@lucide/svelte/icons/list-tree';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Trophy from '@lucide/svelte/icons/trophy';
  import { api, ApiErr, type BracketMatch, type EventBracket, type Id, type MatchScore } from '../../lib/api';
  import { editableMatch, lockedMatches, scoreNumber, stages } from '../../lib/bracket';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { errorText } from '../../lib/state/data.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { haptic } from '../../lib/tg';
  import Button from '../../ui/Button.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Group from '../../ui/Group.svelte';
  import Sheet from '../../ui/Sheet.svelte';

  let { overlay, id, manage, seed, onchange }: {
    overlay: Overlay; id: Id; manage: boolean; seed: EventBracket; onchange: (board: EventBracket) => void;
  } = $props();
  let board = $state.raw(untrack(() => seed));
  let editing = $state.raw<BracketMatch | null>(null), home = $state(''), away = $state('');
  let pending = $state.raw<BracketMatch | null>(null), busy = $state(false), stale = $state(false);
  const names = $derived(new Map(board.teams.map((team) => [team.id, team.name])));
  const locked = $derived(lockedMatches(board));
  const h = $derived(scoreNumber(home)), a = $derived(scoreNumber(away));
  const tied = $derived(h !== null && h === a);
  const canSave = $derived(h !== null && a !== null && !tied && editing?.home != null && editing.away != null);

  function put(next: EventBracket) {
    if (editing) {
      const current = next[editing.stage].find((r) => r.round === editing?.round)?.matches.find((m) => m.id === editing?.id);
      if (!current || current.home !== editing.home || current.away !== editing.away ||
          current.home_score !== editing.home_score || current.away_score !== editing.away_score) editing = null;
    }
    board = next; pending = null; stale = false; onchange(next);
  }
  // A slow read started on open must never overwrite a score entered from the prefetched board.
  let version = 0;
  async function refresh() {
    const read = ++version;
    try { const next = await api.eventBracket(id); if (read === version) put(next); }
    catch { if (read === version) stale = true; }
  }
  onMount(() => { void refresh(); });

  const reasons = new Map<string, Key>([
    ['bracket_teams', 'br.needTeams'], ['bracket_dependent_scored', 'br.locked'], ['bracket_tbd', 'br.waiting'],
    ['bracket_draw', 'br.tie'], ['groups_scored', 'gr.scored'], ['bracket_scored', 'br.started'],
  ]);
  function fail(err: unknown) {
    const message = err instanceof ApiErr ? err.message : '';
    const reason = reasons.get(message);
    haptic.error();
    say(reason ? t(reason) : errorText(err), 'pleading_face_3d');
  }

  async function draw() {
    if (!manage || busy || stale || board.upper.length) return;
    busy = true;
    try {
      if (!(await sheets.ask({ title: t('br.drawAsk'), text: t('br.drawText'), ok: t('br.draw'), cancel: t('common.cancel') }))) return;
      if (stale || board.upper.length) return;
      ++version;
      put(await api.drawBracket(id, 'random')); haptic.ok();
    } catch (err) { fail(err); await refresh(); }
    finally { busy = false; }
  }

  function edit(match: BracketMatch) {
    editing = match;
    home = match.home_score?.toString() ?? ''; away = match.away_score?.toString() ?? '';
  }
  async function save(match: BracketMatch, score: MatchScore | null) {
    if (!manage || busy || stale || !editableMatch(match, locked)) return;
    ++version; busy = true; editing = null;
    pending = { ...match, home_score: score?.home_score ?? null, away_score: score?.away_score ?? null,
      winner: score ? (score.home_score > score.away_score ? match.home : match.away) : null };
    try {
      const saved = await api.scoreMatch(id, match.id, score);
      if ('stage' in saved) pending = saved;
      haptic.ok();
    }
    catch (err) { pending = null; fail(err); }
    // Only the server advances teams. Keep an accepted score visible even if this read needs a retry.
    await refresh(); busy = false;
  }
  function submit(e: SubmitEvent, match: BracketMatch) {
    e.preventDefault();
    if (canSave && h !== null && a !== null) void save(match, { home_score: h, away_score: a });
  }
  function name(id: Id | null, status: BracketMatch['status']) {
    if (id !== null) return names.get(id);
    if (status === 'pending') return t('br.tbd');
    if (status === 'played') return t('br.removed');
    return t('br.noTeam');
  }
</script>

<Sheet {overlay} icon={ListTree} full title={t('br.title')}>
  <div class="board">
    {#if stale}
      <div class="retry"><span>{t('br.loadError')}</span><Button kind="secondary" size="s" onclick={refresh}>{t('common.retry')}</Button></div>
    {/if}
    {#if !board.upper.length}
      <EmptyState inline text={t('br.none')} />
      {#if manage}<Button full loading={busy} disabled={stale} onclick={draw}>{t('br.draw')}</Button>{/if}
    {:else}
      {#each stages as stage (stage)}
        {#if board[stage].length}
          <section>
            <h2>{t(`br.${stage}`)}</h2>
            <div class="rounds">
              {#each board[stage] as round (round.round)}
                <div class="round">
                  <Group>
                    {#if stage !== 'final'}<h3>{t('br.round', { n: round.round })}</h3>{/if}
                    {#each round.matches as match (match.id)}
                      {@const m = pending?.id === match.id ? pending : match}
                      {@const editable = manage && editableMatch(match, locked)}
                      <div class="match">
                        {#snippet sides()}
                          {#each ['home', 'away'] as side (side)}
                            {@const team = side === 'home' ? m.home : m.away}
                            {@const score = side === 'home' ? m.home_score : m.away_score}
                            <span class={['side', { winner: team !== null && team === m.winner, unknown: team === null }]}>
                              <span class="name">{name(team, m.status)}</span>
                              <span class="score">{score ?? '–'}</span>
                            </span>
                          {/each}
                        {/snippet}
                        {#if editable && editing?.id === m.id && !stale}
                          <form onsubmit={(e) => submit(e, match)}>
                            <label>{name(m.home, m.status)}
                              <!-- svelte-ignore a11y_autofocus (the organizer just opened this match's editor) -->
                              <input autofocus inputmode="numeric" autocomplete="off" disabled={m.home === null || m.away === null} bind:value={home} />
                            </label>
                            <label>{name(m.away, m.status)}<input inputmode="numeric" autocomplete="off" disabled={m.home === null || m.away === null} bind:value={away} /></label>
                            {#if tied}<p class="hint">{t('br.tie')}</p>{/if}
                            <div class="actions">
                              <Button kind="plain" size="s" onclick={() => (editing = null)}>{t('common.cancel')}</Button>
                              {#if m.status === 'played'}<Button kind="secondary" size="s" onclick={() => save(match, null)}>{t('gr.clear')}</Button>{/if}
                              <Button type="submit" size="s" disabled={!canSave}>{t('common.save')}</Button>
                            </div>
                          </form>
                        {:else}
                          {#if editable}
                            <button type="button" class="fixture" disabled={busy || stale} onclick={() => edit(match)}>
                              <Pencil size={13} aria-hidden="true" /> <span class="teams">{@render sides()}</span>
                            </button>
                          {:else}<div class="fixture"><span class="teams">{@render sides()}</span></div>{/if}
                          {#if m.status === 'bye'}<p class="hint">{t('br.bye')}</p>{/if}
                        {/if}
                      </div>
                    {/each}
                  </Group>
                </div>
              {/each}
            </div>
          </section>
        {/if}
      {/each}
      {@const champion = pending?.stage === 'final' ? pending.winner : board.winner}
      {#if champion !== null}<p class="champ"><Trophy size={18} />{t('br.champion', { name: names.get(champion) ?? '' })}</p>{/if}
    {/if}
  </div>
</Sheet>

<style>
  .board { display: grid; gap: var(--s-5); min-width: 0; }
  section { min-width: 0; }
  h2 { margin: 0 var(--s-1) var(--s-2); font: 700 var(--fs-t3)/1.2 var(--font-display); }
  .rounds { display: flex; align-items: flex-start; gap: var(--s-2); overflow-x: auto; scroll-snap-type: x proximity; }
  .round { flex: 0 0 min(85%, 300px); min-width: 0; scroll-snap-align: start; }
  .round:only-child { flex-basis: 100%; }
  h3 { margin: 0; padding: 10px 14px; background: var(--fill); color: var(--text-2); font: 600 var(--fs-sub)/1.3 var(--font-text); }
  .match + .match { border-top: 1px solid var(--separator); }
  .fixture { width: 100%; display: flex; gap: 8px; align-items: center; padding: 9px 14px; color: var(--text); }
  button.fixture { border: 0; background: transparent; text-align: start; cursor: pointer; }
  button.fixture:active { background: var(--tap); }
  .fixture :global(svg) { flex: none; color: var(--text-3); }
  .teams { flex: 1; min-width: 0; }
  .side, label { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; font: 500 var(--fs-body)/1.4 var(--font-text); }
  .side + .side, label + label { margin-top: 4px; }
  .name, label, .champ { overflow-wrap: anywhere; }
  .score, input { font-variant-numeric: tabular-nums; }
  .score { max-width: 52%; text-align: end; overflow-wrap: anywhere; }
  .winner { color: var(--accent-text); font-weight: 700; }
  .unknown, .hint { color: var(--text-3); }
  form { padding: 10px 12px; }
  input { flex: none; width: 4em; min-height: 36px; border: 0; border-radius: var(--r-s); background: var(--fill); color: var(--text); font-size: var(--fs-row); text-align: center; }
  input:focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
  .actions, .retry { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 6px; margin-top: 8px; }
  .retry { justify-content: space-between; }
  .hint { margin: 0 14px 8px; font-size: var(--fs-sub); }
  form .hint { margin: 6px 0; }
  .champ { display: flex; align-items: center; gap: 8px; margin: 0 4px; color: var(--accent-text); font-weight: 700; }
  .champ :global(svg) { flex: none; }
</style>
