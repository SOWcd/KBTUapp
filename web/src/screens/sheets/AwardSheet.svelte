<script lang="ts">
  // One award up close (SPEC §4.11), over whatever profile it was tapped on. An achievement: the medal big with the
  // tilt light, what it takes, the way to the next level and how rare every level is; a secret one shows only its
  // hint until earned. A badge: the event it came from. The Creator's seal: what it is, in the words everyone
  // reads, the creator included.
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
  import { session } from '../../lib/state/session.svelte';
  import Megaphone from '@lucide/svelte/icons/megaphone';

  let { overlay, it, mine = false }: { overlay: Overlay; it: ShelfItem; mine?: boolean } = $props();
  let sharing = $state(false);
  async function shareIt() {
    if (!it.ach) return;
    sharing = true; haptic.tap();
    try { if (await shareCard({ kind: 'aw', code: it.ach.code }, 'https://t.me/KBTUappBot?startapp=aw_' + it.ach.code, t('aw.shareText', { name: it.name }))) say(phrase('say.shared'), 'party_popper_3d'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { sharing = false; }
  }
  // "Recruiter" is earned by my invite link: the link right here (owner, Oct 29: no hunting for it on Me)
  let inviting = $state(false);
  const ref = $derived(mine && it.ach?.code === 'referral' ? session.me?.referrals : null);
  async function invite() {
    if (!ref) return;
    inviting = true; haptic.tap();
    try { await shareCard({ kind: 'rf', id: '0' }, `https://t.me/KBTUappBot?startapp=r_${ref.code}`, t('ref.text'), () => (inviting = false)); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { inviting = false; }
  }
  const a = $derived(it.ach), b = $derived(it.badge);
  const hidden = $derived(!!a && a.secret && a.level === 0);
  const tiers = $derived(!!a && a.levels.length > 1);
  const next = $derived(a?.levels.find((l) => !l.reached));
  const pct = $derived(a && next ? Math.min(100, Math.max(3, (a.count / next.need) * 100)) : 100); // as the words say: 6 of 15
  const share = (x: number) => (x > 0 && x < 0.01 ? '<1' : String(Math.round(x * 100)));
  const tierOf = (i: number) => t(`ach.tier.${i + 1}` as 'ach.tier.1');
  // the stage's light: the metal's own colour (one-level accent, bronze, silver, gold, legend; a drawn medal its metal);
  // none on a medal not earned yet. The rays and halo only behind a round one (a pin's corners stay clean)
  const GLOW = ['124, 77, 255', '224, 160, 106', '200, 210, 230', '255, 196, 80', '176, 124, 255']; // r, g, b: rgba() below (no color-mix on old iOS)
  const DRAWN: Record<string, string> = { medal_init26: GLOW[3], medal_init26f: GLOW[2] };
  const round = $derived(!!a || !!it.founder || !!it.idea);
  const glow = $derived(it.founder || it.idea ? GLOW[0] : !a || !a.level ? '' : DRAWN[a.emoji] ?? (tiers ? GLOW[Math.min(a.level, 4)] : GLOW[0]));
  // the same metal darker, for the line over the name on a light sheet (the bright gold is 1.7:1 on white)
  const deep = $derived(glow.split(',').map((c) => Math.round(+c * 0.55)).join(', '));
  // the line over the name: the event a medal is from, else the level reached; a badge: its club and day
  const kicker = $derived(a?.code === 'init26' || a?.code === 'init26f' ? t('aw.init26') : a?.level && tiers ? t('aw.level', { tier: tierOf(a.level - 1) })
    : b ? `${nameOf(b.org)} · ${dayMonth(b.at)}` : '');

  let medal: HTMLSpanElement;
  onMount(() => {
    haptic.soft();
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches)
      medal.animate([{ transform: 'scale(0.55) rotate(-14deg)', opacity: 0 }, { transform: 'scale(1.06) rotate(3deg)', opacity: 1, offset: 0.62 }, { transform: 'none' }],
        { duration: 620, easing: 'cubic-bezier(.2,.9,.25,1)' });
  });
</script>

<Sheet {overlay} title={it.ach ? t('cap.achievement') : it.founder ? t('cap.founder') : it.idea ? t('cap.idea') : t('cap.badge')}>
  <div class="stage" class:lit={round && !!glow} style:--glow={glow} use:glass>
    {#if round && glow}<span class="rays" aria-hidden="true"></span><span class="halo" aria-hidden="true"></span>{/if}
    <span class="big" class:round bind:this={medal}><Award {it} size={round ? 196 : 132} /><span class="shine"></span>{#if round && glow}<span class="sweep"></span>{/if}</span>
  </div>
  {#if kicker}<p class="kick" class:metal={!!glow} style:--k={glow} style:--kd={deep}>{kicker}</p>{/if}
  <h2 class="t-h2 name">{it.name}</h2>

  {#if a}
    {#if a.now}<p class="tier">{tn('ach.streakNow', a.now)}</p>{/if}
    <p class="t-callout how">{t(`ach.${a.code}.how` as 'ach.regular.how')}</p>
    {#if a.level && a.at && tiers}<p class="t-foot got">{t('aw.earned', { date: dayMonth(a.at) })}</p>{/if}
    {#if !hidden}
      {#if a.level && !tiers}
        <!-- earned, one level: the day and how rare, side by side (once: no "Earned" above and below) -->
        <div class="facts">
          <div><b>{a.at ? dayMonth(a.at) : t('aw.have')}</b>{#if a.at}<span>{t('aw.gotOn')}</span>{/if}</div>
          <div><b>{share(Math.max(a.levels[0].rarity, 0.001))}%</b><span>{t('aw.haveIt')}</span></div>
        </div>
      {:else if next}
        <div class="prog">
          <div class="row"><b>{t('ach.progress', { count: a.count, need: next.need })}</b>{#if tiers}<span>{t('aw.toLevel', { tier: tierOf(a.levels.indexOf(next)) })}</span>{/if}</div>
          <div class="bar"><span style="width:{pct}%"></span></div>
        </div>
      {:else}
        <p class="top">{t('aw.topCount', { count: a.count })}</p>
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
      {:else if !a.level}
        <p class="t-foot rar">{t('person.rarity', { p: share(a.levels[0].rarity) })}</p>
      {/if}
    {/if}
  {:else if b}
    <p class="t-callout how">{t('aw.badgeHow')}</p>
  {:else if it.founder || it.idea}
    <p class="t-callout how">{t('seal.one')}</p>
  {/if}

  {#snippet footer()}
    <div class="acts btns">
      {#if ref}<Button kind="primary" size="l" full loading={inviting} onclick={invite}>{#snippet icon()}<Megaphone size={18} />{/snippet}{t('ref.invite')}</Button>{/if}
      {#if mine && a && a.level > 0}
        <Button kind={ref ? 'secondary' : 'primary'} size="l" full loading={sharing} onclick={shareIt}>{#snippet icon()}<Share size={18} />{/snippet}{t('aw.share')}</Button>
      {/if}
    </div>
  {/snippet}
</Sheet>

<style>
  .acts { display: flex; gap: 8px; }
  .stage { position: relative; display: flex; justify-content: center; padding: 10px 0 6px; perspective: 700px; }
  .lit { padding: 26px 0 22px; }
  /* behind the medal: a soft halo of its metal and slow rays, both fading out well inside the sheet */
  .halo, .rays { position: absolute; left: 50%; top: 50%; width: min(330px, 100%); aspect-ratio: 1; border-radius: 50%; pointer-events: none; translate: -50% -50%; }
  .halo { background: radial-gradient(closest-side, rgba(var(--glow), 0.6), rgba(var(--glow), 0.22) 55%, transparent); }
  .rays { background: repeating-conic-gradient(rgba(var(--glow), 0.22) 0 6deg, transparent 6deg 18deg);
    mask: radial-gradient(closest-side, black 34%, transparent 92%); animation: turn 80s linear infinite; }
  :global(html.lowfx) .rays { animation: none; }
  @media (prefers-reduced-motion: reduce) { .rays, .sweep { animation: none; } }
  @keyframes turn { to { rotate: 360deg; } }
  /* one pass of light across the metal as it lands */
  .sweep { position: absolute; inset: 0; border-radius: 50%; pointer-events: none; mix-blend-mode: soft-light; background-size: 260% 100%;
    background-image: linear-gradient(110deg, transparent 42%, rgba(255, 255, 255, 0.8) 50%, transparent 58%); background-position: 130% 0;
    animation: sweep 1.3s 0.5s cubic-bezier(0.4, 0, 0.2, 1) both; }
  @keyframes sweep { to { background-position: -30% 0; } }
  .kick { text-align: center; margin-top: 4px; font: 700 var(--fs-cap)/1.3 var(--font-text); letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent-text); }
  .kick.metal { color: rgb(var(--k)); }
  :global(html[data-theme='light']) .kick.metal { color: rgb(var(--kd)); }
  .facts { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; margin-top: 18px; border-radius: var(--r-l); overflow: hidden; background: var(--line); }
  .facts div { display: flex; flex-direction: column; gap: 2px; padding: 12px 14px; background: var(--surface-2); }
  .facts b { font: 720 var(--fs-card)/1.2 var(--font-display); }
  .facts span { font: 560 var(--fs-cap)/1.25 var(--font-text); color: var(--text-2); }
  .big { position: relative; z-index: 1; display: inline-flex; transform: rotateX(calc(var(--gy, 0) * -14deg)) rotateY(calc(var(--gx, 0) * 16deg)); transition: transform 160ms ease-out; }
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
