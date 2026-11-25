<script lang="ts">
  // "Name me in People of the app?": the feature's own consent (server credits.CONSENT), from the bot's one message and
  // from Settings' switch. It shows exactly what everyone would see (my face, my name, the lines) and takes a yes or a no.
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { answerCredits } from '../../lib/credits';
  import { t } from '../../lib/i18n/index.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import CreditLines from '../../ui/CreditLines.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const me = $derived(session.me);
  const mine = $derived(data.credits?.mine);
  let busy = $state<boolean | null>(null);
  async function say(show: boolean) {
    if (busy !== null) return;
    busy = show;
    const kept = await answerCredits(show);
    busy = null;
    if (kept) close(overlay.id); // not kept: the list was read again, the sheet shows what is true now
  }
</script>

<Sheet {overlay} icon={UsersRound} title={t('cr.title')}>
  <div class="ask">
    <h2 class="t-h2 hd">{t('cr.askT')}</h2>
    <p class="t-body dim">{t('cr.askText')}</p>
    {#if me && mine}
      <div class="card">
        <Avatar person={me} size={48} tappable={false} />
        <span class="txt">
          <b>{me.name}</b>
          {#if mine.idea}<span class="role">{t('cr.idea')}</span>{/if}
          {#if mine.team}<span class="role">{t('cr.team')}</span>{/if}
          {#if mine.honor}<span class="role">{t('ach.honor.name')}</span>{/if}
          <CreditLines items={mine.items} />
        </span>
      </div>
    {/if}
    <p class="t-foot dim note">{t('cr.askNote')}</p>
  </div>

  {#snippet footer()}
    <div class="acts">
      <Button kind="primary" size="l" full loading={busy === true} onclick={() => say(true)}>{t('cr.show')}</Button>
      <Button kind="plain" size="m" full loading={busy === false} onclick={() => say(false)}>{t('cr.hide')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .ask { display: flex; flex-direction: column; padding: var(--s-2) 0; }
  .hd { margin: 0 0 var(--s-2); text-wrap: balance; }
  .dim { margin: 0; color: var(--text-2); text-wrap: pretty; }
  .card { display: flex; align-items: flex-start; gap: var(--s-3); margin-top: var(--s-5); padding: var(--s-4); border-radius: var(--r-group); background: var(--surface); }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
  .txt b { font: 600 var(--fs-row)/1.25 var(--font-text); overflow-wrap: anywhere; }
  .role { font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .note { margin-top: var(--s-4); color: var(--text-3); }
  .acts { display: flex; flex-direction: column; gap: var(--s-1); }
</style>
