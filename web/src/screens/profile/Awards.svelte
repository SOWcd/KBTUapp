<script lang="ts">
  // Awards (SPEC §4.11), a sheet from the badge's numbers (no longer Profile's third page): the whole collection. On top, the one closest to its next level (the reason to go to
  // one more event); then every achievement as a card — the medal in its tier's rim, the tier, the way to the next level,
  // how rare it is — earned first; then the badges. "Showcase" turns the page into a picker: up to 6 achievements or
  // badges for the badge on Me, in the order tapped, with the shelf previewed on top. A tap otherwise opens the award card.
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Check from '@lucide/svelte/icons/check';
  import { api, type Achievement } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { data, loadMyCard } from '../../lib/state/data.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { achItem, achName, badgeItem, closest as closestOf, hero, leftLine, nextOf, shelfItem, tierName, type ShelfItem } from '../../lib/awards';
  import { dayMonth } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Medal from '../../ui/Medal.svelte';
  import Pin from '../../ui/Pin.svelte';
  import Award from '../../ui/Award.svelte';
  import Button from '../../ui/Button.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import Recent from './Recent.svelte';

  const me = $derived(session.me);
  const p = $derived(data.myCard); // loaded with the app (and kept for the next launch); coming into view refreshes it
  $effect(() => { void me?.showcase; if (me?.student) void loadMyCard(); }); // opened: refreshed

  const ach = $derived(p?.awards.achievements ?? []);
  const earned = $derived(ach.filter((a) => a.level > 0));
  const hidden = (a: Achievement) => a.secret && a.level === 0;
  const ratio = (a: Achievement) => { const n = nextOf(a); return n ? a.count / n.need : 1; };
  // earned first (higher tiers first), then the ones on their way, then the secrets
  const sorted = $derived([...ach].sort((a, b) => Number(hidden(a)) - Number(hidden(b)) || b.level - a.level || ratio(b) - ratio(a)));
  // the closest to its next level: the reason to go to one more event
  const closest = $derived(closestOf(ach));
  const tierOf = (i: number) => t(`ach.tier.${i + 1}` as 'ach.tier.1');
  const pct = (a: Achievement) => { const n = nextOf(a); return n ? Math.min(100, Math.max(4, (a.count / n.need) * 100)) : 100; };
  const share = (x: number) => (x > 0 && x < 0.01 ? '<1' : String(Math.round(x * 100)));
  const tierClass = (a: Achievement) => (a.level === 0 ? 'none' : a.levels.length === 1 ? 'one' : ['bronze', 'silver', 'gold', 'legend'][a.level - 1] ?? 'legend');

  // ---- the showcase picker ----
  let editing = $state(false);
  let picked = $state<string[]>([]);
  let saving = $state(false);
  function edit() {
    if (!p) return;
    picked = (p.shelf.length ? p.shelf : hero(p).shelf.map((x) => x.key.startsWith('a') ? x.key.slice(1) : x.key)).slice(0, 6);
    editing = true;
    haptic.select();
  }
  function toggle(key: string, have: boolean) {
    const i = picked.indexOf(key);
    if (i >= 0) { picked = picked.filter((k) => k !== key); haptic.select(); return; }
    if (!have) { haptic.error(); say(t('awp.locked'), 'pleading_face_3d'); return; }
    if (picked.length >= 6) { haptic.error(); say(t('awp.full'), 'pleading_face_3d'); return; }
    picked = [...picked, key];
    haptic.select();
  }
  async function done() {
    saving = true;
    try {
      session.me = await api.updateMe({ showcase: picked });
      editing = false;
      haptic.ok(); say(t('awp.saved'), 'sparkles_3d');
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { saving = false; }
  }
  const preview = $derived(p ? picked.map((k) => shelfItem(p!, k)).filter((x): x is ShelfItem => !!x) : []);
  const open = (it: ShelfItem) => sheets.award(it, true);
</script>

<div class="page" class:editing>
  {#if session.ready && !me?.student}
    <section class="hello">
      <span class="mark"><KbtuMark /></span>
      <h2 class="t-h2">{t('awp.guestTitle')}</h2>
      <p class="t-callout">{t('awp.guestText')}</p>
      <Button kind="primary" size="l" full onclick={() => sheets.login()}>{t('guest.button')}</Button>
    </section>
  {:else}
    <header class="hd">
      <span><h1 class="t-h1">{t('page.awards')}</h1>
        <p class="t-foot">{p ? [p.attended >= 0 ? `${p.attended} ${tn('person.eventsWord', p.attended)}` : '', t('awp.summary', { n: earned.length, total: ach.length }), tn('awp.badges', p.awards.badges.length)].filter(Boolean).join(' · ') : ' '}</p></span>
      {#if p && !editing}<button class="pill" onclick={edit}><Sparkles size={17} />{t('awp.showcase')}</button>{/if}
    </header>

    {#if p}
      {#if editing}
        <!-- the picker: the shelf as it will hang on the badge, then the collection below with order marks -->
        <section class="pick">
          <div class="pick-top"><b>{t('awp.pick')}</b><span class="num">{picked.length}/6</span></div>
          <div class="shelf">
            {#each Array(6) as _, i (i)}
              {#if preview[i]}<button class="slot full" onclick={() => toggle(picked[i], true)} aria-label={preview[i].name}><Award it={preview[i]} size={42} /></button>
              {:else}<span class="slot" aria-label={t('awp.empty')}></span>{/if}
            {/each}
          </div>
          <Button kind="primary" size="m" full loading={saving} onclick={done}>{#snippet icon()}<Check size={18} />{/snippet}{t('awp.done')}</Button>
        </section>
      {:else if closest}
        {@const n = nextOf(closest)}
        <button class="next" onclick={() => open(achItem(closest))}>
          <Medal a={closest} size={60} />
          <span class="nx">
            <i class="t-cap">{t('awp.next')}</i>
            <b class="ellipsis">{achName(closest) + (closest.levels.length > 1 && n ? ' · ' + tierOf(closest.levels.indexOf(n)) : '')}</b>
            <span class="bar"><span style="width:{pct(closest)}%"></span></span>
            <em>{leftLine(closest)}</em>
          </span>
        </button>
      {/if}

      {#if !editing}<Recent />{/if}

      <h2 class="sh">{t('person.achievements')}</h2>
      <div class="grid">
        {#each sorted as a, i (a.code)}
          {@const n = nextOf(a)}
          {@const order = picked.indexOf(a.code)}
          <button class="ach {tierClass(a)}" class:off={a.level === 0} class:on={editing && order >= 0} style="--i:{i}"
                  onclick={() => (editing ? toggle(a.code, a.level > 0) : open(achItem(a)))}>
            <span class="md"><Medal {a} size={62} /></span>
            <b class="nm">{achName(a)}</b>
            <i class="tr">{a.level ? (a.levels.length > 1 ? t('aw.level', { tier: tierName(a) }) : t('aw.have')) : t('ach.locked')}</i>
            {#if !hidden(a)}
              {#if n}
                <span class="prog"><span class="bar"><span style="width:{pct(a)}%"></span></span><span class="cnt num">{a.count}/{n.need}</span></span>
              {:else if a.levels.length > 1}
                <span class="prog max">{t('awp.max')} · {a.count}</span>
              {/if}
              <span class="rare">{t('awp.rarity', { p: share(a.level ? a.levels[a.level - 1].rarity : a.rarity) })}</span>
            {/if}
            {#if editing && order >= 0}<span class="ord num">{order + 1}</span>{/if}
          </button>
        {/each}
      </div>

      <h2 class="sh">{t('person.badges')}</h2>
      {#if p.awards.badges.length}
        <div class="pins">
          {#each p.awards.badges as b, i (b.eventId)}
            {@const order = picked.indexOf('b' + b.eventId)}
            <button class="pinc" class:on={editing && order >= 0} style="--i:{i}" onclick={() => (editing ? toggle('b' + b.eventId, true) : open(badgeItem(b)))}>
              <Pin emoji={b.emoji} color={b.color} size={64} />
              <b class="nm">{b.title}</b>
              <i class="tr">{dayMonth(b.at)}</i>
              {#if editing && order >= 0}<span class="ord num">{order + 1}</span>{/if}
            </button>
          {/each}
        </div>
      {:else}
        <div class="nopins"><span class="ghost"><Pin emoji="sparkles_3d" color="#7C4DFF" size={54} /></span><p class="t-foot">{t('awp.badgesEmpty')}</p></div>
      {/if}
    {:else}
      <div class="skel"><span class="s1"></span><div class="sg"><span></span><span></span><span></span><span></span></div></div>
    {/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { display: flex; flex-direction: column; gap: 14px; }
  .page > :global(*) { flex-shrink: 0; }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }
  .hd p { margin-top: 4px; }
  .pill { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 14px/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .pill:active { transform: scale(0.95); }
  .sh { font: 750 19px/1.2 var(--font-display); letter-spacing: -0.025em; margin-top: 6px; }

  /* the closest one: medal, how far, a bar in the brand gradient */
  .next { display: flex; align-items: center; gap: 14px; padding: 14px 16px 14px 14px; border-radius: var(--r-xl); text-align: left;
    background: radial-gradient(90% 120% at 0% 0%, rgba(124, 77, 255, 0.22), transparent 60%), var(--surface); box-shadow: inset 0 0 0 1px var(--line);
    animation: rise 460ms cubic-bezier(.2, .9, .25, 1.05) backwards; transition: transform var(--t-fast) var(--ease); }
  .next:active { transform: scale(0.98); }
  .nx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
  .nx i { font-style: normal; color: var(--accent-text); }
  .nx b { font: 720 17px/1.2 var(--font-display); letter-spacing: -0.015em; }
  .nx em { font: 560 13px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .bar { position: relative; display: block; height: 6px; border-radius: 3px; background: var(--surface-3); overflow: hidden; flex: 1; }
  .bar > span { position: absolute; inset: 0 auto 0 0; border-radius: 3px; background: var(--grad-accent); transition: width 600ms cubic-bezier(.2, .9, .25, 1); }

  /* every achievement: a card lit by its tier */
  .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .ach { --g: transparent; position: relative; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 16px 12px 12px; border-radius: var(--r-l); text-align: center;
    background: radial-gradient(80% 60% at 50% 0%, var(--g), transparent 75%), var(--surface); box-shadow: inset 0 0 0 1px var(--line);
    animation: rise 440ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 40ms); transition: transform var(--t-fast) var(--ease), box-shadow var(--t-base) var(--ease); }
  .ach:active, .pinc:active { transform: scale(0.97); }
  .ach.bronze { --g: rgba(205, 127, 50, 0.24); }
  .ach.silver { --g: rgba(170, 184, 214, 0.26); }
  .ach.gold, .ach.one { --g: rgba(255, 200, 61, 0.24); }
  .ach.legend { --g: rgba(124, 77, 255, 0.3); }
  .md { position: relative; display: flex; margin-bottom: 6px; }
  /* one pass of light across an earned medal when it comes into view (inside the object only: owner's taste) */
  .ach:not(.off) .md::after { content: ''; position: absolute; inset: 3px; border-radius: 50%; pointer-events: none; mix-blend-mode: overlay;
    background: linear-gradient(115deg, transparent 35%, rgba(255, 255, 255, 0.75) 50%, transparent 65%) no-repeat; background-size: 250% 100%;
    animation: sheen 1.6s ease-out 700ms backwards; animation-delay: calc(700ms + var(--i) * 90ms); background-position: 160% 0; }
  @keyframes sheen { from { background-position: -60% 0; } }
  .nm { font: 680 14.5px/1.2 var(--font-text); letter-spacing: -0.01em; }
  .tr { font: 600 12px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  .ach.off .nm { color: var(--text-2); }
  .prog { display: flex; align-items: center; gap: 8px; width: 100%; margin-top: 6px; }
  .prog .bar { height: 5px; }
  .cnt { flex: none; font: 650 11.5px/1 var(--font-text); color: var(--text-2); }
  .prog.max { justify-content: center; font: 650 11.5px/1 var(--font-text); color: var(--warning-text); }
  .rare { font: 550 11px/1.2 var(--font-text); color: var(--text-3); margin-top: 2px; }

  .pins { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
  .pinc { position: relative; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 6px 10px; border-radius: var(--r-l); text-align: center;
    background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); animation: rise 440ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 50ms);
    transition: transform var(--t-fast) var(--ease); }
  .pinc .nm { font-size: 12.5px; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .nopins { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-radius: var(--r-l); border: 1.5px dashed var(--line-2); }
  .ghost { display: flex; flex: none; opacity: 0.55; filter: grayscale(0.4); }

  /* the picker */
  .pick { position: sticky; top: 0; z-index: 2; display: flex; flex-direction: column; gap: 12px; padding: 14px; border-radius: var(--r-xl);
    background: color-mix(in srgb, var(--surface) 88%, transparent); -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
    box-shadow: inset 0 0 0 1.5px var(--accent), 0 18px 34px -24px rgba(0, 0, 0, 0.6); animation: rise 360ms cubic-bezier(.2, .9, .25, 1.05) backwards; }
  .pick-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .pick-top b { font: 680 15px/1.2 var(--font-text); }
  .pick-top .num { font: 700 13px/1 var(--font-text); color: var(--accent-text); }
  .shelf { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 6px; }
  .slot { aspect-ratio: 1; border-radius: 50%; border: 1.5px dashed var(--line-2); display: flex; align-items: center; justify-content: center; }
  .slot.full { border: none; animation: pop 380ms cubic-bezier(.2, 1.4, .4, 1) backwards; }
  @keyframes pop { from { transform: scale(0.5); opacity: 0; } }
  .editing .ach.on, .editing .pinc.on { box-shadow: inset 0 0 0 2px var(--accent); }
  .editing .ach.off { opacity: 0.55; }
  .ord { position: absolute; top: 8px; right: 8px; width: 22px; height: 22px; border-radius: 50%; background: var(--accent); color: #fff;
    font: 750 12px/22px var(--font-text); text-align: center; animation: pop 300ms cubic-bezier(.2, 1.4, .4, 1) backwards; }

  .hello { display: flex; flex-direction: column; gap: 12px; padding: 22px 18px 18px; border-radius: var(--r-xl); color: #fff;
    background: radial-gradient(90% 80% at 20% 0%, rgba(255, 178, 61, 0.45), transparent 60%), linear-gradient(160deg, #2443B8, #101633); }
  .hello p { color: rgba(255, 255, 255, 0.82); }
  .mark { color: #fff; width: 64px; height: 64px; border-radius: 20px; background: rgba(255, 255, 255, 0.14); display: flex; align-items: center; justify-content: center; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2); }

  .skel { display: flex; flex-direction: column; gap: 12px; }
  .skel span { display: block; border-radius: var(--r-l); background: var(--surface-2); animation: pulse 1.2s ease-in-out infinite; }
  .s1 { height: 92px; }
  .sg { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .sg span { height: 168px; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  @keyframes rise { from { opacity: 0; transform: translateY(14px) scale(0.98); } }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
</style>
