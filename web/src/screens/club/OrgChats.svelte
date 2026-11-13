<script lang="ts">
  // The org's Telegram chats on its page (PLAN 86): its Vice+ add them by @name, a link or an
  // invite link, pick the main channel (the page's Subscribe button) and add our bot, which keeps each card current.
  // Saved here at once, not with the profile's Save, like the short links.
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import { api, ApiErr, type Id, type StudioChat, type SwearRow } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { compact, addBotLink } from '../../lib/chats';
  import { haptic, openLink } from '../../lib/tg';
  import Button from '../../ui/Button.svelte';
  import ChatAvatar from '../../ui/ChatAvatar.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import { menu } from '../../ui/menu';

  // n: how many are linked (the profile's row says it)
  let { org, n = $bindable() }: { org: Id; n?: number } = $props();
  let chats = $state<StudioChat[]>([]);
  const load = () => api.orgChats(org).then((l) => (chats = keep(l))).catch(() => {});
  $effect(() => { void load(); });
  // back from Telegram's picker: the chat our bot was just added to shows up (the bot links it, PLAN Nov 5)
  $effect(() => {
    const back = () => { if (!document.hidden) setTimeout(load, 1500); };
    document.addEventListener('visibilitychange', back);
    return () => document.removeEventListener('visibilitychange', back);
  });
  let picking = $state<'group' | 'channel' | null>(null);
  async function pick(kind: 'group' | 'channel') {
    picking = kind;
    try { const { url } = await api.pickOrgChat(org, kind); haptic.tap(); openLink(url); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { picking = null; }
  }
  let byLink = $state(false);
  // a change here shows on Studio's channel tile at once (it reads my memberships, loaded with the app)
  function keep(l: StudioChat[]): StudioChat[] {
    const mine = session.me?.memberships.find((x) => x.org.id === org);
    const c = l.find((x) => x.main);
    if (mine && mine.channel !== undefined) mine.channel = c ? { title: c.title, mirror: c.mirror && c.kind === 'channel' && !c.closed } : null;
    n = l.length;
    return l;
  }

  let link = $state('');
  let busy = $state(false);
  async function add(ev: Event) {
    ev.preventDefault();
    busy = true;
    try { chats = keep(await api.addOrgChat(org, link.trim())); link = ''; haptic.ok(); }
    catch (e) {
      haptic.error();
      const why = !(e instanceof ApiErr) ? 'common.error' : e.code === 'unavailable' ? 'chats.why.later' : e.message === 'notchat' ? 'chats.why.notchat'
        : e.message === 'taken' ? 'oc.why.taken' : e.message === 'catalog' ? 'oc.why.catalog' : e.message === 'limit' ? 'oc.why.limit' : e.code === 'bad_input' ? 'chats.why.bad' : 'common.error';
      say(t(why as 'common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
  async function main(c: StudioChat) {
    try { chats = keep(await api.mainOrgChat(org, c.id)); haptic.select(); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function mirror(c: StudioChat, on: boolean) {
    try { chats = keep(await api.mirrorOrgChat(org, c.id, on)); haptic.select(); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // a group's swear filter (its President or Vice; the bot must be able to delete and restrict there) and 30 days of it
  let report = $state<SwearRow[]>([]);
  $effect(() => { api.swearReport(org).then((r) => (report = r)).catch(() => {}); });
  const groups = $derived(chats.filter((c) => c.bot && c.kind === 'group'));
  async function swear(c: StudioChat, on: boolean) {
    c.swear = on;
    try { chats = keep(await api.swearOrgChat(org, c.id, on)); haptic.select(); }
    catch (e) {
      c.swear = !on;
      haptic.error();
      say(t(e instanceof ApiErr && e.message === 'rights' ? 'oc.swearRights' : 'common.error'), 'warning_3d');
    }
  }
  const mask = (s: string) => (s.length < 3 ? s : s[0] + '*'.repeat(s.length - 2) + s.at(-1));
  const why = (r: SwearRow) => [r.stems.map(mask).join(', '), r.mutes ? t('oc.swearMuted', { n: r.mutes }) : ''].filter(Boolean).join(' · ');
  async function drop(c: StudioChat) {
    if (!(await sheets.ask({ title: t('oc.dropAsk', { title: c.title }), ok: t('oc.drop'), cancel: t('common.cancel'), danger: true }))) return;
    try { chats = keep(await api.dropOrgChat(org, c.id)); haptic.warn(); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // a channel counts subscribers, a group members, as Telegram says
  const count = (c: StudioChat) => (c.members ? tn(c.kind === 'channel' ? 'clubs.subscribers' : 'chats.members', c.members).replace(String(c.members), compact(c.members)) : '');
  const line = (c: StudioChat) => [c.main ? t('oc.main') : t(`chats.${c.kind}`), count(c), c.closed && t('oc.closed'), c.bot && t('oc.bot')].filter(Boolean).join(' · ');
  const mainOne = $derived(chats.find((c) => c.main));
  const more = (e: MouseEvent, c: StudioChat) => menu(e.currentTarget as Element, [
    ...(c.kind === 'channel' && !c.closed && !c.main ? [{ label: t('oc.makeMain'), onselect: () => main(c) }] : []),
    { label: t('oc.drop'), destructive: true, onselect: () => drop(c) },
  ]);
</script>

<div class="oc">
  <Group footnote={t('oc.studioNote') + (chats.some((c) => !c.bot) ? ' ' + t('oc.botNote') : '') + (chats.some((c) => c.bot && c.kind === 'group') ? ' ' + t('oc.allNote') : '')}>
    {#each chats as c (c.id)}
      <Row dense title={c.title} subtitle={line(c)}>
        {#snippet lead()}<ChatAvatar title={c.title} photo={c.photo} kind={c.kind} size={36} />{/snippet}
        {#snippet trailing()}
          {#if !c.bot}<Button kind="tinted" size="s" onclick={() => openLink(addBotLink(c))}>{t('oc.addBot')}</Button>{/if}
          <IconButton icon={Ellipsis} label={t('common.more')} kind="plain" size="s" onclick={(e) => more(e, c)} />
        {/snippet}
      </Row>
    {/each}
    <!-- Telegram's own picker: our bot is added there as an admin and links the chat (no typing @names, owner Nov 5) -->
    <Row tone="add" title={t('oc.pickGroup')} disabled={!!picking} onclick={() => pick('group')} />
    <Row tone="add" title={t('oc.pickChannel')} disabled={!!picking} onclick={() => pick('channel')} />
    {#if !byLink}<Row tone="add" title={t('oc.byLink')} onclick={() => (byLink = true)} />{/if}
  </Group>
  {#if mainOne}
    <!-- the main channel's posts in the club's news (PLAN 86 part 2): on by linking it, off here -->
    <Group footnote={t('oc.mirrorNote')}>
      <Row title={t('oc.mirror')} accessory="switch" checked={mainOne.mirror} onchange={(on) => mirror(mainOne, on)} />
    </Group>
  {/if}
  {#if groups.length}
    <Group caption={t('oc.swear')} footnote={t('oc.swearNote')}>
      {#each groups as c (c.id)}<Row title={c.title} accessory="switch" checked={c.swear} onchange={(on) => swear(c, on)} />{/each}
    </Group>
  {/if}
  {#if report.length}
    <Group caption={t('oc.swearLog')}>
      {#each report as r, i (i)}<Row dense title={r.person?.name ?? t('oc.swearSomeone')} subtitle={why(r)} value={String(r.warns)} />{/each}
    </Group>
  {/if}
  {#if byLink}<form class="add" onsubmit={add}>
    <!-- engine: Field's autocapitalize / spellcheck (a @username is typed as is) -->
    <Field label={t('oc.link')} bind:value={link} maxlength={200} placeholder="@kbtu_club" autocomplete="off" enterkeyhint="done" />
    <Button kind="secondary" size="m" type="submit" loading={busy} disabled={link.trim().length < 4}>{t('oc.add')}</Button>
  </form>{/if}
</div>

<style>
  .oc { display: flex; flex-direction: column; gap: var(--gap-group); }
  .add { display: flex; flex-direction: column; gap: var(--s-2); }
</style>
