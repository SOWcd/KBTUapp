<script lang="ts">
  // One award up close (SPEC §4.11), full screen over a dimmed profile (owner, Nov 1: the sheet's top cut the light
  // behind the medal). An achievement: the medal big with the
  // tilt light, what it takes, the way to the next level and how rare every level is; a secret one shows only its
  // hint until earned. A badge: the event it came from. The Creator's seal: what it is, in the words everyone
  // reads, the creator included.
  // Mine and earned: Share sends our bot's card (aw_<code>: the reader sees their own way to it).
  // ponytail: no earned date (nothing records it until the unlock moment ships).
  import { onMount } from 'svelte';
  import Check from '@lucide/svelte/icons/check';
  import type { ShelfItem } from '../../lib/awards';
  import { removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';
  import Share from '@lucide/svelte/icons/share';
  import { haptic, shareCard } from '../../lib/tg';
  import { say } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { glass } from '../../ui/glass';
  import CloseX from '../../ui/CloseX.svelte';
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
  const DRAWN: Record<string, string> = { medal_init26_2: GLOW[3], medal_init26f_2: GLOW[2], medal_first500: GLOW[3] }; // a new art gets a new name: phones keep the old file for hours
  const round = $derived(!!a || !!it.founder || !!it.idea);
  const glow = $derived(it.founder || it.idea ? GLOW[0] : !a || !a.level ? '' : DRAWN[a.emoji] ?? (tiers ? GLOW[Math.min(a.level, 4)] : GLOW[0]));
  // the line over the name: the event a medal is from, else the level reached; a badge: its club and day
  const kicker = $derived(a?.code === 'init26' || a?.code === 'init26f' ? t('aw.init26') : a?.level && tiers ? t('aw.level', { tier: tierOf(a.level - 1) })
    : b ? `${nameOf(b.org)} · ${dayMonth(b.at)}` : '');

  $effect(() => { overlay.title = it.ach ? t('cap.achievement') : it.founder ? t('cap.founder') : it.idea ? t('cap.idea') : t('cap.badge'); });

  let medal: HTMLSpanElement, scrim: HTMLDivElement, wrap: HTMLDivElement;
  let gone = false;
  onMount(() => {
    haptic.soft();
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 280, easing: 'ease-out' });
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      medal.animate([{ transform: 'scale(0.55) rotate(-14deg)', opacity: 0 }, { transform: 'scale(1.06) rotate(3deg)', opacity: 1, offset: 0.62 }, { transform: 'none' }],
        { duration: 620, easing: 'cubic-bezier(.2,.9,.25,1)' });
      for (const [i, el] of [...wrap.querySelectorAll('.up')].entries())
        el.animate([{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }], { duration: 400, delay: 260 + i * 60, easing: 'cubic-bezier(.2,.9,.25,1)', fill: 'backwards' });
    }
    return hideChrome();
  });
  function leave() {
    if (gone) return;
    gone = true;
    wrap.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(0.96)' }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, easing: 'ease-in', fill: 'forwards' }).onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="scrim" bind:this={scrim} style:--glow={glow || GLOW[0]} onclick={() => leave()} role="presentation"></div>
<div class="wrap theme-dark" bind:this={wrap}>
  <div class="page">
  <div class="stage" class:lit={round && !!glow} style:--glow={glow} use:glass>
    {#if round && glow}<span class="rays" aria-hidden="true"></span><span class="halo" aria-hidden="true"></span>{/if}
    <span class="big" class:round bind:this={medal}><Award {it} size={round ? 196 : 132} /><span class="shine"></span>{#if round && glow}<span class="sweep"></span>{/if}</span>
  </div>
  {#if kicker}<p class="kick up" class:metal={!!glow} style:--k={glow}>{kicker}</p>{/if}
  <h2 class="t-h1 name up">{it.name}</h2>

  {#if a}
    {#if a.now}<p class="tier">{tn('ach.streakNow', a.now)}</p>{/if}
    <p class="t-callout how up">{t(`ach.${a.code}.how` as 'ach.regular.how')}</p>
    {#if a.level && a.at && tiers}<p class="t-foot got">{t('aw.earned', { date: dayMonth(a.at) })}</p>{/if}
    {#if !hidden}
      {#if a.level && !tiers}
        <!-- earned, one level: the day and how rare, side by side (once: no "Earned" above and below) -->
        <div class="facts up">
          <div><b>{a.at ? dayMonth(a.at) : t('aw.have')}</b>{#if a.at}<span>{t('aw.gotOn')}</span>{/if}</div>
          <div><b>{share(Math.max(a.levels[0].rarity, 0.001))}%</b><span>{t('aw.haveIt')}</span></div>
        </div>
      {:else if next}
        <div class="prog up">
          <div class="row"><b>{t('ach.progress', { count: a.count, need: next.need })}</b>{#if tiers}<span>{t('aw.toLevel', { tier: tierOf(a.levels.indexOf(next)) })}</span>{/if}</div>
          <div class="bar"><span style="width:{pct}%"></span></div>
        </div>
      {:else}
        <p class="top">{t('aw.topCount', { count: a.count })}</p>
      {/if}
      {#if tiers}
        <div class="ladder up">
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

  <!-- small glass pills in the medal's metal, right under it (owner, Nov 1: the wide blue button at the bottom was ugly) -->
  {#if ref || (mine && a && a.level > 0)}
    <div class="acts up" style:--glow={glow || GLOW[0]}>
      {#if ref}<button class="pill glass glass-pill main" use:glass disabled={inviting} onclick={invite}><Megaphone size={17} />{t('ref.invite')}</button>{/if}
      {#if mine && a && a.level > 0}
        <button class="pill glass glass-pill" class:main={!ref} use:glass disabled={sharing} onclick={shareIt}><Share size={17} />{t('aw.share')}</button>
      {/if}
    </div>
  {/if}
  </div>
  <CloseX onclick={() => leave()} />
</div>

<style>
  /* full screen: the profile dimmed and blurred, a faint wash of the medal's metal from above */
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet);
    background: radial-gradient(70% 45% at 50% 30%, rgba(var(--glow), 0.22), transparent 70%), rgba(3, 4, 10, 0.88);
    -webkit-backdrop-filter: blur(18px); backdrop-filter: blur(18px); }
  :global(html.lowfx) .scrim { -webkit-backdrop-filter: none; backdrop-filter: none; background: radial-gradient(70% 45% at 50% 30%, rgba(var(--glow), 0.22), transparent 70%), rgba(3, 4, 10, 0.96); }
  .wrap { position: absolute; inset: 0; z-index: var(--z-sheet); pointer-events: none; display: flex; flex-direction: column; background: none; }
  .wrap > :global(*) { pointer-events: auto; }
  .page { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: none; padding: calc(var(--top) + 8px) 20px 12px; display: flex; flex-direction: column; }
  .page::-webkit-scrollbar { display: none; }
  .page > :first-child { margin-top: auto; }
  .page > :last-child { margin-bottom: auto; }
  .page { padding-bottom: calc(var(--safe-bottom) + 84px); }
  .acts { display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
  .pill { position: relative; height: 46px; padding: 0 22px; display: inline-flex; align-items: center; gap: 8px; border-radius: var(--r-full);
    color: var(--text); font: 650 var(--fs-body)/1 var(--font-text); background-color: rgba(255, 255, 255, 0.1); }
  .pill.main { background-color: rgba(var(--glow), 0.32); }
  .pill > :global(svg) { position: relative; }
  .pill:active { transform: scale(0.96); }
  .pill:disabled { opacity: 0.6; }
  .stage { position: relative; display: flex; justify-content: center; padding: 10px 0 6px; perspective: 700px; }
  .lit { padding: 40px 0 34px; }
  /* behind the medal (full screen now, nothing cuts it): a soft halo of its metal and fine rays that fade out long
     before any edge, turning slowly; thin lines, not wedges (owner, Nov 1: the old wide rays read childish) */
  .halo, .rays { position: absolute; left: 50%; top: 50%; aspect-ratio: 1; border-radius: 50%; pointer-events: none; translate: -50% -50%; }
  .halo { width: 300px; background: radial-gradient(closest-side, rgba(var(--glow), 0.42), rgba(var(--glow), 0.12) 60%, transparent); }
  .rays { width: 420px; background: repeating-conic-gradient(rgba(var(--glow), 0.16) 0 1.2deg, transparent 1.2deg 9deg);
    -webkit-mask: radial-gradient(closest-side, transparent 30%, black 44%, transparent 86%); mask: radial-gradient(closest-side, transparent 30%, black 44%, transparent 86%);
    animation: turn 120s linear infinite; }
  :global(html.lowfx) .rays { animation: none; }
  @media (prefers-reduced-motion: reduce) { .rays, .sweep { animation: none; } }
  @keyframes turn { to { rotate: 360deg; } }
  /* one narrow pass of light across the metal as it lands */
  .sweep { position: absolute; inset: 0; border-radius: 50%; pointer-events: none; mix-blend-mode: overlay; background-size: 300% 100%;
    background-image: linear-gradient(115deg, transparent 46%, rgba(255, 255, 255, 0.55) 50%, transparent 54%); background-position: 130% 0;
    animation: sweep 1.4s 0.55s cubic-bezier(0.4, 0, 0.2, 1) both; }
  @keyframes sweep { to { background-position: -30% 0; } }
  .kick { text-align: center; margin-top: 4px; font: 700 var(--fs-cap)/1.3 var(--font-text); letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent-text); }
  .kick.metal { color: rgb(var(--k)); }
    .facts { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; margin-top: 18px; border-radius: var(--r-l); overflow: hidden; background: var(--line); }
  .facts div { display: flex; flex-direction: column; gap: 2px; padding: 12px 14px; background: var(--surface-2); }
  .facts b { font: 720 var(--fs-card)/1.2 var(--font-display); }
  .facts span { font: 560 var(--fs-cap)/1.25 var(--font-text); color: var(--text-2); }
  .big { position: relative; z-index: 1; display: inline-flex; transform: rotateX(calc(var(--gy, 0) * -14deg)) rotateY(calc(var(--gx, 0) * 16deg)); transition: transform 160ms ease-out; }
  /* the light slides over the metal with the tilt (round medals only: a pin's corners stay clean) */
  .shine { display: none; }
  /* a soft specular band that slides with the tilt, as on polished metal (owner, Nov 1: the white spot was so-so) */
  .round .shine { display: block; position: absolute; inset: 0; border-radius: 50%; pointer-events: none; mix-blend-mode: soft-light;
    background: linear-gradient(125deg, transparent calc(28% + var(--gx, 0) * 24%), rgba(255, 255, 255, 0.5) calc(40% + var(--gx, 0) * 24%), transparent calc(54% + var(--gx, 0) * 24%)); }
  .name { text-align: center; margin-top: 8px; color: var(--text); }
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
