<script lang="ts">
  import { withNick } from '../../lib/perms';
  // A club's applications (Vice+, §4.5), oldest first. The owner's flow: look at the person (the avatar opens
  // their card), write to them first ("come by, let's meet"), then accept or decline; the bot tells them.
  // The switch on top closes applications: nobody can apply, people can still write to the club.
  // Studio's "Recruiting" tile opens this: the casting (recruitment rounds) is a row here, not a tile of its own.
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
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
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
      haptic.error(); say(t('common.error'), 'pleading_face_3d');
    }
  }

  async function setOpen(on: boolean) {
    if (!o) return;
    o.recruiting = on;
    try { Object.assign(o, await api.setRecruiting(org, on)); say(phrase(on ? 'say.recruitOn' : 'say.recruitOff'), on ? 'raising_hands_3d_default' : 'sparkles_3d'); }
    catch { o.recruiting = !on; say(t('common.error'), 'pleading_face_3d'); }
  }
  const line = (r: JoinRequest) => [r.course && t('person.course', { n: r.course }), schoolShort(r.school)].filter(Boolean).join(' · ');
</script>

<Sheet {overlay} full title={t('cast.card')}>
  <h2 class="t-h2 hd">{t('cast.card')}</h2>
  {#if o}
    <label class="switch">
      <span><b>{t('jr.open')}</b><i class="t-foot">{o.recruiting ? t('jr.openHint') : t('jr.closedHint')}</i></span>
      <input type="checkbox" role="switch" checked={o.recruiting} onchange={(e) => { haptic.tap(); void setOpen(e.currentTarget.checked); }} />
    </label>
  {/if}
  {#if casting}
    <button class="cast" onclick={() => (round ? sheets.roundBoard(org) : sheets.roundSetup(org, null, loadRound))}>
      <Megaphone size={20} /><span class="lbl">{t('cast.row')}</span>
      {#if round?.counts?.new}<b class="count">{round.counts.new}</b>{:else}<span class="t-foot ellipsis">{round ? tn('cast.apps', total) : t('cast.cardOpen')}</span>{/if}
      <ChevronRight size={18} />
    </button>
  {/if}
  {#if list}
    <div class="list">
      {#each list as r (r.id)}
        <article class="req">
          <div class="top">
            <Avatar person={r.person} size={44} />
            <span class="who">
              <b class="ellipsis">{withNick(r.fullName, r.person)}</b>
              <span class="t-foot ellipsis">{[line(r), relDay(r.createdAt)].filter(Boolean).join(' · ')}</span>
            </span>
            {#if r.username}
              <Button kind="secondary" size="s" onclick={() => openLink('https://t.me/' + r.username)}>{#snippet icon()}<TelegramMark size={15} />{/snippet}{t('jr.write')}</Button>
            {/if}
          </div>
          <div class="acts">
            <Button kind="neutral" size="m" full onclick={() => decide(r, false)}>{t('jr.decline')}</Button>
            <Button kind="primary" size="m" full onclick={() => decide(r, true)}>{t('jr.accept')}</Button>
          </div>
        </article>
      {:else}
        <p class="t-foot none">{t('jr.none')}</p>
      {/each}
    </div>
  {/if}
</Sheet>

<style>
  .hd { margin: 4px 0 14px; }
  .list { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
  .req { display: flex; flex-direction: column; gap: 12px; padding: 12px; border-radius: var(--r-l); background: var(--surface-2); }
  .top { display: flex; align-items: center; gap: 12px; }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .who b { font: 650 15.5px/1.3 var(--font-text); }
  .acts { display: flex; gap: 8px; }
  .acts :global(.btn.full) { flex: 1; width: auto; min-width: 0; }
  .acts :global(.btn.neutral) { background: var(--surface-3); } /* the card is surface-2 already */
  .cast { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 54px; margin-top: 10px; padding: 0 12px 0 14px; border-radius: var(--r-l);
    background: var(--surface-2); text-align: left; color: var(--text-3); }
  .cast > :global(svg:first-child) { flex: none; color: var(--accent-text); }
  .cast .lbl { flex: 1; color: var(--text); font: 620 15px/1 var(--font-text); }
  .count { min-width: 24px; height: 24px; padding: 0 7px; border-radius: 12px; background: var(--accent); color: var(--on-accent); font: 700 13px/24px var(--font-text); text-align: center; }
  .none { padding: 18px 4px; text-align: center; }
</style>
