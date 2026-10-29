<script lang="ts">
  // The organizer's side of /show (server checkin.py): a scan of the laptop's pairing QR (sh_<code>) binds it to my
  // session, and here are the controls the screen itself no longer has: Start, Finish, the list, "disconnect". Anyone
  // who doesn't run a session gets a polite no and the screen stays as it was. Without a code: my sessions.
  import { api, ApiErr, type Id, type ScreenSession } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { downloadFile, haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import MonitorUp from '@lucide/svelte/icons/monitor-up';
  import Play from '@lucide/svelte/icons/play';
  import Square from '@lucide/svelte/icons/square';
  import Download from '@lucide/svelte/icons/download';
  import Unplug from '@lucide/svelte/icons/unplug';

  let { overlay, code }: { overlay: Overlay; code?: string } = $props();
  let list = $state<ScreenSession[] | null>(null);
  let pick = $state(false);   // an unpaired screen and several open sessions: which one
  let note = $state('');      // why there's nothing to do here
  let busy = $state(0);

  const refresh = () => api.screens().then((l) => { if (!pick) list = l; }).catch(() => {});
  async function bind(session?: Id) {
    try {
      const s = await api.bindScreen(code!, session);
      pick = false; haptic.ok(); say(t('scr.paired'), 'sparkles_3d');
      list = [s, ...(await api.screens().catch(() => [])).filter((x) => x.session !== s.session)];
    } catch (e) {
      const m = e instanceof ApiErr ? e.message : '';
      if (m === 'pick') { pick = true; list = (await api.screens().catch(() => [])).filter((x) => !x.ended); return; }
      haptic.error();
      note = m === 'pair' ? t('scr.stale') : m === 'screen' ? t('scr.notYours') : t('common.error');
      list = [];
    }
  }
  $effect(() => {
    if (code) void bind(); else void refresh();
    const id = setInterval(refresh, 4000); // the count goes up while people scan
    return () => clearInterval(id);
  });

  async function act(s: ScreenSession, a: 'start' | 'finish' | 'unpair') {
    if (busy) return;
    if (a === 'finish' && !(await sheets.ask({ title: t('scr.finishAsk'), text: t('scr.finishText'), ok: t('scr.finish'), cancel: t('scr.keep') }))) return;
    if (a === 'unpair' && !(await sheets.ask({ title: t('scr.unpairAsk'), text: t('scr.unpairText'), ok: t('scr.unpair'), cancel: t('scr.keep') }))) return;
    busy = s.session;
    try {
      const n = await api.screenAct(s.session, a);
      list = (list ?? []).map((x) => (x.session === n.session ? n : x)); haptic.ok();
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); } finally { busy = 0; }
  }
  async function csv(s: ScreenSession) {
    try { const l = await api.screenCsv(s.session); downloadFile(location.origin + l.url, l.name); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} title={t('scr.title')}>
  <h2 class="t-h2 hd">{pick ? t('scr.pick') : t('scr.title')}</h2>
  {#if note}
    <p class="t-foot sub">{note}</p>
  {:else if list && !list.length}
    <p class="t-foot sub">{pick ? t('scr.noneOpen') : t('scr.none')}</p>
  {/if}
  {#each list ?? [] as s (s.session)}
    <div class="ss surface">
      <div class="top">
        <b class="ellipsis">{s.title}</b>
        <span class="st" class:on={s.param}>{s.ended ? t('scr.closed') : s.started ? t('scr.live') : t('scr.waiting')}</span>
      </div>
      <p class="num"><b>{s.done}</b>{#if s.expected}<span> / {s.expected}</span>{/if} <i class="t-foot">{t('scr.done')}{s.pending ? ' · ' + t('scr.joining', { n: s.pending }) : ''}</i></p>
      <p class="t-foot scr"><MonitorUp size={15} />{t('scr.screens', { n: s.screens })}</p>
      <div class="acts">
        {#if pick}
          <Button kind="primary" size="m" full onclick={() => bind(s.session)}>{t('scr.here')}</Button>
        {:else}
          {#if !s.started}<Button kind="primary" size="m" full loading={busy === s.session} onclick={() => act(s, 'start')}>{#snippet icon()}<Play size={17} />{/snippet}{t('scr.start')}</Button>{/if}
          {#if s.started && !s.ended}<Button kind="secondary" size="m" full loading={busy === s.session} onclick={() => act(s, 'finish')}>{#snippet icon()}<Square size={16} />{/snippet}{t('scr.finish')}</Button>{/if}
          {#if s.started}<Button kind="secondary" size="m" full onclick={() => csv(s)}>{#snippet icon()}<Download size={17} />{/snippet}{t('scr.csv')}</Button>{/if}
          {#if s.screens}<Button kind="plain" size="m" full onclick={() => act(s, 'unpair')}>{#snippet icon()}<Unplug size={17} />{/snippet}{t('scr.unpair')}</Button>{/if}
        {/if}
      </div>
    </div>
  {/each}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 14px; }
  .ss { display: flex; flex-direction: column; gap: 8px; padding: 14px; border-radius: var(--r-l); margin: 10px 0; }
  .top { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0; }
  .top b { font: 650 16px/1.25 var(--font-text); min-width: 0; }
  .st { flex: none; font: 600 12.5px/1 var(--font-text); padding: 6px 10px; border-radius: 999px; color: var(--text-2);
    background: color-mix(in srgb, var(--text) 8%, transparent); }
  .st.on { color: #fff; background: var(--accent); }
  .num { margin: 0; font-variant-numeric: tabular-nums; }
  .num b { font: 800 34px/1 var(--font-text); }
  .num span { font: 600 20px/1 var(--font-text); color: var(--text-2); }
  .num i { font-style: normal; }
  .scr { display: flex; align-items: center; gap: 6px; margin: 0; }
  .acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
  .acts :global(.btn.full) { flex: 1 1 140px; width: auto; min-width: 0; }
</style>
