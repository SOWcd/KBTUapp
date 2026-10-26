<script lang="ts">
  // Found people: name, year, skills; "get in touch" sends them an offer in the bot (forum.contact).
  import { api, ApiErr, type ForumCard, type Id } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';

  let { cards }: { cards: ForumCard[] } = $props();
  let sent = $state<Set<Id>>(new Set());
  async function touch(id: Id) {
    try { await api.offer({ to: id }); haptic.ok(); sent = new Set([...sent, id]); say(t('fo.offerSay'), 'raising_hands_3d_default'); }
    catch (e) { haptic.error(); say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'fo.slow' : 'common.error'), 'pleading_face_3d'); }
  }
</script>

<div class="list surface">
  {#each cards as c (c.person.id)}
    <div class="row">
      <Avatar person={c.person} size={40} />
      <span class="tx"><b class="ellipsis">{c.name}{c.course ? ` · ${t('fo.course', { n: c.course })}` : ''}</b><i class="ellipsis">{c.skills.map((s) => s.name).join(', ')}</i></span>
      <button class="go" class:done={sent.has(c.person.id)} disabled={sent.has(c.person.id)} onclick={() => touch(c.person.id)}>{t(sent.has(c.person.id) ? 'fo.sent' : 'fo.touch')}</button>
    </div>
  {:else}
    <p class="t-foot empty">{t('fo.nobody')}</p>
  {/each}
</div>

<style>
  .list { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; }
  .row + .row { border-top: 1px solid var(--line); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 640 15px/1.25 var(--font-text); }
  .tx i { font: 500 12.5px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .go { flex: none; height: 32px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 13px/1 var(--font-text); }
  .go.done { background: var(--surface-2); color: var(--text-3); }
  .empty { padding: 18px 14px; }
</style>
