// The frames in plan units (the 2023 plan's): the old map is the plan itself, ours a 1000-unit square cut of it at
// (120, 130), Uni-Q's sheet fitted to it by its room numbers (design/map/tools/clean, median error ~9 units). A spot
// marked on one map is found on another through these (CampusMap: switching maps, a flaw's pin on another map).
import uniq from '../../assets/map/uniq-tiles.json';
import type { Ver } from '../../lib/mapgl';

const FIT = [[0.186469, 0.000447], [-0.001899, 0.196124], [9.528454, 5.881245]];
/** each map's width in plan units */
export const UNITS: Record<Ver, number> = { main: uniq.w * FIT[0][0], old: 1240, kbtu: 1000 };

/** a point of map `v` (fractions of its width and height) in plan units */
export function toPlan(v: Ver, u: number, w: number): [number, number] {
  if (v === 'old') return [u * 1240, w * 1240];
  if (v === 'kbtu') return [120 + u * 1000, 130 + w * 1000];
  const px = u * uniq.w, py = w * uniq.h;
  return [px * FIT[0][0] + py * FIT[1][0] + FIT[2][0], px * FIT[0][1] + py * FIT[1][1] + FIT[2][1]];
}

/** plan units back to a point of map `v` */
export function fromPlan(v: Ver, X: number, Y: number): [number, number] {
  if (v === 'old') return [X / 1240, Y / 1240];
  if (v === 'kbtu') return [(X - 120) / 1000, (Y - 130) / 1000];
  const [[a, c], [b, d], [e, f]] = FIT, X0 = X - e, Y0 = Y - f, det = a * d - b * c;
  return [(d * X0 - b * Y0) / det / uniq.w, (a * Y0 - c * X0) / det / uniq.h];
}
