<script lang="ts">
  // Spy (server logic/rooms.py, logic/spy.py): a room made here or come into by its code (typed, or the QR / shared
  // link startapp=g_<code>, which opens this with `code` and joins at once). .claude/handoff/game-spy.md lists the states.
  // The room is polled with the version this phone has (204 until it moves): every second while a phase has a clock,
  // else every five. The clock is the server's (deadline - now) whatever the phone's says. A move made on an old
  // version comes back not applied with the fresh room, and goes once more on that one.
  // The look: the app's orb holds the game's mark; a room's code is four tiles, the same ones a guest types into; the
  // role is a sealed envelope that opens only while a finger holds it, and nothing on a phone tells the spy's from a
  // local's at a glance: the open letter looks the same for both, and every phone's places answer a tap the same way
  // (the question "name it?"; only the spy's yes is a move).
  import { onDestroy, onMount } from 'svelte';
  import HatGlasses from '@lucide/svelte/icons/hat-glasses';
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Crown from '@lucide/svelte/icons/crown';
  import Send from '@lucide/svelte/icons/send';
  import Minus from '@lucide/svelte/icons/minus';
  import Plus from '@lucide/svelte/icons/plus';
  import Check from '@lucide/svelte/icons/check';
  import Users from '@lucide/svelte/icons/users';
  import Timer from '@lucide/svelte/icons/timer';
  import Smartphone from '@lucide/svelte/icons/smartphone';
  import { api, ApiErr, type Id, type Room, type RoomMove } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { gw, type GameKey } from '../../lib/i18n/games';
  import { SPY_ART, SPY_LOCATIONS, roomLink, type SpyLocation } from '../../lib/games/spy';
  import { haptic, tgShare } from '../../lib/tg';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import Sheet from '../../ui/Sheet.svelte';
  import Qr from '../../ui/Qr.svelte';
  import Orb from '../../ui/Orb.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import '../../lib/qrnow'; // the room's code in the first frame

  let { overlay, code }: { overlay: Overlay; code?: string } = $props();
  let room = $state<Room | null>(null);
  let typed = $state(''), minutes = $state(5), shown = $state(false), busy = $state<'create' | 'join' | null>(null), err = $state('');
  let pick = $state<Id | null>(null); // my vote from the tap, until the server's room says it
  let skew = 0, clock = $state(Date.now() / 1000), timer: ReturnType<typeof setTimeout> | undefined, alive = true;

  const place = (id: string) => gw(`spy.loc.${id}` as GameKey);
  const who = (id: Id | null | undefined) => room?.players.find((p) => p.id === id);
  const nameOf = (id: Id | null | undefined) => who(id)?.name ?? '';
  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const secs = $derived(room?.deadline ? Math.max(0, room.deadline - clock - skew) : 0);
  const left = $derived(Math.ceil(secs));
  const span = $derived(!room ? 1 : room.phase === 'play' ? room.minutes * 60 : room.phase === 'vote' ? 60 : 30); // the phase's whole length (server spy.py)

  // the room this phone is in, kept so the game opened again (Back by mistake, the app relaunched) is the same round:
  // by its id, which only its players can read (a code is reused once its room is gone: never a stranger's room)
  const KEY = 'kb-spy-room';
  const keep = (id: Id | null) => { try { if (id) localStorage.setItem(KEY, String(id)); else localStorage.removeItem(KEY); } catch { /* storage blocked */ } };
  const kept = () => { try { return Number(localStorage.getItem(KEY)) || null; } catch { return null; } };

  function take(r: Room) {
    if (room && r.id === room.id && r.v < room.v) return; // an answer overtaken by a newer one
    if (r.phase !== room?.phase) { shown = false; pick = null; }
    room = r; skew = r.now - Date.now() / 1000;
    keep(r.id); // through the reveal too: the host may start one more round in it
  }
  // out on this phone: at the reveal the server keeps the seat until a rematch drops whoever stopped polling
  function forget() { room = null; typed = ''; keep(null); clearTimeout(timer); }
  function schedule() { clearTimeout(timer); if (alive && room) timer = setTimeout(poll, room.live ? 1000 : 5000); }
  async function poll() {
    if (!room) return;
    try { const r = await api.room(room.id, room.v); if (r) take(r); }
    catch (e) { if (e instanceof ApiErr && e.code === 'not_found') { room = null; keep(null); say(gw('spy.gone'), 'pleading_face_3d'); return; } }
    schedule();
  }
  function why(e: unknown) {
    const k = !(e instanceof ApiErr) ? null : e.code === 'not_found' ? 'spy.err.code' : e.code === 'closed' ? 'spy.err.started'
      : e.code === 'full' ? 'spy.err.full' : e.code === 'rate_limited' ? 'spy.err.limit' : null;
    return k ? gw(k) : t('common.error');
  }
  /** quiet: the kept room is gone by now, which is no news */
  async function enter(p: Promise<Room>, how: 'create' | 'join', quiet = false) {
    busy = how; err = '';
    try { take(await p); haptic.ok(); schedule(); }
    catch (e) { keep(null); if (quiet) typed = ''; else { err = why(e); haptic.error(); } } // the digits stay: a typo is one digit away
    finally { busy = null; }
  }
  async function move(m: RoomMove) {
    if (!room) return;
    const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
    try {
      let a = await api.roomMove(room.id, room.v, m, id);
      if (!a.applied && a.room) { take(a.room); a = await api.roomMove(a.room.id, a.room.v, m, id); }
      if (m.type === 'leave') { forget(); return; }
      if (a.room) take(a.room);
      schedule();
    } catch (e) {
      if (m.type === 'leave' && e instanceof ApiErr && e.code === 'not_found') { forget(); return; } // a double tap: already out
      pick = null; haptic.error(); say(why(e), 'pleading_face_3d');
    }
  }
  function type(e: Event & { currentTarget: HTMLInputElement }) {
    const el = e.currentTarget;
    typed = el.value = el.value.replace(/\D/g, '').slice(0, 4);
    err = '';
    if (typed.length === 4) { el.blur(); void enter(api.roomJoin(typed), 'join'); } // the fourth digit is the Join
  }
  // naming a place ends the round: asked first, and asked on every phone alike; only the spy's yes is a move
  async function guess(l: SpyLocation) {
    if (!(await sheets.ask({ title: gw('spy.guessAsk', { place: place(l) }), text: gw('spy.guessAskText'), ok: gw('spy.guess'), cancel: t('common.cancel') }))) return;
    if (room?.role === 'spy') void move({ type: 'guess', location: l }); else say(gw('spy.onlySpy'), 'thinking_face_3d');
  }
  // the host's way to the vote ends everyone's discussion: asked first
  async function voteNow() {
    if (await sheets.ask({ title: gw('spy.voteAsk'), text: gw('spy.voteAskText'), ok: gw('spy.voteNow'), cancel: t('common.cancel') })) void move({ type: 'vote_now' });
  }
  function vote(id: Id) { pick = id; haptic.select(); void move({ type: 'vote', target: id }); }
  const hold = (on: boolean) => { if (on !== shown) { shown = on; if (on) haptic.soft(); } };

  onMount(() => {
    const back = code ? null : kept();
    if (code) { typed = code; void enter(api.roomJoin(code), 'join'); }
    else if (back) void enter(api.room(back).then((r) => r ?? Promise.reject(new Error('empty'))), 'join', true);
    const tick = setInterval(() => { clock = Date.now() / 1000; }, 250);
    return () => clearInterval(tick);
  });
  onDestroy(() => { alive = false; clearTimeout(timer); });
</script>


<!-- the game's mark, drawn here: a hat over a pair of glasses -->
{#snippet mark(size: number)}
  <svg class="mark" width={size} height={size} viewBox="0 0 48 48" fill="currentColor" aria-hidden="true">
    <path d="M14 21v-6a6 6 0 0 1 6-6h8a6 6 0 0 1 6 6v6z" />
    <rect x="5" y="20" width="38" height="4.5" rx="2.25" />
    <g fill-opacity=".28" stroke="currentColor" stroke-width="3"><circle cx="16" cy="34" r="6" /><circle cx="32" cy="34" r="6" /></g>
    <path d="M22 33a2.4 2.4 0 0 1 4 0" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
  </svg>
{/snippet}

<!-- the phase's clock: the server's seconds, a bar running out with them, red for the last ten -->
{#snippet time(title: string)}
  <header class="clock" class:low={left <= 10}>
    <h2 class="ct">{title}</h2>
    <p class="cn num" role="timer" aria-label={gw('spy.left', { time: mmss(left) })}>{mmss(left)}</p>
    <span class="bar" aria-hidden="true"><i style:transform="scaleX({Math.min(1, secs / span)})"></i></span>
  </header>
{/snippet}

<!-- the role: a sealed envelope; the letter is in the page only while a finger (or a key) holds it open, and looks the
     same whatever it says. small: a strip, for the vote -->
{#snippet secret(r: Room, small = false)}
  <button class="env" class:small class:open={shown} aria-label={gw('spy.hold')} data-nohaptic
    onpointerdown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); hold(true); }} onpointerup={() => hold(false)} onpointercancel={() => hold(false)}
    onkeydown={(e) => { if (e.key === ' ' || e.key === 'Enter') hold(true); }} onkeyup={() => hold(false)} onblur={() => hold(false)}
    oncontextmenu={(e) => e.preventDefault()}>
    <span class="flap"></span>
    <span class="seal">{@render mark(small ? 22 : 30)}</span>
    <span class="how"><span class="cap">{gw('spy.role')}</span><b>{gw('spy.hold')}</b></span>
    {#if shown}
      <span class="letter">
        <span class="cap">{gw(r.role === 'spy' ? 'spy.role' : 'spy.placeCap')}</span>
        <b class="big">{r.role === 'spy' ? gw('spy.youSpy') : place(r.location ?? '')}</b>
        {#if !small}<span class="hint">{gw(r.role === 'spy' ? 'spy.spyHint' : 'spy.localHint')}</span>{/if}
      </span>
    {/if}
  </button>
{/snippet}

<!-- the places as tiles, the same on every phone: a tap asks "name it?" whoever taps (see guess) -->
{#snippet places(can: boolean)}
  <section class="places">
    <h3 class="st">{gw('spy.places')}</h3>
    <div class="grid">
      {#each SPY_LOCATIONS as l (l)}
        <button class="pl" disabled={!can} onclick={() => guess(l)}><span class="em" aria-hidden="true">{SPY_ART[l]}</span><span class="nm">{place(l)}</span></button>
      {/each}
    </div>
  </section>
{/snippet}

<!-- who voted for whom, at the reveal -->
{#snippet ballots(title: string, votes: { from: Id; to: Id }[])}
  {#if votes.length}
    <section class="tally">
      <h3 class="st">{title}</h3>
      <ul class="card">
        {#each votes as v (v.from)}
          {@const from = who(v.from)}
          {@const to = who(v.to)}
          {#if from && to}
            <li><Avatar person={from} size={28} tappable={false} /><b>{from.name}</b><ArrowRight size={16} /><Avatar person={to} size={28} tappable={false} /><b>{to.name}</b></li>
          {/if}
        {/each}
      </ul>
    </section>
  {/if}
{/snippet}

<Sheet {overlay} full title={gw('spy.title')} icon={HatGlasses}>
  {#if !room}
    <div class="home stagger">
      <div class="orb"><Orb size={132}><span class="om">{@render mark(56)}</span></Orb></div>
      <p class="pitch">{gw('spy.about')}</p>
      <ul class="facts">
        <li><Users size={15} />{gw('spy.f.players')}</li>
        <li><Timer size={15} />{gw('spy.f.time')}</li>
        <li><Smartphone size={15} />{gw('spy.f.phone')}</li>
      </ul>
      <Button size="l" full lit loading={busy === 'create'} disabled={busy === 'join'} onclick={() => enter(api.roomCreate('spy'), 'create')}>{gw('spy.create')}</Button>
      <p class="or"><span>{gw('spy.orCode')}</span></p>
      <!-- a wrong code stays in its tiles, shaken; a tap selects it all, so the next digit starts over or one is fixed -->
      <label class="code" class:wait={busy === 'join'} class:bad={!!err} class:all={typed.length === 4}>
        <input inputmode="numeric" autocomplete="off" maxlength="4" aria-label={gw('spy.codePh')} value={typed} oninput={type} onfocus={(e) => e.currentTarget.select()} disabled={!!busy} />
        {#each [0, 1, 2, 3] as i (i)}<span class="tile num" class:at={i === typed.length} style:--i={i}>{typed[i] ?? ''}</span>{/each}
      </label>
      <p class="err" role="alert">{err}</p>
    </div>
  {:else}
    {@const r = room}
    {@const host = who(r.host)}
    {#key r.phase}
      <div class="phase stagger">
        {#if r.phase === 'lobby'}
          <section class="invite">
            <!-- whose room this is: a mistyped code is seen at once -->
            {#if host}<p class="owner"><Avatar person={host} size={28} tappable={false} /><b>{gw('spy.room')} · {host.name}</b></p>{/if}
            <div class="digits" role="img" aria-label={gw('spy.code', { code: r.code })}>{#each r.code.split('') as d, i (i)}<span class="tile num">{d}</span>{/each}</div>
            <div class="plate"><Qr text={roomLink(r.code)}><span class="qm">{@render mark(22)}</span></Qr></div>
            <p class="hint">{gw('spy.scan')}</p>
            <Button kind="secondary" full onclick={() => tgShare(roomLink(r.code), gw('spy.shareText'))}>{#snippet icon()}<Send size={18} />{/snippet}{gw('spy.share')}</Button>
          </section>
          <section class="crew">
            <h3 class="st">{gw('spy.players', { n: r.players.length })}</h3>
            <ul class="seats">
              {#each r.players as p (p.id)}
                <li class:me={p.id === r.me}>
                  <span class="face"><Avatar person={p} size={52} tappable={false} />{#if p.id === r.host}<i class="crown" title={gw('spy.host')}><Crown size={12} strokeWidth={2.6} /></i>{/if}</span>
                  <b>{p.name}</b>
                </li>
              {/each}
              {#each { length: Math.max(0, 3 - r.players.length) } as _, i (i)}<li class="free"><i class="seat" title={gw('spy.seat')}></i><b>…</b></li>{/each}
            </ul>
          </section>
        {:else if r.phase === 'play'}
          {@const first = who(r.first)}
          {@render time(gw('spy.minutes'))}
          <!-- the host's way on: small, at the top, away from the thumb, and asked before it goes -->
          {#if r.me === r.host}<button class="skip" onclick={voteNow}>{gw('spy.voteNow')}<ChevronRight size={15} /></button>{/if}
          {@render secret(r)}
          {#if first}<p class="first"><Avatar person={first} size={24} tappable={false} /><span>{gw('spy.first', { name: first.name })}</span></p>{/if}
          {@render places(true)}
        {:else if r.phase === 'vote'}
          {@const mine = pick ?? r.myVote}
          {@render time(gw('spy.vote'))}
          <section class="ballot">
            <p class="hint rule">{gw('spy.voteHint')}</p>
            {#each r.players.filter((p) => p.id !== r.me) as p (p.id)}
              <button class="cand" class:on={mine === p.id} aria-pressed={mine === p.id} data-nohaptic onclick={() => vote(p.id)}>
                <Avatar person={p} size={44} tappable={false} />
                <span class="cw"><b>{p.name}</b>{#if r.voted?.includes(p.id)}<span class="did"><Check size={14} strokeWidth={3} />{gw('spy.hasVoted')}</span>{/if}</span>
                <i class="radio"><Check size={15} strokeWidth={3} /></i>
              </button>
            {/each}
            <p class="sum"><b>{mine != null ? gw('spy.myVote', { name: nameOf(mine) }) : ''}</b><span>{gw('spy.voted', { n: r.voted?.length ?? 0, total: r.players.length })}</span></p>
          </section>
          {@render secret(r, true)}
        {:else if r.phase === 'guess'}
          {@const spy = who(r.accused)}
          {@render time(gw('spy.guess'))}
          <div class="caught" class:me={r.accused === r.me}>
            {#if spy}<Avatar person={spy} size={72} tappable={false} />{/if}
            <p>{r.accused === r.me ? gw('spy.caughtMe') : gw('spy.caught', { name: spy?.name ?? '' })}</p>
          </div>
          {@render places(r.accused === r.me)}
        {:else if r.result}
          {@const res = r.result}
          {@const spy = who(res.spy)}
          <!-- the orb's light: green when my side won -->
          <header class="end">
            <div class="orb"><Orb size={132} tone={(res.winner === 'spy') === (res.spy === r.me) ? 'success' : 'danger'}><span class="om">{@render mark(56)}</span></Orb></div>
            <h2 class="fs-t1">{gw(res.winner === 'spy' ? 'spy.winSpy' : 'spy.winLocals')}</h2>
            <p class="lead">{gw(`spy.why.${res.why}`)}</p>
          </header>
          <div class="duo">
            <div class="fact"><span class="top">{#if spy}<Avatar person={spy} size={56} tappable={false} />{/if}</span><span class="cap">{gw('spy.spyCap')}</span><b>{spy?.name ?? ''}</b></div>
            <div class="fact"><span class="top em" aria-hidden="true">{SPY_ART[r.location as SpyLocation] ?? ''}</span><span class="cap">{gw('spy.placeCap')}</span><b>{place(r.location ?? '')}</b></div>
          </div>
          {#if res.guess}<p class="said"><span class="cap">{gw('spy.guessCap')}</span><b><span aria-hidden="true">{SPY_ART[res.guess as SpyLocation] ?? ''}</span> {place(res.guess)}</b></p>{/if}
          {@render ballots(gw('spy.votesHit'), res.votes.filter((v) => v.to === res.spy))}
          {@render ballots(gw('spy.votesMiss'), res.votes.filter((v) => v.to !== res.spy))}
        {/if}
      </div>
    {/key}
  {/if}
  {#snippet footer()}
    {#if room?.phase === 'lobby'}
      {@const n = room.players.length}
      <div class="ft">
        {#if room.me !== room.host}
          <p class="note">{gw('spy.waitHost')}<span class="dots" aria-hidden="true"><i></i><i></i><i></i></span></p>
        {:else}
          {#if n < 3 || n > 12}<p class="note">{gw('spy.needMore')}</p>{/if}
          <!-- how long to talk, beside the button that starts the talk -->
          <div class="go">
            <span class="step" role="group" aria-label={gw('spy.minutes')}>
              <Button kind="gray" size="s" round label={gw('spy.less')} disabled={minutes <= 1} onclick={() => minutes--}>{#snippet icon()}<Minus size={18} />{/snippet}</Button>
              <b class="num" aria-live="polite">{gw('spy.min', { n: minutes })}</b>
              <Button kind="gray" size="s" round label={gw('spy.more')} disabled={minutes >= 15} onclick={() => minutes++}>{#snippet icon()}<Plus size={18} />{/snippet}</Button>
            </span>
            <Button size="l" full lit disabled={n < 3 || n > 12} onclick={() => move({ type: 'start', minutes })}>{gw('spy.start')}</Button>
          </div>
        {/if}
        <Button kind="plain" destructive full onclick={() => move({ type: 'leave' })}>{gw('spy.leave')}</Button>
      </div>
    {:else if room?.phase === 'reveal'}
      <!-- one more round in the same room, everyone still in it: the host's -->
      <div class="ft">
        {#if room.me === room.host}<Button size="l" full lit onclick={() => move({ type: 'again' })}>{gw('spy.again')}</Button>
        {:else}<p class="note">{gw('spy.waitAgain')}</p>{/if}
        <Button kind="plain" destructive full onclick={forget}>{gw('spy.leave')}</Button>
      </div>
    {/if}
  {/snippet}
</Sheet>

<style>
  .home, .phase { display: flex; flex-direction: column; gap: var(--gap-group); padding-bottom: var(--s-4); }
  .home { gap: var(--s-4); text-align: center; }
  .orb { display: grid; place-items: center; margin: var(--s-2) 0 var(--s-1); }
  .om { color: white; opacity: 0.94; }
  h2, h3, p, ul { margin: 0; }
  ul { padding: 0; list-style: none; }
  .pitch { font: 600 var(--fs-row)/1.4 var(--font-text); letter-spacing: -0.01em; color: var(--text); text-wrap: balance; }
  .lead { font: 450 var(--fs-body)/1.45 var(--font-text); color: var(--text-2); text-wrap: balance; }
  .cap { font: 600 var(--fs-cap)/1.2 var(--font-text); letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-3); }
  .hint { font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); text-wrap: balance; }
  .st { margin: 0 var(--s-1); font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .card { border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim); }

  .facts { display: flex; flex-wrap: wrap; justify-content: center; gap: var(--s-2); margin: var(--s-1) 0 var(--s-3); }
  .facts li { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 var(--s-3); border-radius: var(--r-full); background: var(--fill);
    font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-2); }

  .or { display: flex; align-items: center; gap: var(--s-3); margin-top: var(--s-2); font: 450 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  .or::before, .or::after { content: ''; flex: 1; height: 1px; background: var(--separator); }

  /* a code's four tiles: typed into here, shown in the lobby */
  .code, .digits { position: relative; display: flex; justify-content: center; gap: var(--s-2); }
  .tile { display: grid; place-items: center; width: 56px; height: 68px; border-radius: var(--r-m); background: var(--fill);
    font: 700 var(--fs-title)/1 var(--font-display); letter-spacing: -0.02em; color: var(--text); transition: box-shadow var(--t-fast) var(--ease); }
  .code input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; font-size: var(--fs-row); text-align: center; }
  .code .tile:empty::before { content: ''; width: 6px; height: 6px; border-radius: var(--r-full); background: var(--fill-2); }
  .code:focus-within .tile.at::before { display: none; }
  .code:focus-within .tile.at, .code.all:focus-within .tile { box-shadow: inset 0 0 0 2px var(--accent); }
  .code:focus-within .tile.at::after { content: ''; width: 2px; height: 28px; border-radius: var(--r-full); background: var(--accent); animation: blink 1.1s steps(1) infinite; }
  .code.wait .tile { animation: wait 1s var(--ease) calc(var(--i) * 120ms) infinite alternate; }
  .code.bad { animation: shake 360ms var(--ease); }
  .code.bad .tile { box-shadow: inset 0 0 0 1.5px var(--danger); }
  .err { min-height: 1.4em; margin-top: calc(var(--s-2) * -1); font: 600 var(--fs-sub)/1.4 var(--font-text); color: var(--danger-text); }

  .invite { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--card-pad); border-radius: var(--r-l);
    background: radial-gradient(90% 60% at 50% 0%, var(--accent-soft), transparent 70%), var(--surface); box-shadow: var(--card-rim); text-align: center; }
  .owner { display: flex; align-items: center; gap: var(--s-2); font: 600 var(--fs-body)/1.2 var(--font-text); }
  /* a white plate in both themes: a camera reads dark on white */
  .plate { width: 168px; padding: var(--s-3); border-radius: var(--r-l); background: white; box-shadow: var(--shadow-thumb); }
  .qm { display: grid; place-items: center; width: 100%; height: 100%; border-radius: var(--r-xs); background: var(--ink); color: white; }

  /* the players around the table: faces, the host's with a crown, mine ringed */
  .crew, .places, .ballot, .tally { display: flex; flex-direction: column; gap: var(--s-3); }
  .seats { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--s-4) var(--s-2); }
  .seats li { display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; animation: pop var(--t-slow) var(--ease-bounce) both; }
  .seats b { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 600 var(--fs-sub)/1.2 var(--font-text); }
  .face { position: relative; display: inline-flex; border-radius: var(--r-full); }
  .me .face { box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--accent); }
  .crown { position: absolute; right: -4px; top: -4px; display: grid; place-items: center; width: 22px; height: 22px; border-radius: var(--r-full);
    background: var(--gold); color: var(--ink); box-shadow: 0 0 0 2px var(--bg); }
  .seat { width: 52px; height: 52px; border-radius: var(--r-full); border: 1.5px dashed var(--text-3); animation: wait 1.2s var(--ease) infinite alternate; }
  .free b { color: var(--text-3); }

  .ft { display: flex; flex-direction: column; gap: var(--s-2); }
  .go { display: flex; align-items: center; gap: var(--s-3); }
  .go :global(.btn.full) { flex: 1 1 0; width: auto; min-width: 0; }
  .step { flex: none; display: inline-flex; align-items: center; gap: var(--s-1); }
  .step b { min-width: 3.6em; text-align: center; font: 600 var(--fs-body)/1 var(--font-text); }
  .note { display: flex; justify-content: center; align-items: baseline; gap: 3px; font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); text-align: center; }
  .dots { display: inline-flex; gap: 3px; margin-left: 3px; }
  .dots i { width: 3px; height: 3px; border-radius: var(--r-full); background: currentColor; animation: wait 900ms var(--ease) infinite alternate; }
  .dots i:nth-child(2) { animation-delay: 200ms; } .dots i:nth-child(3) { animation-delay: 400ms; }

  .clock { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); padding-top: var(--s-1); }
  .ct { font: 600 var(--fs-body)/1.2 var(--font-text); color: var(--text-2); }
  .cn { font: 800 calc(var(--fs-title) * 1.9)/1 var(--font-display); letter-spacing: -0.035em; transition: color var(--t-base) var(--ease); }
  .bar { width: 100%; height: 4px; margin-top: var(--s-2); border-radius: var(--r-full); background: var(--fill); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: inherit; background: var(--grad-accent); transform-origin: left; transition: transform 250ms linear; }
  .low .cn { color: var(--danger-text); }
  .low .bar i { background: var(--danger); }
  .skip { align-self: flex-end; display: inline-flex; align-items: center; gap: 2px; min-height: var(--tap); margin: calc(var(--s-5) * -1) 0 calc(var(--s-4) * -1); padding: 0 var(--s-1);
    font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }

  /* the envelope: a card with its back folds drawn, a flap sealed with the game's mark; held, the flap lifts and the
     letter comes up. One look for every role */
  .env { position: relative; display: block; width: 100%; height: 212px; border-radius: var(--r-xl); overflow: hidden; perspective: 700px;
    background: radial-gradient(110% 80% at 50% 100%, var(--accent-soft), transparent 72%), var(--surface); box-shadow: var(--card-rim); color: var(--text); text-align: center;
    touch-action: none; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; transition: transform var(--t-base) var(--ease-bounce); }
  .env.open { transform: scale(0.975); }
  .env::before { content: ''; position: absolute; inset: 0; transition: opacity var(--t-base) var(--ease); background:
    linear-gradient(to bottom right, transparent calc(50% - 0.6px), var(--line-2) 50%, transparent calc(50% + 0.6px)) left bottom / 50% 46% no-repeat,
    linear-gradient(to bottom left, transparent calc(50% - 0.6px), var(--line-2) 50%, transparent calc(50% + 0.6px)) right bottom / 50% 46% no-repeat; }
  .flap { position: absolute; left: 0; right: 0; top: 0; height: 54%; transform-origin: top; clip-path: polygon(0 0, 100% 0, 50% 100%);
    background: linear-gradient(var(--surface-2), var(--fill-2)); transition: transform var(--t-slow) var(--ease), opacity var(--t-base) var(--ease); }
  .seal { position: absolute; left: 50%; top: 54%; display: grid; place-items: center; width: 60px; height: 60px; margin: -30px 0 0 -30px; border-radius: var(--r-full);
    background: var(--grad-accent); color: white; box-shadow: inset 0 0 0 3px rgba(255, 255, 255, 0.18), var(--shadow-thumb);
    transition: transform var(--t-slow) var(--ease-bounce), opacity var(--t-base) var(--ease); }
  .seal::after { content: ''; position: absolute; inset: 0; border-radius: inherit; box-shadow: 0 0 0 1.5px var(--accent); opacity: 0; animation: ring 2.4s var(--ease) infinite; }
  .how { position: absolute; left: var(--s-4); right: var(--s-4); bottom: var(--s-4); display: flex; flex-direction: column; gap: var(--s-1); transition: opacity var(--t-base) var(--ease); }
  .how b { font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .how .cap { display: none; }
  .open .flap { transform: rotateX(-140deg); opacity: 0; }
  .open .seal { transform: scale(0.5); opacity: 0; }
  .open .how, .env.open::before { opacity: 0; }
  .letter { position: absolute; inset: var(--s-3); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s-2); padding: var(--s-4);
    border-radius: var(--r-l); background: var(--surface-solid); box-shadow: var(--card-rim); animation: letter var(--t-slow) var(--ease) both; }
  .letter .big { font: 700 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.02em; }
  /* the strip: the seal and the words in a row, no flap */
  .env.small { height: 76px; border-radius: var(--r-l); background: var(--surface); }
  .small::before, .small .flap { display: none; }
  .small .seal { left: var(--s-4); top: 50%; width: 44px; height: 44px; margin: -22px 0 0; }
  .small .how { left: 76px; top: 0; bottom: 0; justify-content: center; text-align: left; }
  .small .how .cap { display: block; }
  .small .letter { inset: var(--s-1); padding: var(--s-2); gap: 2px; border-radius: var(--r-m); }
  .small .letter .big { font-size: var(--fs-t3); }

  .first { display: flex; align-items: center; justify-content: center; gap: var(--s-2); margin-top: calc(var(--s-2) * -1); font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }

  /* the places: picture tiles, three across */
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-2); }
  .pl { display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; min-height: 98px; padding: var(--s-3) var(--s-1) var(--s-2); border-radius: var(--r-l);
    background: var(--surface); box-shadow: var(--card-rim); color: var(--text); transition: transform var(--t-base) var(--ease-bounce), opacity var(--t-base) var(--ease); }
  .pl:enabled:active { transform: scale(0.94); }
  .pl:disabled { cursor: default; opacity: 0.55; }
  .em { font-size: var(--fs-title); line-height: 1.1; }
  .nm { max-width: 100%; font: 600 var(--fs-cap)/1.2 var(--font-text); text-align: center; overflow-wrap: anywhere; }

  .rule { margin: 0 var(--s-1); text-align: center; }
  .cand { display: flex; align-items: center; gap: var(--s-3); width: 100%; min-height: 64px; padding: var(--s-2) var(--s-4) var(--s-2) var(--s-3);
    border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim); transition: background-color var(--t-base) var(--ease), transform var(--t-fast) var(--ease); }
  .cand:active { transform: scale(0.98); }
  .cw { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .cw b { font: 600 var(--fs-row)/1.25 var(--font-text); overflow-wrap: anywhere; }
  .did { display: inline-flex; align-items: center; gap: var(--s-1); font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--success-text); animation: rise var(--t-base) var(--ease) both; }
  .cand.on { background: var(--accent-soft); box-shadow: inset 0 0 0 1.5px var(--accent); }
  .radio { flex: none; display: grid; place-items: center; width: 28px; height: 28px; border-radius: var(--r-full); box-shadow: inset 0 0 0 1.5px var(--line-2); color: transparent;
    transition: background-color var(--t-base) var(--ease), transform var(--t-slow) var(--ease-bounce); }
  .on .radio { background: var(--accent); box-shadow: none; color: var(--on-accent); transform: scale(1.08); }
  .sum { display: flex; flex-direction: column; align-items: center; gap: var(--s-1); min-height: 2.9em; text-align: center; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .sum b { font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text); }

  .caught { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--s-5); border-radius: var(--r-l);
    background: var(--surface); box-shadow: var(--card-rim); text-align: center; font: 600 var(--fs-row)/1.3 var(--font-text); text-wrap: balance; }
  .caught.me { background: linear-gradient(var(--danger-soft), var(--danger-soft)), var(--surface); color: var(--danger-text); }

  .end { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); text-align: center; }
  .duo { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-3); }
  .fact { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: var(--s-1); min-width: 0; min-height: 132px; padding: var(--s-4) var(--s-3);
    border-radius: var(--r-l); background: radial-gradient(90% 70% at 50% 0%, var(--accent-soft), transparent 70%), var(--surface); box-shadow: var(--card-rim); text-align: center; }
  .top { display: grid; place-items: center; height: 56px; margin-bottom: auto; }
  .fact .em { font-size: calc(var(--fs-title) * 1.4); }
  .fact .cap { margin-top: var(--s-2); }
  .fact b { max-width: 100%; font: 700 var(--fs-row)/1.2 var(--font-display); overflow-wrap: anywhere; }
  .said { display: flex; flex-direction: column; align-items: center; gap: var(--s-1); margin-top: calc(var(--s-2) * -1); text-align: center; }
  .said b { font: 600 var(--fs-row)/1.25 var(--font-text); }
  .tally li { display: flex; align-items: center; gap: var(--s-2); min-height: var(--row-dense); padding: var(--s-2) var(--s-4); color: var(--text-3); }
  .tally li + li { box-shadow: inset 0 0.5px 0 var(--separator); }
  .tally b { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 600 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .tally li > :global(svg) { flex: none; margin: 0 var(--s-1); }

  @keyframes blink { 50% { opacity: 0; } }
  @keyframes wait { from { opacity: 1; } to { opacity: 0.35; } }
  @keyframes shake { 20% { transform: translateX(-8px); } 45% { transform: translateX(7px); } 70% { transform: translateX(-4px); } 90% { transform: translateX(2px); } }
  @keyframes ring { 0% { opacity: 0.7; transform: scale(1); } 70%, 100% { opacity: 0; transform: scale(1.5); } }
  @keyframes rise { from { opacity: 0; transform: translateY(4px); } }
  @keyframes letter { from { opacity: 0; transform: translateY(28px) scale(0.96); } }
  @keyframes pop { from { opacity: 0; transform: scale(0.6); } }
  @media (prefers-reduced-motion: reduce) {
    .seal::after, .seat, .dots i, .code.wait .tile, .code.bad, .letter, .did, .seats li { animation: none; }
  }
  :global(html.lowfx) .seal::after { animation: none; }
</style>
