<script lang="ts">
  // The editor's "For the memo" block (PLAN "Memo in one tap", DMP's template): what this event asks DMP for. Each
  // request is a switch; on, its few fields (a request present in `memo` = asked). The server writes DMP's text from it
  // and the bot brings the whole week's memo on Wednesday. Dates default to the event's day. A room may be in the dorm
  // (its gates for guests), with more dates and times; DMP's own things to provide; a promo over several days; the studio.
  import Plus from '@lucide/svelte/icons/plus';
  import X from '@lucide/svelte/icons/x';
  import type { MemoAsks, MemoSide } from '../../lib/api';
  import { haptic } from '../../lib/tg';
  import { fold } from '../../ui/fold';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import { t } from '../../lib/i18n/index.svelte';

  let { memo = $bindable(), seats, date, only, flat = false }: { memo: MemoAsks; seats: string; date: string; only?: keyof MemoAsks; flat?: boolean } = $props();
  // flat: the editor's own panel: the switches in sight, no header to fold them
  // only: the memo sheet's one item: that request's fields, no switches
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
  // the guests' entrance follows the place: KBTU's three or the dorm's two gates
  $effect(() => {
    const g = memo.guests;
    if (g && !!memo.room?.dorm !== (GATES as readonly string[]).includes(g.side ?? '')) g.side = memo.room?.dorm ? 'turgut' : 'tole';
  });
  // an older promo had one date: now a list of days
  $effect(() => { const p = memo.promo; if (p && !p.dates) { p.dates = p.date ? [p.date] : [date]; delete p.date; } });
  // a count field: empty or 0 is none (a number input hands Field a number or null)
  const num = (v: unknown) => (+String(v) > 0 ? +String(v) : null);
  const str = (n: number | null | undefined) => (n == null ? '' : String(n));
  const DENSITY = ['70-100', '110-150', '200-250'];
</script>

<!-- engine: Field has no date type: the dates by hand, in Field's look (.fl) -->
{#snippet ask(k: (typeof ASKS)[number])}
  {#if !bare}<Group><Row title={t(`memo.${k}`)} accessory="switch" checked={!!memo[k]} onchange={(on) => toggle(k, on)} /></Group>{/if}
{/snippet}

<section class="memo" class:bare>
  <!-- folded by default (six switches crowd the editor); the row says what is asked, so a closed one
       hides nothing -->
  {#if !bare && !flat}
    <Group><Row title={t('memo.fold')} subtitle={asked.length ? asked.map((k) => t(`memo.${k}`)).join(', ') : t('memo.none')} accessory="disclosure" {open}
      onclick={() => { haptic.tap(); open = !open; }} /></Group>
  {/if}
  {#if open || bare || flat}
  <div class="body" transition:fold>
  {#if !bare}<p class="hint">{t('memo.blockHint')}</p>{/if}

  {@render ask('room')}
  {#if memo.room}
    <div class="sub">
      <Segmented items={[{ value: 'kbtu', label: t('memo.atKbtu') }, { value: 'dorm', label: t('memo.atDorm') }]} value={memo.room.dorm ? 'dorm' : 'kbtu'}
        label={t('memo.room')} onchange={(v) => (memo.room!.dorm = v === 'dorm')} />
      {#if memo.room.dorm}
        <Field label={t('memo.dormPlace')} bind:value={memo.room.dormPlace} maxlength={120} placeholder={t('memo.dormPh')} />
      {:else}
        <Group>
          <Row title={t('memo.roomAny')} accessory="switch" checked={!!memo.room.any} onchange={(on) => (memo.room!.any = on)} />
          <Row title={t('memo.projector')} accessory="switch" checked={!!memo.room.projector} onchange={(on) => (memo.room!.projector = on)} />
          <Row title={t('memo.board')} accessory="switch" checked={!!memo.room.board} onchange={(on) => (memo.room!.board = on)} />
        </Group>
        <Field label={t('memo.capacity')} type="number" inputmode="numeric" placeholder={seats || '50'}
          bind:value={() => str(memo.room!.capacity), (v) => (memo.room!.capacity = num(v))} />
      {/if}
      {#each memo.room.slots ?? [] as sl, i (i)}
        <label class="fl"><span>{t('ed.date')}</span><input type="date" bind:value={sl.date} /></label>
        <div class="two">
          <label class="fl"><span>{t('ed.start')}</span><input type="time" bind:value={sl.from} /></label>
          <label class="fl"><span>{t('ed.end')}</span><input type="time" bind:value={sl.to} /></label>
        </div>
        <span class="lone"><Button kind="plain" size="s" onclick={() => memo.room!.slots!.splice(i, 1)}>{#snippet icon()}<X size={15} />{/snippet}{t('memo.drop')}</Button></span>
      {/each}
      {#if (memo.room.slots?.length ?? 0) < 10}<span class="lone"><Button kind="tinted" size="s" onclick={() => (memo.room!.slots = [...(memo.room!.slots ?? []), { date, from: '', to: '' }])}>
        {#snippet icon()}<Plus size={16} />{/snippet}{t('memo.addSlot')}</Button></span>{/if}
    </div>
  {/if}

  {@render ask('guests')}
  {#if memo.guests}
    <div class="sub">
      <Field label={t('memo.guestList')} multiline rows={3} bind:value={memo.guests.list} maxlength={1500} placeholder={t('memo.guestPh')} />
      <Segmented items={(memo.room?.dorm ? GATES : SIDES).map((s) => ({ value: s as string, label: t(`memo.side.${s}`) }))} value={memo.guests.side ?? ''}
        label={t('memo.guests')} onchange={(v) => (memo.guests!.side = v as MemoSide)} />
    </div>
  {/if}

  {@render ask('provide')}
  {#if memo.provide}
    <div class="sub">
      <Group>
        <Row title={t('memo.jbl')} accessory="switch" checked={!!memo.provide.jbl} onchange={(on) => (memo.provide!.jbl = on)} />
        <Row title={t('memo.mixer')} accessory="switch" checked={!!memo.provide.mixer} onchange={(on) => (memo.provide!.mixer = on)} />
      </Group>
      <div class="three">
        <Field label={t('memo.tables')} type="number" inputmode="numeric" bind:value={() => str(memo.provide!.tables), (v) => (memo.provide!.tables = num(v))} />
        <Field label={t('memo.chairs')} type="number" inputmode="numeric" bind:value={() => str(memo.provide!.chairs), (v) => (memo.provide!.chairs = num(v))} />
        <Field label={t('memo.cooler')} type="number" inputmode="numeric" placeholder={t('memo.cups')} bind:value={() => str(memo.provide!.cooler), (v) => (memo.provide!.cooler = num(v))} />
      </div>
      <Field label={t('memo.other')} bind:value={memo.provide.other} maxlength={200} placeholder={t('memo.otherPh')} />
    </div>
  {/if}

  {@render ask('promo')}
  {#if memo.promo}
    <div class="sub">
      <Field label={t('memo.where')} bind:value={memo.promo.place} maxlength={120} placeholder={t('memo.promoPh')} />
      {#each memo.promo.dates ?? [] as _, i (i)}
        <div class="day"><label class="fl"><span>{t('ed.date')}</span><input type="date" bind:value={memo.promo.dates![i]} /></label>
          {#if (memo.promo.dates?.length ?? 0) > 1}<IconButton icon={X} kind="plain" size="s" label={t('memo.drop')} onclick={() => memo.promo!.dates!.splice(i, 1)} />{/if}</div>
      {/each}
      {#if (memo.promo.dates?.length ?? 0) < 31}<span class="lone"><Button kind="tinted" size="s" onclick={() => memo.promo!.dates!.push(memo.promo!.dates!.at(-1) ?? date)}>
        {#snippet icon()}<Plus size={16} />{/snippet}{t('memo.addDay')}</Button></span>{/if}
      <div class="two">
        <label class="fl"><span>{t('ed.start')}</span><input type="time" bind:value={memo.promo.from} /></label>
        <label class="fl"><span>{t('ed.end')}</span><input type="time" bind:value={memo.promo.to} /></label>
      </div>
      <Field label={t('memo.extras')} bind:value={memo.promo.extras} maxlength={200} placeholder={t('memo.extrasPh')} />
    </div>
  {/if}

  {@render ask('gear')}
  {#if memo.gear}
    <div class="sub">
      <Field label={t('memo.gearList')} multiline rows={3} bind:value={memo.gear.items} maxlength={1500} placeholder={t('memo.gearPh')} />
      <div class="two">
        <label class="fl"><span>{t('memo.outDate')}</span><input type="date" bind:value={memo.gear.outDate} /></label>
        <Field label={t('memo.outTime')} bind:value={memo.gear.outTime} maxlength={20} placeholder="17:00-17:30" />
      </div>
      <div class="two">
        <label class="fl"><span>{t('memo.inDate')}</span><input type="date" bind:value={memo.gear.inDate} /></label>
        <Field label={t('memo.inTime')} bind:value={memo.gear.inTime} maxlength={20} placeholder="10:00-10:30" />
      </div>
      <Field label={t('memo.gearWhere')} bind:value={memo.gear.location} maxlength={120} />
      <Segmented items={SIDES.map((s) => ({ value: s as string, label: t(`memo.side.${s}`) }))} value={memo.gear.side ?? ''} label={t('memo.gear')}
        onchange={(v) => (memo.gear!.side = v as MemoSide)} />
    </div>
  {/if}

  {@render ask('print')}
  {#if memo.print}
    <div class="sub">
      {#each memo.print.items ?? [] as it, i (i)}
        <div class="item">
          <div class="two">
            <Field label={t('memo.printName')} bind:value={it.name} maxlength={60} placeholder={t('memo.printPh')} />
            <Field label={t('memo.count')} type="number" inputmode="numeric" bind:value={() => str(it.count), (v) => (it.count = num(v) ?? 1)} />
          </div>
          <div class="two">
            <Segmented items={['A5', 'A4', 'A3'].map((fm) => ({ value: fm, label: fm }))} value={it.format ?? 'A4'} onchange={(v) => (it.format = v)} label={t('memo.print')} />
            <Segmented items={[{ value: 'color', label: t('memo.color') }, { value: 'bw', label: t('memo.bw') }]} value={it.bw ? 'bw' : 'color'} label={t('memo.print')}
              onchange={(v) => (it.bw = v === 'bw')} />
          </div>
          <span class="lbl">{t('memo.density')}</span>
          <Segmented items={DENSITY.map((d, k) => ({ value: k, label: d }))} value={it.density ?? 0} label={t('memo.density')} onchange={(k) => (it.density = k as 0 | 1 | 2)} />
          <Field label={t('memo.note')} bind:value={it.note} maxlength={120} placeholder={t('memo.notePh')} />
          {#if (memo.print.items?.length ?? 0) > 1}<span class="lone"><Button kind="plain" size="s" onclick={() => memo.print!.items!.splice(i, 1)}>
            {#snippet icon()}<X size={15} />{/snippet}{t('memo.drop')}</Button></span>{/if}
        </div>
      {/each}
      {#if (memo.print.items?.length ?? 0) < 5}<span class="lone"><Button kind="tinted" size="s" onclick={() => memo.print!.items!.push({ name: '', count: 1, format: 'A4', bw: false, note: '' })}>
        {#snippet icon()}<Plus size={16} />{/snippet}{t('memo.more')}</Button></span>{/if}
      <p class="hint">{t('memo.printHint')}</p>
    </div>
  {/if}

  {@render ask('film')}
  {#if memo.film}
    <div class="sub">
      <label class="fl"><span>{t('ed.date')}</span><input type="date" bind:value={memo.film.date} /></label>
      <div class="two">
        <label class="fl"><span>{t('ed.start')}</span><input type="time" bind:value={memo.film.from} /></label>
        <label class="fl"><span>{t('ed.end')}</span><input type="time" bind:value={memo.film.to} /></label>
      </div>
      <Field label={t('memo.note')} bind:value={memo.film.note} maxlength={200} placeholder={t('memo.filmPh')} />
    </div>
  {/if}
  </div>
  {/if}
</section>

<style>
  .memo, .body { display: flex; flex-direction: column; gap: var(--s-3); }
  .hint { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  /* a request's fields, under its switch */
  .sub { display: flex; flex-direction: column; gap: var(--s-3); margin: 0 0 var(--s-2) var(--s-3); padding-left: var(--s-3); border-left: 2px solid var(--line-2); }
  .bare .sub { margin: 0; padding: 0; border: 0; } /* one request alone: nothing to hang under */
  .two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-2); align-items: end; }
  .three { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--s-2); align-items: end; }
  .day { display: flex; align-items: flex-end; gap: var(--s-1); }
  .day .fl { flex: 1; }
  .day > :global(:last-child:not(.fl)) { margin-bottom: 7px; }
  .lone { align-self: flex-start; }
  .lbl { margin: 0 var(--s-4) -6px; font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .item { display: flex; flex-direction: column; gap: var(--s-3); }
  .item + .item { padding-top: var(--s-3); border-top: 0.5px solid var(--separator); }
  /* Field's look for the date and time inputs it can't take yet */
  .fl { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .fl > span { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .fl > input { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
</style>
