<script lang="ts">
  // Found people: name, year, skills; "get in touch" sends them an offer in the bot (forum.contact).
  import { api, ApiErr, type ForumCard, type Id } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Button from '../../ui/Button.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { cards }: { cards: ForumCard[] } = $props();
  let sent = $state<Set<Id>>(new Set());
  async function touch(id: Id) {
    try { await api.offer({ to: id }); haptic.ok(); sent = new Set([...sent, id]); say(t('fo.offerSay'), 'raising_hands_3d_default'); }
    catch (e) { haptic.error(); say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'fo.slow' : 'common.error'), 'pleading_face_3d'); }
  }
</script>

<Group>
  {#each cards as c (c.person.id)}
    <Row dense title={`${c.name}${c.course ? ` · ${t('fo.course', { n: c.course })}` : ''}`} subtitle={c.skills.map((s) => s.name).join(', ') || undefined}>
      {#snippet lead()}<Avatar person={c.person} size={40} />{/snippet}
      {#snippet trailing()}<Button kind="tinted" size="s" disabled={sent.has(c.person.id)} onclick={() => touch(c.person.id)}>{t(sent.has(c.person.id) ? 'fo.sent' : 'fo.touch')}</Button>{/snippet}
    </Row>
  {:else}
    <EmptyState inline text={t('fo.nobody')} />
  {/each}
</Group>
