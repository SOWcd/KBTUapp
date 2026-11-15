<script lang="ts">
  // The one write-and-send bar (comments, the assistant, forum replies): a field that grows to five lines and a send
  // button; Enter sends, Shift+Enter breaks the line. "Send as" (the forum) is a Menu on my avatar at the start, and the
  // placeholder says which one is on (the caller's words), never a silent toggle.
  //   value (bindable), placeholder, onsend, sending (the button spins), maxlength, label (the send button's name)
  //   as  { me, anon, onchange }: me as the first choice, anonymous (the mask) as the second
  //   pill  one rounded field with the send button inside its right end (the AI apps' bar: the assistant)
  //   focus  takes the focus as it mounts (a stand-in field may hold it till then: App's assistant); its words count as unsent;
  //     a microtask later, so Sheet's unsent-text guard (its onMount runs after ours) sees the focus
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Avatar from './Avatar.svelte';
  import IconButton from './IconButton.svelte';
  import { menu } from './menu';
  import { grow } from './grow';
  import { t } from '../lib/i18n/index.svelte';

  type Me = { id: number; name: string; avatar?: string | null };
  type Props = { value?: string; placeholder: string; onsend: () => void; sending?: boolean; maxlength?: number; label?: string;
    as?: { me: Me; anon: boolean; onchange: (anon: boolean) => void }; pill?: boolean; focus?: boolean };
  let { value = $bindable(''), placeholder, onsend, sending = false, maxlength = 500, label, as, pill = false, focus = false }: Props = $props();

  const empty = $derived(!value.trim());
  const send = () => { if (!empty && !sending) onsend(); };
  const key = (e: KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } };
  function who(e: MouseEvent) {
    if (!as) return;
    const a = as;
    menu(e.currentTarget as Element, [
      { label: a.me.name, checked: !a.anon, onselect: () => a.onchange(false) },
      { label: t('bd.asAnon'), icon: VenetianMask, checked: a.anon, onselect: () => a.onchange(true) },
    ], 'start');
  }
</script>

<div class={['cmp', { pill }]}>
  {#if as}
    <button class="as" aria-haspopup="menu" aria-label={as.anon ? t('bd.asAnon') : as.me.name} onclick={who}>
      {#if as.anon}<span class="mask"><VenetianMask size={18} strokeWidth={2} /></span>
      {:else}<Avatar person={as.me} size={32} tappable={false} />{/if}
    </button>
  {/if}
  <textarea bind:value rows="1" {maxlength} {placeholder} enterkeyhint="send" data-unsent={focus || undefined}
    {@attach (el) => { if (focus) queueMicrotask(() => { if (el.isConnected) el.focus({ preventScroll: true }); }); }} onkeydown={key} use:grow={132}></textarea>
  <IconButton kind="filled" icon={ArrowUp} size={pill ? 's' : 'm'} label={label ?? t('cm.send')} disabled={empty} loading={sending} onclick={send} />
</div>

<style>
  .cmp { display: flex; align-items: flex-end; gap: var(--s-2); }
  .as { flex: none; width: var(--ctl-m); height: var(--ctl-m); display: grid; place-items: center; border-radius: var(--r-full); }
  .mask { width: 32px; height: 32px; display: grid; place-items: center; border-radius: var(--r-full); background: var(--surface-3); color: var(--text); }
  textarea { flex: 1; min-width: 0; min-height: var(--ctl-m); padding: 11px var(--s-4); border-radius: var(--r-l); resize: none;
    background: var(--fill); color: var(--text); font: 450 var(--fs-row)/1.3 var(--font-text); letter-spacing: -0.012em; }
  textarea::placeholder { color: var(--text-3); }
  /* the pill: the field's ground on the whole bar, the button 4 px in from its right end; a pill on one line (28 px past its half height), a rounded block as it grows */
  .pill { gap: 0; padding: 4px; border-radius: var(--r-xl); background: var(--fill); }
  .pill textarea { min-height: var(--ctl-s); padding: 7px var(--s-2) 7px var(--s-4); background: none; border-radius: 0; }
</style>
