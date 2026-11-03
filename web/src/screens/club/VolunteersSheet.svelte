<script lang="ts">
  // An event's volunteer applications, the organizers' (the "events" right): waiting first, each with its
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
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import { schoolShort } from '../../lib/short';

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
  const line = (x: VolunteerApp) => [x.course && t('person.course', { n: x.course }), schoolShort(x.school), relDay(x.at)].filter(Boolean).join(' · ');
</script>

<Sheet {overlay} icon={HandHeart} full title={t('vol.list')}>
  <p class="t-foot sub">{t('vol.taken', { n: yes, of: need })}</p>
  {#if list}
    <div class="list">
      {#each list as x (x.person.id)}
        {#snippet write()}<Button kind="secondary" size="s" onclick={() => openLink('https://t.me/' + x.username)}>{#snippet icon()}<TelegramMark size={15} />{/snippet}{t('jr.write')}</Button>{/snippet}
        <!-- engine: Row needs content under it (the "why", the answer's buttons): one Group per person until then -->
        <div class:off={x.status === 'no'}>
          <Group>
            <Row dense title={withNick(x.fullName, x.person)} subtitle={line(x)} trailing={x.username ? write : undefined}>
              {#snippet lead()}<Avatar person={x.person} size={36} />{/snippet}
            </Row>
            {#if x.note}<p class="note">«{x.note}»</p>{/if}
            {#if x.status === 'asked'}
              <div class="acts btns">
                <Button kind="secondary" size="m" full onclick={() => decide(x, false)}>{t('jr.decline')}</Button>
                <Button kind="primary" size="m" full onclick={() => decide(x, true)}>{t('vol.yes')}</Button>
              </div>
            {:else}
              <Row dense title={t(x.status === 'yes' ? 'vol.isYes' : 'vol.isNo')} trailing={flip} />
              {#snippet flip()}<Button kind="secondary" size="s" onclick={() => decide(x, x.status !== 'yes')}>{t(x.status === 'yes' ? 'vol.unYes' : 'vol.yes')}</Button>{/snippet}
            {/if}
          </Group>
        </div>
      {:else}
        <EmptyState inline text={t('vol.none')} />
      {/each}
    </div>
  {/if}
</Sheet>

<style>
  .sub { margin: 2px var(--s-1) 0; }
  .list { display: flex; flex-direction: column; gap: var(--s-3); margin-top: var(--s-4); }
  .off { opacity: 0.6; }
  .note { padding: 0 var(--s-4) var(--s-3); font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); }
  .acts { display: flex; gap: var(--s-2); padding: 0 var(--s-4) var(--s-4); }
</style>
