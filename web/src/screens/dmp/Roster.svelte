<script lang="ts">
  // A club's roster for DMP (SPEC §3, §4.13): leaders first, then everyone with full name, student ID, course, school and
  // since when; the President's and Vices' contacts (Telegram, email, phone) a tap away; who hasn't come in 60 days marked.
  // On top, a club's ✓ (§2, §4.6): DMP makes a student initiative official — the President hears it from the bot; taking
  // it back asks first.
  import Mail from '@lucide/svelte/icons/mail';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Phone from '@lucide/svelte/icons/phone';
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
  import Avatar from '../../ui/Avatar.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  let { overlay, org, onofficial }: { overlay: Overlay; org: OrgRef; onofficial?: (on: boolean) => void } = $props();
  let list = $state<RosterMember[] | null>(null);
  $effect(() => { api.registryRoster(org.id).then((l) => (list = l)).catch(() => { list = []; say(t('common.error'), 'pleading_face_3d'); }); });
  const quiet = $derived((list ?? []).filter((m) => m.quiet).length);

  let official = $state(untrack(() => org.official));
  let busy = $state(false);
  async function toggle(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, on = el.checked;
    if (!on) { // stays on while we ask
      el.checked = true;
      if (!(await sheets.ask({ title: t('reg.officialOffAsk', { name: org.name }), ok: t('reg.officialOffOk'), cancel: t('common.cancel'), danger: true }))) return;
      el.checked = false;
    }
    busy = true;
    try {
      official = (await api.setOfficial(org.id, on)).official;
      onofficial?.(official);
      haptic.ok(); say(phrase(on ? 'reg.officialOn' : 'reg.officialOff'), on ? 'party_popper_3d' : 'waving_hand_3d_default');
    } catch { el.checked = official; haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} tall title={org.name}>
  <div class="hd"><OrgLogo {org} size={48} /><span><h2 class="t-h2">{org.name}{#if official}<span class="ok"><BadgeCheck size={20} /></span>{/if}</h2><p class="t-foot">{list ? tn('reg.people', list.length) + (quiet ? ' · ' + tn('reg.quietN', quiet) : '') : ' '}</p></span></div>
  {#if org.kind === 'club'}
    <label class="switch off"><span><b>{t('reg.official')}</b><i class="t-foot">{t('reg.officialNote')}</i></span><input type="checkbox" role="switch" checked={official} onchange={toggle} disabled={busy} /></label>
  {/if}
  {#if list}
    <div class="list">
      {#each list as m (m.person.id)}
        <div class="m" class:lead={m.role !== 'member'}>
          <Avatar person={m.person} size={40} />
          <span class="tx">
            <span class="top"><b class="ellipsis">{withNick(m.fullName, m.person)}</b><span class="role" class:hi={m.role === 'president' || m.role === 'vice'}>{ROLE_NAME[m.role]}</span></span>
            <i>{m.studentId}{m.course ? ' · ' + t('person.year', { n: m.course }) : ''}{m.school ? ' · ' + m.school : ''}</i>
            <i>{t('reg.since', { date: dayMonth(m.joinedAt) })}{#if m.quiet}<span class="quiet">{t('reg.quiet')}</span>{/if}</i>
            {#if m.username || m.email || m.phone}
              <span class="contacts">
                {#if m.username}<button onclick={() => openLink('https://t.me/' + m.username)}><TelegramMark size={14} />@{m.username}</button>{/if}
                {#if m.email}<button onclick={() => openLink('mailto:' + m.email)}><Mail size={14} />{m.email}</button>{/if}
                {#if m.phone}<button onclick={() => openLink('tel:' + m.phone)}><Phone size={14} />{m.phone}</button>{/if}
              </span>
            {/if}
          </span>
        </div>
      {:else}<p class="t-foot none">{t('reg.empty')}</p>{/each}
    </div>
  {:else}
    <div class="wait" aria-hidden="true"><span></span><span></span><span></span></div>
  {/if}
</Sheet>

<style>
  .hd { display: flex; align-items: center; gap: 12px; margin: 4px 0 16px; }
  .ok { display: inline-flex; margin-left: 6px; vertical-align: -2px; color: var(--accent-text); }
  .off { margin-bottom: 12px; }
  .list { display: flex; flex-direction: column; gap: 2px; }
  .m { display: flex; gap: 12px; align-items: flex-start; padding: 10px 2px; border-bottom: 1px solid var(--line); }
  .m:last-child { border-bottom: 0; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .top { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .top b { min-width: 0; font: 650 15px/1.25 var(--font-text); }
  .role { flex: none; padding: 3px 8px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text-2); font: 650 11.5px/1 var(--font-text); }
  .role.hi { background: var(--accent-soft); color: var(--accent-text); }
  .tx i { font: 500 12.5px/1.35 var(--font-text); font-style: normal; color: var(--text-2); }
  .quiet { margin-left: 8px; padding: 2px 7px; border-radius: var(--r-full); background: var(--warning-soft); color: var(--warning-text); font-weight: 650; }
  .contacts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .contacts button { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border-radius: var(--r-full); background: var(--surface-2);
    color: var(--accent-text); font: 600 12.5px/1 var(--font-text); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .none { padding: 18px 4px; text-align: center; }
  .wait { display: flex; flex-direction: column; gap: 12px; }
  .wait span { height: 60px; border-radius: var(--r-m); background: var(--surface-2); animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
</style>
