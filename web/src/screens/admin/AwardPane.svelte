<script lang="ts">
  // Admin → Awards → one award (pushed from the right; owner + review Nov 3): its medal large, the variant picked here
  // (Initiation: Performer / Volunteer / Guest, which sets what everything below gives), then Scan (the camera stays
  // open: each card QR is one grant, the person's face with a tick, this run's people below, each undoable) and Link (up
  // to N people for some days; sent as the bot's card). Under them its links with who used each, the owner's "everyone
  // checked in", and who has it (a tap: their profile, or take it back).
  import Check from '@lucide/svelte/icons/check';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { api, ApiErr, type BadgeSession, type GrantItem, type GrantLink } from '../../lib/api';
  import { codesOf, manualMedal, manualName, manualTitle, variantHow, type Manual } from '../../lib/awards';
  import { say, overlays, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn, type Key } from '../../lib/i18n/index.svelte';
  import { haptic, scanQr, shareCard } from '../../lib/tg';
  import { dayMonth, nowTs } from '../../lib/time';
  import { menu } from '../../ui/menu';
  import { fold } from '../../ui/fold';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Medal from '../../ui/Medal.svelte';
  import QrCam from '../../ui/QrCam.svelte';
  import Segmented from '../../ui/Segmented.svelte';

  type Code = GrantItem['code'];
  let { overlay, award: a, onchange }: { overlay: Overlay; award: Manual; onchange?: () => void } = $props();
  const owner = $derived(!!session.me?.founder);
  const fail = () => { haptic.error(); say(t('common.error'), 'warning_3d'); };
  // svelte-ignore state_referenced_locally
  let code = $state<Code>(a.variants?.[0].code ?? (a.code as Code));
  const art = $derived(a.variants?.find((v) => v.code === code)?.emoji ?? a.emoji);
  const how = $derived(a.variants ? variantHow(a.code, code) : t(`ach.${a.code}.how` as Key));
  let mode = $state<'scan' | 'link' | null>(null);

  // ---- what the page lists: this award's links, who has it, the owner's check-ins (one request each, as it opens)
  let links = $state<GrantLink[]>([]), holders = $state<GrantItem[] | null>(null), checkins = $state<BadgeSession[]>([]);
  const mine = $derived(links.filter((l) => codesOf(a).includes(l.code)));
  const loadLinks = () => api.grantLinks().then((l) => (links = l)).catch(() => {});
  const loadHolders = () => api.awardPeople(a.code).then((l) => (holders = l)).catch(() => (holders = []));
  void loadLinks(); void loadHolders();
  $effect(() => { if (owner && a.code !== 'bugs') api.badgeSessions().then((l) => (checkins = l)).catch(() => {}); });
  const changed = () => { void loadHolders(); onchange?.(); };

  // ---- the scanner: our camera on the page; Telegram's popup only when ours is refused or missing
  let live = $state<'off' | 'on' | 'failed'>('off');
  let run = '', ran = $state<GrantItem[]>([]), hit = $state<GrantItem | null>(null), granting = $state(false);
  let hitTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => () => clearTimeout(hitTimer));
  const seen = new Map<string, number>(); // a card left in view isn't "already has it" over and over: QR text -> grant id
  // the camera rests while a grant runs and while anything (a menu, a confirm) covers this page
  const paused = $derived(mode !== 'scan' || granting || overlays[overlays.length - 1]?.id !== overlay.id);
  function scanned(text: string) {
    if (seen.has(text)) return;
    granting = true;
    api.grantScan(text, code, run).then((g) => {
      seen.set(text, g.id); ran = [g, ...ran]; hit = g; haptic.ok();
      clearTimeout(hitTimer); hitTimer = setTimeout(() => (hit = null), 1100);
    }).catch((e) => {
      haptic.error();
      if (e instanceof ApiErr && e.code === 'conflict') seen.set(text, 0);
      say(e instanceof ApiErr && e.code === 'conflict' ? t('give.already') : t('give.notFound'), 'pleading_face_3d');
    }).finally(() => (granting = false));
  }
  function popup() {
    if (!scanQr(t('aw.aim'), (text) => { scanned(text); return false; })) say(t('give.phone'), 'pleading_face_3d');
  }
  function scan() {
    haptic.tap();
    run = Math.random().toString(36).slice(2, 10); ran = []; seen.clear();
    if (!('mediaDevices' in navigator)) { popup(); return; }
    mode = 'scan'; live = 'off';
  }
  $effect(() => { if (live === 'failed' && mode === 'scan') { mode = null; popup(); } });
  function stop() { haptic.tap(); mode = null; if (ran.length) changed(); }
  function unscan(g: GrantItem) {
    ran = ran.filter((x) => x.id !== g.id);
    for (const [k, id] of seen) if (id === g.id) seen.delete(k);
    api.ungrant(g.id).then(() => haptic.soft()).catch(fail);
  }
  async function unscanAll() {
    if (!(await sheets.ask({ title: t('aw.undoAllAsk', { n: ran.length }), ok: t('aw.undoAll'), cancel: t('common.cancel'), danger: true }))) return;
    const was = ran;
    ran = []; seen.clear();
    api.undoBatch('s_' + run).then(() => { haptic.soft(); say(t('say.ungranted'), 'waving_hand_3d_default'); }).catch(() => { ran = was; fail(); });
  }

  // ---- a link: up to N people (0: no cap), for some days; made when the card goes (the server's /api/share)
  let uses = $state(1), days = $state(7), sending = $state(false);
  async function send() {
    sending = true; haptic.tap();
    try {
      if (await shareCard({ kind: 'gl', id: '0', code, uses: uses || null, days }, 'https://t.me/KBTUappBot', manualName(code))) { haptic.ok(); say(t('give.sent'), 'party_popper_3d'); mode = null; }
      void loadLinks();
    } catch { fail(); } finally { sending = false; }
  }
  const liveLink = (l: GrantLink) => l.until > nowTs() && (l.max === null || l.people.length < l.max);
  let openLink = $state<string | null>(null);
  async function revoke(l: GrantLink) {
    if (!(await sheets.ask({ title: t('aw.revokeAsk'), text: t('aw.revokeText'), ok: t('aw.revoke'), cancel: t('common.cancel'), danger: true }))) return;
    const was = l.until;
    l.until = nowTs();
    api.revokeLink(l.token).then(() => { haptic.soft(); say(t('aw.revoked'), 'locked_3d'); }).catch(() => { l.until = was; fail(); });
  }
  async function takeOne(l: GrantLink, g: GrantItem) {
    if (!(await sheets.ask({ title: t('adm.takeBackAsk', { award: manualName(g.code), name: g.person.name }), ok: t('adm.takeBack'), cancel: t('common.cancel'), danger: true }))) return;
    const was = l.people;
    l.people = was.filter((x) => x.id !== g.id);
    api.ungrant(g.id).then(() => { haptic.soft(); say(t('adm.takenBack'), 'waving_hand_3d_default'); changed(); }).catch(() => { l.people = was; fail(); });
  }
  async function takeAll(l: GrantLink) {
    if (!(await sheets.ask({ title: t('aw.takeAllAsk', { award: manualName(l.code), n: l.people.length }), ok: t('aw.takeAll'), cancel: t('common.cancel'), danger: true }))) return;
    const was = l.people;
    l.people = [];
    api.undoBatch('l_' + l.token).then(() => { haptic.soft(); say(t('adm.takenBack'), 'waving_hand_3d_default'); changed(); }).catch(() => { l.people = was; fail(); });
  }

  // ---- who has it: a tap, their profile or the award back (all of its grants)
  function holder(e: MouseEvent, g: GrantItem) {
    menu(e.currentTarget as Element, [
      { label: t('tab.profile'), onselect: () => sheets.person(g.person.id) },
      { label: t('adm.takeBack'), destructive: true, onselect: async () => {
        if (!(await sheets.ask({ title: t('adm.takeBackAsk', { award: manualName(g.code), name: g.person.name }), ok: t('adm.takeBack'), cancel: t('common.cancel'), danger: true }))) return;
        const was = holders;
        holders = (holders ?? []).filter((x) => x.id !== g.id);
        api.takeBackGrant(g.person.id, g.code).then(() => { haptic.soft(); say(t('adm.takenBack'), 'waving_hand_3d_default'); onchange?.(); }).catch(() => { holders = was; fail(); });
      } },
    ]);
  }

  // ---- everyone counted at a check-in (the owner), one Undo for all
  let bulk = $state<{ n: number; batch: string; title: string; code: Code } | null>(null);
  async function giveAll(s: BadgeSession) {
    if (!(await sheets.ask({ title: t('scr.grantAsk', { variant: manualName(code) }), text: t('scr.grantText', { n: s.done }), ok: t('scr.grant'), cancel: t('scr.keep') }))) return;
    try { const r = await api.screenGrant(s.id, code); bulk = { n: r.granted, batch: r.batch, title: s.title, code }; haptic.ok(); say(t('scr.granted', { n: r.granted }), 'party_popper_3d'); changed(); }
    catch { fail(); }
  }
  async function undoAll() {
    const b = bulk!;
    if (!(await sheets.ask({ title: t('aw.takeAllAsk', { award: manualName(b.code), n: b.n }), ok: t('aw.takeAll'), cancel: t('common.cancel'), danger: true }))) return;
    bulk = null;
    api.undoBatch(b.batch).then(() => { haptic.soft(); say(t('adm.takenBack'), 'waving_hand_3d_default'); changed(); }).catch(() => { bulk = b; fail(); });
  }
</script>

<Pane {overlay} title={manualTitle(a)}>
  {#if mode === 'scan'}
    <!-- scanning: the camera alone, what is being given above it -->
    <div class="scan">
      <Group><Row dense title={manualName(code)}>{#snippet lead()}<Medal a={manualMedal(a.code, art)} size={32} />{/snippet}</Row></Group>
      <div class="cam">
        <QrCam bind:live {paused} onscan={scanned} />
        <span class="aim" class:hit={!!hit}></span>
        {#if hit}
          {#key hit.id}
            <div class="got glass glass-pill theme-dark">
              <span class="face"><Avatar person={hit.person} size={56} tappable={false} /><span class="tick"><Check size={16} strokeWidth={3} /></span></span>
              <b class="ellipsis">{hit.person.name}</b>
            </div>
          {/key}
        {:else}<p>{t('aw.aim')}</p>{/if}
      </div>
      {#if ran.length}
        <div class="strip">
          {#each ran as g (g.id)}
            <button class="ran" onclick={(e) => menu(e.currentTarget, [{ label: t('aw.undo'), destructive: true, onselect: () => unscan(g) }])}>
              <Avatar person={g.person} size={48} tappable={false} /><span class="ellipsis">{g.person.name.split(' ')[0]}</span>
            </button>
          {/each}
        </div>
      {/if}
      <div class="foot btns">
        {#if ran.length > 1}<Button kind="gray" size="l" full onclick={unscanAll}>{t('aw.undoAll')}</Button>{/if}
        <Button kind="filled" size="l" full onclick={stop}>{t('aw.done')}</Button>
      </div>
    </div>
  {:else}
    <div class="page stagger">
      <div class="hero">
        <span class="glow" aria-hidden="true"></span>
        {#key art}<span class="medal"><Medal a={manualMedal(a.code, art)} size={112} /></span>{/key}
        <p class="how">{how}</p>
      </div>

      <div class="acts">
        {#if a.variants}
          <Segmented bind:value={code} label={t(`ach.${a.code}.name` as Key)} onchange={() => haptic.select()}
            items={a.variants.map((v) => ({ value: v.code, label: manualName(v.code, true) }))} />
        {/if}
        <div class="btns">
          {#if a.scan}<Button kind="filled" full onclick={scan}>{#snippet icon()}<ScanLine size={18} />{/snippet}{t('aw.scan')}</Button>{/if}
          <Button kind={a.scan ? 'tinted' : 'filled'} full on={mode === 'link'} onclick={() => { haptic.select(); mode = mode === 'link' ? null : 'link'; }}>{#snippet icon()}<TelegramMark size={17} />{/snippet}{t('aw.link')}</Button>
        </div>
        {#if mode === 'link'}
          <div class="form" transition:fold>
            <span class="lbl">{t('aw.people')}</span>
            <Segmented bind:value={uses} label={t('aw.people')} items={[1, 10, 50, 0].map((n) => ({ value: n, label: n ? String(n) : t('aw.noCap') }))} />
            <span class="lbl">{t('aw.days')}</span>
            <Segmented bind:value={days} label={t('aw.days')} items={[1, 3, 7, 14].map((n) => ({ value: n, label: t('aw.nd', { n }) }))} />
            <Button kind="filled" full loading={sending} onclick={send}>{t('aw.send')}</Button>
          </div>
        {/if}
      </div>

      {#if mine.length}
        <Group caption={t('aw.links')}>
          {#each mine as l (l.token)}
            {@const on = liveLink(l)}
            <Row dense title={l.max === null ? t('aw.usedAny', { n: l.people.length }) : t('aw.used', { n: l.people.length, max: l.max })}
              subtitle={(a.variants ? manualName(l.code, true) + ' · ' : '') + (on ? t('aw.until', { date: dayMonth(l.until) }) : t('aw.ended'))}
              accessory="disclosure" open={openLink === l.token} disabled={!on && !l.people.length}
              onclick={() => { haptic.select(); openLink = openLink === l.token ? null : l.token; }} />
            {#if openLink === l.token}
              {#each l.people as g (g.id)}
                <Row dense title={g.person.name} onclick={(e) => menu(e.currentTarget as Element, [{ label: t('adm.takeBack'), destructive: true, onselect: () => takeOne(l, g) }])}>
                  {#snippet lead()}<Avatar person={g.person} size={32} tappable={false} />{/snippet}
                </Row>
              {/each}
              {#if l.people.length > 1}<Row dense tone="destructive" title={t('aw.takeAll')} onclick={() => takeAll(l)} />{/if}
              {#if on}<Row dense tone="destructive" title={t('aw.revoke')} onclick={() => revoke(l)} />{/if}
            {/if}
          {/each}
        </Group>
      {/if}

      {#if owner && checkins.length}
        <Group caption={t('bdg.sessions')}>
          {#each checkins as s (s.id)}
            <Row dense tone="action" title={s.title} subtitle={`${dayMonth(s.at)} · ${t('bdg.counted', { n: s.done })}`} disabled={!s.done} onclick={() => giveAll(s)} />
          {/each}
          {#if bulk && bulk.code === code}<Row dense tone="destructive" title={t('aw.undo')} subtitle={t('aw.bulk', { n: bulk.n, title: bulk.title })} onclick={undoAll} />{/if}
        </Group>
      {/if}

      {#if holders?.length}
        <Group caption={`${t('aw.holders')} · ${tn('aw.n', holders.length)}`}>
          {#each holders as g (g.id)}
            <Row dense title={g.person.name} subtitle={(a.variants ? manualName(g.code, true) + ' · ' : '') + dayMonth(g.at)} onclick={(e) => holder(e, g)}>
              {#snippet lead()}<Avatar person={g.person} size={32} tappable={false} />{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}
    </div>
  {/if}
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-6); }
  /* the medal on a soft light of its own, floating slowly (felt more than seen: 3 px) */
  .hero { position: relative; display: flex; flex-direction: column; align-items: center; gap: var(--s-4); padding: var(--s-2) var(--s-4) 0; text-align: center; }
  .glow { position: absolute; top: -12px; left: 50%; width: 220px; height: 160px; translate: -50% 0; pointer-events: none;
    background: radial-gradient(closest-side, var(--accent-soft), transparent); }
  .medal { position: relative; display: inline-flex; animation: float 6s ease-in-out infinite, pop 520ms var(--ease-spring); }
  @keyframes float { 50% { transform: translate3d(0, -3px, 0); } }
  @keyframes pop { from { scale: 0.85; opacity: 0; } }
  :global(html.lowfx) .medal { animation: none; }
  .how { position: relative; max-width: 300px; font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); }
  .btns { display: flex; gap: var(--s-2); }
  .acts { display: flex; flex-direction: column; gap: var(--s-3); }
  .form { display: flex; flex-direction: column; gap: var(--s-2); }
  .lbl { margin: 6px var(--s-4) 0; font: 450 var(--fs-sub)/1.2 var(--font-text); letter-spacing: 0.02em; text-transform: uppercase; color: var(--text-3); }
  .form > :global(.btn) { margin-top: var(--s-2); }

  /* the scanner: the camera, a tick with the person's face and name on each hit */
  .scan { display: flex; flex-direction: column; gap: var(--s-4); }
  .cam { position: relative; aspect-ratio: 1; max-height: 52vh; border-radius: var(--r-group); overflow: hidden; background: black; }
  .cam p { position: absolute; left: 12px; right: 12px; bottom: 14px; text-align: center; color: white; font: 600 var(--fs-body)/1.3 var(--font-text); text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6); }
  .aim { position: absolute; inset: 18%; border-radius: var(--r-l); box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.75), 0 0 0 999px rgba(0, 0, 0, 0.28); pointer-events: none; transition: box-shadow .2s; }
  .aim.hit { box-shadow: 0 0 0 4px var(--success), 0 0 0 999px rgba(0, 0, 0, 0.5); animation: pulse 420ms var(--ease-spring); }
  @keyframes pulse { 40% { transform: scale(1.04); } }
  .got { position: absolute; left: 50%; top: 50%; translate: -50% -50%; display: flex; flex-direction: column; align-items: center; gap: var(--s-2); max-width: 72%;
    padding: var(--s-4) var(--s-5); border-radius: var(--r-l); color: white; font: 700 var(--fs-card)/1.2 var(--font-text); animation: got 360ms var(--ease-spring); }
  .got b { position: relative; max-width: 100%; }
  .face { position: relative; display: inline-flex; }
  .tick { position: absolute; right: -4px; bottom: -4px; display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%;
    background: var(--success); color: white; box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.5); animation: got 420ms 120ms var(--ease-spring) backwards; }
  @keyframes got { from { opacity: 0; scale: 0.6; } }
  .strip { display: flex; gap: var(--s-3); overflow-x: auto; padding: 4px 2px; scrollbar-width: none; }
  .ran { flex: none; width: 60px; display: flex; flex-direction: column; align-items: center; gap: 4px; font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-2); }
  .ran span { max-width: 100%; }
  .foot { position: sticky; bottom: calc(var(--safe-bottom) + 12px); }
</style>
