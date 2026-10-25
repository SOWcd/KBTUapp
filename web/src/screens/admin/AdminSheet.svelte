<script lang="ts">
  // The admin panel (SPEC §2), a hub since Oct 14 (owner: "redo it completely", it was one long page of everything):
  // the numbers on top; "To decide" — clubs waiting for the check (§4.6) and reports (§4.10), each opened in place —
  // or a quiet "all clear"; then one row per job, each its own sheet: clubs and schools, creator awards, the chats
  // directory, DMP's registry; what I took down (30 days, the way back) folds under its row.
  import { fold } from '../../ui/fold';
  import Flag from '@lucide/svelte/icons/flag';
  import BookUser from '@lucide/svelte/icons/book-user';
  import Medal from '@lucide/svelte/icons/medal';
  import Building from '@lucide/svelte/icons/building-2';
  import EyeOff from '@lucide/svelte/icons/eye-off';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Avatar from '../../ui/Avatar.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { ago } from '../../lib/time';
  import { api, ApiErr, type AdminDay, type AdminStats, type ClubApplication, type ReportItem, type ReportReason, type TakenDown } from '../../lib/api';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { openLink, haptic } from '../../lib/tg';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { loadAfisha } from '../../lib/state/data.svelte';
  import { loadMe, session } from '../../lib/state/session.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import ScrollText from '@lucide/svelte/icons/scroll-text';
  import { t, tn, i18n } from '../../lib/i18n/index.svelte';
  import { withNick } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import { schoolShort } from '../../lib/short';

  let { overlay }: { overlay: Overlay } = $props();
  let busy = $state(false);
  // a moderator (owner, Oct 22) only filters content: the reports, what was taken down, the chats directory
  const admin = $derived(session.me?.role === 'admin');
  const owner = $derived(admin && !!session.me?.founder);
  // the rows' numbers, fetched with the panel
  let clubsN = $state<number | null>(null);
  let schoolsN = $state(0);
  $effect(() => { if (admin) api.adminOrgs().then((l) => { clubsN = l.filter((o) => o.kind === 'club').length; schoolsN = l.length - clubsN; }).catch(() => {}); });
  let chatsN = $state<number | null>(null);
  let chatsP = $state(0); // suggested, waiting for a look
  $effect(() => { api.chats().then((c) => { chatsN = c.all.length; chatsP = c.pending?.length ?? 0; }).catch(() => {}); });
  // ---- the numbers (PLAN "Admin stats"): no per-person logs, counts only; the chart is the nightly rows ----
  let stats = $state<AdminStats | null>(null);
  $effect(() => { if (admin) api.adminStats().then((s) => (stats = s)).catch(() => {}); });
  const peak = $derived(Math.max(1, stats?.today ?? 0, ...(stats?.days ?? []).map((d) => d.active)));
  // 30 slots: 29 nightly rows ending yesterday (Almaty days), then today so far (the visits log)
  const today = Math.floor((Date.now() / 1000 + 5 * 3600) / 86400);
  const slots = $derived.by(() => {
    const by = new Map((stats?.days ?? []).map((d) => [d.day, d.active]));
    if (stats?.today != null) by.set(today, stats.today);
    return Array.from({ length: 30 }, (_, i) => ({ day: today - 29 + i, n: by.get(today - 29 + i) }));
  });
  // a day tapped on the chart (owner, Oct 21): how many and who came in
  let picked = $state<AdminDay | null>(null), pickedDay = $state<number | null>(null);
  async function pickDay(day: number, toggle = true) {
    if (pickedDay === day && !toggle) return;
    haptic.select();
    if (pickedDay === day) { pickedDay = null; picked = null; return; }
    pickedDay = day; picked = null;
    try { const d = await api.adminDay(day); if (pickedDay === day) picked = d; } catch { say(t('common.error'), 'pleading_face_3d'); }
  }
  // a bar is ~8 px wide: the finger picks by where it is along the chart, and slides from day to day
  let scrub = false;
  function at(e: PointerEvent, toggle: boolean) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const i = Math.min(slots.length - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * slots.length)));
    void pickDay(slots[i].day, toggle);
  }
  const dayName = (day: number) => new Intl.DateTimeFormat(i18n.lang, { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(day * 864e5));

  // ---- reports: one row per reported thing still up ----
  let reports = $state<ReportItem[] | null>(null);
  $effect(() => { api.reports().then((l) => (reports = l)).catch(() => (reports = [])); });
  const reasons = (r: ReportItem) => (Object.entries(r.reasons) as [ReportReason, number][]).map(([k, n]) => t(`rep.${k}`) + (n > 1 ? ` ×${n}` : '')).join(', ');
  async function resolve(r: ReportItem, remove: boolean) {
    try {
      await api.resolveReport(r.target, r.id, remove);
      reports = (reports ?? []).filter((x) => !(x.target === r.target && x.id === r.id));
      if (remove) void loadDown();
      void loadMe(); // the count on the Admin row
      haptic.ok(); say(remove ? t('adm.removed') : t('adm.kept'), 'raising_hands_3d_default');
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // ---- a wrong call undone: what I took down from the reports in the last 30 days, folded under its count ----
  let down = $state<TakenDown[] | null>(null);
  let downOpen = $state(false);
  const loadDown = () => api.takenDown().then((l) => (down = l)).catch(() => (down = []));
  $effect(() => { void loadDown(); });
  async function undo(x: TakenDown) {
    try { await api.restore(x.target, x.id); down = (down ?? []).filter((y) => !(y.target === x.target && y.id === x.id)); haptic.ok(); say(t('adm.restored'), 'raising_hands_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // ---- clubs waiting for the check (§4.6): yes creates the club with its applicant as President; no needs a reason ----
  let apps = $state<ClubApplication[] | null>(null);
  $effect(() => { if (admin) api.clubApplications().then((l) => (apps = l)).catch(() => (apps = [])); else apps = []; });
  const pending = $derived((apps ?? []).filter((a) => a.status === 'pending'));
  let refusing = $state<number | null>(null);
  let why = $state('');
  async function decide(a: ClubApplication, approve: boolean) {
    busy = true;
    try {
      const done = await api.decideClubApplication(a.id, approve, approve ? undefined : why.trim());
      apps = (apps ?? []).map((x) => (x.id === a.id ? done : x)); refusing = null; why = '';
      if (approve) { clubsN = (clubsN ?? 0) + 1; void loadAfisha(); }
      void loadMe();
      haptic.ok(); say(approve ? t('adm.cappYes', { name: a.name }) : t('adm.cappNo'), approve ? 'party_popper_3d' : 'waving_hand_3d_default');
    } catch (e) { haptic.error(); say(e instanceof ApiErr && e.message === 'taken' ? t('nc.taken') : t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }

  // one application open at a time: its text, the reason and the answer
  let capp = $state<number | null>(null);
  const todo = $derived(pending.length + (reports?.length ?? 0));

  function look(r: ReportItem) {
    if (r.target === 'comment') sheets.comments(r.where.kind as 'post' | 'event', r.where.id, r.text);
    else if (r.target === 'event') sheets.event(r.id);
    else if (r.target === 'user') sheets.person(r.id); // a profile: its nick, own photo and "about me"
    else if (r.target === 'photo') sheets.event(r.where.id); // the album's event (the thumb is in the row)
    else if (r.target === 'post') sheets.comments('post', r.id, r.text.split(' · ')[0]); // no post screen: the row has its words, the thread its talk
  }
</script>

<!-- the title is the capsule's, with the shield (owner, Oct 21: not twice) -->
<Sheet {overlay} full title={t('me.admin')} icon={ShieldCheck}>
  {#if stats}
    <section class="stats surface">
      <div class="top">
        <div class="hero"><b class="num">{stats.students}</b><span>{t('st.students')}{#if stats.newToday}<em class="num">+{stats.newToday} {t('st.today')}</em>{/if}</span></div>
        <span class="live"><i></i><b class="num">{stats.online}</b> {t('st.online')}</span>
      </div>
      <div class="nums">
        {#each [['st.day', stats.day], ['st.week', stats.week], ['st.month', stats.month]] as [string, number][] as [k, n] (k)}
          <span><b class="num">{n}</b><i>{t(k as 'st.online')}</i></span>
        {/each}
      </div>
      <div class="chart" role="group" aria-label={t('st.chart')} onpointerdown={(e) => { scrub = true; at(e, true); }} onpointermove={(e) => scrub && at(e, false)}
        onpointerup={() => (scrub = false)} onpointercancel={() => (scrub = false)}>
        <!-- the buttons are for the keyboard and screen readers (a pointer tap is handled by the chart: e.detail is 0 only for keys) -->
        {#each slots as d (d.day)}<button class:none={d.n == null} class:on={pickedDay === d.day} class:now={d.day === today} onclick={(e) => e.detail === 0 && pickDay(d.day)}
          aria-label={`${dayName(d.day)}: ${d.n ?? 0}`}><span style="height:{d.n == null ? 4 : Math.max(6, (d.n / peak) * 100)}%"></span></button>{/each}
      </div>
      <div class="foot"><i>{t('st.chart')}</i><i>{t('st.peak', { n: peak })}</i></div>
      {#if pickedDay != null}
        <div class="dayv" transition:fold>
          <p class="dh"><b>{dayName(pickedDay)}</b>{#if picked}<span class="num">{tn('st.dayCame', picked.active)}{picked.new ? ' · ' + tn('st.dayNew', picked.new) : ''}</span>{/if}</p>
          {#if picked?.people}
            <div class="who">
              {#each picked.people as p (p.id)}
                <button disabled={!p.profile && !p.username} onclick={() => (p.profile ? sheets.person(p.id) : openLink('https://t.me/' + p.username))}><Avatar person={{ id: p.id, name: p.name }} size={28} tappable={false} /><span class="ellipsis">{p.name}</span>
                  {#if p.username}<i class="ellipsis">@{p.username}</i>{/if}{#if p.new}<em>{t('st.newOne')}</em>{/if}</button>
              {/each}
            </div>
          {:else if picked}<p class="t-foot">{t('st.dayOld')}</p>{/if}
        </div>
      {/if}
    </section>
  {/if}

  <h3 class="t-cap sh">{t('adm.todo')}{#if todo}<b class="cnt num">{todo}</b>{/if}</h3>
  {#if apps && reports && !todo}
    <p class="clear surface"><CircleCheck size={20} />{t('adm.allClear')}</p>
  {/if}
  {#if pending.length}
    <div class="todo">
      {#each pending as a (a.id)}
        <div class="capp surface">
          <button class="ch" aria-expanded={capp === a.id} onclick={() => { haptic.select(); capp = capp === a.id ? null : a.id; refusing = null; }}>
            <OrgLogo org={{ id: 0, slug: '', name: a.name, short: a.short, emoji: a.emoji, cover: a.cover, kind: 'club', official: false }} size={40} />
            <span><em>{t('adm.cappTag')}</em><b class="ellipsis">{a.name}</b><i class="ellipsis">{a.applicant ? withNick(a.applicant.fullName, a.applicant.person) : '—'}{a.applicant?.course ? ' · ' + t('person.course', { n: a.applicant.course }) : ''}{a.applicant?.school ? ' · ' + schoolShort(a.applicant.school) : ''}</i></span>
            <span class="chev"><ChevronRight size={18} /></span>
          </button>
          {#if capp === a.id}
          <div class="cb" transition:fold>
          <p class="selectable">{a.description}</p>
          {#if a.why}<p class="why selectable"><b>{t('adm.cappWhy')}</b> {a.why}</p>{/if}
          {#each a.links as l (l)}<button class="lnk" onclick={() => openLink(l)}>{l}</button>{/each}
          {#if refusing === a.id}
            <textarea bind:value={why} rows="2" maxlength="300" placeholder={t('adm.cappReason')}></textarea>
            <div class="ra"><Button kind="neutral" size="s" onclick={() => (refusing = null)}>{t('common.cancel')}</Button>
              <Button kind="danger" size="s" loading={busy} disabled={why.trim().length < 3} onclick={() => decide(a, false)}>{t('adm.cappRefuse')}</Button></div>
          {:else}
            <div class="ra">
              <Button kind="primary" size="s" loading={busy} onclick={() => decide(a, true)}>{t('adm.cappApprove')}</Button>
              <Button kind="neutral" size="s" onclick={() => { refusing = a.id; why = ''; }}>{t('adm.cappRefuse')}</Button>
              {#if a.applicant?.username}<Button kind="secondary" size="s" onclick={() => openLink('https://t.me/' + a.applicant!.username)}>{t('adm.cappWrite')}</Button>{/if}
            </div>
          {/if}
          </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
  {#if reports?.length}
    <section class="reps">
      <h4 class="rh"><Flag size={14} />{tn('adm.reports', reports.length)}</h4>
      {#each reports as r (r.target + r.id)}
        <div class="rep">
          <button class="rt" onclick={() => look(r)}>{#if r.target === 'photo'}<img class="rph" src={r.text} alt="" />{:else}<b class:clamp-2={r.target !== 'post'}>{r.text}</b>{/if}<i>{t(`adm.rep.${r.target}`)} · {reasons(r)} · {ago(r.at)}</i></button>
          <!-- what the reporters wrote (never who): newest first -->
          {#each r.notes ?? [] as n, i (i)}<p class="rn selectable"><b>{t(`rep.${n.reason}`)}</b> {n.note}</p>{/each}
          <div class="ra">
            <Button kind="danger" size="s" onclick={() => resolve(r, true)}>{t('adm.takeDown')}</Button>
            <Button kind="neutral" size="s" onclick={() => resolve(r, false)}>{t('adm.keep')}</Button>
          </div>
        </div>
      {/each}
    </section>
  {/if}

  <h3 class="t-cap sh">{t('adm.manage')}</h3>
  <div class="rows surface">
    {#if admin}
    <button class="r" onclick={() => sheets.adminClubs()}><span class="ic"><Building size={20} /></span><span class="lb">{t('adm.clubs')}{#if clubsN != null}<i>{tn('reg.clubs', clubsN)} · {tn('adm.schools', schoolsN)}</i>{/if}</span><ChevronRight size={18} /></button>
    <!-- the app's team (owner, Oct 22): moderators, admins (the owner gives those), bans -->
    <button class="r" onclick={() => sheets.adminTeam()}><span class="ic"><UsersRound size={20} /></span><span class="lb">{t('staff.title')}<i>{t('staff.sub')}</i></span><ChevronRight size={18} /></button>
    {#if owner}<button class="r" onclick={() => sheets.adminAudit()}><span class="ic"><ScrollText size={20} /></span><span class="lb">{t('audit.title')}<i>{t('audit.sub')}</i></span><ChevronRight size={18} /></button>{/if}
    <button class="r" onclick={() => sheets.give()}><span class="ic"><Medal size={20} /></span><span class="lb">{t('give.title')}<i>{t('adm.giveSub')}</i></span><ChevronRight size={18} /></button>
    {/if}
    <button class="r" onclick={() => sheets.adminChats()}><span class="ic"><TelegramMark size={20} /></span><span class="lb">{t('adm.chats')}{#if chatsN != null}<i>{tn('adm.chatsSub', chatsN)}{chatsP ? ` · ${t('adm.chatPending')}: ${chatsP}` : ''}</i>{/if}</span><ChevronRight size={18} /></button>
    {#if admin}
    <!-- the AI page (owner, Oct 21): what the translator does, what failed -->
    <button class="r" onclick={() => sheets.adminAi()}><span class="ic"><Sparkles size={20} /></span><span class="lb">{t('ai.title')}{#if stats?.ai}<i>{stats.ai.on ? `${t('ai.on')} · ${stats.ai.today} ${t('ai.today')}` : t('ai.off')}</i>{/if}</span><ChevronRight size={18} /></button>
    <button class="r" onclick={() => sheets.registry()}><span class="ic"><BookUser size={20} /></span><span class="lb">{t('reg.title')}<i>{t('reg.sub')}</i></span><ChevronRight size={18} /></button>
    {/if}
    {#if down?.length}
      <button class="r" aria-expanded={downOpen} onclick={() => (downOpen = !downOpen)}><span class="ic"><EyeOff size={20} /></span><span class="lb">{t('adm.undoTitle')}</span><i class="n num">{down.length}</i><span class="chev"><ChevronRight size={18} /></span></button>
    {/if}
  </div>
  {#if down?.length}
    {#if downOpen}
      <div class="chl surface" transition:fold>{#each down as x (x.target + x.id)}<div class="chr"><span class="ellipsis">{x.text}<i>{t(`adm.rep.${x.target}`)} · {ago(x.at)}</i></span><button class="undo" onclick={() => undo(x)}>{t('adm.restore')}</button></div>{/each}</div>
    {/if}
  {/if}
</Sheet>

<style>
  .sh { display: flex; align-items: center; gap: 8px; margin: 20px 2px 8px; }
  .cnt { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 10px; background: var(--danger); color: #fff; font: 700 12px/20px var(--font-text); text-align: center; letter-spacing: 0; }
  .clear { display: flex; align-items: center; gap: 10px; padding: 14px; color: var(--text-2); font: 600 14.5px/1.3 var(--font-text); }
  .clear :global(svg) { color: var(--success, #2FBF71); }

  .stats { display: flex; flex-direction: column; gap: 14px; padding: 16px; }
  .top { display: flex; align-items: flex-start; gap: 12px; }
  .hero { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
  .hero b { font: 800 40px/0.95 var(--font-display, var(--font-text)); letter-spacing: -0.03em; }
  .hero span { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font: 550 14px/1.2 var(--font-text); color: var(--text-2); }
  .hero em { padding: 3px 8px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 700 12px/1.2 var(--font-text); font-style: normal; }
  .live { flex: none; display: flex; align-items: center; gap: 6px; height: 30px; padding: 0 12px; border-radius: var(--r-full);
    background: color-mix(in srgb, var(--success, #2FBF71) 14%, transparent); color: var(--success, #2FBF71); font: 600 13px/1 var(--font-text); }
  .live b { font: 750 14px/1 var(--font-text); }
  .live i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: pulse 2s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 55%, transparent); } 50% { box-shadow: 0 0 0 5px transparent; } }
  @media (prefers-reduced-motion: reduce) { .live i { animation: none; } }
  .nums { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .nums span { display: flex; flex-direction: column; gap: 4px; min-width: 0; padding: 10px 12px; border-radius: var(--r-m); background: var(--surface-2); }
  .nums b { font: 750 19px/1.1 var(--font-display, var(--font-text)); }
  .nums i { font: 500 12px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  .chart { display: flex; align-items: stretch; gap: 3px; height: 64px; touch-action: pan-y; }
  .chart button { flex: 1; min-width: 0; display: flex; align-items: flex-end; padding: 0; }
  .chart span { width: 100%; border-radius: 2px; background: linear-gradient(to top, color-mix(in srgb, var(--accent) 55%, transparent), var(--accent)); transition: opacity .2s; }
  .chart .none span { background: var(--line); }
  .chart .now span { background: linear-gradient(to top, color-mix(in srgb, var(--success) 55%, transparent), var(--success)); } /* today, still counting */
  .chart:has(.on) button:not(.on) span { opacity: 0.4; }
  .dayv { display: flex; flex-direction: column; gap: 10px; padding-top: 4px; border-top: 1px solid var(--line); }
  .dh { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin: 8px 0 0; }
  .dh b { font: 700 var(--fs-body)/1.2 var(--font-text); }
  .dh span { font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .who { display: flex; flex-direction: column; max-height: 280px; overflow-y: auto; margin: 0 -4px; }
  .who button { display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 4px; border-radius: 10px; text-align: left; }
  .who button:active { background: var(--surface-2); }
  .who span { flex: 0 1 auto; min-width: 0; font: 600 var(--fs-body)/1.2 var(--font-text); }
  .who i { flex: 1; min-width: 0; font: 500 var(--fs-sub)/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .who em { flex: none; padding: 3px 8px; border-radius: var(--r-full); background: var(--success-soft); color: var(--success-text); font: 650 var(--fs-micro)/1 var(--font-text); font-style: normal; }
  .foot { display: flex; justify-content: space-between; gap: 8px; margin-top: -6px; }
  .foot i { font: 500 12px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }

  .todo { display: flex; flex-direction: column; gap: 8px; }
  .capp { display: flex; flex-direction: column; overflow: hidden; }
  .ch { display: flex; align-items: center; gap: 12px; padding: 12px; text-align: left; }
  .ch > span:nth-child(2) { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .ch em { align-self: flex-start; padding: 2px 7px; border-radius: 6px; background: var(--accent-soft); color: var(--accent-text); font: 700 10.5px/1.3 var(--font-text); font-style: normal; letter-spacing: 0.04em; text-transform: uppercase; }
  .ch b { font: 700 15.5px/1.2 var(--font-text); }
  .ch i { font: 500 12.5px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .chev { flex: none; display: flex; color: var(--text-3); transition: transform var(--t-base) var(--ease); }
  [aria-expanded='true'] .chev { transform: rotate(90deg); }
  .cb { display: flex; flex-direction: column; gap: 8px; padding: 0 12px 12px; }
  .cb p { font: 500 14px/1.45 var(--font-text); white-space: pre-wrap; }
  .cb .why b { font-weight: 700; }
  .lnk { align-self: flex-start; font: 600 13px/1.3 var(--font-text); color: var(--accent-text); word-break: break-all; text-align: left; }
  .cb textarea { width: 100%; padding: 10px 12px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text); font: 500 15px/1.4 var(--font-text); resize: none; }

  .reps { margin-top: 8px; padding: 12px; border-radius: var(--r-l); background: var(--danger-soft); }
  .rh { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; font: 700 12px/1.2 var(--font-text); letter-spacing: 0.04em; text-transform: uppercase; color: var(--danger-text); }
  .rep { padding: 10px 0; border-top: 1px solid var(--line-2); }
  .rep:first-of-type { border-top: 0; }
  .rt { display: flex; flex-direction: column; gap: 4px; width: 100%; text-align: left; }
  .rn { margin: 6px 0 0; padding: 8px 10px; border-radius: var(--r-s, 10px); background: var(--surface-2); font: 500 13.5px/1.35 var(--font-text); color: var(--text-2); overflow-wrap: anywhere; white-space: pre-wrap; }
  .rn b { color: var(--text); font-weight: 650; }
  .rt b { font: 600 15px/1.35 var(--font-text); }
  .rph { width: 96px; height: 96px; border-radius: var(--r-m); object-fit: cover; background: var(--surface-2); }
  .rt i { font: 500 12.5px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .ra { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }

  .rows { display: flex; flex-direction: column; padding: 2px 0; overflow: hidden; }
  .r { display: flex; align-items: center; gap: 12px; min-height: 60px; padding: 8px 14px; text-align: left; color: var(--text-3); }
  .r + .r { box-shadow: inset 0 1px 0 var(--line); }
  .r:active { background: var(--surface-2); }
  .ic { display: flex; color: var(--accent-text); }
  .lb { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; font: 600 15.5px/1.2 var(--font-text); color: var(--text); }
  .lb i { font: 500 12.5px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .ic { flex: none; width: 36px; height: 36px; align-items: center; justify-content: center; border-radius: 10px; background: var(--accent-soft); }
  .n { font: 600 14px/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .chl { display: flex; flex-direction: column; margin-top: 8px; }
  .chr { display: flex; align-items: center; gap: 8px; padding: 10px 8px 10px 14px; }
  .chr + .chr { border-top: 1px solid var(--line); }
  .chr span { flex: 1; min-width: 0; font: 600 14.5px/1.3 var(--font-text); }
  .chr i { margin-left: 6px; font-style: normal; font-weight: 500; color: var(--text-3); }
  .chr button.undo { flex: none; height: 30px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 620 13px/1 var(--font-text); }
</style>
