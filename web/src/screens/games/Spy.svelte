<script lang="ts">
  // Spy (server logic/rooms.py, logic/spy.py): a room made here or come into by its code (typed, or the QR / shared
  // link startapp=g_<code>, which opens this with `code` and joins at once). .claude/handoff/game-spy.md lists the states.
  // The room is polled with the version this phone has (204 until it moves): every second while a phase has a clock,
  // else every five. The clock is the server's (deadline - now) whatever the phone's says. A move made on an old
  // version comes back not applied with the fresh room, and goes once more on that one.
  // The look: the app's orb holds the game's mark; a room's code is four tiles, the same ones a guest types into; the
  // role sits under a cover that lifts only while a finger holds it, and every phone shows the same list of places
  // (the spy's taps name one, nobody else's do anything), so a glance at a neighbour's screen tells nothing.
  import { onDestroy, onMount } from 'svelte';
  import HatGlasses from '@lucide/svelte/icons/hat-glasses';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import Search from '@lucide/svelte/icons/search';
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
  import { SPY_LOCATIONS, roomLink } from '../../lib/games/spy';
  import { haptic, tgShare } from '../../lib/tg';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import Sheet from '../../ui/Sheet.svelte';
  import Qr from '../../ui/Qr.svelte';
  import Orb from '../../ui/Orb.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
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

  // the room this phone is in, kept so the game opened again (Back by mistake, the app relaunched) is the same round
  const KEY = 'kb-spy';
  const keep = (c: string | null) => { try { if (c) localStorage.setItem(KEY, c); else localStorage.removeItem(KEY); } catch { /* storage blocked */ } };
  const kept = () => { try { return localStorage.getItem(KEY); } catch { return null; } };

  function take(r: Room) {
    if (room && r.id === room.id && r.v < room.v) return; // an answer overtaken by a newer one
    if (r.phase !== room?.phase) { shown = false; pick = null; }
    room = r; skew = r.now - Date.now() / 1000;
    keep(r.phase === 'reveal' ? null : r.code);
  }
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
    catch (e) { typed = ''; if (!room) keep(null); if (!quiet) { err = why(e); haptic.error(); if (room) say(err, 'pleading_face_3d'); } }
    finally { busy = null; }
  }
  async function move(m: RoomMove) {
    if (!room) return;
    const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
    try {
      let a = await api.roomMove(room.id, room.v, m, id);
      if (!a.applied && a.room) { take(a.room); a = await api.roomMove(a.room.id, a.room.v, m, id); }
      if (m.type === 'leave') { room = null; typed = ''; keep(null); clearTimeout(timer); return; }
      if (a.room) take(a.room);
      schedule();
    } catch (e) { pick = null; haptic.error(); say(why(e), 'pleading_face_3d'); }
  }
  function type(e: Event & { currentTarget: HTMLInputElement }) {
    const el = e.currentTarget;
    typed = el.value = el.value.replace(/\D/g, '').slice(0, 4);
    err = '';
    if (typed.length === 4) { el.blur(); void enter(api.roomJoin(typed), 'join'); } // the fourth digit is the Join
  }
  // naming a place ends the round: asked first
  async function guess(l: string) {
    if (await sheets.ask({ title: gw('spy.guessAsk', { place: place(l) }), text: gw('spy.guessAskText'), ok: gw('spy.guess'), cancel: t('common.cancel') })) void move({ type: 'guess', location: l });
  }
  function vote(id: Id) { pick = id; haptic.select(); void move({ type: 'vote', target: id }); }
  const hold = (on: boolean) => { if (on !== shown) { shown = on; if (on) haptic.soft(); } };

  onMount(() => {
    const c = code ?? kept();
    if (c) { typed = c; void enter(api.roomJoin(c), 'join', !code); }
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

<!-- the role: in the page only while a finger (or a key) holds the cover -->
{#snippet secret(r: Room, small = false)}
  <button class="secret" class:small class:open={shown} class:spy={shown && r.role === 'spy'} aria-label={gw('spy.hold')} data-nohaptic
    onpointerdown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); hold(true); }} onpointerup={() => hold(false)} onpointercancel={() => hold(false)}
    onkeydown={(e) => { if (e.key === ' ' || e.key === 'Enter') hold(true); }} onkeyup={() => hold(false)} onblur={() => hold(false)}
    oncontextmenu={(e) => e.preventDefault()}>
    <span class="cover">
      <span class="seal">{@render mark(small ? 22 : 34)}</span>
      <span class="ctx"><span class="cap">{gw('spy.role')}</span><b>{gw('spy.hold')}</b></span>
    </span>
    {#if shown}
      <span class="inside">
        {#if r.role === 'spy'}
          {#if !small}{@render mark(40)}{/if}
          <b class="big">{gw('spy.youSpy')}</b>
          {#if !small}<span class="hint">{gw('spy.spyHint')}</span>{/if}
        {:else}
          <span class="cap">{gw('spy.placeCap')}</span>
          <b class="big">{place(r.location ?? '')}</b>
          {#if !small}<span class="hint">{gw('spy.localHint')}</span>{/if}
        {/if}
      </span>
    {/if}
  </button>
{/snippet}

<!-- every phone shows the same list; only the spy's taps name a place -->
{#snippet places(title: string, can: boolean)}
  <section class="places">
    <h3 class="sh">{title}</h3>
    <div class="grid">{#each SPY_LOCATIONS as l (l)}<button class="pl" disabled={!can} onclick={() => guess(l)}>{place(l)}</button>{/each}</div>
  </section>
{/snippet}

<Sheet {overlay} full title={gw('spy.title')} icon={HatGlasses}>
  {#if !room}
    <div class="home stagger">
      <div class="orb"><Orb size={132}><span class="om">{@render mark(56)}</span></Orb></div>
      <h2 class="fs-t1">{gw('spy.title')}</h2>
      <p class="lead">{gw('spy.about')}</p>
      <ul class="facts">
        <li><Users size={15} />{gw('spy.f.players')}</li>
        <li><Timer size={15} />{gw('spy.f.time')}</li>
        <li><Smartphone size={15} />{gw('spy.f.phone')}</li>
      </ul>
      <Button size="l" full lit loading={busy === 'create'} disabled={busy === 'join'} onclick={() => enter(api.roomCreate('spy'), 'create')}>{gw('spy.create')}</Button>
      <p class="or"><span>{gw('spy.orCode')}</span></p>
      <label class="code" class:wait={busy === 'join'} class:bad={!!err}>
        <input inputmode="numeric" autocomplete="off" maxlength="4" aria-label={gw('spy.codePh')} value={typed} oninput={type} disabled={!!busy} />
        {#each [0, 1, 2, 3] as i (i)}<span class="tile num" class:at={i === typed.length} style:--i={i}>{typed[i] ?? ''}</span>{/each}
      </label>
      <p class="err" role="alert">{err}</p>
    </div>
  {:else}
    {@const r = room}
    {#key r.phase}
      <div class="phase stagger">
        {#if r.phase === 'lobby'}
          <section class="invite">
            <p class="cap">{gw('spy.codePh')}</p>
            <div class="digits" role="img" aria-label={gw('spy.code', { code: r.code })}>{#each r.code.split('') as d, i (i)}<span class="tile num">{d}</span>{/each}</div>
            <div class="plate"><Qr text={roomLink(r.code)}><span class="qm">{@render mark(22)}</span></Qr></div>
            <p class="hint">{gw('spy.scan')}</p>
            <Button kind="secondary" full onclick={() => tgShare(roomLink(r.code), gw('spy.shareText'))}>{#snippet icon()}<Send size={18} />{/snippet}{gw('spy.share')}</Button>
          </section>
          <Group caption={gw('spy.players', { n: r.players.length })}>
            {#each r.players as p (p.id)}
              <Row dense title={p.name} value={p.id === r.host ? gw('spy.host') : p.id === r.me ? gw('spy.you') : undefined}>
                {#snippet lead()}<Avatar person={p} size={32} tappable={false} />{/snippet}
              </Row>
            {/each}
            {#each { length: Math.max(0, 3 - r.players.length) } as _, i (i)}
              <Row dense title="" placeholder={gw('spy.seat')}>{#snippet lead()}<i class="seat"></i>{/snippet}</Row>
            {/each}
          </Group>
          {#if r.me === r.host}
            <Group>
              <Row title={gw('spy.minutes')}>
                {#snippet trailing()}
                  <span class="step">
                    <Button kind="gray" size="s" round label={gw('spy.less')} disabled={minutes <= 1} onclick={() => minutes--}>{#snippet icon()}<Minus size={18} />{/snippet}</Button>
                    <b class="num" aria-live="polite">{gw('spy.min', { n: minutes })}</b>
                    <Button kind="gray" size="s" round label={gw('spy.more')} disabled={minutes >= 15} onclick={() => minutes++}>{#snippet icon()}<Plus size={18} />{/snippet}</Button>
                  </span>
                {/snippet}
              </Row>
            </Group>
          {/if}
        {:else if r.phase === 'play'}
          {@const first = who(r.first)}
          {@render time(gw('spy.minutes'))}
          {@render secret(r)}
          {#if first}<p class="first"><Avatar person={first} size={24} tappable={false} /><span>{gw('spy.first', { name: first.name })}</span></p>{/if}
          {@render places(gw('spy.places'), r.role === 'spy')}
        {:else if r.phase === 'vote'}
          {@const mine = pick ?? r.myVote}
          {@render time(gw('spy.vote'))}
          <section class="ballot">
            <h3 class="sh">{gw('spy.voted', { n: r.voted?.length ?? 0, total: r.players.length })}</h3>
            {#each r.players.filter((p) => p.id !== r.me) as p (p.id)}
              <button class="cand" class:on={mine === p.id} aria-pressed={mine === p.id} data-nohaptic onclick={() => vote(p.id)}>
                <span class="face"><Avatar person={p} size={40} tappable={false} />{#if r.voted?.includes(p.id)}<i class="tick" title={gw('spy.hasVoted')}><Check size={11} strokeWidth={3.4} /></i>{/if}</span>
                <b>{p.name}</b>
                <i class="radio"><Check size={15} strokeWidth={3} /></i>
              </button>
            {/each}
          </section>
          {@render secret(r, true)}
        {:else if r.phase === 'guess'}
          {@const spy = who(r.accused)}
          {@render time(gw('spy.guess'))}
          <div class="caught" class:me={r.accused === r.me}>
            {#if spy}<Avatar person={spy} size={72} tappable={false} />{/if}
            <p>{r.accused === r.me ? gw('spy.caughtMe') : gw('spy.caught', { name: spy?.name ?? '' })}</p>
          </div>
          {@render places(gw('spy.places'), r.accused === r.me)}
        {:else if r.result}
          {@const res = r.result}
          {@const spy = who(res.spy)}
          <!-- the orb's light: green when my side won -->
          <header class="end">
            <div class="orb"><Orb size={132} tone={(res.winner === 'spy') === (res.spy === r.me) ? 'success' : 'danger'}><span class="om">{@render mark(56)}</span></Orb></div>
            <h2 class="fs-t1">{gw(res.winner === 'spy' ? 'spy.winSpy' : 'spy.winLocals')}</h2>
            <p class="lead">{gw(`spy.why.${res.why}`)}</p>
          </header>
          <Group>
            {#if spy}<Row dense title={spy.name} value={gw('spy.spyCap')}>{#snippet lead()}<Avatar person={spy} size={32} tappable={false} />{/snippet}</Row>{/if}
            <Row dense title={place(r.location ?? '')} value={gw('spy.placeCap')}>{#snippet lead()}<i class="dot"><MapPin size={17} /></i>{/snippet}</Row>
            {#if res.guess}<Row dense title={place(res.guess)} value={gw('spy.guessCap')}>{#snippet lead()}<i class="dot" class:hit={res.guess === r.location}><Search size={17} /></i>{/snippet}</Row>{/if}
          </Group>
          {#if res.votes.length}
            <Group caption={gw('spy.votes')}>
              {#each res.votes as v (v.from)}
                {@const from = who(v.from)}
                {#if from}
                  <Row dense title={from.name} value={`→ ${nameOf(v.to)}`}>
                    {#snippet lead()}<Avatar person={from} size={32} tappable={false} />{/snippet}
                    {#snippet detail()}{#if v.to === res.spy}<i class="hitmark"><Check size={16} strokeWidth={3} /></i>{/if}{/snippet}
                  </Row>
                {/if}
              {/each}
            </Group>
          {/if}
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
          <Button size="l" full lit disabled={n < 3 || n > 12} onclick={() => move({ type: 'start', minutes })}>{gw('spy.start')}</Button>
        {/if}
        <Button kind="plain" destructive full onclick={() => move({ type: 'leave' })}>{gw('spy.leave')}</Button>
      </div>
    {:else if room?.phase === 'play' && room.me === room.host}
      <Button kind="gray" size="l" full onclick={() => move({ type: 'vote_now' })}>{gw('spy.voteNow')}</Button>
    {:else if room?.phase === 'reveal'}
      <Button size="l" full lit loading={busy === 'create'} onclick={() => enter(api.roomCreate('spy'), 'create')}>{gw('spy.again')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .home, .phase { display: flex; flex-direction: column; gap: var(--gap-group); padding-bottom: var(--s-4); }
  .home { align-items: stretch; gap: var(--s-4); text-align: center; }
  .orb { display: grid; place-items: center; margin: var(--s-2) 0 var(--s-1); }
  .om { color: white; opacity: 0.94; }
  h2, h3, p, ul { margin: 0; }
  .lead { font: 450 var(--fs-body)/1.45 var(--font-text); color: var(--text-2); text-wrap: balance; }
  .cap { font: 600 var(--fs-cap)/1.2 var(--font-text); letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-3); }
  .hint { font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); text-wrap: balance; }
  .sh { font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); margin: 0 var(--s-1); }

  .facts { display: flex; flex-wrap: wrap; justify-content: center; gap: var(--s-2); padding: 0; margin: var(--s-1) 0 var(--s-3); list-style: none; }
  .facts li { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 var(--s-3); border-radius: var(--r-full); background: var(--fill);
    font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-2); }

  .or { display: flex; align-items: center; gap: var(--s-3); margin-top: var(--s-2); font: 450 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  .or::before, .or::after { content: ''; flex: 1; height: 1px; background: var(--separator); }

  /* a code's four tiles: typed into here, shown in the lobby */
  .code, .digits { position: relative; display: flex; justify-content: center; gap: var(--s-2); }
  .tile { display: grid; place-items: center; width: 56px; height: 68px; border-radius: var(--r-m); background: var(--fill);
    font: 700 var(--fs-title)/1 var(--font-display); letter-spacing: -0.02em; color: var(--text); transition: box-shadow var(--t-fast) var(--ease); }
  .code input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; font-size: var(--fs-row); text-align: center; }
  .code:focus-within .tile.at { box-shadow: inset 0 0 0 2px var(--accent); }
  .code:focus-within .tile.at::after { content: ''; width: 2px; height: 28px; border-radius: var(--r-full); background: var(--accent); animation: blink 1.1s steps(1) infinite; }
  .code.wait .tile { animation: wait 1s var(--ease) calc(var(--i) * 120ms) infinite alternate; }
  .code.bad { animation: shake 360ms var(--ease); }
  .code.bad .tile { box-shadow: inset 0 0 0 1.5px var(--danger); }
  .err { min-height: 1.4em; margin-top: calc(var(--s-2) * -1); font: 600 var(--fs-sub)/1.4 var(--font-text); color: var(--danger-text); }

  .invite { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--card-pad); border-radius: var(--r-l);
    background: var(--surface); box-shadow: var(--card-rim); text-align: center; }
  .invite .tile { background: var(--fill); }
  /* a white plate in both themes: a camera reads dark on white */
  .plate { width: 168px; padding: var(--s-3); border-radius: var(--r-l); background: white; box-shadow: var(--shadow-thumb); }
  .qm { display: grid; place-items: center; width: 100%; height: 100%; border-radius: var(--r-xs); background: var(--ink); color: white; }
  .seat { width: 32px; height: 32px; border-radius: var(--r-full); border: 1.5px dashed var(--line-2); animation: wait 1.2s var(--ease) infinite alternate; }
  .step { display: inline-flex; align-items: center; gap: var(--s-2); }
  .step b { min-width: 4.2em; text-align: center; font: 600 var(--fs-row)/1 var(--font-text); }

  .ft { display: flex; flex-direction: column; gap: var(--s-2); }
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

  .secret { position: relative; display: grid; place-items: center; width: 100%; min-height: 196px; border-radius: var(--r-xl); overflow: hidden;
    background: var(--surface); box-shadow: var(--card-rim); color: var(--text); text-align: center;
    touch-action: none; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; transition: transform var(--t-base) var(--ease-bounce); }
  .secret.small { min-height: 76px; border-radius: var(--r-l); }
  .secret.open { transform: scale(0.975); background: linear-gradient(var(--accent-soft), var(--accent-soft)), var(--surface); }
  .secret.spy { background: linear-gradient(var(--danger-soft), var(--danger-soft)), var(--surface); }
  /* the cover: fine rings around the seal, like a stamp's */
  .cover { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s-3); padding: var(--s-4);
    background: repeating-radial-gradient(circle at 50% 38%, transparent 0 15px, var(--line) 15px 16px);
    transition: opacity var(--t-base) var(--ease), transform var(--t-slow) var(--ease); }
  .small .cover { flex-direction: row; justify-content: flex-start; padding: 0 var(--s-5); background: none; text-align: left; }
  .open .cover { opacity: 0; transform: scale(1.1); }
  .seal { position: relative; display: grid; place-items: center; width: 68px; height: 68px; border-radius: var(--r-full); background: var(--grad-accent); color: white; }
  .small .seal { width: 44px; height: 44px; flex: none; }
  .seal::after { content: ''; position: absolute; inset: 0; border-radius: inherit; box-shadow: 0 0 0 1.5px var(--accent); opacity: 0; animation: ring 2.4s var(--ease) infinite; }
  .ctx { display: flex; flex-direction: column; gap: var(--s-1); }
  .ctx b { font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .inside { position: relative; display: flex; flex-direction: column; align-items: center; gap: var(--s-2); padding: var(--s-5); animation: rise var(--t-base) var(--ease) both; }
  .inside .big { font: 700 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.02em; }
  .small .inside { padding: var(--s-3); gap: 2px; }
  .small .inside .big { font-size: var(--fs-t3); }
  .spy .inside { color: var(--danger-text); }
  .spy .inside .hint { color: var(--text-2); }

  .first { display: flex; align-items: center; justify-content: center; gap: var(--s-2); margin-top: calc(var(--s-2) * -1); font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }

  .places, .ballot { display: flex; flex-direction: column; gap: var(--s-2); }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
  .pl { min-height: var(--row-dense); padding: var(--s-2) var(--s-3); border-radius: var(--r-m); background: var(--surface); box-shadow: var(--card-rim);
    font: 600 var(--fs-sub)/1.25 var(--font-text); color: var(--text); text-align: center; opacity: 1; overflow-wrap: anywhere; transition: transform var(--t-fast) var(--ease); }
  .pl:enabled:active { transform: scale(0.96); }
  .pl:disabled { cursor: default; }

  .cand { display: flex; align-items: center; gap: var(--s-3); width: 100%; min-height: var(--row-h2); padding: var(--s-2) var(--s-4) var(--s-2) var(--s-3);
    border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim); transition: background-color var(--t-base) var(--ease), transform var(--t-fast) var(--ease); }
  .cand:active { transform: scale(0.98); }
  .cand b { flex: 1; min-width: 0; font: 600 var(--fs-row)/1.25 var(--font-text); overflow-wrap: anywhere; }
  .cand.on { background: var(--accent-soft); box-shadow: inset 0 0 0 1.5px var(--accent); }
  .face { position: relative; flex: none; display: inline-flex; }
  .tick { position: absolute; right: -3px; bottom: -3px; display: grid; place-items: center; width: 17px; height: 17px; border-radius: var(--r-full);
    background: var(--success); color: white; box-shadow: 0 0 0 2px var(--surface-solid); animation: pop var(--t-slow) var(--ease-bounce) both; }
  .radio { flex: none; display: grid; place-items: center; width: 26px; height: 26px; border-radius: var(--r-full); box-shadow: inset 0 0 0 1.5px var(--line-2); color: transparent;
    transition: background-color var(--t-base) var(--ease), transform var(--t-slow) var(--ease-bounce); }
  .on .radio { background: var(--accent); box-shadow: none; color: var(--on-accent); transform: scale(1.08); }

  .caught { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--s-5); border-radius: var(--r-l);
    background: var(--surface); box-shadow: var(--card-rim); text-align: center; font: 600 var(--fs-row)/1.3 var(--font-text); text-wrap: balance; }
  .caught.me { background: linear-gradient(var(--danger-soft), var(--danger-soft)), var(--surface); color: var(--danger-text); }

  .end { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); text-align: center; }
  .dot { display: grid; place-items: center; width: 32px; height: 32px; border-radius: var(--r-full); background: var(--fill); color: var(--text-2); }
  .dot.hit, .hitmark { color: var(--success-text); }
  .dot.hit { background: var(--success-soft); }
  .hitmark { display: inline-flex; }

  @keyframes blink { 50% { opacity: 0; } }
  @keyframes wait { from { opacity: 1; } to { opacity: 0.35; } }
  @keyframes shake { 20% { transform: translateX(-8px); } 45% { transform: translateX(7px); } 70% { transform: translateX(-4px); } 90% { transform: translateX(2px); } }
  @keyframes ring { 0% { opacity: 0.7; transform: scale(1); } 70%, 100% { opacity: 0; transform: scale(1.5); } }
  @keyframes rise { from { opacity: 0; transform: scale(0.94); } }
  @keyframes pop { from { transform: scale(0); } }
  @media (prefers-reduced-motion: reduce) {
    .seal::after, .seat, .dots i, .code.wait .tile, .code.bad, .inside, .tick { animation: none; }
  }
  :global(html.lowfx) .seal::after { animation: none; }
</style>
