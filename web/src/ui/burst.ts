// Emoji burst on «Going» (a prototype favourite): fresh nodes per tap in one fixed layer, Web
// Animations on transform + opacity only, paths clamped to stay on screen, the layer is removed
// when the last emoji lands. Happy = a fountain up with a soft fall; sad = a short drop, like tears.
// It starts where the finger last touched, so callers don't have to pass coordinates (or from a given point).
const HAPPY = ['party_popper_3d', 'fire_3d', 'sparkles_3d', 'partying_face_3d', 'high_voltage_3d', 'blue_heart_3d', 'raising_hands_3d_default', 'trophy_3d'];
const SAD = ['loudly_crying_face_3d', 'crying_face_3d', 'broken_heart_3d', 'pleading_face_3d'];

const last = { x: innerWidth / 2, y: innerHeight / 2 };
addEventListener('pointerdown', (e) => { last.x = e.clientX; last.y = e.clientY; }, { capture: true, passive: true });

/** `emoji`: one of the moment's own (the event's) mixed into the happy ones, every third. */
export function burst(sad = false, from?: { x: number; y: number }, emoji?: string | null): void {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !Element.prototype.animate) return;
  const lite = document.documentElement.classList.contains('lowfx'); // power saving: half the emoji
  const { x, y } = from ?? last, W = innerWidth, H = innerHeight, n = (sad ? 8 : 16) / (lite ? 2 : 1), set = sad ? SAD : HAPPY;
  const layer = document.createElement('div');
  layer.className = 'burst';
  document.body.append(layer);
  // A real throw (the old one was slow and stiff, and near an edge it stacked the emoji in a column):
  // each emoji flies a parabola under gravity, sampled into keyframes; the fountain leans toward the screen's middle,
  // and a path that would leave the screen is narrowed as a whole, never squashed against the edge.
  const g = sad ? 1500 : 2400, lean = Math.max(-1, Math.min(1, (W / 2 - x) / (W / 2)));
  let left = n;
  for (let i = 0; i < n; i++) {
    const sz = sad ? 32 + Math.random() * 16 : 30 + Math.random() * 24;
    const rise = sad ? 20 + Math.random() * 40 : Math.min(y - 90, 140 + Math.random() * 170); // the top of the arc above the finger
    const vy = -Math.sqrt(2 * g * Math.max(rise, 20));
    const T = (sad ? 1.0 : 0.95) + Math.random() * 0.25;
    let vx = (lean * (sad ? 40 : 170)) + (Math.random() - 0.5) * (sad ? 160 : 420);
    const reach = vx * T; // keep the whole path on screen
    const room = reach > 0 ? W - 10 - sz / 2 - x : x - 10 - sz / 2;
    if (Math.abs(reach) > room) vx *= Math.max(0, room) / Math.abs(reach);
    const spin = vx * 0.25 + (Math.random() - 0.5) * 60;
    const frames: Keyframe[] = [];
    for (let k = 0; k <= 12; k++) {
      const f = k / 12, t = f * T;
      const fy = Math.min(H - y - sz / 2, vy * t + (g * t * t) / 2);
      const sc = f < 0.12 ? 0.3 + (f / 0.12) * 0.9 : f < 0.22 ? 1.2 - ((f - 0.12) / 0.1) * 0.2 : 1 - (f - 0.22) * 0.2;
      frames.push({ transform: `translate(${(vx * t).toFixed(1)}px,${fy.toFixed(1)}px) scale(${sc.toFixed(3)}) rotate(${(spin * f).toFixed(1)}deg)`, opacity: f < 0.7 ? 1 : (1 - f) / 0.3 });
    }
    const img = document.createElement('img');
    img.src = `emoji/${!sad && emoji && i % 3 === 0 ? emoji : set[i % set.length]}.webp`;
    img.alt = '';
    img.style.cssText = `left:${x - sz / 2}px;top:${y - sz / 2}px;width:${sz}px;height:${sz}px`;
    layer.append(img);
    img.animate(frames, { duration: T * 1000, delay: Math.random() * (sad ? 140 : 70), easing: 'linear', fill: 'both' })
      .onfinish = () => { if (!--left) layer.remove(); };
  }
}
