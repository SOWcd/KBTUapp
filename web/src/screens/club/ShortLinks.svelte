<script lang="ts">
  // The club's own short links (Vice+, owner Oct 25): kbtu.sow.kz/<slug> to the club, one of its upcoming events or its
  // round, never anywhere outside the app. Made, copied and taken down here at once, not with the profile's Save.
  import Copy from '@lucide/svelte/icons/copy';
  import Trash from '@lucide/svelte/icons/trash-2';
  import { api, ApiErr, type EventCard, type Id, type ShortLink } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Button from '../../ui/Button.svelte';

  let { org }: { org: Id } = $props();
  let links = $state<ShortLink[]>([]);
  let events = $state<EventCard[]>([]);
  $effect(() => {
    api.shortLinks(org).then((l) => (links = l)).catch(() => {});
    api.orgEvents(org).then((l) => (events = l.filter((e) => e.status === 'published' && (e.endsAt ?? e.startsAt) > nowTs()))).catch(() => {});
  });
  const host = location.host;
  let slug = $state('');
  let to = $state('club'); // 'club', 'round', or an event's id
  const s = $derived(slug.trim().toLowerCase());
  const ok = $derived(/^(?=.{2,32}$)[a-z0-9]+(?:-[a-z0-9]+)*$/.test(s)); // logic.SHORT
  const where = (l: ShortLink) => (l.kind === 'event' ? l.eventTitle ?? '' : t(l.kind === 'club' ? 'sl.club' : 'sl.round'));

  async function copy(x: string) {
    try { await navigator.clipboard.writeText(`https://${host}/${x}`); haptic.ok(); say(t('sl.copied'), 'sparkles_3d'); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
  }
  let busy = $state(false);
  async function add(ev: Event) {
    ev.preventDefault();
    busy = true;
    try {
      links = await api.addShortLink(org, to === 'club' || to === 'round' ? { slug: s, kind: to } : { slug: s, kind: 'event', eventId: Number(to) });
      void copy(s);
      slug = '';
    } catch (e) {
      haptic.error();
      const m = e instanceof ApiErr ? (e.message === 'taken' || e.message === 'limit' ? e.message : e.code === 'bad_input' ? 'bad' : '') : '';
      say(m ? t(`sl.${m as 'taken'}`) : t('common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
  async function drop(x: string) {
    if (!(await sheets.ask({ title: t('sl.dropAsk', { link: `${host}/${x}` }), ok: t('sl.drop'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.dropShortLink(x); links = links.filter((l) => l.slug !== x); haptic.warn(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<h3 class="t-cap cap">{t('sl.title')}</h3>
<p class="t-foot note">{t('sl.note')}</p>
{#each links as l (l.slug)}
  <div class="ln">
    <span class="tx"><b class="ellipsis selectable">{host}/{l.slug}</b><i class="t-foot ellipsis">{where(l)}</i></span>
    <button class="ic" aria-label={t('sl.copy')} onclick={() => copy(l.slug)}><Copy size={18} /></button>
    <button class="ic del" aria-label={t('sl.drop')} onclick={() => drop(l.slug)}><Trash size={18} /></button>
  </div>
{/each}
<form class="add" onsubmit={add}>
  <label class="field"><span class="t-cap">{host}/</span>
    <input bind:value={slug} maxlength="32" placeholder="join-us" autocapitalize="none" autocomplete="off" spellcheck="false" enterkeyhint="done" /></label>
  <select bind:value={to} aria-label={t('sl.to')}>
    <option value="club">{t('sl.club')}</option>
    <option value="round">{t('sl.round')}</option>
    {#each events as e (e.id)}<option value={String(e.id)}>{e.title}</option>{/each}
  </select>
  <Button kind="primary" size="m" type="submit" loading={busy} disabled={!ok}>{t('sl.add')}</Button>
</form>

<style>
  .cap { margin: 22px 2px 2px; }
  .note { margin: 0 2px 10px; }
  .ln { display: flex; align-items: center; gap: 8px; padding: 8px 2px; }
  .ln + .ln { box-shadow: inset 0 1px 0 var(--line); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 650 15px/1.25 var(--font-text); }
  .tx i { font-style: normal; }
  .ic { flex: none; display: flex; padding: 8px; border-radius: var(--r-full); color: var(--text-2); background: var(--surface-2); }
  .ic.del { color: var(--danger-text); }
  .add { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
  .add select { height: 44px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text); font: 550 15px/1 var(--font-text); }
</style>
