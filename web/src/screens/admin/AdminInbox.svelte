<script lang="ts" module>
  let doneOpen = $state(false); // the Done list stays as he left it, opening to opening
</script>

<script lang="ts">
  // Admin → "To decide" (review Nov 3): everything waiting for the staff in one list, one request (server logic/inbox.py,
  // loaded with the app, again as Admin opens): what's already hidden first (a person waits; a red edge says so), then
  // the oldest. A card says what it is, has one main action and one other; the rest is behind its ⋯. A decision answers
  // at once and leaves a slim line in its place with Undo (no "are you sure" for what can be undone); someone else's
  // decision first says who. Nothing waiting: one quiet line. Below, "Done": who did what lately, the Undo there too.
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import { api, ApiErr, type ChannelModPost, type DoneRow, type InboxItem, type ReportItem, type TgcRule } from '../../lib/api';
  import { data, loadInbox } from '../../lib/state/data.svelte';
  import { loadChannel } from '../../lib/state/channel.svelte';
  import { loadMe, session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say } from '../../lib/state/ui.svelte';
  import { t, tn, type Key } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { ago } from '../../lib/time';
  import { withNick, roleName } from '../../lib/perms';
  import { nameOf, schoolShort } from '../../lib/short';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import { menu, type MenuItem } from '../../ui/menu';
  import { fold } from '../../ui/fold';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import ChatAvatar from '../../ui/ChatAvatar.svelte';
  import Section from '../../ui/Section.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Field from '../../ui/Field.svelte';
  import ForumWho, { whyLine } from './ForumWho.svelte';

  const admin = $derived(session.me?.role === 'admin');
  const owner = $derived(admin && !!session.me?.founder);
  $effect(() => { void loadInbox(true); }); // fresh on every opening; what the app loaded shows meanwhile

  // the list as shown: the server's, with the cards decided here kept in their place as slim lines (till Admin closes)
  let handled = $state<Record<string, { text: string; target?: string; it: InboxItem; at: number }>>({});
  const list = $derived.by(() => {
    const out = (data.inbox?.items ?? []).filter((x) => !handled[x.key]);
    for (const h of Object.values(handled).sort((a, b) => a.at - b.at)) out.splice(Math.min(h.at, out.length), 0, h.it);
    return out;
  });
  const waiting = $derived(list.filter((x) => !handled[x.key]).length);
  const done = $derived(data.inbox?.done ?? []);
  // a decision's own Done row (by its audit target), once the reload brings it: its Undo
  const undoOf = (target?: string) => (target ? done.find((d) => d.target === target && d.mine && d.undo) : undefined);

  /** A decision: the card folds into its line at once; the server's no puts it back (or says who came first). */
  async function decide(it: InboxItem, text: string, target: string | undefined, go: () => Promise<unknown>) {
    const at = list.indexOf(it);
    handled[it.key] = { text, target, it, at };
    haptic.ok();
    try { await go(); }
    catch (e) {
      if (e instanceof ApiErr && e.code === 'conflict' && e.message === 'decided') {
        const by = (e.data as { by?: string | null }).by;
        handled[it.key] = { text: by ? t('adm.decided', { name: by }) : t('adm.decidedAnon'), it, at };
      } else { delete handled[it.key]; haptic.error(); say(t('common.error'), 'warning_3d'); }
    }
    void loadInbox(); void loadMe();
  }

  async function undo(d: DoneRow) {
    haptic.select();
    try { await api.undoDone(d.id); say(t('adm.undoneSay'), 'raising_hands_3d_default'); }
    catch (e) {
      const by = e instanceof ApiErr && e.code === 'conflict' ? (e.data as { by?: string | null }).by : undefined;
      haptic.error(); say(by ? t('adm.decided', { name: by }) : e instanceof ApiErr && e.code === 'not_found' ? t('adm.tooLate') : t('common.error'), 'warning_3d');
    }
    // the card it came from is waiting again: it comes back in the list
    for (const [k, h] of Object.entries(handled)) if (h.target === d.target) delete handled[k];
    void loadInbox(); void loadMe(); void loadChannel();
  }

  // ---- reports ----
  const reasons = (r: ReportItem) => (Object.entries(r.reasons) as [string, number][]).map(([k]) => t(`rep.${k}` as Key)).join(', ');
  // the reporters in one word: someone often right, or an account days old (never who)
  function whoReported(r: ReportItem): string {
    const l = r.reporters ?? [];
    if (l.some((x) => x.right >= 3 && x.right > x.wrong * 2)) return t('adm.trusted');
    if (l.some((x) => x.days != null && x.days < 7)) return t('adm.newAcc');
    return '';
  }
  const RULES: TgcRule[] = ['abuse', 'fake', 'spam', 'pdata', 'disrupt', 'other'];
  let rules = $state<Record<number, TgcRule>>({});
  const ruleOf = (r: ReportItem): TgcRule => rules[r.id] ?? r.rule ?? 'other';
  const repTarget = (r: ReportItem) => (r.target === 'fpost' ? `fchan:${r.id}` : `${r.target}:${r.id}`);
  function resolve(it: InboxItem, r: ReportItem, remove: boolean, abuse = false) {
    const text = abuse ? t('adm.abuse') : t(remove ? (r.target === 'tgc' ? 'adm.act.tg_confirm' : 'adm.act.report_remove') : r.removed ? 'adm.act.tg_restore' : 'adm.act.report_keep');
    void decide(it, text, remove ? repTarget(r) : undefined, () => api.resolveReport(r.target, r.id, remove, abuse || undefined, r.target === 'tgc' && remove ? ruleOf(r) : undefined));
  }
  // a photo: Delete asks first (a Gallery post's files are erased, no Undo); Return keeps it, for everyone again
  async function dropPhoto(it: InboxItem, r: ReportItem) {
    const gallery = r.where.kind === 'gallery';
    if (await sheets.ask({ title: t('adm.photoDeleteAsk'), text: gallery ? t('adm.photoDeleteText') : undefined, ok: t('adm.photoDelete'), cancel: t('common.cancel'), danger: true }))
      resolve(it, r, true);
  }
  function look(r: ReportItem) {
    if (r.target === 'comment') sheets.comments(r.where.kind as 'post' | 'event', r.where.id, r.text);
    else if (r.target === 'event') sheets.event(r.id);
    else if (r.target === 'user') sheets.person(r.id);
    else if (r.target === 'photo' && r.where.kind === 'gallery') // a Gallery post of no event: the photo itself, full screen
      sheets.photos([{ id: r.id, url: r.text.replace(/\.t\.webp$/, '.webp'), thumb: r.text, w: 0, h: 0, blur: '', canDelete: false, by: null, mine: true }], 0);
    else if (r.target === 'photo') sheets.event(r.where.id);
    else if (r.target === 'post') sheets.comments('post', r.id, r.text.split(' · ')[0]);
    else if (r.target === 'ask') sheets.forum(r.id);
    else if (r.target === 'tgc' && r.where.link) openLink(r.where.link);
    else if (r.target === 'fpost' && r.where.msg) openLink(`https://t.me/KBTUappForum/${r.where.msg}`);
  }
  function tgcMenu(e: MouseEvent, it: InboxItem, r: ReportItem) {
    menu(e.currentTarget as Element, [
      ...RULES.map((k): MenuItem => ({ label: t(`tgc.rule.${k}`), checked: ruleOf(r) === k, onselect: () => (rules[r.id] = k) })),
      { label: t('adm.abuse'), destructive: true, onselect: async () => {
        if (await sheets.ask({ title: t('adm.abuseAsk'), text: t('adm.abuseText'), ok: t('adm.abuse'), cancel: t('common.cancel'), danger: true })) resolve(it, r, false, true);
      } },
    ]);
  }

  // ---- club applications: Decline asks for the reason the applicant reads ----
  let refusing = $state<string | null>(null), why = $state('');  // the card's key (club and ✓ requests alike)
  let opened = $state<number | null>(null);

  // ---- the forum channel: the owner alone reveals an anonymous author, each look audited ----
  async function reveal(id: number) {
    if (!(await sheets.ask({ title: t('fc.revealAsk'), text: t('fc.revealText'), ok: t('fc.reveal'), cancel: t('common.cancel') }))) return;
    try { const who = await api.revealChannelPost(id); say(t('fc.wrote', { name: who.name }), 'locked_3d'); } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function sendAgain(it: InboxItem, id: number) {
    // a lost send may be in the comments already (the bot can't tell): sent again only after a look there
    if (!(await sheets.ask({ title: t('fcr.againAsk'), text: t('fcr.againText'), ok: t('fcr.again'), cancel: t('common.cancel') }))) return;
    void decide(it, t('adm.act.fchan_reply_release'), undefined, () => api.channelReplyMod(id, true, true));
  }

  // what a decided card was about, after its verdict on the slim line
  const what = (it: InboxItem): string => it.kind === 'report' ? it.data.text : it.kind === 'capp' ? it.data.name : it.kind === 'opath' ? it.data.org.name : it.kind === 'chat' ? it.data.title
    : it.kind === 'claim' ? it.data.name : it.data.body;
  const tagOf = (it: InboxItem): string =>
    it.kind === 'report' ? t(`adm.rep.${it.data.target}`) : it.kind === 'capp' ? t('adm.cappTag') : it.kind === 'opath' ? t('adm.k.opath') : it.kind === 'fpost' ? t('adm.rep.fpost')
      : it.kind === 'freply' ? t('adm.k.freply') : it.kind === 'chat' ? t('adm.k.chat') : t('adm.k.claim');
  function more(it: InboxItem): MenuItem[] {
    if (it.kind === 'capp' && it.data.applicant?.username) { const u = it.data.applicant.username; return [{ label: t('adm.cappWrite'), onselect: () => openLink('https://t.me/' + u) }]; }
    if (it.kind === 'fpost' && owner && it.data.anon) { const id = it.data.id; return [{ label: t('fc.reveal'), onselect: () => reveal(id) }]; }
    if (it.kind === 'freply' && owner && it.data.anon) { const id = it.data.post; return [{ label: t('fc.reveal'), onselect: () => reveal(id) }]; }
    return [];
  }
</script>

{#snippet head(it: InboxItem, items: MenuItem[], onmore?: (e: MouseEvent) => void)}
  <div class="hd">
    <!-- already hidden: the kind in red with the card's red edge (one tag, so the kind reads whole at 375) -->
    <span class="kt" title={it.hidden ? t('adm.k.hidden') : undefined}><Tag tone={it.hidden ? 'danger' : 'neutral'}>{tagOf(it)}</Tag></span>
    <span class="age">{it.at ? ago(it.at) : ''}</span>
    {#if onmore || items.length}<IconButton icon={Ellipsis} label={t('common.more')} kind="plain" size="s" onclick={(e) => (onmore ? onmore(e) : menu(e.currentTarget as Element, items))} />{/if}
  </div>
{/snippet}

{#snippet two(main: string, onmain: () => void, other: string, onother: () => void)}
  <div class="btns"><Button kind="gray" size="m" onclick={onother}>{other}</Button><Button kind="filled" size="m" full onclick={onmain}>{main}</Button></div>
{/snippet}

{#if waiting || Object.keys(handled).length}
  <Section title={t('adm.queue')} count={waiting}>
    <div class="list stagger">
      {#each list as it (it.key)}
        {@const h = handled[it.key]}
        {#if h}
          {@const u = undoOf(h.target)}
          <div class="slim" in:fold>
            <Group>
              {#if u}
                <Row dense title={h.text} subtitle={what(it) || undefined}>
                  {#snippet lead()}<span class="ok"><CircleCheck size={22} /></span>{/snippet}
                  {#snippet trailing()}<Button kind="tinted" size="s" onclick={() => undo(u)}>{t('adm.undo')}</Button>{/snippet}
                </Row>
              {:else}
                <Row dense title={h.text} subtitle={what(it) || undefined}>{#snippet lead()}<span class="ok"><CircleCheck size={22} /></span>{/snippet}</Row>
              {/if}
            </Group>
          </div>
        {:else if it.kind === 'report'}
          {@const r = it.data}
          <div class="card" class:hid={it.hidden} out:fold>
            {@render head(it, [], r.target === 'tgc' ? (e) => tgcMenu(e, it, r) : undefined)}
            <button class="body" onclick={() => look(r)}>
              {#if r.target === 'photo'}<img class="ph" src={r.text} alt="" />{:else}<b class="clamp-3 selectable">{r.text}</b>{/if}
              <i>{r.target === 'tgc'
                ? [r.ai ? t(`adm.tgcAi.${r.ai}`) : '', whoReported(r), t('adm.ruleNow', { rule: t(`tgc.rule.${ruleOf(r)}`) })].filter(Boolean).join(' · ')
                : `${reasons(r)}${r.count > 1 ? ' · ' + tn('adm.reports', r.count) : ''}`}</i>
            </button>
            {#each r.notes ?? [] as n, i (i)}<p class="note selectable">{n.note}</p>{/each}
            {#if r.target === 'tgc' && r.removed}{@render two(t('adm.tgcConfirm'), () => resolve(it, r, true), t('adm.tgcRestore'), () => resolve(it, r, false))}
            {:else if r.target === 'photo'}{@render two(t('adm.photoDelete'), () => dropPhoto(it, r), t('adm.photoBack'), () => resolve(it, r, false))}
            {:else}{@render two(t('adm.takeDown'), () => resolve(it, r, true), t('adm.keep'), () => resolve(it, r, false))}{/if}
          </div>
        {:else if it.kind === 'capp'}
          {@const a = it.data}
          <div class="card" class:hid={it.hidden} out:fold>
            {@render head(it, more(it))}
            <button class="who" aria-expanded={opened === a.id} onclick={() => { haptic.select(); opened = opened === a.id ? null : a.id; }}>
              <OrgLogo org={{ id: 0, slug: '', name: a.name, short: a.short, emoji: a.emoji, cover: a.cover, kind: 'club', official: false }} size={44} />
              <span class="tx"><b>{a.name}</b><i>{a.applicant ? withNick(a.applicant.fullName, a.applicant.person) : '—'}{a.applicant?.course ? ' · ' + t('person.course', { n: a.applicant.course }) : ''}{a.applicant?.school ? ' · ' + schoolShort(a.applicant.school) : ''}</i></span>
              <span class="turn"><ChevronDown size={18} /></span>
            </button>
            {#if opened === a.id}
              <div class="cb" transition:fold>
                <p class="selectable">{a.description}</p>
                {#if a.why}<p class="selectable"><b>{t('adm.cappWhy')}</b> {a.why}</p>{/if}
                {#each a.links as l (l)}<Button kind="plain" size="s" onclick={() => openLink(l)}>{l.replace('https://', '')}</Button>{/each}
              </div>
            {/if}
            {#if refusing === it.key}
              <div class="cb" transition:fold>
                <Field label={t('adm.cappReason')} bind:value={why} multiline rows={2} maxlength={300} />
                <div class="btns"><Button kind="gray" size="m" full onclick={() => (refusing = null)}>{t('common.cancel')}</Button>
                  <Button kind="filled" size="m" full destructive disabled={why.trim().length < 3}
                    onclick={() => { const w = why.trim(); refusing = null; void decide(it, t('adm.act.capp_no'), `capp:${a.id}`, () => api.decideClubApplication(a.id, false, w)); }}>{t('adm.cappRefuse')}</Button></div>
              </div>
            {:else}
              {@render two(t('adm.cappApprove'), () => decide(it, t('adm.act.capp_yes'), undefined, () => api.decideClubApplication(a.id, true)), t('adm.cappRefuse'), () => { refusing = it.key; why = ''; })}
            {/if}
          </div>
        {:else if it.kind === 'opath'}
          {@const r = it.data}
          <div class="card" out:fold>
            {@render head(it, [])}
            <button class="who" onclick={() => sheets.club(r.org.id)}>
              <OrgLogo org={r.org} size={44} />
              <span class="tx"><b>{nameOf(r.org)}</b><i>{tn('studio.members', r.members)}</i></span>
            </button>
            {#if refusing === it.key}
              <div class="cb" transition:fold>
                <Field label={t('adm.opathReason')} bind:value={why} multiline rows={2} maxlength={300} />
                <div class="btns"><Button kind="gray" size="m" full onclick={() => (refusing = null)}>{t('common.cancel')}</Button>
                  <Button kind="filled" size="m" full destructive disabled={why.trim().length < 3}
                    onclick={() => { const w = why.trim(); refusing = null; void decide(it, t('adm.act.opath_no'), `opath:${r.id}`, () => api.decideOfficial(r.id, false, w)); }}>{t('adm.cappRefuse')}</Button></div>
              </div>
            {:else}
              {@render two(t('adm.opathApprove'), () => decide(it, t('adm.act.opath_yes'), `opath:${r.id}`, () => api.decideOfficial(r.id, true)), t('adm.cappRefuse'), () => { refusing = it.key; why = ''; })}
            {/if}
          </div>
        {:else if it.kind === 'fpost'}
          {@const p = it.data as ChannelModPost}
          <div class="card" class:hid={it.hidden} out:fold>
            {@render head(it, more(it))}
            <ForumWho anon={p.anon} nick={p.nick} author={p.author} />
            {#if p.why}<i class="meta">{whyLine(p.why, p.aiWhy)}</i>{/if}
            <p class="text selectable">{p.body}</p>
            {#if p.own}<i class="meta">{t('fc.ownPost')}</i>
            {:else}{@render two(t('fc.release'), () => decide(it, t('adm.act.fchan_release'), undefined, () => api.channelModDecide(p.id, true)),
              t('fc.takeDown'), () => decide(it, t('adm.act.fchan_hide'), `fchan:${p.id}`, () => api.channelModDecide(p.id, false)))}{/if}
          </div>
        {:else if it.kind === 'freply'}
          {@const r = it.data}
          <div class="card" class:hid={it.hidden} out:fold>
            {@render head(it, more(it))}
            <ForumWho anon={r.anon} nick={r.nick} />
            {#if r.why || r.reports}<i class="meta">{[whyLine(r.why, r.aiWhy, true), r.reports ? t('fcr.reports', { n: r.reports }) : ''].filter(Boolean).join(' · ')}</i>{/if}
            <p class="quote">{r.postBody}</p>
            <p class="text selectable">{r.body}</p>
            {#if it.hidden && r.why === 'lost'}
              {@render two(t('fcr.again'), () => sendAgain(it, r.id), t('fc.takeDown'), () => decide(it, t('adm.act.fchan_reply_hide'), `fchanr:${r.id}`, () => api.channelReplyMod(r.id, false)))}
            {:else if it.hidden}
              {@render two(t('fc.release'), () => decide(it, t('adm.act.fchan_reply_release'), undefined, () => api.channelReplyMod(r.id, true)),
                t('fc.takeDown'), () => decide(it, t('adm.act.fchan_reply_hide'), `fchanr:${r.id}`, () => api.channelReplyMod(r.id, false)))}
            {:else}
              {@render two(t('fc.takeDown'), () => decide(it, t('adm.act.fchan_reply_hide'), `fchanr:${r.id}`, () => api.channelReplyMod(r.id, false)),
                t('fcr.keep'), () => decide(it, t('adm.act.fchan_reply_keep'), undefined, () => api.channelReplyMod(r.id, true)))}
            {/if}
          </div>
        {:else if it.kind === 'chat'}
          {@const c = it.data}
          <div class="card" class:hid={it.hidden} out:fold>
            {@render head(it, [])}
            <!-- the link itself, so a look tells a real chat from a stray one -->
            <button class="who" onclick={() => openLink(c.url)}>
              <ChatAvatar title={c.title} photo={c.photo} kind={c.kind} size={44} />
              <span class="tx"><b>{c.title}</b><i>{c.url.replace('https://', '')} · {t(`chats.${c.kind}`)}{c.members ? ' · ' + c.members : ''}{c.org ? ' · ' + nameOf(c.org) : ''}</i></span>
              <span class="turn"><ArrowUpRight size={18} /></span>
            </button>
            {@render two(t('adm.chatApprove'), () => decide(it, t('adm.act.chat_approve'), undefined, () => api.approveChat(c.id)),
              t('adm.chatDecline'), () => decide(it, t('adm.act.chat_decline'), `chat:${c.id}`, () => api.deleteChat(c.id)))}
          </div>
        {:else if it.kind === 'claim'}
          {@const r = it.data}
          <div class="card" class:hid={it.hidden} out:fold>
            {@render head(it, [])}
            <div class="who"><Avatar person={r.person} size={44} />
              <span class="tx"><b>{r.name}</b><i>{t('ro.listed', { name: r.sheetName ?? '—' })}</i>
                <i>{nameOf(r.org)} · {r.title || roleName(r.role, null)}{r.dept ? ' · ' + r.dept : ''}</i></span></div>
            {@render two(t('ro.confirm'), () => decide(it, t('adm.act.roster_ok'), undefined, () => api.rosterDecide(r.id, true)),
              t('ro.decline'), () => decide(it, t('adm.act.roster_no'), undefined, () => api.rosterDecide(r.id, false)))}
          </div>
        {/if}
      {/each}
    </div>
  </Section>
{:else if data.inbox}
  <Group><Row title={t('adm.nothing')}>{#snippet lead()}<span class="ok"><CircleCheck size={24} /></span>{/snippet}</Row></Group>
{/if}

{#if done.length}
  <div class="done">
    <Group><Row title={t('adm.doneList')} value={String(done.length)} accessory="disclosure" open={doneOpen} onclick={() => { haptic.select(); doneOpen = !doneOpen; }} /></Group>
    {#if doneOpen}
      <div transition:fold>
        <Group>
          {#each done as d (d.id)}
            {@const title = d.kind === 'photo' ? t(`adm.act.${d.action}` as Key) : d.text}
            {@const sub = `${d.kind === 'photo' ? '' : t(`adm.act.${d.action}` as Key) + ' · '}${d.mine ? t('adm.you') : d.by ?? '—'} · ${ago(d.at)}${d.undone ? ' · ' + t('adm.undone') : ''}`}
            {#if d.undo && (d.mine || admin)}
              <Row dense {title} subtitle={sub}>
                {#snippet trailing()}<Button kind="tinted" size="s" onclick={() => undo(d)}>{t('adm.undo')}</Button>{/snippet}
              </Row>
            {:else}<Row dense {title} subtitle={sub} />{/if}
          {/each}
        </Group>
      </div>
    {/if}
  </div>
{/if}

<style>
  .list { display: flex; flex-direction: column; gap: var(--s-3); }
  .card { position: relative; display: flex; flex-direction: column; gap: var(--s-3); padding: 14px var(--s-4) var(--s-4); border-radius: var(--r-group);
    background: var(--surface); box-shadow: var(--shadow-card); }
  /* already out of sight, a person waiting for the verdict: a red edge reads before the words */
  .card.hid::before { content: ''; position: absolute; left: 0; top: var(--s-4); bottom: var(--s-4); width: 3px; border-radius: 0 var(--r-full) var(--r-full) 0; background: var(--danger); }
  .hd { display: flex; flex-wrap: nowrap; align-items: center; gap: 6px; min-height: 36px; margin-right: -8px; }
  /* the kind gives way first (an ellipsis), so the head stays one line at 320 */
  .kt { flex: 0 1 auto; min-width: 0; display: flex; overflow: hidden; }
  .kt :global(.chip) { flex: 0 1 auto; min-width: 0; display: block; line-height: 28px; overflow: hidden; text-overflow: ellipsis; }
  .age { flex: 1 0 auto; text-align: right; font: 500 var(--fs-sub)/1 var(--font-text); color: var(--text-3); white-space: nowrap; }
  .body { display: flex; flex-direction: column; gap: 4px; text-align: left; }
  .body b, .text { font: 600 var(--fs-body)/1.4 var(--font-text); overflow-wrap: anywhere; white-space: pre-line; }
  .body i, .meta { font: 450 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-3); }
  .ph { width: 96px; height: 96px; border-radius: var(--r-m); object-fit: cover; background: var(--surface-2); }
  .note { padding: var(--s-2) var(--s-3); border-radius: var(--r-m); background: var(--fill); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-2); overflow-wrap: anywhere; white-space: pre-wrap; }
  .quote { padding-left: var(--s-3); box-shadow: inset 2px 0 0 var(--line); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .btns { display: flex; gap: var(--s-2); margin-top: 2px; }
  .btns > :global(.btn) { flex: none; }
  .btns > :global(.btn.full) { flex: 1; width: auto; min-width: 0; } /* the main one takes what the other leaves */
  .who { display: flex; align-items: center; gap: var(--s-3); text-align: left; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 600 var(--fs-body)/1.3 var(--font-text); overflow-wrap: anywhere; }
  .tx i { font: 450 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-3); overflow-wrap: anywhere; }
  .turn { flex: none; display: flex; color: var(--text-3); opacity: 0.6; transition: transform var(--t-base) var(--ease); }
  [aria-expanded='true'] .turn { transform: rotate(180deg); }
  .cb { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); }
  .cb > :global(.fld) { align-self: stretch; }
  .cb > .btns { align-self: stretch; }
  .cb p { font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; }
  .ok { display: inline-flex; color: var(--success); }
  .slim { animation: settle 260ms var(--ease-spring); }
  @keyframes settle { from { opacity: 0; transform: scale(0.98); } }
  .done { display: flex; flex-direction: column; gap: var(--s-3); }
</style>
