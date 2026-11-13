<script lang="ts">
  // In-app confirmation. A plain yes/no is an iOS alert in the middle of the screen (owner, Nov 13: a bottom sheet
  // where a tap outside already says "no" made its cancel button look useless); one that asks for words stays a sheet
  // (the keyboard needs it). Back, Escape, a tap outside (and a pull, on the sheet) count as "no".
  // Destructive actions are always confirmed here, never by a system dialog. With `input`, a few words to write first (at least 2 characters), handed to `done`; with `input.tel`, a phone number (+7XXXXXXXXXX);
  // `input.value` fills it in (an edit), `input.line` makes it one line (a nick: Enter saves). `link`: a consent's policy.
  import { onMount, untrack } from 'svelte';
  import Sheet from './Sheet.svelte';
  import Button from './Button.svelte';
  import { close, removeOverlay, type Overlay } from '../lib/state/ui.svelte';
  import { fmtPhone, kzPhone } from '../lib/phone';
  import { openLink } from '../lib/tg';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';

  type Props = { overlay: Overlay; title: string; text?: string; ok: string; cancel: string; danger?: boolean; wait?: number; link?: { label: string; url: string };
    input?: { placeholder: string; max: number; tel?: boolean; value?: string; line?: boolean }; done: (yes: boolean, written: string) => void };
  let { overlay, title, text = '', ok, cancel, danger = false, wait = 0, link, input, done }: Props = $props();

  // wait: "ok" stays dim this long (a second confirm: a double tap must not pass both)
  let ready = $state(untrack(() => !wait));
  onMount(() => { if (!wait) return; const id = setTimeout(() => (ready = true), wait); return () => clearTimeout(id); });

  let written = $state(untrack(() => input?.value ?? ''));
  const said = $derived(input?.tel ? kzPhone(written) ?? '' : written.trim().replace(/\s+/g, ' '));
  let answered = false;
  function answer(yes: boolean) {
    if (!answered) { answered = true; done(yes, said); }
    close(overlay.id);
  }
  $effect(() => { if (overlay.closing && !answered) { answered = true; done(false, ''); } });

  // ---- the alert (no input) ----
  // long labels side by side would wrap: stacked then, the confirm on top (iOS)
  const stack = $derived([ok, cancel].some((l) => l.length > 14));
  const uid = `ask${untrack(() => overlay.id)}`;
  let card = $state<HTMLDivElement>();
  let gone = false;
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  onMount(() => {
    if (input || !card) return;
    const opener = document.activeElement as HTMLElement | null;
    card.querySelector<HTMLElement>('.no')?.focus({ preventScroll: true });
    return () => { if (opener?.isConnected && !opener.matches('input, textarea, [contenteditable]')) opener.focus({ preventScroll: true }); };
  });
  $effect(() => {
    if (input || !overlay.closing || gone) return;
    gone = true;
    if (still() || !card) return removeOverlay(overlay.id);
    card.parentElement!.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140, easing: 'ease-in', fill: 'forwards' }).onfinish = () => removeOverlay(overlay.id);
  });
  // the focus stays on the two buttons (a modal): Tab goes round them
  function trap(e: KeyboardEvent) {
    if (e.key !== 'Tab' || !card) return;
    const all = [...card.querySelectorAll<HTMLElement>('button:not(:disabled)')];
    const i = all.indexOf(document.activeElement as HTMLElement);
    e.preventDefault();
    all[(i + (e.shiftKey ? -1 : 1) + all.length) % all.length]?.focus();
  }
</script>

{#if !input}
<div class="layer" class:still={still()}>
  <div class="dim-bg" onclick={() => close(overlay.id, true)} role="presentation"></div>
  <div class="alert glass glass-sheet" bind:this={card} role="alertdialog" aria-modal="true" aria-labelledby="{uid}t" aria-describedby={text ? `${uid}d` : undefined} tabindex="-1" onkeydown={trap}>
    <div class="say-it">
      <h2 class="t-h3" id="{uid}t">{title}</h2>
      {#if text}<p class="t-foot txt" id="{uid}d">{text}</p>{/if}
      {#if link}<button class="t-foot lnk-a" onclick={() => openLink(link.url)}>{link.label}<ArrowUpRight size={14} /></button>{/if}
    </div>
    <div class="acts" class:stack>
      {#if stack}<button class="act yes" class:red={danger} disabled={!ready} onclick={() => answer(true)}>{ok}</button>{/if}
      <button class="act no" onclick={() => answer(false)}>{cancel}</button>
      {#if !stack}<button class="act yes" class:red={danger} disabled={!ready} onclick={() => answer(true)}>{ok}</button>{/if}
    </div>
  </div>
</div>
{:else}

<Sheet {overlay} hold={() => false}><!-- a dialog: its few words never ask "leave?" over itself -->
  <h2 class="t-h3 q">{title}</h2>
  {#if text}<p class="t-body dim">{text}</p>{/if}
  {#if link}<div class="lnk"><Button kind="plain" size="m" onclick={() => openLink(link.url)}>{link.label}<ArrowUpRight size={16} /></Button></div>{/if}
  {#if input?.tel}<label class="field say"><input type="tel" inputmode="tel" autocomplete="tel" placeholder={input.placeholder} bind:value={written} oninput={() => (written = fmtPhone(written))} /></label>
  {:else if input?.line}<label class="field say"><input bind:value={written} maxlength={input.max} placeholder={input.placeholder} enterkeyhint="done" autocomplete="off"
    onkeydown={(e) => { if (e.key === 'Enter' && said.length >= 2) answer(true); }} /></label>
  {:else if input}<label class="field say"><textarea bind:value={written} rows="3" maxlength={input.max} placeholder={input.placeholder}></textarea></label>{/if}
  {#snippet footer()}
    <div class="row btns">
      <Button kind="neutral" size="l" full onclick={() => answer(false)}>{cancel}</Button>
      <Button kind={danger ? 'danger' : 'primary'} size="l" full disabled={!ready || !!input && said.length < 2} onclick={() => answer(true)}>{ok}</Button>
    </div>
  {/snippet}
</Sheet>
{/if}

<style>
  .q { margin: 6px 0 8px; }
  .dim { white-space: pre-line; } /* a text in paragraphs (an invite's description, then what saying yes means) */
  .say { margin-top: 12px; }
  .lnk { display: flex; margin: 4px 0 0 -12px; }
  .lnk :global(.lbl) { display: inline-flex; align-items: center; gap: 4px; }
  .say textarea { width: 100%; resize: none; }
  .say input { width: 100%; }
  .row { display: flex; gap: 10px; }

  /* the alert: over every sheet, menu and toast; the page under it stays where it is */
  .layer { position: absolute; inset: 0; z-index: var(--z-ask); display: flex; align-items: center; justify-content: center;
    padding: calc(var(--safe-top) + 16px) 16px calc(var(--safe-bottom) + 16px); touch-action: none; overscroll-behavior: contain;
    animation: fade 180ms ease-out both; }
  .dim-bg { position: absolute; inset: 0; background: var(--scrim); }
  .alert { position: relative; width: 100%; max-width: 300px; max-height: 100%; display: flex; flex-direction: column; overflow: hidden;
    border-radius: var(--r-l); background-color: var(--menu-bg); text-align: center;
    animation: pop 180ms var(--ease-spring) both; }
  .alert:focus { outline: none; }
  .still, .still .alert { animation: none; }
  .say-it { padding: 20px 18px 18px; overflow-y: auto; overscroll-behavior: contain; touch-action: pan-y; }
  .txt { margin-top: 6px; white-space: pre-line; overflow-wrap: break-word; }
  .lnk-a { display: inline-flex; align-items: center; gap: 3px; margin-top: 10px; color: var(--accent-text); }
  .acts { flex: none; display: flex; border-top: 0.5px solid var(--separator); }
  .act { flex: 1 1 0; min-width: 0; min-height: var(--ctl-m); padding: 10px 8px; font: 450 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.012em;
    color: var(--accent-text); overflow-wrap: break-word; transition: background-color var(--t-fast), opacity var(--t-fast); }
  .act + .act { border-left: 0.5px solid var(--separator); }
  .stack { flex-direction: column; }
  .stack .act + .act { border-left: 0; border-top: 0.5px solid var(--separator); }
  .yes { font-weight: 600; }
  .red { color: var(--danger-text); }
  .act:disabled { opacity: 0.4; }
  .act:active:not(:disabled), .act:focus-visible { background: var(--fill); outline: none; }
  @media (hover: hover) { .act:hover:not(:disabled) { background: var(--fill); } }
  @keyframes fade { from { opacity: 0; } }
  @keyframes pop { from { opacity: 0; transform: scale(1.06); } }
</style>
