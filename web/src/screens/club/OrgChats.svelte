<script lang="ts">
  // The org's Telegram chats on its page (PLAN 86): its Vice+ add them by @name, a link or an
  // invite link, pick the main channel (the page's Subscribe button) and add our bot, which keeps each card current.
  // Saved here at once, not with the profile's Save, like the short links.
  import Trash from '@lucide/svelte/icons/trash-2';
  import Lock from '@lucide/svelte/icons/lock';
  import { api, ApiErr, type Id, type StudioChat } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { compact, addBotLink } from '../../lib/chats';
  import { haptic, openLink } from '../../lib/tg';
  import Button from '../../ui/Button.svelte';
  import ChatAvatar from '../../ui/ChatAvatar.svelte';

  let { org }: { org: Id } = $props();
  let chats = $state<StudioChat[]>([]);
  $effect(() => { api.orgChats(org).then((l) => (chats = l)).catch(() => {}); });
  // a change here shows on Studio's channel tile at once (it reads my memberships, loaded with the app)
  function keep(l: StudioChat[]): StudioChat[] {
    const mine = session.me?.memberships.find((x) => x.org.id === org);
    const c = l.find((x) => x.main);
    if (mine && mine.channel !== undefined) mine.channel = c ? { title: c.title, mirror: c.mirror && c.kind === 'channel' && !c.closed } : null;
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
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function mirror(c: StudioChat, on: boolean) {
    try { chats = keep(await api.mirrorOrgChat(org, c.id, on)); haptic.select(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function drop(c: StudioChat) {
    if (!(await sheets.ask({ title: t('oc.dropAsk', { title: c.title }), ok: t('oc.drop'), cancel: t('common.cancel'), danger: true }))) return;
    try { chats = keep(await api.dropOrgChat(org, c.id)); haptic.warn(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // a channel counts subscribers, a group members, as Telegram says
  const count = (c: StudioChat) => (c.members ? tn(c.kind === 'channel' ? 'clubs.subscribers' : 'chats.members', c.members).replace(String(c.members), compact(c.members)) : '');
  const line = (c: StudioChat) => [c.main ? t('oc.main') : t(`chats.${c.kind}`), count(c)].filter(Boolean).join(' · ');
</script>

<h3 class="t-cap cap">{t('oc.studio')}</h3>
<p class="t-foot note">{t('oc.studioNote')}</p>
{#each chats as c (c.id)}
  <div class="ch">
    <div class="top">
      <ChatAvatar title={c.title} photo={c.photo} kind={c.kind} size={40} />
      <span class="tx"><b class="ellipsis">{#if c.closed}<Lock size={13} />{/if}{c.title}</b><i class="t-foot ellipsis">{line(c)}</i></span>
      <button class="ic del" aria-label={t('oc.drop')} onclick={() => drop(c)}><Trash size={18} /></button>
    </div>
    <div class="acts">
      {#if c.kind === 'channel' && !c.closed && !c.main}<button class="pill" onclick={() => main(c)}>{t('oc.makeMain')}</button>{/if}
      {#if c.bot}<span class="pill on">{t('oc.bot')}</span>
      {:else}<button class="pill" onclick={() => { haptic.tap(); openLink(addBotLink(c)); }}>{t('oc.addBot')}</button>{/if}
    </div>
    {#if c.main}
      <!-- the main channel's posts in the club's news (PLAN 86 part 2): on by linking it, off here -->
      <label class="switch mir"><span><b>{t('oc.mirror')}</b><i class="t-foot">{t('oc.mirrorNote')}</i></span>
        <input type="checkbox" role="switch" checked={c.mirror} onchange={(e) => mirror(c, e.currentTarget.checked)} /></label>
    {/if}
  </div>
{/each}
{#if chats.some((c) => !c.bot)}<p class="t-foot note">{t('oc.botNote')}</p>{/if}
<form class="add" onsubmit={add}>
  <label class="field"><span class="t-cap">{t('oc.link')}</span>
    <input bind:value={link} maxlength="200" placeholder="@kbtu_club" autocapitalize="none" autocomplete="off" spellcheck="false" enterkeyhint="done" /></label>
  <Button kind="primary" size="m" type="submit" loading={busy} disabled={link.trim().length < 4}>{t('oc.add')}</Button>
</form>

<style>
  .cap { margin: 22px 2px 2px; }
  .note { margin: 0 2px 10px; }
  .ch { display: flex; flex-direction: column; gap: 8px; padding: 10px 2px; }
  .ch + .ch { box-shadow: inset 0 1px 0 var(--line); }
  .top { display: flex; align-items: center; gap: 10px; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { display: flex; align-items: center; gap: 5px; font: 650 15px/1.25 var(--font-text); }
  .tx b :global(svg) { flex: none; color: var(--text-3); }
  .tx i { font-style: normal; }
  .ic { flex: none; display: flex; padding: 8px; border-radius: var(--r-full); color: var(--text-2); background: var(--surface-2); }
  .ic.del { color: var(--danger-text); }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; padding-left: 50px; }
  .pill { height: 30px; padding: 0 12px; border-radius: var(--r-full); display: inline-flex; align-items: center; background: var(--accent-soft); color: var(--accent-text); font: 620 13px/1 var(--font-text); }
  .pill.on { background: var(--success-soft); color: var(--success-text); }
  .mir { margin: 2px 0 0 50px; }
  .mir b { display: block; font: 620 14.5px/1.25 var(--font-text); }
  .mir i { display: block; margin-top: 2px; font-style: normal; }
  .add { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
</style>
