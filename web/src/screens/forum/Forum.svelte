<script lang="ts">
  // The forum (PLAN F1 + the adversarial review): for now one segment, Find people. Offers to answer, my skills and
  // switches, requests (mine first), and people by a skill. Contact is always an offer the other side accepts in the
  // bot; their Telegram shows only then. The app's staff only, behind the server's flag, while it's tried out.
  import Plus from '@lucide/svelte/icons/plus';
  import Flag from '@lucide/svelte/icons/flag';
  import Ban from '@lucide/svelte/icons/ban';
  import { api, ApiErr, type Ask, type Contact, type ForumCard, type ForumMe, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import PersonCards from './PersonCards.svelte';
  import ForumMod from './ForumMod.svelte';
  import { session } from '../../lib/state/session.svelte';

  let { overlay, ask: focus }: { overlay: Overlay; ask?: Id } = $props();
  let me = $state<ForumMe | null>(null), list = $state<Ask[]>([]), offers = $state<Contact[]>([]);
  let skill = $state<Id | null>(null), q = $state(''), found = $state<ForumCard[] | null>(null), closing = $state<Id | null>(null);
  const load = () => {
    api.forumMe().then((m) => (me = m)).catch(() => {});
    api.asks(skill).then((l) => (list = l)).catch(() => {});
    api.contacts().then((l) => (offers = l)).catch(() => {});
  };
  $effect(() => { void skill; load(); });
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const s = q.trim();
    clearTimeout(timer);
    if (!s) { found = null; return; }
    timer = setTimeout(() => api.findPeople(s).then((l) => (found = l)).catch(() => (found = [])), 350);
  });
  // the request a ping opened: in sight once it's there
  $effect(() => { if (focus && list.length) setTimeout(() => document.getElementById(`ask-${focus}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 300); });

  const fail = (e: unknown) => { haptic.error(); say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'fo.slow' : 'common.error'), 'pleading_face_3d'); };
  async function setMe(patch: { open?: boolean; pings?: boolean }) {
    try { me = await api.setForumMe(patch); haptic.tap(); } catch (e) { fail(e); }
  }
  async function help(a: Ask) {
    try { await api.offer({ ask: a.id }); haptic.ok(); a.offered = 'pending'; say(t('fo.offerSay'), 'raising_hands_3d_default'); } catch (e) { fail(e); }
  }
  async function answer(c: Contact, yes: boolean) {
    try { offers = await api.answerOffer(c.id, yes); haptic.ok(); } catch (e) { fail(e); }
  }
  async function shut(a: Ask, foundIt: boolean | null) {
    try { await api.closeAsk(a.id, foundIt); haptic.ok(); closing = null; load(); } catch (e) { fail(e); }
  }
  async function block(id: Id) {
    try { await api.block(id); haptic.ok(); say(t('fo.blockedSay'), 'waving_hand_3d_default'); load(); } catch (e) { fail(e); }
  }
  const staff = $derived(session.me?.role === 'admin' || session.me?.role === 'moderator');
  const standing = (a: Ask) => a.status === 'held' ? t('fo.held') : a.status === 'hidden' ? t('fo.hidden') : a.status === 'closed' ? t('fo.closed') : '';
</script>

<Sheet {overlay} full title={t('fo.title')}>
  <div class="seg top" role="tablist"><button class="on" role="tab" aria-selected="true">{t('fo.find')}</button></div>
  {#if staff}<ForumMod changed={load} />{/if}

  {#if offers.length}
    <h3 class="t-cap cap">{t('fo.offers')}</h3>
    <div class="list surface">
      {#each offers as c (c.id)}
        <div class="row">
          <Avatar person={c.person} size={40} />
          <span class="tx"><b class="ellipsis">{c.name}{c.course ? ` · ${t('fo.course', { n: c.course })}` : ''}</b>
            <i class="ellipsis">{c.ask ?? c.skills.map((s) => s.name).join(', ')}</i></span>
          {#if c.status === 'accepted' && c.telegram}<button class="go" onclick={() => openLink(c.telegram!)}>{t('fo.write')}</button>
          {:else if c.incoming}<button class="go" onclick={() => answer(c, true)}>{t('fo.accept')}</button><button class="no" onclick={() => answer(c, false)}>{t('fo.decline')}</button>
          {:else}<span class="t-foot">{t('fo.waiting')}</span>{/if}
        </div>
      {/each}
    </div>
  {/if}

  <h3 class="t-cap cap">{t('fo.me')}</h3>
  <div class="mine surface">
    <button class="skills" onclick={() => sheets.forumSkills(load)}>
      {#if me?.skills.length}{#each me.skills as s (s.id)}<span class="chip">{s.name}</span>{/each}{:else}<span class="t-foot">{t('fo.addSkills')}</span>{/if}
    </button>
    <label class="switch"><span><b>{t('fo.open')}</b><i class="t-foot">{t('fo.openNote')}</i></span>
      <input type="checkbox" role="switch" checked={me?.open ?? false} onchange={(e) => setMe({ open: e.currentTarget.checked })} /></label>
    {#if me?.open}
      <label class="switch"><span><b>{t('fo.pings')}</b><i class="t-foot">{t('fo.pingsNote')}</i></span>
        <input type="checkbox" role="switch" checked={me.pings} onchange={(e) => setMe({ pings: e.currentTarget.checked })} /></label>
    {/if}
  </div>

  <div class="head"><h3 class="t-cap">{t('fo.asks')}</h3><button class="new" onclick={() => sheets.newAsk(load)}><Plus size={16} />{t('fo.newAsk')}</button></div>
  {#if me?.skills.length}
    <div class="filter hscroll" data-noswipe>
      <button class="chip" class:on={skill === null} onclick={() => (skill = null)}>{t('fo.all')}</button>
      {#each me.skills as s (s.id)}<button class="chip" class:on={skill === s.id} onclick={() => (skill = s.id)}>{s.name}</button>{/each}
    </div>
  {/if}
  {#each list as a (a.id)}
    <article class="ask surface" id="ask-{a.id}" class:focus={a.id === focus}>
      <div class="ah"><span class="kind">{t(`fo.kind.${a.kind}`)}</span><span class="t-foot">{t('fo.until', { when: dayMonth(a.expiresAt) })}</span></div>
      <b class="at">{a.title}</b>
      {#if a.body}<p class="ab">{a.body}</p>{/if}
      {#if a.skills.length}<div class="sk">{#each a.skills as s (s.id)}<span class="chip">{s.name}</span>{/each}</div>{/if}
      <div class="by"><Avatar person={a.author.person} size={24} /><span class="t-foot">{a.author.name}{a.author.course ? ` · ${t('fo.course', { n: a.author.course })}` : ''}</span></div>
      {#if a.mine}
        {#if standing(a)}<p class="st t-foot">{standing(a)}</p>{/if}
        {#if a.offers?.length}<p class="t-foot">{tn('fo.offersN', a.offers.length)}: {a.offers.map((o) => o.name).join(', ')}</p>{/if}
        {#if a.status === 'live' || a.status === 'held'}
          {#if closing === a.id}
            <div class="acts"><button class="go" onclick={() => shut(a, true)}>{t('fo.foundHere')}</button><button class="no" onclick={() => shut(a, false)}>{t('fo.foundElse')}</button><button class="no" onclick={() => shut(a, null)}>{t('fo.notNeeded')}</button></div>
          {:else}<div class="acts"><button class="no" onclick={() => (closing = a.id)}>{t('fo.close')}</button></div>{/if}
        {/if}
      {:else}
        <div class="acts">
          <button class="go" disabled={!!a.offered} onclick={() => help(a)}>{t(a.offered ? 'fo.offered' : 'fo.help')}</button>
          <button class="icon" aria-label={t('fo.report')} onclick={() => sheets.report('ask', a.id, a.title, load)}><Flag size={16} /></button>
          <button class="icon" aria-label={t('fo.block')} onclick={() => block(a.author.person.id)}><Ban size={16} /></button>
        </div>
      {/if}
      {#if a.matches}<button class="people" onclick={() => sheets.askPeople(a.id, a.title)}>{tn('fo.matches', a.matches)}</button>{/if}
    </article>
  {:else}
    <p class="t-foot empty">{t('fo.noAsks')}</p>
  {/each}

  <h3 class="t-cap cap">{t('fo.findPeople')}</h3>
  <SearchField bind:value={q} placeholder={t('fo.findPh')} />
  {#if found}<div class="res"><PersonCards cards={found} /></div>{/if}
</Sheet>

<style>
  .top { margin: 4px 0 6px; }
  .cap, .head { margin: 22px 4px 10px; }
  .head { display: flex; align-items: center; justify-content: space-between; }
  .new { display: inline-flex; align-items: center; gap: 4px; color: var(--accent-text); font: 650 14px/1 var(--font-text); }
  .list { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; }
  .row + .row { border-top: 1px solid var(--line); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 640 15px/1.25 var(--font-text); }
  .tx i { font: 500 12.5px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .go, .no { flex: none; height: 32px; padding: 0 12px; border-radius: var(--r-full); font: 650 13px/1 var(--font-text); }
  .go { background: var(--accent-soft); color: var(--accent-text); }
  .go:disabled { background: var(--surface-2); color: var(--text-3); }
  .no { background: var(--surface-2); color: var(--text-2); }
  .mine { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .skills { display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 14px; text-align: left; }
  .mine .switch { border-radius: 0; background: none; box-shadow: inset 0 1px 0 var(--line); }
  .chip { display: inline-flex; align-items: center; height: 28px; padding: 0 10px; border-radius: var(--r-full); background: var(--surface-2); font: 600 13px/1 var(--font-text); color: var(--text); white-space: nowrap; }
  .chip.on { background: var(--accent-soft); color: var(--accent-text); }
  .filter { gap: 6px; margin: 0 calc(-1 * var(--gutter)) 10px; padding: 0 var(--gutter); }
  .ask { display: flex; flex-direction: column; gap: 8px; padding: 14px; border-radius: var(--r-l); margin-bottom: 10px; }
  .ask.focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
  .ah { display: flex; justify-content: space-between; align-items: center; }
  .kind { font: 700 11px/1 var(--font-text); letter-spacing: 0.06em; text-transform: uppercase; color: var(--accent-text); }
  .at { font: 680 16px/1.25 var(--font-text); }
  .ab { font: 450 14px/1.4 var(--font-text); color: var(--text-2); white-space: pre-line; }
  .sk { display: flex; flex-wrap: wrap; gap: 6px; }
  .by { display: flex; align-items: center; gap: 8px; }
  .st { color: var(--warning-text, var(--text-2)); }
  .acts { display: flex; gap: 8px; align-items: center; }
  .icon { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-3); }
  .people { align-self: flex-start; color: var(--accent-text); font: 620 13.5px/1.2 var(--font-text); }
  .empty { padding: 10px 4px; }
  .res { margin-top: 10px; }
</style>
