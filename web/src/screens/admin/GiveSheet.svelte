<script lang="ts">
  import { fold } from '../../ui/fold';
  // The creator's own awards (PLAN "Creator awards"), from the admin panel (owner, Oct 13: not a block of "Give"
  // buttons on everyone's Awards page). The face-to-face ones are a scanner that stays open, one grant a badge QR (the
  // same badge again only after 4 s: the camera keeps seeing it); "Bug hunter" is earned in a chat, so it goes there
  // as a one-time link. Each grant is undoable for a minute; "You gave" below, where after that minute one given by
  // mistake is taken back, the whole award (owner, Oct 14: only from the admin panel, never from a person's profile).
  import { api, ApiErr, type GrantItem } from '../../lib/api';
  import { say, overlays, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, scanQr, shareCard } from '../../lib/tg';
  import { ago, nowTs } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import QrCam from '../../ui/QrCam.svelte';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';

  let { overlay }: { overlay: Overlay } = $props();

  const GIVE = [
    { code: 'creator_laugh', emoji: 'face_with_tears_of_joy_3d', link: false },
    { code: 'creator_found', emoji: 'waving_hand_3d_default', link: false },
    { code: 'bugs', emoji: 'lady_beetle_3d', link: true },
  ] as const;
  const name = (code: string) => t(`ach.${code}.name` as 'ach.bugs.name');

  let gave = $state<GrantItem[] | null>(null);
  let showGave = $state(false);
  let tickNow = $state(nowTs());
  api.myGrants().then((l) => (gave = l)).catch(() => {});
  $effect(() => { const i = setInterval(() => (tickNow = nowTs()), 5000); return () => clearInterval(i); });

  // our camera in the sheet (owner, Oct 21: not Telegram's popup); Telegram's only when ours is refused or missing
  let scanning = $state<GrantItem['code'] | null>(null);
  let live = $state<'off' | 'on' | 'failed'>('off');
  let hit = $state(0);
  let granting = $state(false);
  const done = new Set<string>(); // given in this sheet: a badge left in view doesn't come back as "already has it"
  // the camera rests while a grant runs and while another sheet (a confirm) covers this one
  const paused = $derived(!scanning || granting || overlays[overlays.length - 1]?.id !== overlay.id);
  function grant(text: string, code: GrantItem['code']) {
    if (done.has(code + text)) return;
    granting = true;
    api.grantScan(text, code).then((g) => { done.add(code + text); gave = [g, ...(gave ?? [])]; hit++; haptic.ok(); })
      .catch((e) => { haptic.error(); say(e instanceof ApiErr && e.code === 'conflict' ? t('give.already') : t('give.notFound'), 'pleading_face_3d'); })
      .finally(() => (granting = false));
  }
  function popup(code: GrantItem['code']) {
    let last = '', lastAt = 0;
    const ok = scanQr(t('give.scan', { award: name(code) }), (text) => {
      if (text === last && Date.now() - lastAt < 4000) return false;
      last = text; lastAt = Date.now();
      grant(text, code);
      return false;
    });
    if (!ok) say(t('give.phone'), 'pleading_face_3d');
  }
  function scan(code: GrantItem['code']) {
    haptic.select();
    if (scanning === code) { scanning = null; return; }
    if (!('mediaDevices' in navigator)) { popup(code); return; }
    scanning = code; live = 'off';
  }
  $effect(() => { if (live === 'failed' && scanning) { const c = scanning; scanning = null; popup(c); } });
  function send(code: GrantItem['code']) {
    shareCard({ kind: 'gl', id: '0', code }, 'https://t.me/KBTUappBot', name(code))
      .then((sent) => { if (sent) { haptic.ok(); say(t('give.sent'), 'party_popper_3d'); } })
      .catch(() => say(t('common.error'), 'pleading_face_3d'));
  }
  async function takeBack(g: GrantItem) {
    if (!(await sheets.ask({ title: t('adm.takeBackAsk', { award: name(g.code), name: g.person.name }), ok: t('adm.takeBack'), cancel: t('common.cancel'), danger: true }))) return;
    try {
      await api.takeBackGrant(g.person.id, g.code);
      gave = (gave ?? []).filter((x) => x.person.id !== g.person.id || x.code !== g.code);
      haptic.soft(); say(t('adm.takenBack'), 'waving_hand_3d_default');
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function undo(g: GrantItem) {
    try { await api.ungrant(g.id); gave = (gave ?? []).filter((x) => x.id !== g.id); haptic.soft(); say(t('say.ungranted'), 'waving_hand_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} full title={t('give.title')}>
  <div class="tiles">
    {#each GIVE as g (g.code)}
      <button class="tile surface" class:on={scanning === g.code} onclick={() => (g.link ? send(g.code) : scan(g.code))}>
        <Emoji name={g.emoji} size={44} />
        <b>{name(g.code)}</b>
        <i>{t(g.link ? 'give.byLink' : 'give.byQr')}</i>
      </button>
    {/each}
  </div>
  {#if scanning}
    {@const code = scanning}
    <div class="cam" transition:fold>
      <QrCam bind:live {paused} onscan={(v) => grant(v, code)} />
      {#key hit}<span class="aim" class:flash={hit > 0}></span>{/key}
      <p>{t('give.scan', { award: name(code) })}</p>
    </div>
  {/if}
  {#if gave?.length}
    <button class="gv surface" class:open={showGave} onclick={() => (showGave = !showGave)}><span>{t('give.gave', { n: gave.length })}</span><ChevronDown size={18} /></button>
    {#if showGave}
      <div transition:fold>
      {#each gave.slice(0, 50) as g (g.id)}
        <div class="gr"><span class="ellipsis">{g.person.name} · {name(g.code)} · {ago(g.at)}</span>
          {#if tickNow - g.at < 55}<button onclick={() => undo(g)}>{t('give.undo')}</button>
          {:else}<button class="off" onclick={() => takeBack(g)}>{t('adm.takeBack')}</button>{/if}</div>
      {/each}
      </div>
    {/if}
  {/if}
</Sheet>

<style>
  .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .tiles .tile:last-child:nth-child(odd) { grid-column: 1 / -1; }
  .tile { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; padding: 14px; text-align: left; }
  .tile b { font: 650 15px/1.25 var(--font-text); }
  .tile i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .tile.on { box-shadow: 0 0 0 2px var(--accent); }
  .cam { position: relative; margin-top: 12px; aspect-ratio: 1; max-height: 44vh; border-radius: var(--r-l); overflow: hidden; background: #000; }
  .cam p { position: absolute; left: 12px; right: 12px; bottom: 12px; text-align: center; color: #fff; font: 650 14px/1.3 var(--font-text); text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6); }
  .aim { position: absolute; inset: 18%; border-radius: 22px; box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.75), 0 0 0 999px rgba(0, 0, 0, 0.28); pointer-events: none; }
  .aim.flash { box-shadow: 0 0 0 4px var(--success), 0 0 0 999px rgba(0, 0, 0, 0.28); animation: pulse 420ms cubic-bezier(.2, .9, .25, 1.2); }
  @keyframes pulse { from { transform: scale(1.08); } }
  .gv { display: flex; align-items: center; justify-content: space-between; width: 100%; margin-top: 12px; padding: 14px; font: 650 15px/1.2 var(--font-text); }
  .gv :global(svg) { color: var(--text-2); transition: transform .2s; }
  .gv.open :global(svg) { transform: rotate(180deg); }
  .gr { display: flex; align-items: center; gap: 10px; padding: 6px 0; font: 500 13.5px/1.3 var(--font-text); color: var(--text-2); }
  .gr span { flex: 1; min-width: 0; }
  .gr button { flex: none; height: 30px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 13px/1 var(--font-text); }
  .gr button.off { background: var(--danger-soft); color: var(--danger-text); }
</style>
