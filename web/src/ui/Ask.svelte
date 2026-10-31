<script lang="ts">
  // In-app confirmation: a short sheet with the question and two buttons. Back, a tap outside or a pull
  // down count as "no". Destructive actions are always confirmed here, never by a system dialog. With `input`, a few
  // words to write first (at least 2 characters), handed to `done`; with `input.tel`, a phone number (+7XXXXXXXXXX);
  // `input.value` fills it in (an edit), `input.line` makes it one line (a nick: Enter saves).
  import { untrack } from 'svelte';
  import Sheet from './Sheet.svelte';
  import Button from './Button.svelte';
  import { close, type Overlay } from '../lib/state/ui.svelte';
  import { fmtPhone, kzPhone } from '../lib/phone';

  type Props = { overlay: Overlay; title: string; text?: string; ok: string; cancel: string; danger?: boolean;
    input?: { placeholder: string; max: number; tel?: boolean; value?: string; line?: boolean }; done: (yes: boolean, written: string) => void };
  let { overlay, title, text = '', ok, cancel, danger = false, input, done }: Props = $props();

  let written = $state(untrack(() => input?.value ?? ''));
  const said = $derived(input?.tel ? kzPhone(written) ?? '' : written.trim().replace(/\s+/g, ' '));
  let answered = false;
  function answer(yes: boolean) {
    if (!answered) { answered = true; done(yes, said); }
    close(overlay.id);
  }
  $effect(() => { if (overlay.closing && !answered) { answered = true; done(false, ''); } });
</script>

<Sheet {overlay} hold={() => false}><!-- a dialog: its few words never ask "leave?" over itself -->
  <h2 class="t-h3 q">{title}</h2>
  {#if text}<p class="t-body dim">{text}</p>{/if}
  {#if input?.tel}<label class="field say"><input type="tel" inputmode="tel" autocomplete="tel" placeholder={input.placeholder} bind:value={written} oninput={() => (written = fmtPhone(written))} /></label>
  {:else if input?.line}<label class="field say"><input bind:value={written} maxlength={input.max} placeholder={input.placeholder} enterkeyhint="done" autocomplete="off"
    onkeydown={(e) => { if (e.key === 'Enter' && said.length >= 2) answer(true); }} /></label>
  {:else if input}<label class="field say"><textarea bind:value={written} rows="3" maxlength={input.max} placeholder={input.placeholder}></textarea></label>{/if}
  {#snippet footer()}
    <div class="row btns">
      <Button kind="neutral" size="l" full onclick={() => answer(false)}>{cancel}</Button>
      <Button kind={danger ? 'danger' : 'primary'} size="l" full disabled={!!input && said.length < 2} onclick={() => answer(true)}>{ok}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .q { margin: 6px 0 8px; }
  .say { margin-top: 12px; }
  .say textarea { width: 100%; resize: none; }
  .say input { width: 100%; }
  .row { display: flex; gap: 10px; }
</style>
