<script lang="ts">
  // The forum (PLAN F1 + the adversarial review): for now one part, Find people (no switch until there's a second: one segment drew a lone button). Offers to answer, my skills and
  // switches, requests (mine first), and people by a skill. Contact is always an offer the other side accepts in the
  // bot; their Telegram shows only then. The app's staff only, behind the server's flag, while it's tried out. Its
  // moderation (held requests, the skills catalog) lives in Admin → Forum posts: this sheet is the same for everyone.
    import Flag from '@lucide/svelte/icons/flag';
  import Ban from '@lucide/svelte/icons/ban';
  import { api, ApiErr, type Ask, type Contact, type ForumCard, type ForumMe, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import UserRoundSearch from '@lucide/svelte/icons/user-round-search';
  import Avatar from '../../ui/Avatar.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Card from '../../ui/Card.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import PersonCards from './PersonCards.svelte';

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
  const standing = (a: Ask) => a.status === 'held' ? t('fo.held') : a.status === 'hidden' ? t('fo.hidden') : a.status === 'closed' ? t('fo.closed') : '';
</script>

<Sheet {overlay} icon={UserRoundSearch} full title={t('fo.title')}>
  <div class="col">
    {#if offers.length}
      <Group caption={t('fo.offers')}>
        {#each offers as c (c.id)}
          <Row dense title={`${c.name}${c.course ? ` · ${t('fo.course', { n: c.course })}` : ''}`} subtitle={c.ask ?? (c.skills.map((s) => s.name).join(', ') || undefined)}
            value={c.status === 'accepted' && c.telegram || c.incoming ? undefined : t('fo.waiting')}>
            {#snippet lead()}<Avatar person={c.person} size={40} />{/snippet}
            {#snippet detail()}
              {#if c.status === 'accepted' && c.telegram}<Button kind="tinted" size="s" onclick={() => openLink(c.telegram!)}>{t('fo.write')}</Button>
              {:else if c.incoming}<Button kind="tinted" size="s" onclick={() => answer(c, true)}>{t('fo.accept')}</Button><Button kind="gray" size="s" onclick={() => answer(c, false)}>{t('fo.decline')}</Button>{/if}
            {/snippet}
          </Row>
        {/each}
      </Group>
    {/if}

    <Group caption={t('fo.me')}>
      <Row title={t('fo.mySkills')} subtitle={me?.skills.length ? me.skills.map((s) => s.name).join(', ') : undefined} value={me?.skills.length ? undefined : t('fo.addSkills')}
        accessory="chevron" onclick={() => sheets.forumSkills(load)} />
    </Group>
    <!-- each switch's note is its group's footnote, never a line in the row -->
    <Group footnote={t('fo.openNote')}>
      <Row title={t('fo.open')} accessory="switch" checked={me?.open ?? false} onchange={(on) => setMe({ open: on })} />
    </Group>
    {#if me?.open}
      <Group footnote={t('fo.pingsNote')}>
        <Row title={t('fo.pings')} accessory="switch" checked={me.pings} onchange={(on) => setMe({ pings: on })} />
      </Group>
    {/if}

    <Section title={t('fo.asks')}>
      <Group><Row tone="add" title={t('fo.newAsk')} onclick={() => sheets.newAsk(load)} /></Group>
      {#if me?.skills.length}
        <div class="filter hscroll">
          <Chip selected={skill === null} onclick={() => (skill = null)}>{t('fo.all')}</Chip>
          {#each me.skills as s (s.id)}<Chip selected={skill === s.id} onclick={() => (skill = s.id)}>{s.name}</Chip>{/each}
        </div>
      {/if}
      {#each list as a (a.id)}
        <div class="ask" id="ask-{a.id}" class:focus={a.id === focus}>
          <Card>
            <div class="in">
              <div class="ah"><Tag tone="accent">{t(`fo.kind.${a.kind}`)}</Tag><span class="meta">{t('fo.until', { when: dayMonth(a.expiresAt) })}</span></div>
              <b class="at">{a.title}</b>
              {#if a.body}<p class="ab">{a.body}</p>{/if}
              {#if a.skills.length}<div class="sk">{#each a.skills as s (s.id)}<Tag>{s.name}</Tag>{/each}</div>{/if}
              <div class="by"><Avatar person={a.author.person} size={24} /><span class="meta">{a.author.name}{a.author.course ? ` · ${t('fo.course', { n: a.author.course })}` : ''}</span></div>
              {#if a.mine}
                {#if standing(a)}<p class="st">{standing(a)}</p>{/if}
                {#if a.offers?.length}<p class="meta">{tn('fo.offersN', a.offers.length)}: {a.offers.map((o) => o.name).join(', ')}</p>{/if}
                {#if a.status === 'live' || a.status === 'held'}
                  {#if closing === a.id}
                    <div class="acts"><Button kind="tinted" size="s" onclick={() => shut(a, true)}>{t('fo.foundHere')}</Button><Button kind="gray" size="s" onclick={() => shut(a, false)}>{t('fo.foundElse')}</Button><Button kind="gray" size="s" onclick={() => shut(a, null)}>{t('fo.notNeeded')}</Button></div>
                  {:else}<div class="acts"><Button kind="gray" size="s" onclick={() => (closing = a.id)}>{t('fo.close')}</Button></div>{/if}
                {/if}
              {:else}
                <div class="acts">
                  <Button kind="tinted" size="s" disabled={!!a.offered} onclick={() => help(a)}>{t(a.offered ? 'fo.offered' : 'fo.help')}</Button>
                  <IconButton size="s" icon={Flag} label={t('fo.report')} onclick={() => sheets.report('ask', a.id, a.title, load)} />
                  <IconButton size="s" icon={Ban} label={t('fo.block')} onclick={() => block(a.author.person.id)} />
                </div>
              {/if}
              {#if a.matches}<span class="people"><Button kind="plain" size="s" onclick={() => sheets.askPeople(a.id, a.title)}>{tn('fo.matches', a.matches)}</Button></span>{/if}
            </div>
          </Card>
        </div>
      {:else}
        <EmptyState inline text={t('fo.noAsks')} />
      {/each}
    </Section>

    <Section title={t('fo.findPeople')}>
      <SearchField bind:value={q} placeholder={t('fo.findPh')} />
      {#if found}<PersonCards cards={found} />{/if}
    </Section>
  </div>
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--gap-group); }
  .filter { gap: var(--s-2); margin: 0 calc(-1 * var(--gutter)); padding: 4px var(--gutter); }
  .ask.focus :global(.card) { box-shadow: inset 0 0 0 1.5px var(--accent); }
  .in { display: flex; flex-direction: column; gap: var(--s-2); }
  .ah { display: flex; justify-content: space-between; align-items: center; gap: var(--s-2); }
  .meta { font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .at { font: 600 var(--fs-card)/1.25 var(--font-text); }
  .ab { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); white-space: pre-line; }
  .sk { display: flex; flex-wrap: wrap; gap: 6px; }
  .by { display: flex; align-items: center; gap: var(--s-2); }
  .st { font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--warning-text); }
  .acts { display: flex; flex-wrap: wrap; gap: var(--s-2); align-items: center; }
  .people { align-self: flex-start; margin-left: calc(-1 * var(--s-4)); }
</style>
