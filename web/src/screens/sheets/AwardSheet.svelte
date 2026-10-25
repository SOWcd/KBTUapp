<script lang="ts">
  // One award up close (SPEC §4.11), over whatever profile it was tapped on. An achievement: the medal big with the
  // tilt light, what it takes, the way to the next level and how rare every level is; a secret one shows only its
  // hint until earned. A badge: the event it came from. The Creator's seal: what it is, in the words everyone
  // reads, the creator included (owner, Oct 6: "show me what others see").
  // Mine and earned: Share sends our bot's card (aw_<code>: the reader sees their own way to it).
  // ponytail: no earned date (nothing records it until the unlock moment ships).
  import { onMount } from 'svelte';
  import Check from '@lucide/svelte/icons/check';
  import type { ShelfItem } from '../../lib/awards';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';
  import Share from '@lucide/svelte/icons/share';
  import { haptic, shareCard } from '../../lib/tg';
  import { say } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import Button from '../../ui/Button.svelte';
  import { glass } from '../../ui/glass';
  import Sheet from '../../ui/Sheet.svelte';
  import Award from '../../ui/Award.svelte';
  import { nameOf } from '../../lib/short';

  let { overlay, it, mine = false }: { overlay: Overlay; it: ShelfItem; mine?: boolean } = $props();
  let sharing = $state(false);
  async function shareIt() {
    if (!it.ach) return;
    sharing = true; haptic.tap();
    try { if (await shareCard({ kind: 'aw', code: it.ach.code }, 'https://t.me/KBTUappBot?startapp=aw_' + it.ach.code, t('aw.shareText', { name: it.name }))) say(phrase('say.shared'), 'party_popper_3d'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { sharing = false; }
  }
  const a = $derived(it.ach), b = $derived(it.badge);
  const hidden = $derived(!!a && a.secret && a.level === 0);
  const tiers = $derived(!!a && a.levels.length > 1);
  const next = $derived(a?.levels.find((l) => !l.reached));
  const pct = $derived(a && next ? Math.min(100, Math.max(3, (a.count / next.need) * 100)) : 100); // as the words say: 6 of 15
  const share = (x: number) => (x > 0 && x < 0.01 ? '<1' : String(Math.round(x * 100)));
  const tierOf = (i: number) => t(`ach.tier.${i + 1}` as 'ach.tier.1');

  let medal: HTMLSpanElement;
  onMount(() => {
    haptic.soft();
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches)
      medal.animate([{ transform: 'scale(0.55) rotate(-14deg)', opacity: 0 }, { transform: 'scale(1.06) rotate(3deg)', opacity: 1, offset: 0.62 }, { transform: 'none' }],
        { duration: 620, easing: 'cubic-bezier(.2,.9,.25,1)' });
  });
</script>

<Sheet {overlay} title={it.ach ? t('cap.achievement') : it.founder ? t('cap.founder') : it.idea ? t('cap.idea') : t('cap.badge')}>
  <div class="stage" use:glass>
    <span class="big" class:round={!!a || !!it.founder || !!it.idea} bind:this={medal}><Award {it} size={132} /><span class="shine"></span></span>
  </div>
  <h2 class="t-h2 name">{it.name}</h2>

  {#if a}
    {#if a.level && tiers}<p class="tier">{t('aw.level', { tier: tierOf(a.level - 1) })}</p>{/if}
    {#if a.now}<p class="tier">{tn('ach.streakNow', a.now)}</p>{/if}
    <p class="t-callout how">{t(`ach.${a.code}.how` as 'ach.regular.how')}</p>
    {#if a.level && a.at}<p class="t-foot got">{t('aw.earned', { date: dayMonth(a.at) })}</p>{/if}
    {#if !hidden}
      {#if next}
        <div class="prog">
          <div class="row"><b>{t('ach.progress', { count: a.count, need: next.need })}</b>{#if tiers}<span>{t('aw.toLevel', { tier: tierOf(a.levels.indexOf(next)) })}</span>{/if}</div>
          <div class="bar"><span style="width:{pct}%"></span></div>
        </div>
      {:else}
        <p class="top">{tiers ? t('aw.topCount', { count: a.count }) : t('aw.have')}</p>
      {/if}
      {#if tiers}
        <div class="ladder">
          <div class="lh t-cap"><span>{t('aw.levels')}</span><span>{t('aw.need')}</span><span>{t('aw.students')}</span></div>
          {#each a.levels as l, i (i)}
            <div class="lv" class:got={l.reached}>
              <span class="ln">{#if l.reached}<Check size={15} strokeWidth={2.6} />{/if}{tierOf(i)}</span>
              <span>{l.need}</span><span>{share(l.rarity)}%</span>
            </div>
          {/each}
        </div>
      {:else}
        <p class="t-foot rar">{t('person.rarity', { p: share(a.levels[0].rarity) })}</p>
      {/if}
    {/if}
  {:else if b}
    <p class="tier">{nameOf(b.org)} · {dayMonth(b.at)}</p>
    <p class="t-callout how">{t('aw.badgeHow')}</p>
  {:else if it.founder || it.idea}
    <p class="t-callout how">{t('seal.one')}</p>
  {/if}

  {#snippet footer()}
    {#if mine && a && a.level > 0}
      <Button kind="primary" size="l" full loading={sharing} onclick={shareIt}>{#snippet icon()}<Share size={18} />{/snippet}{t('aw.share')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .stage { display: flex; justify-content: center; padding: 10px 0 6px; perspective: 700px; }
  .big { position: relative; display: inline-flex; transform: rotateX(calc(var(--gy, 0) * -14deg)) rotateY(calc(var(--gx, 0) * 16deg)); transition: transform 160ms ease-out; }
  /* the light slides over the metal with the tilt (round medals only: a pin's corners stay clean) */
  .shine { display: none; }
  .round .shine { display: block; position: absolute; inset: 0; border-radius: 50%; pointer-events: none; mix-blend-mode: soft-light;
    background: radial-gradient(60% 60% at calc(35% + var(--gx, 0) * 30%) calc(25% + var(--gy, 0) * 30%), rgba(255, 255, 255, 0.75), transparent 70%); }
  .name { text-align: center; margin-top: 8px; }
  .got { text-align: center; margin-top: 2px; }
  .tier { text-align: center; margin-top: 4px; font: 650 14px/1.3 var(--font-text); color: var(--accent-text); }
  .how { text-align: center; margin: 10px 6px 0; color: var(--text-2); }

  .prog { margin-top: 16px; padding: 12px 14px; border-radius: var(--r-m); background: var(--surface-2); }
  .prog .row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .prog b { font: 720 17px/1.2 var(--font-display); }
  .prog .row span { font: 560 13px/1.2 var(--font-text); color: var(--text-2); }
  .bar { height: 8px; margin-top: 10px; border-radius: 4px; background: var(--surface-3); overflow: hidden; }
  .bar span { display: block; height: 100%; border-radius: 4px; background: var(--grad-accent); }
  .rar { text-align: center; margin-top: 8px; }
  .top { text-align: center; margin-top: 14px; font: 650 14px/1.3 var(--font-text); color: var(--success-text); }

  .ladder { margin-top: 14px; display: flex; flex-direction: column; border-radius: var(--r-m); background: var(--surface-2); padding: 4px 0; }
  .lh, .lv { display: grid; grid-template-columns: 1fr 70px 90px; align-items: center; padding: 8px 14px; }
  .lh { color: var(--text-3); padding-bottom: 4px; }
  .lh span:not(:first-child), .lv span:not(:first-child) { text-align: right; }
  .lv { font: 600 14.5px/1.2 var(--font-text); color: var(--text-2); }
  .lv + .lv { box-shadow: inset 0 1px 0 var(--line); }
  .lv.got { color: var(--text); }
  .ln { display: inline-flex; align-items: center; gap: 6px; }
  .lv.got .ln { color: var(--success-text); }
</style>
