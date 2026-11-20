<script lang="ts">
  // An office's own people (DMP) greeted as the team, once per phone (App.svelte teamHi): full screen, its logo, its
  // name, one button (not signed in yet: Microsoft, and a quiet Later). Was a toast (missed it on his
  // own phone). The award reveal's shape (Unlock), calm: a fade and a short rise, no confetti. `ondone`: the link's own
  // sheet, once it's gone.
  import { onMount } from 'svelte';
  import Hand from '@lucide/svelte/icons/hand';
  import type { OrgRef } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, org, ondone, shown }: { overlay: Overlay; org: OrgRef; ondone?: () => void; shown?: () => void } = $props();
  $effect(() => { overlay.title = org.name; overlay.icon = Hand; }); // the capsule names the office in full, the page says hi

  let scrim: HTMLDivElement;
  let wrap: HTMLDivElement;
  let gone = false;
  onMount(() => {
    shown?.(); // seen once it's on screen, never before (a chunk that failed shows it again next launch)
    haptic.soft();
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 360, easing: 'ease-out' });
    for (const [i, el] of [...wrap.querySelectorAll('.up')].entries())
      el.animate([{ opacity: 0, transform: 'translateY(16px) scale(0.98)' }, { opacity: 1, transform: 'none' }], { duration: 560, delay: 160 + i * 90, easing: 'cubic-bezier(.2,.9,.25,1)', fill: 'backwards' });
    const hi = setTimeout(() => haptic.ok(), 420);
    const off = hideChrome();
    return () => { clearTimeout(hi); off(); };
  });
  function leave() {
    if (gone) return;
    gone = true;
    wrap.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(0.97)' }], { duration: 220, easing: 'ease-in', fill: 'forwards' });
    const x = scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: 'ease-in', fill: 'forwards' });
    x.onfinish = () => { removeOverlay(overlay.id); ondone?.(); };
  }
  $effect(() => { if (overlay.closing) leave(); });
  // the creator's staff with no KBTU row yet (me.msOnly): Microsoft is their way in, no student ID; signing in makes them
  // a student, and App's loadMine fills Studio and the registry then. Anyone else: the plain welcome
  const guest = $derived(!!session.me?.msOnly);
  function go() { haptic.tap(); close(overlay.id); }
  function signIn() { haptic.tap(); close(overlay.id); sheets.login(); }
</script>

<div class="scrim" bind:this={scrim} role="presentation"></div>
<div class="wrap" bind:this={wrap}>
  <div class="page">
    <span class="logo up"><OrgLogo {org} size={112} /></span>
    <h1 class="fs-title hi up">{t('say.hi.team', { org: org.abbr ?? org.name })}</h1>
    <p class="line up">{t(guest ? 'say.hi.teamSign' : 'say.hi.teamLine')}</p>
  </div>
  <div class="foot up">
    {#if guest}
      <Button kind="primary" size="l" full onclick={signIn}>{t('login.ms')}</Button>
      <div class="later"><Button kind="plain" size="s" onclick={go}>{t('say.hi.teamLater')}</Button></div>
    {:else}
      <Button kind="primary" size="l" full onclick={go}>{t('say.hi.teamGo')}</Button>
    {/if}
  </div>
</div>

<style>
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet);
    background: radial-gradient(70% 45% at 50% 40%, var(--accent-soft), transparent 70%), var(--bg); }
  .wrap { position: absolute; inset: 0; z-index: var(--z-sheet); display: flex; flex-direction: column; color: var(--text); text-align: center;
    padding: var(--top) 24px calc(var(--safe-bottom) + 20px); }
  .page { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: none; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; }
  .page::-webkit-scrollbar { display: none; }
  .logo { display: inline-flex; margin-bottom: 14px; }
  .hi { text-wrap: balance; }
  .line { max-width: 300px; font: 450 var(--fs-card)/1.4 var(--font-text); color: var(--text-2); text-wrap: balance; }
  .foot { width: 100%; max-width: 420px; align-self: center; }
  .later { display: flex; justify-content: center; margin-top: 6px; --plain-ink: var(--text-3); }
</style>
