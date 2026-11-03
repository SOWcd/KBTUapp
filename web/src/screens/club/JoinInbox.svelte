<script lang="ts">
  import { withNick } from '../../lib/perms';
  // A club's applications (Vice+, §4.5), oldest first. The owner's flow: look at the person (the avatar opens
  // their card), write to them first ("come by, let's meet"), then accept or decline; the bot tells them.
  // "Recruiting" (the round) is the row on top; the switch below it takes any-time join requests without a round.
  // Studio's "Recruiting" tile opens this for Vice+.
  // ponytail: "Write" needs a Telegram @username (no username, no chat link); a bot relay if that bites.
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { api, type Id, type JoinRequest, type Round } from '../../lib/api';
  import { data, phrase, studioChanged } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { relDay } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Inbox from '@lucide/svelte/icons/inbox';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { may } from '../../lib/perms';
  import { schoolShort } from '../../lib/short';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  let list = $state<JoinRequest[] | null>(null);
  $effect(() => { api.joinRequests(org).then((l) => (list = l)).catch(() => (list = [])); });
  const o = $derived(data.orgs.find((x) => x.id === org));
  const casting = $derived(may(session.me?.memberships.find((x) => x.org.id === org), 'casting'));
  let round = $state<Round | null>(null);
  const loadRound = () => { if (casting) api.round(org).then((x) => (round = x)).catch(() => {}); };
  $effect(loadRound);
  const total = $derived(Object.values(round?.counts ?? {}).reduce((p: number, c) => p + (c ?? 0), 0));

  async function decide(r: JoinRequest, accept: boolean) {
    if (!accept && !(await sheets.ask({ title: t('jr.declineAsk'), text: t('jr.declineText'), ok: t('jr.decline'), cancel: t('join.keep'), danger: true }))) return;
    list = list!.filter((x) => x.id !== r.id);
    accept ? haptic.ok() : haptic.warn();
    try {
      await api.decideJoin(r.id, accept);
      say(phrase(accept ? 'say.accepted' : 'say.declined'), accept ? 'party_popper_3d' : 'waving_hand_3d_default');
      studioChanged(); // member counts and the Studio row
    } catch {
      list = [r, ...list!].sort((a, b) => a.id - b.id);
      haptic.error(); say(t('common.error'), 'warning_3d');
    }
  }

  async function setOpen(on: boolean) {
    if (!o) return;
    o.recruiting = on;
    try { Object.assign(o, await api.setRecruiting(org, on)); say(phrase(on ? 'say.recruitOn' : 'say.recruitOff'), on ? 'raising_hands_3d_default' : 'sparkles_3d'); }
    catch { o.recruiting = !on; say(t('common.error'), 'warning_3d'); }
  }
  const line = (r: JoinRequest) => [r.course && t('person.course', { n: r.course }), schoolShort(r.school)].filter(Boolean).join(' · ');
</script>

<Sheet {overlay} icon={Inbox} full title={t('cast.card')}>
  <div class="list">
    {#if casting || o}
      <Group footnote={o ? t('jr.openHint') : undefined}>
        {#if casting}
          <Row icon={Megaphone} title={round ? round.title : t('cast.cardOpen')} count={round?.counts?.new ?? 0}
            value={round && !round.counts?.new ? tn('cast.apps', total) : undefined} accessory="chevron"
            onclick={() => (round ? sheets.roundBoard(org) : sheets.roundSetup(org, null, loadRound))} />
        {/if}
        {#if o}
          <Row icon={UserPlus} title={t('jr.open')} accessory="switch" checked={o.recruiting} onchange={(on) => { haptic.tap(); void setOpen(on); }} />
        {/if}
      </Group>
    {/if}
    {#if list}
      {#each list as r (r.id)}
        {#snippet write()}<Button kind="secondary" size="s" onclick={() => openLink('https://t.me/' + r.username)}>{#snippet icon()}<TelegramMark size={15} />{/snippet}{t('jr.write')}</Button>{/snippet}
        <!-- engine: Row needs content under it (the answer's buttons): one Group per applicant until then -->
        <Group>
          <Row dense title={withNick(r.fullName, r.person)} subtitle={[line(r), relDay(r.createdAt)].filter(Boolean).join(' · ')} trailing={r.username ? write : undefined}>
            {#snippet lead()}<Avatar person={r.person} size={36} />{/snippet}
          </Row>
          <div class="acts btns">
            <Button kind="secondary" size="m" full onclick={() => decide(r, false)}>{t('jr.decline')}</Button>
            <Button kind="primary" size="m" full onclick={() => decide(r, true)}>{t('jr.accept')}</Button>
          </div>
        </Group>
      {:else}
        <EmptyState inline text={t('jr.none')} />
      {/each}
    {/if}
  </div>
</Sheet>

<style>
  .list { display: flex; flex-direction: column; gap: var(--s-3); }
  .acts { display: flex; gap: var(--s-2); padding: 0 var(--s-4) var(--s-4); }
</style>
