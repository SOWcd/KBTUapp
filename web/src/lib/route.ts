// Indoor routes (PLAN item 22): the graph the owner edits on the main map (corridor points, stairs and lifts that repeat
// on their floors under one id, exits with their hours) and the ways over it. Points are fractions of the plan's width
// and height, as uniq-rooms.json has them; all floors share one frame, so a staircase sits at the same (u, v) on each.

/** k: stairs, lift, exit (else a corridor point); g: the staircase's or lift's id on all its floors; r: rooms whose door
 *  opens here; b: backup, only when there is no other way (owner, Oct 11); h: an exit's hours Mon-Fri, Sat, Sun */
export type MapNode = { id: number; f: number; u: number; v: number; k?: 's' | 'l' | 'x'; g?: number; name?: string; r?: string[]; b?: boolean; h?: string[] };
export type Graph = { n: MapNode[]; e: [number, number][]; ver: number };
export type Mode = 'fast' | 'lift' | 'alt';
export type Pt = { f: number; u: number; v: number; node?: MapNode };
export type Leg = { f: number; pts: Pt[]; up?: MapNode; to?: number };
export type Route = { mode: Mode; secs: number; legs: Leg[]; via: number[] };

// ponytail: one guessed scale for the whole plan (about 250 m across, the wings ~170 m apart); calibrate against a measured corridor
export const PLAN_M = 250;
const WALK = 1.2, STAIR = 20, LIFT_WAIT = 40, LIFT_FLOOR = 8, BACKUP = 600; // m/s, s per flight, s, s, s for a backup point

/** a point's distance in metres on one floor; ar: the plan's height to its width */
export const metres = (a: { u: number; v: number }, b: { u: number; v: number }, ar: number) => Math.hypot(a.u - b.u, (a.v - b.v) * ar) * PLAN_M;

/** Is an exit open at `d` (local time)? Hours per Mon-Fri, Sat, Sun, "07:00-18:00"; "22:00-07:00" runs past midnight; "" closed */
export function openAt(n: MapNode, d: Date): boolean {
  const h = n.h?.[d.getDay() === 0 ? 2 : d.getDay() === 6 ? 1 : 0];
  if (!h) return false;
  const [a, b] = h.split('-').map((x) => +x.slice(0, 2) * 60 + +x.slice(3)), m = d.getHours() * 60 + d.getMinutes();
  return a <= b ? m >= a && m < b : m >= a || m < b;
}

type Arc = { to: number; w: number; stair?: number; lift?: boolean };
function arcs(g: Graph, ar: number): Map<number, Arc[]> {
  const by = new Map(g.n.map((n) => [n.id, n])), adj = new Map<number, Arc[]>(g.n.map((n) => [n.id, []]));
  const add = (a: number, b: number, x: Omit<Arc, 'to'>) => { adj.get(a)!.push({ to: b, ...x }); adj.get(b)!.push({ to: a, ...x }); };
  for (const [a, b] of g.e) { const A = by.get(a), B = by.get(b); if (A && B && A.f === B.f) add(a, b, { w: metres(A, B, ar) / WALK }); }
  // a staircase links each of its floors to the next it reaches (one from 3 to 5 skips 4); a lift any two, with the wait
  const groups = new Map<string, MapNode[]>();
  for (const n of g.n) if ((n.k === 's' || n.k === 'l') && n.g != null) groups.set(`${n.k}${n.g}`, [...(groups.get(`${n.k}${n.g}`) ?? []), n]);
  for (const ns of groups.values()) {
    ns.sort((a, b) => a.f - b.f);
    ns.forEach((a, i) => ns.slice(i + 1).forEach((b) => {
      if (a.k === 'l') add(a.id, b.id, { w: LIFT_WAIT + LIFT_FLOOR * (b.f - a.f), lift: true });
      else if (b === ns[i + 1]) add(a.id, b.id, { w: STAIR * (b.f - a.f), stair: a.g });
    }));
  }
  return adj;
}

/** Where a room, or any point, joins the graph: the point its door opens onto (r), else the nearest spot on a corridor of
 *  its floor (the room's number sits in the room; its door is on the corridor beside it). [node, seconds to walk there,
 *  the spot on the corridor: drawn, so the line leaves the room straight into the corridor, not through walls] */
export type At = [number, number, { u: number; v: number }?];
export function attach(g: Graph, p: Pt, ar: number, name?: string): At[] {
  const named = name && g.n.find((n) => n.f === p.f && (n.r?.includes(name) || n.name === name));
  if (named) return [[named.id, 0]];
  const by = new Map(g.n.map((n) => [n.id, n]));
  let best: At[] = [], bd = Infinity;
  for (const [a, b] of g.e) {
    const A = by.get(a), B = by.get(b);
    if (!A || !B || A.f !== p.f || B.f !== p.f) continue;
    const dx = B.u - A.u, dy = (B.v - A.v) * ar, L = dx * dx + dy * dy;
    const t = L ? Math.max(0, Math.min(1, ((p.u - A.u) * dx + (p.v - A.v) * ar * dy) / L)) : 0;
    const q = { u: A.u + dx * t, v: A.v + (dy * t) / ar }, d = metres(p, q, ar);
    if (d < bd) { bd = d; best = [[a, (d + metres(q, A, ar)) / WALK, q], [b, (d + metres(q, B, ar)) / WALK, q]]; }
  }
  if (!best.length) for (const n of g.n) if (n.f === p.f && metres(p, n, ar) < bd) { bd = metres(p, n, ar); best = [[n.id, bd / WALK]]; }
  return best;
}

// ponytail: Dijkstra with a linear scan for the next point; fine for a few thousand points, a heap if the graph grows past that
function shortest(g: Graph, adj: Map<number, Arc[]>, from: At[], to: Map<number, number>, ok: (a: Arc) => boolean, extra: (a: Arc) => number) {
  const by = new Map(g.n.map((n) => [n.id, n])), dist = new Map<number, number>(), prev = new Map<number, number>(), done = new Set<number>();
  for (const [id, w] of from) if (w < (dist.get(id) ?? Infinity)) dist.set(id, w);
  let best = Infinity, end = -1;
  for (;;) {
    let cur = -1, cd = Infinity;
    for (const [id, d] of dist) if (!done.has(id) && d < cd) { cur = id; cd = d; }
    if (cur < 0 || cd >= best) break;
    done.add(cur);
    const last = to.get(cur);
    if (last != null && cd + last < best) { best = cd + last; end = cur; }
    for (const a of adj.get(cur) ?? []) {
      if (!ok(a)) continue;
      const w = cd + a.w + extra(a) + (by.get(a.to)?.b ? BACKUP : 0);
      if (w < (dist.get(a.to) ?? Infinity)) { dist.set(a.to, w); prev.set(a.to, cur); }
    }
  }
  if (end < 0) return null;
  const ids = [end];
  while (prev.has(ids[0])) ids.unshift(prev.get(ids[0])!);
  return { secs: best, ids };
}

/** The ways from a to b: the fastest by stairs, by lift (when the floor changes), and another staircase's when it differs
 *  and is at most 30% longer (owner, Oct 15). b may be a set of points (the exits open now). */
export function routes(g: Graph, ar: number, a: { at: At[]; pt: Pt }, b: { at: At[]; pt?: Pt }): Route[] {
  const adj = arcs(g, ar), by = new Map(g.n.map((n) => [n.id, n])), to = new Map(b.at.map(([id, w]) => [id, w]));
  const make = (mode: Mode, r: { secs: number; ids: number[] } | null): Route | null => {
    if (!r) return null;
    // between the room's number and the corridor: the spot on the corridor, or an elbow to its door point, so the line
    // runs along the room and turns out through the door, not across walls (owner, Oct 15: an "L", not a diagonal)
    const ns = r.ids.map((id) => by.get(id)!), end = (p: Pt, at: At[], d: MapNode, next?: MapNode): Pt[] => {
      const q = at.find((x) => x[0] === d.id)?.[2];
      if (q) return [{ f: p.f, ...q }];
      if (!next || next.f !== d.f || p.f !== d.f) return [];
      const along = Math.abs(next.v - d.v) * ar > Math.abs(next.u - d.u); // the corridor runs up and down here
      return [{ f: p.f, u: along ? p.u : d.u, v: along ? d.v : p.v }];
    };
    const pts: Pt[] = [a.pt, ...end(a.pt, a.at, ns[0], ns[1]), ...ns.map((n) => ({ f: n.f, u: n.u, v: n.v, node: n })),
      ...(b.pt ? [...end(b.pt, b.at, ns[ns.length - 1], ns[ns.length - 2]).reverse(), b.pt] : [])];
    const legs: Leg[] = [{ f: pts[0].f, pts: [] }];
    for (const p of pts) {
      const leg = legs[legs.length - 1];
      if (p.f !== leg.f) { const up = leg.pts[leg.pts.length - 1]?.node; Object.assign(leg, { up, to: p.f }); legs.push({ f: p.f, pts: [] }); }
      legs[legs.length - 1].pts.push(p);
    }
    // straight up several flights: one step, "to floor 4", not a stop on each floor
    for (let i = 0; i < legs.length - 1; i++) while (legs[i + 1].pts.length === 1 && legs[i + 1].to != null) { legs[i].to = legs[i + 1].to; legs.splice(i + 1, 1); }
    const via = r.ids.map((id) => by.get(id)!).filter((n) => n.k === 's' || n.k === 'l').map((n) => n.g!);
    return { mode, secs: r.secs - BACKUP * ns.filter((n) => n.b).length, legs, via }; // the walk, not the backup's penalty
  };
  const fast = make('fast', shortest(g, adj, a.at, to, (x) => !x.lift, () => 0));
  if (!fast) return [];
  const out = [fast];
  if (fast.legs.length > 1) {
    const lift = make('lift', shortest(g, adj, a.at, to, (x) => x.stair == null, () => 0));
    if (lift) out.push(lift);
    const used = new Set(fast.via), alt = make('alt', shortest(g, adj, a.at, to, (x) => !x.lift, (x) => (x.stair != null && used.has(x.stair) ? BACKUP : 0)));
    if (alt && alt.secs <= fast.secs * 1.3 && alt.via.some((s) => !used.has(s))) out.push(alt);
  }
  return out;
}
