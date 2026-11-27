<script lang="ts">
  // Spy (server logic/rooms.py, logic/spy.py): a room made here or come into by its code (typed, or the QR / shared
  // link startapp=g_<code>, which opens this with `code` and joins at once). Bare and unstyled on purpose: the wiring
  // only, the look is designed separately (.claude/handoff/game-spy.md lists every state).
  // The room is polled with the version this phone has (204 until it moves): every second while a phase has a clock,
  // else every five. The clock is the server's (deadline - now) whatever the phone's says. A move made on an old
  // version comes back not applied with the fresh room, and goes once more on that one.
  import { onDestroy, onMount } from 'svelte';
  import { api, ApiErr, type Id, type Room, type RoomMove } from '../../lib/api';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { SPY_LOCATIONS, roomLink } from '../../lib/games/spy';
  import { haptic, tgShare } from '../../lib/tg';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Qr from '../../ui/Qr.svelte';
  import '../../lib/qrnow'; // the room's code in the first frame

  let { overlay, code }: { overlay: Overlay; code?: string } = $props();
  let room = $state<Room | null>(null);
  let typed = $state(''), minutes = $state(5), shown = $state(false), busy = $state(false);
  let skew = 0, clock = $state(Date.now() / 1000), timer: ReturnType<typeof setTimeout> | undefined, alive = true;

  const place = (id: string) => t(`spy.loc.${id}` as Key);
  const nameOf = (id: Id | null | undefined) => room?.players.find((p) => p.id === id)?.name ?? '';
  const left = $derived(room?.deadline ? Math.max(0, Math.ceil(room.deadline - clock - skew)) : 0);
  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  function take(r: Room) {
    if (room && r.id === room.id && r.v < room.v) return; // an answer overtaken by a newer one
    room = r; skew = r.now - Date.now() / 1000;
  }
  function schedule() { clearTimeout(timer); if (alive && room) timer = setTimeout(poll, room.live ? 1000 : 5000); }
  async function poll() {
    if (!room) return;
    try { const r = await api.room(room.id, room.v); if (r) take(r); }
    catch (e) { if (e instanceof ApiErr && e.code === 'not_found') { room = null; say(t('spy.gone'), 'pleading_face_3d'); return; } }
    schedule();
  }
  function fail(e: unknown) {
    haptic.error();
    const why = !(e instanceof ApiErr) ? 'common.error' : e.code === 'not_found' ? 'spy.err.code' : e.code === 'closed' ? 'spy.err.started'
      : e.code === 'full' ? 'spy.err.full' : e.code === 'rate_limited' ? 'spy.err.limit' : 'common.error';
    say(t(why), 'pleading_face_3d');
  }
  async function enter(p: Promise<Room>) {
    busy = true;
    try { take(await p); haptic.ok(); schedule(); } catch (e) { fail(e); } finally { busy = false; }
  }
  async function move(m: RoomMove) {
    if (!room) return;
    const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
    try {
      let a = await api.roomMove(room.id, room.v, m, id);
      if (!a.applied && a.room) { take(a.room); a = await api.roomMove(a.room.id, a.room.v, m, id); }
      if (m.type === 'leave') { room = null; clearTimeout(timer); return; }
      if (a.room) take(a.room);
      haptic.tap(); schedule();
    } catch (e) { fail(e); }
  }

  onMount(() => {
    if (code) void enter(api.roomJoin(code));
    const tick = setInterval(() => { clock = Date.now() / 1000; }, 250);
    return () => clearInterval(tick);
  });
  onDestroy(() => { alive = false; clearTimeout(timer); });
</script>

<Sheet {overlay} title={t('spy.title')}>
  {#if !room}
    <p>{t('spy.about')}</p>
    <button disabled={busy} onclick={() => enter(api.roomCreate('spy'))}>{t('spy.create')}</button>
    <input inputmode="numeric" maxlength="4" placeholder={t('spy.codePh')} bind:value={typed} />
    <button disabled={busy || !/^\d{4}$/.test(typed)} onclick={() => enter(api.roomJoin(typed))}>{t('spy.join')}</button>
  {:else}
    {@const r = room}
    {#if r.phase === 'lobby'}
      <p>{t('spy.code', { code: r.code })}</p>
      <div style:width="160px"><Qr text={roomLink(r.code)} /></div>
      <button onclick={() => tgShare(roomLink(r.code), t('spy.shareText'))}>{t('spy.share')}</button>
      <p>{t('spy.players', { n: r.players.length })}</p>
      <ul>{#each r.players as p (p.id)}<li>{p.name}{p.id === r.host ? ` · ${t('spy.host')}` : ''}</li>{/each}</ul>
      {#if r.me === r.host}
        <label>{t('spy.minutes')} <input type="number" min="1" max="15" bind:value={minutes} /></label>
        {#if r.players.length < 3 || r.players.length > 12}<p>{t('spy.needMore')}</p>{/if}
        <button disabled={r.players.length < 3 || r.players.length > 12} onclick={() => move({ type: 'start', minutes })}>{t('spy.start')}</button>
      {:else}
        <p>{t('spy.waitHost')}</p>
      {/if}
      <button onclick={() => move({ type: 'leave' })}>{t('spy.leave')}</button>
    {:else if r.phase === 'reveal' && r.result}
      <h2>{t(r.result.winner === 'spy' ? 'spy.winSpy' : 'spy.winLocals')}</h2>
      <p>{t(`spy.why.${r.result.why}` as Key)}</p>
      <p>{t('spy.wasSpy', { name: nameOf(r.result.spy) })}</p>
      <p>{t('spy.wasPlace', { place: place(r.location ?? '') })}</p>
      {#if r.result.guess}<p>{t('spy.guessed', { place: place(r.result.guess) })}</p>{/if}
      <ul>{#each r.result.votes as v (v.from)}<li>{nameOf(v.from)} → {nameOf(v.to)}</li>{/each}</ul>
    {:else}
      <!-- hold-to-reveal: the role shows only while a finger is on it -->
      <button onpointerdown={() => (shown = true)} onpointerup={() => (shown = false)} onpointerleave={() => (shown = false)} onpointercancel={() => (shown = false)}>
        {#if !shown}{t('spy.hold')}{:else if r.role === 'spy'}{t('spy.youSpy')} · {t('spy.spyHint')}{:else}{t('spy.youLocal', { place: place(r.location ?? '') })}{/if}
      </button>
      {#if r.deadline}<p>{t('spy.left', { time: mmss(left) })}</p>{/if}
      {#if r.phase === 'play'}
        {#if r.first}<p>{t('spy.first', { name: nameOf(r.first) })}</p>{/if}
        {#if r.me === r.host}<button onclick={() => move({ type: 'vote_now' })}>{t('spy.voteNow')}</button>{/if}
      {:else if r.phase === 'vote'}
        <h2>{t('spy.vote')}</h2>
        <p>{t('spy.voted', { n: r.voted?.length ?? 0, total: r.players.length })}</p>
        <ul>{#each r.players.filter((p) => p.id !== r.me) as p (p.id)}
          <li><button aria-pressed={r.myVote === p.id} onclick={() => move({ type: 'vote', target: p.id })}>{p.name}{r.voted?.includes(p.id) ? ' ✓' : ''}</button></li>
        {/each}</ul>
      {:else if r.phase === 'guess'}
        <p>{r.accused === r.me ? t('spy.caughtMe') : t('spy.caught', { name: nameOf(r.accused) })}</p>
      {/if}
      {#if r.role === 'spy' && (r.phase === 'play' || r.phase === 'guess')}
        <h3>{t('spy.guess')}</h3>
        <ul>{#each SPY_LOCATIONS as l (l)}<li><button onclick={() => move({ type: 'guess', location: l })}>{place(l)}</button></li>{/each}</ul>
      {:else}
        <h3>{t('spy.places')}</h3>
        <ul>{#each SPY_LOCATIONS as l (l)}<li>{place(l)}</li>{/each}</ul>
      {/if}
    {/if}
  {/if}
</Sheet>
