<script lang="ts">
  import { akoTeam } from '../../lib/api/akoTeam';
  // Add an interview day: the date, from–to and a length make the times, shown live as chips the manager taps off;
  // seats, interviewer and the day's Teams link. The new times show on the desk at once and go back if the server says no.
  import { ApiErr, type Id, type AkoDesk, type AkoSlot } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { aw } from '../../lib/i18n/ako';
  import { dateInput, fromInputs, nowTs, time } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Minus from '@lucide/svelte/icons/minus';
  import Plus from '@lucide/svelte/icons/plus';

  let { overlay, org, desk, onchange }: { overlay: Overlay; org: Id; desk: AkoDesk; onchange?: () => void } = $props();

  const LENS = [15, 20, 30, 45, 60];
  const first = dateInput(nowTs() + 86400); // from tomorrow, Almaty
  let day = $state(first);
  let from = $state('10:00');
  let to = $state('13:00');
  let minutes = $state(30);
  let off = $state<string[]>([]);
  let cap = $state(1);
  let who = $state('');
  let teams = $state('');
  let errDay = $state('');
  let errTeams = $state('');
  let busy = $state(false);

  /** the day's own link, if it has one already, unless the manager typed another */
  function pickDay() { errDay = ''; if (!teams.trim()) teams = desk.days[day] ?? ''; }
  pickDay();

  const mins = (hm: string) => (/^\d\d:\d\d$/.test(hm) ? Number(hm.slice(0, 2)) * 60 + Number(hm.slice(3)) : NaN);
  const p2 = (n: number) => String(n).padStart(2, '0');
  const all = $derived.by(() => {
    const a = mins(from), b = mins(to), out: string[] = [];
    if (Number.isNaN(a) || Number.isNaN(b)) return out;
    for (let m = a; m + minutes <= b && out.length < 48; m += minutes) out.push(`${p2(Math.floor(m / 60))}:${p2(m % 60)}`);
    return out;
  });
  const taken = $derived(new Set(desk.slots.filter((s) => dateInput(s.at) === day).map((s) => time(s.at)))); // already on the desk
  const on = $derived(all.filter((x) => !off.includes(x) && !taken.has(x)));
  const toggle = (hm: string) => { haptic.select(); off = off.includes(hm) ? off.filter((x) => x !== hm) : [...off, hm]; };
  const tag = (e: unknown) => (e instanceof ApiErr ? [e.message, (e as { field?: string }).field, (e as { detail?: string }).detail].join(' ') : '');

  async function add() {
    if (busy || !on.length) return;
    const link = teams.trim(), w = who.trim(), d = day, times = [...on];
    errDay = d >= first ? '' : aw('akd.pastDay');
    errTeams = !link || /^https:\/\/\S+$/.test(link) ? '' : aw('akd.teamsBad');
    if (errDay || errTeams) { haptic.warn(); return; }
    busy = true;
    // optimistic: the times stand on the desk under this sheet now
    const stamp = Date.now(), had = desk.days[d];
    const temp: AkoSlot[] = times.map((hm, i) => ({ id: -(stamp + i) as unknown as Id, at: fromInputs(d, hm), minutes, cap, who: w, teams: null, apps: [] }));
    desk.slots.push(...temp);
    if (link) desk.days[d] = link;
    try {
      await akoTeam.akoAddSlots(org, { day: d, times, minutes, cap, who: w || undefined, teams: link || undefined });
      haptic.ok();
      onchange?.();
      close(overlay.id);
    } catch (e) {
      const ids = new Set(temp.map((x) => x.id));
      desk.slots = desk.slots.filter((s) => !ids.has(s.id));
      if (had) desk.days[d] = had; else delete desk.days[d];
      haptic.error();
      const what = tag(e);
      if (what.includes('past')) errDay = aw('akd.pastDay');
      else if (what.includes('teams')) errTeams = aw('akd.teamsBad');
      else say(t('common.error'), 'warning_3d');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} heading={aw('akd.addDay')}>
  <div class="col">
    <label class="fld" class:bad={!!errDay}>
      <span class="lb">{aw('akd.day')}</span>
      <input class="box" type="date" bind:value={day} min={first} onchange={pickDay} aria-invalid={!!errDay} />
      {#if errDay}<span class="err">{errDay}</span>{/if}
    </label>
    <div class="pair">
      <label class="fld"><span class="lb">{aw('akd.from')}</span><input class="box" type="time" step="300" bind:value={from} /></label>
      <label class="fld"><span class="lb">{aw('akd.to')}</span><input class="box" type="time" step="300" bind:value={to} /></label>
    </div>

    <div class="sec">
      <p class="lb">{aw('akd.minutes')}</p>
      <div class="chips" role="radiogroup" aria-label={aw('akd.minutes')}>
        {#each LENS as n (n)}
          <button class="chip" class:on={minutes === n} role="radio" aria-checked={minutes === n} onclick={() => { haptic.select(); minutes = n; }}>{aw('akd.minN', { n })}</button>
        {/each}
      </div>
    </div>

    <div class="sec">
      <p class="lb">{aw('akd.times')}{#if all.length}<span class="n"> · {on.length}</span>{/if}</p>
      {#if all.length}
        <div class="chips">
          {#each all as hm (hm)}
            <button class="chip" class:on={on.includes(hm)} class:off={!on.includes(hm)} aria-pressed={on.includes(hm)} disabled={taken.has(hm)} onclick={() => toggle(hm)}>{hm}</button>
          {/each}
        </div>
      {:else}
        <p class="quiet">{aw('akd.noTimes')}</p>
      {/if}
    </div>

    <Group>
      <Row dense title={aw('akd.cap')}>
        {#snippet trailing()}
          <span class="step">
            <Button kind="secondary" size="s" round label={aw('akd.capLess')} disabled={cap <= 1} onclick={() => (cap -= 1)}>{#snippet icon()}<Minus size={16} strokeWidth={2.4} />{/snippet}</Button>
            <b class="cnt" aria-live="polite">{cap}</b>
            <Button kind="secondary" size="s" round label={aw('akd.capMore')} disabled={cap >= 20} onclick={() => (cap += 1)}>{#snippet icon()}<Plus size={16} strokeWidth={2.4} />{/snippet}</Button>
          </span>
        {/snippet}
      </Row>
    </Group>

    <Field label={aw('akd.who')} bind:value={who} autocomplete="off" enterkeyhint="next" maxlength={80} />
    <Field label={aw('akd.teams')} bind:value={teams} error={errTeams || undefined} type="url" inputmode="url" placeholder={aw('akd.teamsPh')} autocomplete="off" enterkeyhint="done" />
    {#if !teams.trim()}<Notice tone="warning" title={aw('akd.teamsMissing')} text={aw('akd.teamsWarn')} />{/if}
  </div>

  {#snippet footer()}
    <Button size="l" full loading={busy} disabled={!on.length} onclick={add}>{aw('akd.addDay')}</Button>
  {/snippet}
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--s-4); }
  .sec, .fld { display: flex; flex-direction: column; gap: var(--s-2); min-width: 0; }
  .pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-3); }
  .lb { padding: 0 var(--s-4); color: var(--text-3); font: 450 var(--fs-sub)/1.2 var(--font-text); }
  .n { font-variant-numeric: tabular-nums; }
  /* Field's box for the native date and time inputs (Field has no such types) */
  .box { display: block; width: 100%; min-width: 0; height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); letter-spacing: -0.012em; font-variant-numeric: tabular-nums; text-align: left;
    -webkit-appearance: none; appearance: none; transition: box-shadow var(--t-fast); }
  .box::-webkit-date-and-time-value { text-align: left; }
  .box:focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
  .bad .box { box-shadow: inset 0 0 0 1.5px var(--danger); }
  .err { padding: 0 var(--s-4); color: var(--danger-text); font: 450 var(--fs-sub)/1.35 var(--font-text); }
  .quiet { padding: 0 var(--s-4); color: var(--text-3); font: 450 var(--fs-sub)/1.4 var(--font-text); }

  .chips { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .chip { height: var(--ctl-s); padding: 0 var(--s-4); border-radius: var(--r-full); background: var(--fill); color: var(--text);
    font: 600 var(--fs-sub)/1 var(--font-text); font-variant-numeric: tabular-nums;
    transition: opacity var(--t-fast), background-color var(--t-fast), color var(--t-fast); }
  .chip.on { background: var(--accent-soft); color: var(--accent-text); }
  .chip.off { opacity: 0.4; text-decoration: line-through; }
  .chip:active:not(:disabled) { transform: none; opacity: 0.7; }
  .chip:disabled { cursor: default; }

  .step { display: inline-flex; align-items: center; gap: var(--s-2); }
  .cnt { min-width: var(--s-6); text-align: center; font: 600 var(--fs-row)/1 var(--font-text); font-variant-numeric: tabular-nums; }
</style>
