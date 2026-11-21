<script lang="ts">
  // A team event's group stage (server evgroups.py), for everyone who sees the event: each group's table (3 a win, 1 a
  // draw; the server ranks it), then its matches. The organizers (the "events" right, as the teams board) draw the
  // groups, move a team to another group by a tap, redraw, all only until the first score; then enter scores (a tap on a
  // match) and remove the stage. Each tap shows at once and goes back if refused; the table comes from the server after
  // a score (no second copy of its tie-breaks here).
  import { onMount } from 'svelte';
  import Trophy from '@lucide/svelte/icons/trophy';
  import { api, ApiErr, type EventGroup, type EventGroups, type EventMatch, type EventStanding, type Id } from '../../lib/api';
  import { errorText } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { menu } from '../../ui/menu';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, id, manage = false, seed, onchange, replacesBracket = false }: { overlay: Overlay; id: Id; manage?: boolean; seed?: EventGroups; onchange?: (g: EventGroups) => void; replacesBracket?: boolean } = $props();
  // svelte-ignore state_referenced_locally
  let b = $state<EventGroups | null>(seed ?? null);
  // the event sheet's row follows a draw or a removal (the server's word only)
  const put = (x: EventGroups) => { b = x; onchange?.(x); };
  const reload = () => api.eventGroups(id).then(put);
  onMount(() => { reload().catch(() => {}); });
  const fail = (e: unknown) => {
    haptic.error();
    say(e instanceof ApiErr && e.message === 'groups_scored' ? t('gr.scored') : e instanceof ApiErr ? errorText(e) : t('common.error'), 'pleading_face_3d');
  };

  const done = (m: EventMatch) => m.home_score !== null && m.away_score !== null;
  const scored = $derived(!!b?.groups.some((g) => g.matches.some(done)));
  const names = $derived(new Map(b?.groups.flatMap((g) => g.standings.map((s) => [s.team_id, s.name] as const)) ?? []));

  // the draw's two numbers; a redraw starts from the stage's own "advance"
  let size = $state(5), advance = $state(2);
  // svelte-ignore state_referenced_locally
  if (seed?.groups[0]) advance = seed.groups[0].advance;
  let drawing = $state(false);
  async function draw() {
    if (drawing || !b) return;
    if (b.groups.length && !(await sheets.ask({ title: t('gr.redrawAsk'), text: t('gr.redrawText'), ok: t('gr.redraw'), cancel: t('common.cancel') }))) return;
    if (!b.groups.length && replacesBracket && !(await sheets.ask({ title: t('gr.draw'), text: t('br.replace'), ok: t('gr.draw'), cancel: t('common.cancel') }))) return;
    drawing = true;
    try { put(await api.drawGroups(id, size, Math.min(advance, size))); haptic.ok(); say(t('gr.drawn'), 'party_popper_3d'); } catch (e) { fail(e); }
    finally { drawing = false; }
  }

  // a team to another group: its row moves at once, its old matches go; the server makes both groups' fixtures again
  function pickGroup(e: MouseEvent, s: EventStanding, from: EventGroup) {
    if (!b || scored) return;
    const to = b.groups.filter((g) => g.id !== from.id);
    if (!to.length) return;
    menu(e.currentTarget as Element, to.map((g) => ({ label: t('gr.toGroup', { name: g.name }), onselect: () => void move(s, from, g) })));
  }
  async function move(s: EventStanding, from: EventGroup, to: EventGroup) {
    if (!b) return;
    const was = b, ids = [...to.standings.map((x) => x.team_id), s.team_id];
    b = { groups: b.groups.map((g) => g.id === from.id ? { ...g, standings: g.standings.filter((x) => x.team_id !== s.team_id), matches: g.matches.filter((m) => m.home !== s.team_id && m.away !== s.team_id) }
      : g.id === to.id ? { ...g, standings: [...g.standings, { ...s, advance: false }] } : g) };
    haptic.tap();
    try { put(await api.moveGroupTeams(id, to.id, ids)); haptic.ok(); } catch (e) { b = was; fail(e); }
  }

  // a score: two fields in the match's row; Enter or Save keeps it, the table follows from the server
  let editing = $state<Id | null>(null), hs = $state(''), as = $state('');
  function edit(m: EventMatch) {
    if (!manage) return;
    if (editing === m.id) { editing = null; return; }
    editing = m.id; hs = m.home_score === null ? '' : String(m.home_score); as = m.away_score === null ? '' : String(m.away_score);
  }
  const num = (x: string) => (/^\d{1,4}$/.test(x.trim()) ? +x.trim() : null);
  async function setScore(m: EventMatch, clear = false) {
    if (!b) return;
    const h = num(hs), a = num(as);
    if (!clear && (h === null || a === null)) { haptic.error(); return; }
    const was = b, score = clear ? null : { home_score: h!, away_score: a! };
    b = { groups: b.groups.map((g) => ({ ...g, matches: g.matches.map((x) => x.id === m.id ? { ...x, home_score: score?.home_score ?? null, away_score: score?.away_score ?? null } : x) })) };
    editing = null; haptic.ok();
    try { await api.scoreMatch(id, m.id, score); await reload(); } catch (e) { b = was; fail(e); }
  }
  const onkey = (e: KeyboardEvent, m: EventMatch) => { if (e.key === 'Enter') { e.preventDefault(); void setScore(m); } };

  async function remove() {
    if (!b || !(await sheets.ask({ title: t('gr.removeAsk'), text: t('gr.removeText'), ok: t('gr.remove'), cancel: t('common.cancel'), danger: true }))) return;
    const was = b;
    b = { groups: [] }; haptic.tap();
    try { await api.removeGroups(id); put({ groups: [] }); haptic.ok(); say(t('gr.removed'), 'waving_hand_3d_default'); } catch (e) { b = was; fail(e); }
  }
  const opts = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => from + i);
</script>

<Sheet {overlay} icon={Trophy} full title={t('gr.title')}>
  {#if b}
    {#if !b.groups.length}<EmptyState inline text={t('gr.none')} />{/if}
    <div class="list">
      {#each b.groups as g (g.id)}
        {@const live = g.matches.some(done)}
        <Group caption={t('gr.group', { name: g.name })} footnote={g.advance ? t('gr.advanceNote', { n: g.advance }) : undefined}>
          <div class="tbl">
            <div class="tr th" aria-hidden="true">
              <span>#</span><span class="nm"></span><span>{t('gr.p')}</span><span>{t('gr.w')}</span><span>{t('gr.d')}</span>
              <span>{t('gr.l')}</span><span>±</span><span class="pts">{t('gr.pts')}</span>
            </div>
            {#each g.standings as s, i (s.team_id)}
              {#snippet cells()}
                <span class="pos" class:up={live && s.advance}>{i + 1}</span>
                <span class="nm">{s.name}</span>
                <span>{s.played}</span><span>{s.won}</span><span>{s.drawn}</span><span>{s.lost}</span>
                <span>{s.diff > 0 ? '+' + s.diff : s.diff < 0 ? '−' + -s.diff : 0}</span><span class="pts">{s.points}</span>
              {/snippet}
              {#if manage && !scored && b.groups.length > 1}
                <button type="button" class="tr tap" onclick={(e) => pickGroup(e, s, g)}>{@render cells()}</button>
              {:else}
                <div class="tr">{@render cells()}</div>
              {/if}
            {/each}
          </div>
        </Group>
        {#if g.matches.length}
          <Group caption={t('gr.matches')}>
            {#each g.matches as m (m.id)}
              <div class="mt">
                {#snippet line()}
                  <span class="side home">{names.get(m.home) ?? ''}</span>
                  <span class="sc" class:none={!done(m)}>{done(m) ? `${m.home_score}:${m.away_score}` : '–:–'}</span>
                  <span class="side">{names.get(m.away) ?? ''}</span>
                {/snippet}
                {#if manage}<button type="button" class="mrow tap" onclick={() => edit(m)}>{@render line()}</button>
                {:else}<div class="mrow">{@render line()}</div>{/if}
                {#if editing === m.id}
                  <div class="ed">
                    <!-- svelte-ignore a11y_autofocus -->
                    <input class="n" type="text" inputmode="numeric" maxlength="4" autocomplete="off" aria-label={names.get(m.home)} bind:value={hs} onkeydown={(e) => onkey(e, m)} autofocus />
                    <span class="colon">:</span>
                    <input class="n" type="text" inputmode="numeric" maxlength="4" autocomplete="off" aria-label={names.get(m.away)} bind:value={as} onkeydown={(e) => onkey(e, m)} />
                    <span class="acts">
                      {#if done(m)}<Button kind="gray" size="s" onclick={() => setScore(m, true)}>{t('gr.clear')}</Button>{/if}
                      <Button kind="primary" size="s" onclick={() => setScore(m)}>{t('common.save')}</Button>
                    </span>
                  </div>
                {/if}
              </div>
            {/each}
          </Group>
        {/if}
      {/each}

      {#if manage}
        {#if !scored}
          <Group footnote={b.groups.length ? (b.groups.length > 1 ? t('gr.moveHint') + ' ' : '') + t('gr.scoreHint') : undefined}>
            <Row title={t('gr.size')} value={String(size)} menu={opts(3, 8).map((n) => ({ label: String(n), checked: n === size, onselect: () => { size = n; advance = Math.min(advance, n - 1); } }))} />
            <Row title={t('gr.advance')} value={String(advance)} menu={opts(1, Math.min(4, size - 1)).map((n) => ({ label: String(n), checked: n === advance, onselect: () => (advance = n) }))} />
            {#if b.groups.length}<Row tone="action" title={t('gr.redraw')} disabled={drawing} onclick={draw} />{/if}
          </Group>
        {:else}
          <p class="t-foot sub">{t('gr.scored')}</p>
        {/if}
        {#if b.groups.length}<Group><Row tone="destructive" title={t('gr.remove')} onclick={remove} /></Group>{/if}
      {/if}
    </div>
  {/if}
  {#snippet footer()}
    {#if manage && b && !b.groups.length}<Button kind="primary" size="l" full loading={drawing} onclick={draw}>{t('gr.draw')}</Button>{/if}
  {/snippet}
</Sheet>

<style>
  .list { display: flex; flex-direction: column; gap: var(--s-5); margin-top: var(--s-2); }
  .sub { margin: 0 var(--s-1); }
  .tbl { display: flex; flex-direction: column; padding: 4px 0; }
  /* # · team · P W D L · ± · Pts: the numbers fixed and narrow, the name takes the rest and truncates (320 px) */
  .tr {
    display: grid; grid-template-columns: 20px minmax(0, 1fr) repeat(4, 18px) 26px 24px; column-gap: 3px; align-items: center;
    padding: 0 10px; min-height: 40px; width: 100%; border: 0; background: none; color: var(--text); text-align: center;
    font: 500 var(--fs-body)/1.2 var(--font-text); font-variant-numeric: tabular-nums;
  }
  .tr + .tr { box-shadow: inset 0 0.5px 0 var(--separator); }
  .th { min-height: 30px; color: var(--text-3); font-size: var(--fs-cap); font-weight: 600; }
  .tap { cursor: pointer; -webkit-tap-highlight-color: transparent; }
  .tap:active { background: var(--tap); }
  .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; font-weight: 600; }
  .pts { font-weight: 700; }
  .pos { justify-self: start; display: grid; place-items: center; width: 20px; height: 20px; border-radius: var(--r-xs); color: var(--text-3); font-weight: 600; }
  /* advancing: the place on the accent's soft tint, nothing louder */
  .pos.up { background: var(--accent-soft); color: var(--accent-text); }
  .mt + .mt { box-shadow: inset 0 0.5px 0 var(--separator); }
  .mrow {
    display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); column-gap: 10px; align-items: center;
    width: 100%; min-height: 44px; padding: 0 12px; border: 0; background: none; color: var(--text); font: 500 var(--fs-body)/1.2 var(--font-text);
  }
  .side { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
  .home { text-align: right; }
  .sc { min-width: 44px; text-align: center; font-weight: 700; font-variant-numeric: tabular-nums; }
  .sc.none { color: var(--text-3); font-weight: 500; }
  .ed { display: flex; align-items: center; gap: 6px; padding: 0 12px 10px; animation: ed-in 0.22s var(--ease) both; }
  .n {
    width: 48px; height: 36px; border: 0; border-radius: var(--r-s); background: var(--fill); color: var(--text); text-align: center;
    font: 700 var(--fs-row)/1 var(--font-text); font-variant-numeric: tabular-nums; outline: none;
  }
  .n:focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
  .colon { color: var(--text-3); font-weight: 700; }
  .acts { margin-left: auto; display: flex; gap: 6px; }
  @keyframes ed-in { from { opacity: 0; transform: translateY(-4px); } }
</style>
