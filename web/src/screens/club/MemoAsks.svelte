<script lang="ts">
  // The editor's "For the memo" block (PLAN "Memo in one tap", DMP's template): what this event asks DMP for. Each
  // request is a switch; on, its few fields (a request present in `memo` = asked). The server writes DMP's text from it
  // and the bot brings the whole week's memo on Wednesday. Dates default to the event's day. A room may be in the dorm
  // (its gates for guests), with more dates and times; DMP's own things to provide; a promo over several days; the studio.
  import Plus from '@lucide/svelte/icons/plus';
  import X from '@lucide/svelte/icons/x';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import type { MemoAsks } from '../../lib/api';
  import { haptic } from '../../lib/tg';
  import { fold } from '../../ui/fold';
  import { t } from '../../lib/i18n/index.svelte';

  let { memo = $bindable(), seats, date, only }: { memo: MemoAsks; seats: string; date: string; only?: keyof MemoAsks } = $props();
  // only: the memo sheet's one item (owner, Oct 15): that request's fields, no switches
  const bare = $derived(!!only);
  $effect(() => { if (only && !memo[only]) toggle(only, true); });

  const ASKS = ['room', 'guests', 'provide', 'promo', 'gear', 'print', 'film'] as const;
  const asked = $derived(ASKS.filter((k) => memo[k]));
  let open = $state(false);
  const SIDES = ['tole', 'kazybek', 'abylai'] as const;
  const GATES = ['turgut', 'karimov'] as const; // the dorm's
  function toggle(k: keyof MemoAsks, on: boolean) {
    if (!on) { delete memo[k]; return; }
    if (k === 'room') memo.room = { any: true, projector: false, board: false, capacity: null };
    if (k === 'guests') memo.guests = { side: memo.room?.dorm ? 'turgut' : 'tole', list: '' };
    if (k === 'provide') memo.provide = { jbl: false, tables: null, chairs: null, mixer: false, cooler: null, other: '' };
    if (k === 'promo') memo.promo = { place: '', dates: [date], from: '12:00', to: '18:00', extras: '' };
    if (k === 'film') memo.film = { date, from: '', to: '', note: '' };
    if (k === 'gear') memo.gear = { items: '', outDate: date, outTime: '', inDate: '', inTime: '', location: '', side: 'kazybek' };
    if (k === 'print') memo.print = { items: [{ name: '', count: 1, format: 'A4', bw: false, note: '' }] };
  }
  const sw = (k: keyof MemoAsks) => (ev: Event) => toggle(k, (ev.currentTarget as HTMLInputElement).checked);
  // the guests' entrance follows the place: KBTU's three or the dorm's two gates
  $effect(() => {
    const g = memo.guests;
    if (g && !!memo.room?.dorm !== (GATES as readonly string[]).includes(g.side ?? '')) g.side = memo.room?.dorm ? 'turgut' : 'tole';
  });
  // an older promo had one date: now a list of days
  $effect(() => { const p = memo.promo; if (p && !p.dates) { p.dates = p.date ? [p.date] : [date]; delete p.date; } });
  const num = (set: (n: number | null) => void) => (e: Event) => { const v = +(e.currentTarget as HTMLInputElement).value; set(v > 0 ? v : null); };
</script>

<section class="memo" class:bare>
  <!-- folded by default (owner, Oct 13: six switches crowd the editor); the row says what is asked, so a closed one
       hides nothing -->
  {#if !bare}<button class="head surface" aria-expanded={open} onclick={() => { haptic.tap(); open = !open; }}>
    <span class="tx"><b>{t('memo.fold')}</b><i>{asked.length ? asked.map((k) => t(`memo.${k}`)).join(', ') : t('memo.none')}</i></span>
    <ChevronDown size={18} class={open ? 'up' : ''} /></button>{/if}
  {#if open || bare}
  <div class="body" transition:fold>
  {#if !bare}<p class="hint">{t('memo.blockHint')}</p>{/if}

  <label class="switch"><span><b>{t('memo.room')}</b></span><input type="checkbox" role="switch" checked={!!memo.room} onchange={sw('room')} /></label>
  {#if memo.room}
    <div class="sub">
      <div class="seg wide"><button class:on={!memo.room.dorm} onclick={() => (memo.room!.dorm = false)}>{t('memo.atKbtu')}</button>
        <button class:on={memo.room.dorm} onclick={() => (memo.room!.dorm = true)}>{t('memo.atDorm')}</button></div>
      {#if memo.room.dorm}
        <label class="field"><span class="t-cap">{t('memo.dormPlace')}</span><input bind:value={memo.room.dormPlace} maxlength="120" placeholder={t('memo.dormPh')} /></label>
      {:else}
        <label class="chk"><input type="checkbox" bind:checked={memo.room.any} />{t('memo.roomAny')}</label>
        <label class="chk"><input type="checkbox" bind:checked={memo.room.projector} />{t('memo.projector')}</label>
        <label class="chk"><input type="checkbox" bind:checked={memo.room.board} />{t('memo.board')}</label>
        <label class="field"><span class="t-cap">{t('memo.capacity')}</span>
          <input type="number" inputmode="numeric" min="1" placeholder={seats || '50'} value={memo.room.capacity ?? ''} oninput={num((n) => (memo.room!.capacity = n))} /></label>
      {/if}
      {#each memo.room.slots ?? [] as sl, i (i)}
        <label class="field"><span class="t-cap">{t('ed.date')}</span><input type="date" bind:value={sl.date} /></label>
        <div class="two">
          <label class="field"><span class="t-cap">{t('ed.start')}</span><input type="time" bind:value={sl.from} /></label>
          <label class="field"><span class="t-cap">{t('ed.end')}</span><input type="time" bind:value={sl.to} /></label>
        </div>
        <button class="drop" onclick={() => memo.room!.slots!.splice(i, 1)}><X size={15} />{t('memo.drop')}</button>
      {/each}
      {#if (memo.room.slots?.length ?? 0) < 10}<button class="more" onclick={() => (memo.room!.slots = [...(memo.room!.slots ?? []), { date, from: '', to: '' }])}><Plus size={16} />{t('memo.addSlot')}</button>{/if}
    </div>
  {/if}

  <label class="switch"><span><b>{t('memo.guests')}</b></span><input type="checkbox" role="switch" checked={!!memo.guests} onchange={sw('guests')} /></label>
  {#if memo.guests}
    <div class="sub">
      <label class="field"><span class="t-cap">{t('memo.guestList')}</span>
        <textarea bind:value={memo.guests.list} rows="3" maxlength="1500" placeholder={t('memo.guestPh')}></textarea></label>
      <div class="seg wide">{#each memo.room?.dorm ? GATES : SIDES as s (s)}<button class:on={memo.guests.side === s} onclick={() => (memo.guests!.side = s)}>{t(`memo.side.${s}`)}</button>{/each}</div>
    </div>
  {/if}

  <label class="switch"><span><b>{t('memo.provide')}</b></span><input type="checkbox" role="switch" checked={!!memo.provide} onchange={sw('provide')} /></label>
  {#if memo.provide}
    <div class="sub">
      <label class="chk"><input type="checkbox" bind:checked={memo.provide.jbl} />{t('memo.jbl')}</label>
      <label class="chk"><input type="checkbox" bind:checked={memo.provide.mixer} />{t('memo.mixer')}</label>
      <div class="three">
        <label class="field"><span class="t-cap">{t('memo.tables')}</span><input type="number" inputmode="numeric" min="1" value={memo.provide.tables ?? ''} oninput={num((n) => (memo.provide!.tables = n))} /></label>
        <label class="field"><span class="t-cap">{t('memo.chairs')}</span><input type="number" inputmode="numeric" min="1" value={memo.provide.chairs ?? ''} oninput={num((n) => (memo.provide!.chairs = n))} /></label>
        <label class="field"><span class="t-cap">{t('memo.cooler')}</span><input type="number" inputmode="numeric" min="1" placeholder={t('memo.cups')} value={memo.provide.cooler ?? ''} oninput={num((n) => (memo.provide!.cooler = n))} /></label>
      </div>
      <label class="field"><span class="t-cap">{t('memo.other')}</span><input bind:value={memo.provide.other} maxlength="200" placeholder={t('memo.otherPh')} /></label>
    </div>
  {/if}

  <label class="switch"><span><b>{t('memo.promo')}</b></span><input type="checkbox" role="switch" checked={!!memo.promo} onchange={sw('promo')} /></label>
  {#if memo.promo}
    <div class="sub">
      <label class="field"><span class="t-cap">{t('memo.where')}</span><input bind:value={memo.promo.place} maxlength="120" placeholder={t('memo.promoPh')} /></label>
      {#each memo.promo.dates ?? [] as _, i (i)}
        <div class="day"><label class="field"><span class="t-cap">{t('ed.date')}</span><input type="date" bind:value={memo.promo.dates![i]} /></label>
          {#if (memo.promo.dates?.length ?? 0) > 1}<button class="x" aria-label={t('memo.drop')} onclick={() => memo.promo!.dates!.splice(i, 1)}><X size={16} /></button>{/if}</div>
      {/each}
      {#if (memo.promo.dates?.length ?? 0) < 31}<button class="more" onclick={() => memo.promo!.dates!.push(memo.promo!.dates!.at(-1) ?? date)}><Plus size={16} />{t('memo.addDay')}</button>{/if}
      <div class="two">
        <label class="field"><span class="t-cap">{t('ed.start')}</span><input type="time" bind:value={memo.promo.from} /></label>
        <label class="field"><span class="t-cap">{t('ed.end')}</span><input type="time" bind:value={memo.promo.to} /></label>
      </div>
      <label class="field"><span class="t-cap">{t('memo.extras')}</span><input bind:value={memo.promo.extras} maxlength="200" placeholder={t('memo.extrasPh')} /></label>
    </div>
  {/if}

  <label class="switch"><span><b>{t('memo.gear')}</b></span><input type="checkbox" role="switch" checked={!!memo.gear} onchange={sw('gear')} /></label>
  {#if memo.gear}
    <div class="sub">
      <label class="field"><span class="t-cap">{t('memo.gearList')}</span>
        <textarea bind:value={memo.gear.items} rows="3" maxlength="1500" placeholder={t('memo.gearPh')}></textarea></label>
      <div class="two">
        <label class="field"><span class="t-cap">{t('memo.outDate')}</span><input type="date" bind:value={memo.gear.outDate} /></label>
        <label class="field"><span class="t-cap">{t('memo.outTime')}</span><input bind:value={memo.gear.outTime} maxlength="20" placeholder="17:00-17:30" /></label>
      </div>
      <div class="two">
        <label class="field"><span class="t-cap">{t('memo.inDate')}</span><input type="date" bind:value={memo.gear.inDate} /></label>
        <label class="field"><span class="t-cap">{t('memo.inTime')}</span><input bind:value={memo.gear.inTime} maxlength="20" placeholder="10:00-10:30" /></label>
      </div>
      <label class="field"><span class="t-cap">{t('memo.gearWhere')}</span><input bind:value={memo.gear.location} maxlength="120" /></label>
      <div class="seg wide">{#each SIDES as s (s)}<button class:on={memo.gear.side === s} onclick={() => (memo.gear!.side = s)}>{t(`memo.side.${s}`)}</button>{/each}</div>
    </div>
  {/if}

  <label class="switch"><span><b>{t('memo.print')}</b></span><input type="checkbox" role="switch" checked={!!memo.print} onchange={sw('print')} /></label>
  {#if memo.print}
    <div class="sub">
      {#each memo.print.items ?? [] as it, i (i)}
        <div class="item">
          <div class="two">
            <label class="field"><span class="t-cap">{t('memo.printName')}</span><input bind:value={it.name} maxlength="60" placeholder={t('memo.printPh')} /></label>
            <label class="field"><span class="t-cap">{t('memo.count')}</span><input type="number" inputmode="numeric" min="1" bind:value={it.count} /></label>
          </div>
          <div class="segs"><div class="seg">{#each ['A5', 'A4', 'A3'] as fm (fm)}<button class:on={it.format === fm} onclick={() => (it.format = fm)}>{fm}</button>{/each}</div>
            <div class="seg"><button class:on={!it.bw} onclick={() => (it.bw = false)}>{t('memo.color')}</button><button class:on={it.bw} onclick={() => (it.bw = true)}>{t('memo.bw')}</button></div></div>
          <span class="t-cap">{t('memo.density')}</span>
          <div class="seg wide">{#each ['70-100', '110-150', '200-250'] as d, k (d)}<button class:on={(it.density ?? 0) === k} onclick={() => (it.density = k as 0 | 1 | 2)}>{d}</button>{/each}</div>
          <label class="field"><span class="t-cap">{t('memo.note')}</span><input bind:value={it.note} maxlength="120" placeholder={t('memo.notePh')} /></label>
          {#if (memo.print.items?.length ?? 0) > 1}<button class="drop" onclick={() => memo.print!.items!.splice(i, 1)}><X size={15} />{t('memo.drop')}</button>{/if}
        </div>
      {/each}
      {#if (memo.print.items?.length ?? 0) < 5}<button class="more" onclick={() => memo.print!.items!.push({ name: '', count: 1, format: 'A4', bw: false, note: '' })}><Plus size={16} />{t('memo.more')}</button>{/if}
      <p class="hint">{t('memo.printHint')}</p>
    </div>
  {/if}

  <label class="switch"><span><b>{t('memo.film')}</b></span><input type="checkbox" role="switch" checked={!!memo.film} onchange={sw('film')} /></label>
  {#if memo.film}
    <div class="sub">
      <label class="field"><span class="t-cap">{t('ed.date')}</span><input type="date" bind:value={memo.film.date} /></label>
      <div class="two">
        <label class="field"><span class="t-cap">{t('ed.start')}</span><input type="time" bind:value={memo.film.from} /></label>
        <label class="field"><span class="t-cap">{t('ed.end')}</span><input type="time" bind:value={memo.film.to} /></label>
      </div>
      <label class="field"><span class="t-cap">{t('memo.note')}</span><input bind:value={memo.film.note} maxlength="200" placeholder={t('memo.filmPh')} /></label>
    </div>
  {/if}
  </div>
  {/if}
</section>

<style>
  .bare .switch { display: none; }
  .memo { display: flex; flex-direction: column; gap: 10px; }
  .body { display: flex; flex-direction: column; gap: 10px; }
  .head { display: flex; align-items: center; gap: 12px; min-height: 58px; padding: 10px 14px; text-align: left; color: var(--text-3); margin-top: 6px; }
  .head:active { transform: scale(0.99); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { font: 650 15.5px/1.2 var(--font-text); color: var(--text); }
  .tx i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .head :global(svg) { transition: transform var(--t-fast) var(--ease); }
  .head :global(svg.up) { transform: rotate(180deg); }
  .hint { margin: -4px 4px 0; font: 500 12.5px/1.35 var(--font-text); color: var(--text-3); }
  .sub { display: flex; flex-direction: column; gap: 8px; margin: -2px 0 4px 12px; padding-left: 12px; border-left: 2px solid var(--line-2); }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .three { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .three input { min-width: 0; width: 100%; }
  .day { display: flex; align-items: flex-end; gap: 8px; }
  .day .field { flex: 1; }
  .x { flex: none; width: 40px; height: 44px; display: flex; align-items: center; justify-content: center; color: var(--text-3); }
  .seg.wide { display: flex; }
  .seg.wide button { flex: 1; padding: 0 6px; }
  .segs { display: flex; flex-wrap: wrap; gap: 8px; }
  .chk { display: flex; align-items: center; gap: 10px; padding: 6px 4px; font: 550 15px/1.3 var(--font-text); }
  .chk input { width: 20px; height: 20px; accent-color: var(--accent); }
  .item { display: flex; flex-direction: column; gap: 8px; padding-bottom: 8px; }
  .item + .item { border-top: 1px solid var(--line); padding-top: 8px; }
  .drop, .more { display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; padding: 6px 4px; font: 620 14px/1 var(--font-text); color: var(--text-2); }
  .more { color: var(--accent-text); }
</style>
