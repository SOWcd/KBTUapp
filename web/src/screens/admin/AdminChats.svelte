<script lang="ts">
  // Admin → Chats (§4.11): the directory's t.me links, for everyone or for a school and/or a course; a sheet of its own
  // since the admin panel became a hub (owner, Oct 14). The admin says whose a chat is (PLAN 86: then it shows on that
  // club's or school's page too; owner, Oct 22: t.me/kbtusite is SITE's).
  import Plus from '@lucide/svelte/icons/plus';
  import X from '@lucide/svelte/icons/x';
  import { api, ApiErr, type AdminOrg, type Chat } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import { schoolShort, shortOf } from '../../lib/short';

  let { overlay }: { overlay: Overlay } = $props();
  let busy = $state(false);
  // ---- the chats directory (§4.11): t.me links for everyone, or for a school and/or a course ----
  let chats = $state<Chat[] | null>(null);
  // suggested by students through the bot (PLAN item 45): Add puts it in the catalog, the cross declines it
  let pending = $state<Chat[]>([]);
  $effect(() => { api.chats().then((c) => { chats = c.all; pending = c.pending ?? []; }).catch(() => (chats = [])); });
  async function approve(c: Chat) {
    try { const x = await api.approveChat(c.id); pending = pending.filter((p) => p.id !== c.id); chats = [...(chats ?? []), x]; haptic.ok(); say(phrase('say.chatApproved'), 'party_popper_3d'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function decline(c: Chat) {
    try { await api.deleteChat(c.id); pending = pending.filter((p) => p.id !== c.id); haptic.soft(); say(t('say.chatDeclined'), 'waving_hand_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  const admin = $derived(session.me?.role === 'admin');
  let orgs = $state<AdminOrg[]>([]);
  $effect(() => { if (admin) api.adminOrgs().then((l) => (orgs = l.sort((a, b) => a.name.localeCompare(b.name)))).catch(() => {}); });
  async function whose(c: Chat, ev: Event) {
    const v = (ev.currentTarget as HTMLSelectElement).value;
    try { const x = await api.setChatOrg(c.id, v ? Number(v) : null); chats = (chats ?? []).map((y) => (y.id === c.id ? x : y)); haptic.ok(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  let chatForm = $state(false);
  let nch = $state({ title: '', url: '', kind: 'group' as Chat['kind'], school: '', course: 0 });
  async function addChat(ev: Event) {
    ev.preventDefault();
    busy = true;
    try {
      const c = await api.addChat({ title: nch.title.trim(), url: nch.url.trim(), kind: nch.kind, school: nch.school.trim() || null, course: nch.course || null });
      chats = [...(chats ?? []), c]; chatForm = false; nch = { title: '', url: '', kind: 'group', school: '', course: 0 };
      haptic.ok(); say(t('adm.chatAdded'), 'raising_hands_3d_default');
    } catch (e) { haptic.error(); say(e instanceof ApiErr && e.code === 'bad_input' ? t('adm.chatBad') : e instanceof ApiErr && e.message === 'org' ? t('chats.why.org') : t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
  async function dropChat(c: Chat) {
    try { await api.deleteChat(c.id); chats = (chats ?? []).filter((x) => x.id !== c.id); haptic.soft(); say(t('say.chatDropped'), 'file_cabinet_3d'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }

</script>

<Sheet {overlay} full title={t('adm.chats')}>
  <h2 class="t-h2 hd">{t('adm.chats')}</h2>
  <p class="t-foot lead">{t('adm.chatsLead')}</p>
  {#if pending.length}
    <h3 class="t-cap gh">{t('adm.chatPending')} · {pending.length}</h3>
    <div class="chl surface">{#each pending as c (c.id)}<div class="chr">
      <span class="av" class:sq={c.kind === 'forum'}>{#if c.photo}<img src={c.photo} alt="" />{/if}</span>
      <!-- the link itself, so a look tells a real chat from a stray one -->
      <button class="pv ellipsis" onclick={() => openLink(c.url)}>{c.title}<i>{c.org ? `${t('oc.whose')}: ${shortOf(c.org)} · ` : ''}{c.url.includes('/+') ? t('adm.chatInvite') + ' · ' : ''}{c.url.replace('https://', '')} · {t(`chats.${c.kind}`)}{c.members ? ' · ' + c.members : ''}</i></button>
      <Button kind="primary" size="s" onclick={() => approve(c)}>{t('adm.chatApprove')}</Button>
      <button onclick={() => decline(c)} aria-label={t('cm.delete')}><X size={16} /></button>
    </div>{/each}</div>
  {/if}
  {#if chats?.length}
    <div class="chl surface">{#each chats as c (c.id)}<div class="chr"><span class="av" class:sq={c.kind === 'forum'}>{#if c.photo}<img src={c.photo} alt="" />{/if}</span><span class="ellipsis">{c.title}<i>{schoolShort(c.school)}{c.course ? ' ' + t('chats.course', { n: c.course }) : ''}</i></span>
      {#if admin}<select class="whose" aria-label={t('oc.whose')} value={c.org ? String(c.org.id) : ''} onchange={(ev) => whose(c, ev)}>
        <option value="">{t('oc.nobody')}</option>{#each orgs as o (o.id)}<option value={String(o.id)}>{o.abbr || o.name}</option>{/each}</select>{/if}
      <button onclick={() => dropChat(c)} aria-label={t('cm.delete')}><X size={16} /></button></div>{/each}</div>
  {/if}
  {#if chatForm}
    <form class="new" onsubmit={addChat}>
      <label class="field"><span class="t-cap">{t('adm.chatUrl')}</span><input bind:value={nch.url} placeholder="https://t.me/…" autocapitalize="none" spellcheck="false" /></label>
      <label class="field"><span class="t-cap">{t('adm.chatTitle')}</span><input bind:value={nch.title} maxlength="80" /></label>
      <div class="seg wide">{#each ['group', 'forum', 'channel'] as const as k (k)}<button type="button" class:on={nch.kind === k} onclick={() => (nch.kind = k)}>{t(`chats.${k}`)}</button>{/each}</div>
      <div class="two">
        <label class="field"><span class="t-cap">{t('adm.chatSchool')}</span><input bind:value={nch.school} maxlength="40" /></label>
        <label class="field"><span class="t-cap">{t('adm.chatCourse')}</span><select bind:value={nch.course}><option value={0}>{t('chats.everyone')}</option>{#each [1, 2, 3, 4, 5, 6] as n (n)}<option value={n}>{t('chats.course', { n })}</option>{/each}</select></label>
      </div>
      <div class="acts">
        <Button kind="neutral" size="m" full onclick={() => (chatForm = false)}>{t('common.cancel')}</Button>
        <Button kind="primary" size="m" full type="submit" loading={busy} disabled={!nch.url.trim()}>{t('adm.chatAdd')}</Button>
      </div>
    </form>
  {:else}
    <button class="addchat" onclick={() => (chatForm = true)}><Plus size={16} />{t('adm.chatAdd')}</button>
  {/if}

</Sheet>

<style>
  .hd { margin: 4px 0 4px; }
  .lead { margin-bottom: 14px; }
  .new { display: flex; flex-direction: column; gap: 10px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .acts { display: flex; gap: 8px; }
  .acts :global(.btn.full) { flex: 1; width: auto; min-width: 0; }
  .seg.wide { display: flex; margin: 8px 0; }
  .seg.wide button { flex: 1; }
  select { width: 100%; height: 100%; background: none; color: var(--text); font: 500 16px/1 var(--font-text); }
  .chl { display: flex; flex-direction: column; margin-bottom: 12px; }
  .chr { display: flex; align-items: center; gap: 10px; padding: 8px 8px 8px 10px; }
  .chr + .chr { border-top: 1px solid var(--line); }
  .av { flex: none; width: 32px; height: 32px; border-radius: 50%; overflow: hidden; background: var(--surface-2); }
  .av.sq { border-radius: 30%; }
  .av img { width: 100%; height: 100%; object-fit: cover; }
  .chr .ellipsis { flex: 1; min-width: 0; font: 600 14.5px/1.3 var(--font-text); }
  .chr i { margin-left: 6px; font-style: normal; font-weight: 500; color: var(--text-3); }
  .chr button { flex: none; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 50%; color: var(--text-3); }
  .whose { flex: none; width: auto; max-width: 96px; height: 30px; padding: 0 8px; border-radius: var(--r-full); background: var(--surface-2); font: 600 12.5px/1 var(--font-text); color: var(--text-2); }
  .addchat { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; height: 44px; border-radius: var(--r-m); background: var(--surface-2); color: var(--accent-text); font: 620 14.5px/1 var(--font-text); }
  .gh { margin: 4px 2px 8px; }
  .pv { flex: 1; min-width: 0; text-align: left; font: 600 14.5px/1.3 var(--font-text); color: var(--text); }
  .pv i { display: block; margin: 2px 0 0; }
</style>
