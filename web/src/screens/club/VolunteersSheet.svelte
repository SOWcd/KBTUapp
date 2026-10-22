<script lang="ts">
  // An event's volunteer applications (owner, Oct 15), the organizers' (the "events" right): waiting first, each with its
  // "why", full name and course; write to them, then yes or no, the bot tells them. No more yeses than places.
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { api, ApiErr, type Id, type VolunteerApp } from '../../lib/api';
  import { studioChanged } from '../../lib/state/data.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { relDay } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { withNick } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, id, need }: { overlay: Overlay; id: Id; need: number } = $props();
  let list = $state<VolunteerApp[] | null>(null);
  $effect(() => { api.volunteers(id).then((l) => (list = l)).catch(() => (list = [])); });
  const yes = $derived((list ?? []).filter((x) => x.status === 'yes').length);

  async function decide(x: VolunteerApp, ok: boolean) {
    try {
      list = await api.volunteerDecide(id, x.person.id, ok);
      ok ? haptic.ok() : haptic.warn();
      say(ok ? phrase('say.volYes') : t('say.volNo'), ok ? 'raising_hands_3d_default' : 'waving_hand_3d_default');
      studioChanged();
    } catch (e) {
      haptic.error(); say(t(e instanceof ApiErr && e.message === 'full' ? 'vol.full' : 'common.error'), 'pleading_face_3d');
    }
  }
  const line = (x: VolunteerApp) => [x.course && t('person.course', { n: x.course }), x.school, relDay(x.at)].filter(Boolean).join(' · ');
</script>

<Sheet {overlay} tall title={t('vol.list')}>
  <h2 class="t-h2">{t('vol.list')}</h2>
  <p class="t-foot sub">{t('vol.taken', { n: yes, of: need })}</p>
  {#if list}
    <div class="list">
      {#each list as x (x.person.id)}
        <article class="req" class:off={x.status === 'no'}>
          <div class="top">
            <Avatar person={x.person} size={44} />
            <span class="who">
              <b class="ellipsis">{withNick(x.fullName, x.person)}</b>
              <span class="t-foot ellipsis">{line(x)}</span>
            </span>
            {#if x.username}
              <Button kind="secondary" size="s" onclick={() => openLink('https://t.me/' + x.username)}>{#snippet icon()}<TelegramMark size={15} />{/snippet}{t('jr.write')}</Button>
            {/if}
          </div>
          {#if x.note}<p class="note">«{x.note}»</p>{/if}
          {#if x.status === 'asked'}
            <div class="acts">
              <Button kind="neutral" size="m" full onclick={() => decide(x, false)}>{t('jr.decline')}</Button>
              <Button kind="primary" size="m" full onclick={() => decide(x, true)}>{t('vol.yes')}</Button>
            </div>
          {:else}
            <div class="state"><span class="t-foot">{t(x.status === 'yes' ? 'vol.isYes' : 'vol.isNo')}</span>
              <button class="undo" onclick={() => decide(x, x.status !== 'yes')}>{t(x.status === 'yes' ? 'vol.unYes' : 'vol.yes')}</button></div>
          {/if}
        </article>
      {:else}
        <p class="t-foot none">{t('vol.none')}</p>
      {/each}
    </div>
  {/if}
</Sheet>

<style>
  .sub { margin: 2px 4px 0; }
  .list { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
  .req { display: flex; flex-direction: column; gap: 10px; padding: 12px; border-radius: var(--r-l); background: var(--surface-2); }
  .req.off { opacity: 0.6; }
  .top { display: flex; align-items: center; gap: 12px; }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .who b { font: 650 15.5px/1.3 var(--font-text); }
  .note { margin: 0 2px; font: 500 14.5px/1.4 var(--font-text); color: var(--text-2); }
  .acts { display: flex; gap: 8px; }
  .acts :global(.btn.full) { flex: 1; width: auto; min-width: 0; }
  .acts :global(.btn.neutral) { background: var(--surface-3); }
  .state { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 0 2px; }
  .undo { height: 30px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-3); color: var(--text-2); font: 620 13px/1 var(--font-text); }
  .none { padding: 18px 4px; text-align: center; }
</style>
