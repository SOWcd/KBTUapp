<script lang="ts">
  // Spy (server logic/rooms.py, logic/spy.py): a room made here or come into by its code (typed, or the QR / shared
  // link startapp=g_<code>, which opens this with `code` and joins at once). Bare and unstyled on purpose: the wiring
  // only, the look is designed separately (.claude/handoff/game-spy.md lists every state).
  // The room is polled with the version this phone has (204 until it moves): every second while a phase has a clock,
  // else every five. The clock is the server's (deadline - now) whatever the phone's says. A move made on an old
  // version comes back not applied with the fresh room, and goes once more on that one.
  import { onDestroy, onMount } from 'svelte';
  import { api, ApiErr, type Id, type Room, type RoomMove } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { gw, type GameKey } from '../../lib/i18n/games';
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

  const place = (id: string) => gw(`spy.loc.${id}` as GameKey);
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
    catch (e) { if (e instanceof ApiErr && e.code === 'not_found') { room = null; say(gw('spy.gone'), 'pleading_face_3d'); return; } }
    schedule();
  }
  function fail(e: unknown) {
    haptic.error();
    const why = !(e instanceof ApiErr) ? null : e.code === 'not_found' ? 'spy.err.code' : e.code === 'closed' ? 'spy.err.started'
      : e.code === 'full' ? 'spy.err.full' : e.code === 'rate_limited' ? 'spy.err.limit' : null;
    say(why ? gw(why) : t('common.error'), 'pleading_face_3d');
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

<Sheet {overlay} title={gw('spy.title')}>
  {#if !room}
    <p>{gw('spy.about')}</p>
    <button disabled={busy} onclick={() => enter(api.roomCreate('spy'))}>{gw('spy.create')}</button>
    <input inputmode="numeric" maxlength="4" placeholder={gw('spy.codePh')} bind:value={typed} />
    <button disabled={busy || !/^\d{4}$/.test(typed)} onclick={() => enter(api.roomJoin(typed))}>{gw('spy.join')}</button>
  {:else}
    {@const r = room}
    {#if r.phase === 'lobby'}
      <p>{gw('spy.code', { code: r.code })}</p>
      <div style:width="160px"><Qr text={roomLink(r.code)} /></div>
      <button onclick={() => tgShare(roomLink(r.code), gw('spy.shareText'))}>{gw('spy.share')}</button>
      <p>{gw('spy.players', { n: r.players.length })}</p>
      <ul>{#each r.players as p (p.id)}<li>{p.name}{p.id === r.host ? ` · ${gw('spy.host')}` : ''}</li>{/each}</ul>
      {#if r.me === r.host}
        <label>{gw('spy.minutes')} <input type="number" min="1" max="15" bind:value={minutes} /></label>
        {#if r.players.length < 3 || r.players.length > 12}<p>{gw('spy.needMore')}</p>{/if}
        <button disabled={r.players.length < 3 || r.players.length > 12} onclick={() => move({ type: 'start', minutes })}>{gw('spy.start')}</button>
      {:else}
        <p>{gw('spy.waitHost')}</p>
      {/if}
      <button onclick={() => move({ type: 'leave' })}>{gw('spy.leave')}</button>
    {:else if r.phase === 'reveal' && r.result}
      <h2>{gw(r.result.winner === 'spy' ? 'spy.winSpy' : 'spy.winLocals')}</h2>
      <p>{gw(`spy.why.${r.result.why}`)}</p>
      <p>{gw('spy.wasSpy', { name: nameOf(r.result.spy) })}</p>
      <p>{gw('spy.wasPlace', { place: place(r.location ?? '') })}</p>
      {#if r.result.guess}<p>{gw('spy.guessed', { place: place(r.result.guess) })}</p>{/if}
      <ul>{#each r.result.votes as v (v.from)}<li>{nameOf(v.from)} → {nameOf(v.to)}</li>{/each}</ul>
    {:else}
      <!-- hold-to-reveal: the role shows only while a finger is on it -->
      <button onpointerdown={() => (shown = true)} onpointerup={() => (shown = false)} onpointerleave={() => (shown = false)} onpointercancel={() => (shown = false)}>
        {#if !shown}{gw('spy.hold')}{:else if r.role === 'spy'}{gw('spy.youSpy')} · {gw('spy.spyHint')}{:else}{gw('spy.youLocal', { place: place(r.location ?? '') })}{/if}
      </button>
      {#if r.deadline}<p>{gw('spy.left', { time: mmss(left) })}</p>{/if}
      {#if r.phase === 'play'}
        {#if r.first}<p>{gw('spy.first', { name: nameOf(r.first) })}</p>{/if}
        {#if r.me === r.host}<button onclick={() => move({ type: 'vote_now' })}>{gw('spy.voteNow')}</button>{/if}
      {:else if r.phase === 'vote'}
        <h2>{gw('spy.vote')}</h2>
        <p>{gw('spy.voted', { n: r.voted?.length ?? 0, total: r.players.length })}</p>
        <ul>{#each r.players.filter((p) => p.id !== r.me) as p (p.id)}
          <li><button aria-pressed={r.myVote === p.id} onclick={() => move({ type: 'vote', target: p.id })}>{p.name}{r.voted?.includes(p.id) ? ' ✓' : ''}</button></li>
        {/each}</ul>
      {:else if r.phase === 'guess'}
        <p>{r.accused === r.me ? gw('spy.caughtMe') : gw('spy.caught', { name: nameOf(r.accused) })}</p>
      {/if}
      {#if r.role === 'spy' && (r.phase === 'play' || r.phase === 'guess')}
        <h3>{gw('spy.guess')}</h3>
        <ul>{#each SPY_LOCATIONS as l (l)}<li><button onclick={() => move({ type: 'guess', location: l })}>{place(l)}</button></li>{/each}</ul>
      {:else}
        <h3>{gw('spy.places')}</h3>
        <ul>{#each SPY_LOCATIONS as l (l)}<li>{place(l)}</li>{/each}</ul>
      {/if}
    {/if}
  {/if}
</Sheet>
