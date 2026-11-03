<script lang="ts">
  // A form field: its label above (13 px, grey), the input in a --fill box (--r-m, 50 high, 17 px text: 16 or more
  // keeps iOS from zooming in), an error as a red line under it. No hint lines.
  //   label, value (bindable), placeholder, error (shows the line, rings the box)
  //   size       title: the big name of a thing being made (an event, a club, a post): --fs-t1 700 in the display face,
  //              in a larger box that grows with the text (EventEditor's .name)
  //   multiline  a textarea that grows with the text (up to `rows` × 3 lines, then it scrolls)
  //   type, inputmode, autocomplete, enterkeyhint, maxlength: passed to the input
  import { grow } from './grow';

  type Props = { label: string; size?: 'm' | 'title'; value?: string; placeholder?: string; error?: string; multiline?: boolean; rows?: number; maxlength?: number;
    type?: 'text' | 'tel' | 'email' | 'url' | 'number'; inputmode?: 'text' | 'tel' | 'email' | 'url' | 'numeric' | 'decimal';
    autocomplete?: HTMLInputElement['autocomplete']; enterkeyhint?: 'done' | 'next' | 'go' | 'send' | 'search' };
  let { label, size = 'm', value = $bindable(''), placeholder, error, multiline = false, rows = 3, maxlength, type = 'text', inputmode, autocomplete, enterkeyhint }: Props = $props();
  const id = `f${Math.random().toString(36).slice(2, 8)}`;
</script>

<div class="fld" class:bad={!!error} class:title={size === 'title'}>
  <label class="lb" for={id}>{label}</label>
  {#if multiline || size === 'title'}
    <textarea {id} class="box" bind:value {placeholder} {maxlength} rows={size === 'title' ? 1 : rows} aria-invalid={!!error} aria-describedby={error ? id + 'e' : undefined}
      use:grow={size === 'title' ? 4 * 34 : rows * 3 * 23}></textarea>
  {:else}
    <input {id} class="box" {type} bind:value {placeholder} {maxlength} {inputmode} {autocomplete} {enterkeyhint} aria-invalid={!!error}
      aria-describedby={error ? id + 'e' : undefined} />
  {/if}
  {#if error}<p class="err" id={id + 'e'}>{error}</p>{/if}
</div>

<style>
  .fld { display: flex; flex-direction: column; gap: 6px; }
  .lb { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .box { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); letter-spacing: -0.012em; transition: box-shadow var(--t-fast); }
  textarea.box { display: block; padding: 13px var(--s-4); resize: none; }
  .box::placeholder { color: var(--text-3); }
  .box:focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
  .bad .box { box-shadow: inset 0 0 0 1.5px var(--danger); }
  .title .box { padding: var(--s-3) var(--s-4); border-radius: var(--r-l); font: 700 var(--fs-t1)/1.18 var(--font-display); letter-spacing: -0.02em; }
  .err { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--danger-text); }
</style>
