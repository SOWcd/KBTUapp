<script lang="ts">
  // The page after sending. fresh: first the success moment (a check that draws itself), then it settles into the
  // status page: status, my interview (Teams, calendar, change), what's left for enrolment, "keep this link".
  import { untrack } from 'svelte';
  import Check from '@lucide/svelte/icons/check';
  import Clock from '@lucide/svelte/icons/clock';
  import Info from '@lucide/svelte/icons/info';
  import Video from '@lucide/svelte/icons/video';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import Copy from '@lucide/svelte/icons/copy';
  import Button from '../../ui/Button.svelte';
  import { ako } from '../../lib/api/ako';
  import type { AkoView } from '../../lib/api/types';
  import { aw, type AkoKey } from '../../lib/i18n/ako';
  import { time, weekday, dayMonth } from '../../lib/time';
  import AkoDocs, { errKey } from './AkoDocs.svelte';
  import AkoSlots from './AkoSlots.svelte';

  let { view, token, fresh, onchange }: { view: AkoView; token: string; fresh: boolean; onchange: (v: AkoView) => void } = $props();

  let moment = $state(untrack(() => fresh));
  let changing = $state(false);
  let calBusy = $state(false);
  let copied = $state(false);
  let note = $state<AkoKey | ''>('');

  const program = $derived(view.programs.find((p) => p.key === view.program) ?? null);
  const open = $derived(view.status === 'sent' || view.status === 'review');
  const left = $derived(program ? program.later.filter((d) => !view.files.some((f) => f.doc === d)) : []);
  // once shown, the list stays (a page being uploaded must not lose its tile when the last document gets its first page)
  let docs = $state(untrack(() => left.length > 0));
  const k = (s: string) => s as AkoKey;
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

  $effect(() => {
    if (!moment) return;
    const t = setTimeout(() => (moment = false), 2400);
    return () => clearTimeout(t);
  });

  function slotChanged(v: AkoView) {
    if (v.slot && v.slot.id !== view.slot?.id) changing = false;
    onchange(v);
  }
  function teams() {
    if (view.slot?.teams) window.open(view.slot.teams, '_blank', 'noopener,noreferrer');
  }
  async function calendar() {
    note = ''; calBusy = true;
    try {
      const url = URL.createObjectURL(await ako.ics(token));
      const a = document.createElement('a');
      a.href = url; a.download = 'interview.ics';
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) { note = errKey(e); } finally { calBusy = false; }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(location.href); }
    catch {
      // an in-app browser without the clipboard API: the old way
      const ta = document.createElement('textarea');
      ta.value = location.href; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.append(ta); ta.select();
      try { document.execCommand('copy'); } catch { /* nothing more to try */ }
      ta.remove();
    }
    copied = true;
    setTimeout(() => (copied = false), 2600);
  }
</script>

{#if moment}
  <section class="moment" role="status">
    <span class="seal">
      <i class="halo"></i>
      <span class="disc"><span class="wipe"><span><Check size={46} strokeWidth={2.6} /></span></span></span>
    </span>
    <h1 class="a-h1 m1">{aw('ako.doneTitle')}</h1>
    <p class="a-lead m2">{aw('ako.doneLead')}</p>
  </section>
{:else}
  <div class="status">
    <section class="a-card st {view.status}">
      <span class="badge">
        {#if view.status === 'review'}<Clock size={26} />{:else if view.status === 'declined'}<Info size={26} />{:else}<Check size={26} strokeWidth={2.6} />{/if}
      </span>
      <h1 class="a-h1">{aw(k('ako.status.' + view.status))}</h1>
      <p class="a-lead">{aw(k('ako.statusLead.' + view.status))}</p>
      {#if view.sentAt}<p class="a-sub when">{aw('ako.sentOn', { when: dayMonth(view.sentAt) + ', ' + time(view.sentAt) })}</p>{/if}
    </section>

    {#if program?.interview}
      {#if view.slot}
        <section class="a-card iv">
          <span class="a-sub">{aw('ako.step.slot')}</span>
          <b class="day">{cap(weekday(view.slot.at))}, {dayMonth(view.slot.at)}</b>
          <p class="clock"><b>{time(view.slot.at)}</b><span class="a-sub">{aw('ako.almaty')}</span></p>
          <div class="acts">
            {#if view.slot.teams}
              <Button size="l" full onclick={teams}>{#snippet icon()}<Video size={20} />{/snippet}{aw('ako.joinTeams')}</Button>
            {/if}
            <Button kind="gray" size="l" full loading={calBusy} onclick={calendar}>{#snippet icon()}<CalendarPlus size={20} />{/snippet}{aw('ako.addCal')}</Button>
          </div>
          {#if note}<p class="a-note bad" role="alert">{aw(note)}</p>{/if}
          {#if open}
            <button type="button" class="a-quiet" aria-expanded={changing} onclick={() => (changing = !changing)}>{aw(changing ? 'ako.back' : 'ako.changeTime')}</button>
          {/if}
        </section>
        {#if open && changing}
          <div class="times"><AkoSlots {view} {token} compact onchange={slotChanged} /></div>
        {/if}
      {:else if open}
        <section class="again">
          <h2 class="a-h2">{aw('ako.slotTitle')}</h2>
          <div class="times"><AkoSlots {view} {token} compact onchange={slotChanged} /></div>
        </section>
      {/if}
    {/if}

    {#if open && program}
      {#if docs}
        <section class="left">
          <h2 class="a-h2">{aw('ako.laterTitle')}</h2>
          {#if left.length}<p class="a-lead">{aw('ako.laterLead')}</p>
          {:else}<p class="a-note ok done"><Check size={20} strokeWidth={2.6} />{aw('ako.allDone')}</p>{/if}
          <AkoDocs {view} {token} only="later" {onchange} />
        </section>
      {:else}
        <p class="a-note ok done"><Check size={20} strokeWidth={2.6} />{aw('ako.allDone')}</p>
      {/if}
    {/if}

    <section class="a-card keep">
      <p>{aw('ako.keepLink')}</p>
      <Button kind="gray" size="l" full done={copied} onclick={copy}>
        {#snippet icon()}<Copy size={20} />{/snippet}{aw(copied ? 'ako.copied' : 'ako.copyLink')}
      </Button>
      <span class="sr" aria-live="polite">{copied ? aw('ako.copied') : ''}</span>
    </section>
  </div>
{/if}

<style>
  /* ---- the success moment ---- */
  .moment { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 62vh;
    padding: var(--s-10) 0; text-align: center; }
  .seal { position: relative; display: grid; place-items: center; width: 104px; height: 104px; margin-bottom: var(--s-8); }
  .disc { position: relative; display: grid; place-items: center; width: 104px; height: 104px; border-radius: var(--r-full);
    background: var(--success); color: var(--on-accent); animation: seal 520ms var(--ease-bounce) both; }
  .halo { position: absolute; inset: 0; border-radius: var(--r-full); background: var(--success); opacity: 0;
    animation: halo 1100ms var(--ease) 260ms both; }
  /* the check draws itself: a window slides in from the left while its content slides back by the same amount */
  .wipe { display: block; overflow: hidden; animation: wipe 460ms var(--ease-spring) 380ms both; }
  .wipe > span { display: block; animation: unwipe 460ms var(--ease-spring) 380ms both; }
  .wipe :global(svg) { display: block; }
  .m1 { animation: rise var(--t-slow) var(--ease) 620ms both; }
  .m2 { max-width: 20em; animation: rise var(--t-slow) var(--ease) 760ms both; }
  @keyframes seal { from { opacity: 0; transform: scale(0.6); } }
  @keyframes halo { from { opacity: 0.35; transform: scale(1); } to { opacity: 0; transform: scale(1.7); } }
  @keyframes wipe { from { transform: translateX(-100%); } }
  @keyframes unwipe { from { transform: translateX(100%); } }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } }

  /* ---- the status page ---- */
  .status { display: flex; flex-direction: column; gap: var(--s-3); padding-bottom: var(--s-8); }
  .status > * { animation: rise var(--t-slow) var(--ease) both; }
  .status > :nth-child(2) { animation-delay: 60ms; }
  .status > :nth-child(3) { animation-delay: 120ms; }
  .status > :nth-child(n + 4) { animation-delay: 180ms; }
  .status > :global(.a-card + .a-card) { margin-top: 0; }

  .st { display: flex; flex-direction: column; align-items: flex-start; padding: var(--s-6) var(--s-5); }
  .badge { display: grid; place-items: center; width: 44px; height: 44px; margin-bottom: var(--s-4); border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); }
  .st.accepted .badge { background: var(--success-soft); color: var(--success-text); }
  .st.declined .badge { background: var(--fill); color: var(--text-2); }
  .when { margin-top: var(--s-4); color: var(--text-3); }

  .iv { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-1); padding-bottom: var(--s-3); }
  .day { margin-top: var(--s-1); font: 700 var(--fs-sec)/1.2 var(--font-display); letter-spacing: -0.01em; }
  .clock { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0 var(--s-3); }
  .clock b { font: 800 var(--fs-t1)/1.15 var(--font-display); letter-spacing: -0.03em; font-variant-numeric: tabular-nums; }
  .acts { display: flex; flex-direction: column; gap: var(--s-3); width: 100%; margin: var(--s-4) 0 var(--s-1); }
  .iv .a-note { width: 100%; margin-top: var(--s-2); }
  .iv:not(:has(.a-quiet)) { padding-bottom: var(--s-5); }

  .times { animation: rise var(--t-base) var(--ease) both; }
  .again, .left { margin-top: var(--s-6); }

  .done { display: flex; align-items: center; gap: var(--s-2); min-height: 56px; }
  .left .done { margin-top: var(--s-3); }

  .keep { display: flex; flex-direction: column; gap: var(--s-4); margin-top: var(--s-6); }
  .keep p { color: var(--text-2); }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; pointer-events: none; }

  @media (prefers-reduced-motion: reduce) {
    .disc, .halo, .wipe, .wipe > span, .m1, .m2, .status > *, .times { animation: none; }
  }
</style>
