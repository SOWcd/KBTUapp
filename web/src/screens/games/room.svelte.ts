// One game room on this phone (server logic/rooms.py): the room as the server last showed it, kept fresh by a poll that
// sends the version it has (the server answers nothing while nothing changed), and actions that carry an id and that
// version. ponytail: a poll, not a push, because the API runs in several worker processes with nothing shared in
// memory (server rooms.py); 1 s while a round runs or the lobby fills, 5 s once it's over, none while the app is hidden.
// Deadlines are the server's absolute times; `left()` counts down on the server's clock (the skew from its `now`).
import { api, ApiErr, type SpyAct, type SpyRoom } from '../../lib/api';

const LIVE_MS = 1000, IDLE_MS = 5000;

/** an action's id: the same on its retry, so the server does it once */
const actionId = (): string => globalThis.crypto?.randomUUID?.().replace(/-/g, '')
  ?? Array.from({ length: 4 }, () => Math.random().toString(16).slice(2, 10).padEnd(8, '0')).join('');

export class Room {
  room = $state<SpyRoom | null>(null);
  /** the room closed or I'm no longer in it (left, swept): the screen goes back to the start */
  gone = $state(false);
  /** an action on its way (its name), for the tapped control's pressed state */
  busy = $state<SpyAct['act'] | null>(null);
  /** the server's clock minus this phone's, in ms */
  #skew = 0;
  #timer: ReturnType<typeof setTimeout> | null = null;
  #stopped = false;
  #polling = false;

  constructor(first: SpyRoom) {
    this.#take(first);
    document.addEventListener('visibilitychange', this.#wake);
    this.#next();
  }

  /** seconds left to the phase's deadline on the server's clock (0 when none or passed) */
  left(now = Date.now()): number {
    const d = this.room?.deadline;
    return d ? Math.max(0, d - (now + this.#skew) / 1000) : 0;
  }

  /** do it now on this phone (`guess`: what the server will most likely answer), then send it; the server's room wins */
  async act(a: SpyAct, guess?: (r: SpyRoom) => void): Promise<boolean> {
    const r = this.room;
    if (!r || this.busy) return false;
    if (guess) { const next = structuredClone($state.snapshot(r)) as SpyRoom; guess(next); this.room = next; }
    this.busy = a.act;
    const id = actionId();
    try {
      for (let i = 0; ; i++) {
        try {
          const res = await api.roomAct(r.id, r.v, id, a);
          this.#take(res.room, true);
          return res.applied;
        } catch (e) {
          // the line dropped: the same id again, once (done already, the server says so); refused: back to what it shows
          if (i === 0 && e instanceof ApiErr && e.code === 'unavailable') continue;
          if (e instanceof ApiErr && e.code === 'not_found') this.gone = true;
          void this.#poll(true);
          throw e;
        }
      }
    } finally { this.busy = null; }
  }

  async leave(): Promise<void> {
    const r = this.room;
    this.stop();
    if (r) await api.roomLeave(r.id).catch(() => {});
  }

  stop(): void {
    this.#stopped = true;
    if (this.#timer) clearTimeout(this.#timer);
    document.removeEventListener('visibilitychange', this.#wake);
  }

  #take(r: SpyRoom, force = false): void {
    if (!force && this.room && r.v < this.room.v) return; // an older answer overtaken by a newer one
    this.#skew = r.now * 1000 - Date.now();
    this.room = r;
  }

  #next(): void {
    if (this.#stopped) return;
    if (this.#timer) clearTimeout(this.#timer);
    this.#timer = setTimeout(() => void this.#poll(), this.room?.phase === 'over' ? IDLE_MS : LIVE_MS);
  }

  #wake = (): void => { if (!document.hidden) void this.#poll(true); };

  async #poll(full = false): Promise<void> {
    if (this.#stopped || this.#polling || document.hidden) { if (!document.hidden) this.#next(); return; }
    this.#polling = true;
    try {
      const r = this.room;
      if (!r) return;
      const fresh = await api.room(r.id, full ? undefined : r.v);
      if (fresh) this.#take(fresh);
    } catch (e) {
      if (e instanceof ApiErr && e.code === 'not_found') { this.gone = true; this.stop(); }
    } finally {
      this.#polling = false;
      this.#next();
    }
  }
}

/** the room I'm in (the app opened again mid-game), or null */
export const myRoom = (): Promise<SpyRoom | null> => api.roomMine().then((x) => x.room, () => null);
export const newRoom = (): Promise<SpyRoom> => api.roomNew('spy');
export const joinRoom = (code: string): Promise<SpyRoom> => api.roomJoin(code);
