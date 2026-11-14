<script lang="ts">
  // The club's own short links (Vice+): kbtu.sow.kz/<slug> to the club, one of its upcoming events or its
  // round, never anywhere outside the app. Made, copied and taken down here at once, not with the profile's Save.
  import { copyText } from '../../ui/copy';
  import Copy from '@lucide/svelte/icons/copy';
  import Trash from '@lucide/svelte/icons/trash-2';
  import { api, ApiErr, type EventCard, type Id, type ShortLink } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  // n: how many the club has (the profile's row says it)
  let { org, n = $bindable() }: { org: Id; n?: number } = $props();
  let links = $state<ShortLink[]>([]);
  $effect(() => { n = links.length; });
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
  const targets = $derived([{ v: 'club', label: t('sl.club') }, { v: 'round', label: t('sl.round') }, ...events.map((e) => ({ v: String(e.id), label: e.title }))]);
  const where = (l: ShortLink) => (l.kind === 'event' ? l.eventTitle ?? '' : t(l.kind === 'club' ? 'sl.club' : 'sl.round'));

  async function copy(x: string) {
    if (!(await copyText(`https://${host}/${x}`, t('sl.copied')))) say(t('common.error'), 'warning_3d');
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
      say(m ? t(`sl.${m as 'taken'}`) : t('common.error'), 'warning_3d');
    } finally { busy = false; }
  }
  async function drop(x: string) {
    if (!(await sheets.ask({ title: t('sl.dropAsk', { link: `${host}/${x}` }), ok: t('sl.drop'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.dropShortLink(x); links = links.filter((l) => l.slug !== x); haptic.warn(); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<div class="sl">
  {#if links.length}
    <Group>
      {#each links as l (l.slug)}
        <Row dense title="{host}/{l.slug}" subtitle={where(l)}>
          {#snippet trailing()}
            <IconButton icon={Copy} label={t('sl.copy')} kind="plain" size="s" onclick={() => copy(l.slug)} />
            <IconButton icon={Trash} label={t('sl.drop')} kind="plain" size="s" destructive onclick={() => drop(l.slug)} />
          {/snippet}
        </Row>
      {/each}
    </Group>
  {/if}
  <form class="add" onsubmit={add}>
    <!-- engine: Field's autocapitalize / spellcheck (a slug is typed as is) -->
    <Field label="{host}/" bind:value={slug} maxlength={32} placeholder="join-us" autocomplete="off" enterkeyhint="done" />
    <Group footnote={t('sl.note')}>
      <Row title={t('sl.to')} value={targets.find((x) => x.v === to)?.label}
        menu={targets.map((x) => ({ label: x.label, checked: x.v === to, onselect: () => (to = x.v) }))} />
    </Group>
    <Button kind="primary" size="m" type="submit" loading={busy} disabled={!ok}>{t('sl.add')}</Button>
  </form>
</div>

<style>
  .sl { display: flex; flex-direction: column; gap: var(--s-3); }
  .add { display: flex; flex-direction: column; gap: var(--s-2); }
</style>
