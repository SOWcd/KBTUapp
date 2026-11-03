<script lang="ts">
  // A club's roster for DMP (SPEC §3, §4.13): leaders first, then everyone with full name, student ID, course, school and
  // since when; the President's and Vices' contacts (Telegram, email, phone) a tap away; who hasn't come in 60 days marked.
  // On top, a club's ✓ (§2, §4.6): DMP makes a student initiative official — the President hears it from the bot; taking
  // it back asks first.
  import BadgeCheck from '@lucide/svelte/icons/badge-check';
  import { untrack } from 'svelte';
  import { api, type OrgRef, type RosterMember } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { haptic, openLink } from '../../lib/tg';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';
  import { ROLE_NAME, withNick } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import BookUser from '@lucide/svelte/icons/book-user';
  import Avatar from '../../ui/Avatar.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import { schoolShort, shortOf } from '../../lib/short';
  import { fmtPhone, kzPhone } from '../../lib/phone';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Contact from '@lucide/svelte/icons/contact';
  import { menu, type MenuItem } from '../../ui/menu';

  // the President's and Vices' contacts, a tap away (a small menu at their row)
  const contacts = (m: RosterMember): MenuItem[] => [
    ...(m.username ? [{ label: '@' + m.username, onselect: () => openLink('https://t.me/' + m.username) }] : []),
    ...(m.email ? [{ label: m.email, onselect: () => openLink('mailto:' + m.email) }] : []),
    ...(m.phone ? [{ label: kzPhone(m.phone) ? fmtPhone(m.phone) : m.phone, onselect: () => openLink('tel:' + m.phone) }] : []),
  ];

  let { overlay, org, onofficial }: { overlay: Overlay; org: OrgRef; onofficial?: (on: boolean) => void } = $props();
  let list = $state<RosterMember[] | null>(null);
  $effect(() => { api.registryRoster(org.id).then((l) => (list = l)).catch(() => { list = []; say(t('common.error'), 'warning_3d'); }); });
  const quiet = $derived((list ?? []).filter((m) => m.quiet).length);

  let official = $state(untrack(() => org.official));
  let sw = $state(untrack(() => org.official)); // the switch as shown: back on while we ask, and if the answer is no
  let busy = $state(false);
  async function toggle(on: boolean) {
    sw = on;
    if (!on && !(await sheets.ask({ title: t('reg.officialOffAsk', { name: org.name }), ok: t('reg.officialOffOk'), cancel: t('common.cancel'), danger: true }))) { sw = true; return; }
    busy = true;
    try {
      official = sw = (await api.setOfficial(org.id, on)).official;
      onofficial?.(official);
      haptic.ok(); say(phrase(on ? 'reg.officialOn' : 'reg.officialOff'), on ? 'party_popper_3d' : 'waving_hand_3d_default');
    } catch { sw = official; haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }

  // DMP sets any club's short name; the club's Vice+ in its profile
  let abbr = $state(untrack(() => shortOf(org)));
  async function rename() {
    const v = (await sheets.askText({ title: t('ce.abbr'), text: t('ce.abbrHint'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: abbr, max: 8 }))?.trim();
    if (!v || v === abbr) return;
    try { abbr = shortOf(await api.updateOrg(org.id, { abbr: v })); haptic.ok(); }
    catch { haptic.error(); say(t('ce.abbrHint'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} icon={BookUser} full title={t('cap.roster')}>
  <div class="pg">
    <Group>
      <Row title={org.name} subtitle={list ? tn('reg.people', list.length) + (quiet ? ' · ' + tn('reg.quietN', quiet) : '') : undefined}>
        {#snippet lead()}<OrgLogo {org} size={48} />{/snippet}
        {#snippet detail()}{#if official}<span class="ok"><BadgeCheck size={20} /></span>{/if}{/snippet}
      </Row>
    </Group>
    {#if org.kind === 'club'}
      <Group footnote={t('reg.officialNote')}>
        <Row title={t('reg.official')} accessory="switch" checked={sw} disabled={busy} onchange={toggle} />
      </Group>
      <Group>
        <Row title={t('ce.abbr')} value={abbr} accessory="chevron" onclick={rename} />
      </Group>
    {/if}
    {#if list}
      <Group>
        {#each list as m (m.person.id)}
          {@const c = contacts(m)}
          {#snippet reach()}<IconButton icon={Contact} label={t('reg.contacts')} kind="plain" size="s" onclick={(e) => menu(e.currentTarget as Element, c)} />{/snippet}
          <Row dense title={withNick(m.fullName, m.person)} trailing={c.length ? reach : undefined}
            subtitle={[m.studentId, m.course && t('person.year', { n: m.course }), m.school && schoolShort(m.school), t('reg.since', { date: dayMonth(m.joinedAt) })].filter(Boolean).join(' · ')}>
            {#snippet lead()}<Avatar person={m.person} size={36} />{/snippet}
            {#snippet detail()}
              {#if m.quiet}<Tag tone="warning">{t('reg.quiet')}</Tag>{/if}
              <Tag tone={m.role === 'president' || m.role === 'vice' ? 'accent' : 'neutral'}>{ROLE_NAME[m.role]}</Tag>
            {/snippet}
          </Row>
        {:else}<EmptyState inline text={t('reg.empty')} />{/each}
      </Group>
    {:else}
      <Skeleton n={3} />
    {/if}
  </div>
</Sheet>

<style>
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-1); }
  .ok { display: inline-flex; color: var(--accent-text); }
</style>
