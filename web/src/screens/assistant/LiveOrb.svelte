<script lang="ts">
  // KRI's light, alive (Fable's orb, the owner's pick): a fragment shader (lib/gl.ts) laid over the CSS orb (ui/Orb) in
  // the same box. A glass sphere with a nebula inside: a domain-warped gyroid gas marched through in 12 steps behind a
  // refracting shell, stars on three depth shells that parallax through the lens, a halo and a caustic pool on the
  // floor. The gas leans toward a finger and the sphere tilts after it; "thinking" swirls it faster and pulses its core.
  // Dark: light added over the night; light: the same glass on a pale shell, its glow a violet tint laid on the day.
  // The CSS orb is what the screen opens with: the shader builds after the first paint and the landing, runs its first
  // frames unseen to time them, then fades in over it while its nebula blooms. It stays the CSS orb on a weak phone,
  // with less motion, under power saving (which also covers Telegram's LOW class and a low battery), with no WebGL, or
  // when the first frames are too slow.
  //   start   the box is in its place (not flying in): it may begin
  //   energy  0 at rest, 0.5 listening (a draft in the field), 1 thinking (an answer on its way)
  //   hold    nothing to draw for now (covered by another sheet, faded for the keyboard): frames stop
  //   on      out: the shader is showing (the parent hides its CSS orb under it)
  import { shade, weak, type Run, type Shader } from '../../lib/gl';
  import { power } from '../../lib/state/power.svelte';
  import { theme } from '../../lib/state/theme.svelte';

  let { start, energy = 0, hold = false, on = $bindable(false) }: { start: boolean; energy?: number; hold?: boolean; on?: boolean } = $props();

  // GLSL 100: WebGL1 and 2 both take it. The box is 1.6 balls wide and 1.75 tall (room under it for the pool): the
  // ball's radius is uRes.x / 3.2, its centre half a width down from the top
  const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 uRes;
uniform float uTime, uSwirl, uFlow, uThink, uPulse, uTouch, uIntro, uLight;
uniform vec3 uPtr;
uniform mat3 uTilt;
const int N = 12;
float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float ign(vec2 p) { return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715)))); }
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
// the drifting gas: a domain-warped gyroid with a swirl that turns faster toward the middle
vec2 gas(vec3 p) {
  float r = length(p);
  p.xz = rot(uSwirl + (1.0 - r) * mix(1.5, 2.9, uThink)) * p.xz;
  vec3 q = p * 2.3 + vec3(0.0, uFlow * 0.15, 0.0);
  q += 0.60 * sin(q.yzx * 1.15 + uFlow);
  q += 0.30 * sin(q.zxy * 2.30 - uFlow * 0.7);
  float n1 = dot(sin(q), cos(q.yzx * 1.3));
  float n2 = dot(sin(q * 2.4 + 1.3), cos(q.zxy * 2.1));
  return vec2(n1 * 0.42 + n2 * 0.20 + 0.25, n2);
}
float star(vec2 uv, float k) {
  vec2 g = floor(uv), f = fract(uv) - 0.5;
  float h = hash(g), h2 = hash(g + 71.7);
  vec2 o = f - (vec2(h, h2) - 0.5) * 0.7;
  float on = step(0.5, fract(h * 13.7 + h2 * 5.3));
  float tw = 0.65 + 0.35 * sin(uTime * (0.8 + h * 1.7) + h2 * 40.0);
  return exp(-dot(o, o) * mix(500.0, 1500.0, h2) * k) * on * tw * (0.35 + 0.65 * h);
}
void main() {
  vec2 fc = gl_FragCoord.xy;
  float rad = uRes.x / 3.2 * (0.94 + 0.06 * uIntro);
  vec2 p = (fc - vec2(uRes.x * 0.5, uRes.y - uRes.x * 0.5)) / rad;
  float r = length(p);
  vec3 VIO = vec3(0.46, 0.28, 1.0), IND = vec3(0.16, 0.18, 0.85), LAV = vec3(0.80, 0.74, 1.0);
  float energy = 1.0 + 0.55 * uPulse + 0.3 * uTouch;
  // outside: the halo and the caustic pool under the sphere, faded at the box's edges
  float d = max(r - 1.0, 0.0);
  float halo = (exp(-d * 7.0) * 0.16 + exp(-d * 2.4) * 0.045) * energy * smoothstep(0.62, 0.1, d);
  vec2 e = (p - vec2(uPtr.x * uTouch * 0.07, -1.40)) / vec2(0.74, 0.07);
  float ee = dot(e, e);
  float sh = sin(p.x * 7.0 + uFlow * 1.3 + 1.5 * sin(p.x * 3.0 - uFlow * 0.8));
  float pool = exp(-ee * 0.8) * energy, caus = exp(-ee * 4.0) * (0.20 + 0.05 * sh) * energy;
  vec2 uv = fc / uRes;
  float edge = uIntro * smoothstep(0.0, 0.06, uv.x) * smoothstep(1.0, 0.94, uv.x) * smoothstep(0.0, 0.05, uv.y) * smoothstep(1.0, 0.95, uv.y);
  vec3 outD = (VIO * halo + IND * pool * 0.34 + LAV * caus) * edge;
  float aH = halo * 1.2 * edge, aP = (pool * 0.22 + caus * 0.3) * edge;
  vec4 outL = vec4(VIO * 0.62 * aH + mix(IND, VIO, 0.5) * 0.45 * aP, aH + aP);

  vec3 inD = vec3(0.0), inL = vec3(0.0);
  float mask = 0.0;
  if (r < 1.0) {
    float z = sqrt(1.0 - r * r);
    vec3 n = vec3(p, z);
    vec3 rd = refract(vec3(0.0, 0.0, -1.0), n, 0.75);
    float chord = -2.0 * dot(n, rd);
    float dt = chord / float(N);
    float t = dt * ign(fc);
    vec3 acc = vec3(0.0), accL = vec3(0.0);
    float T = 1.0, wL = 0.0, core = 0.0;
    vec3 lean = uPtr * uTouch * 0.16;
    float coreK = mix(9.0, 6.5, uPulse), coreG = 0.55 + 1.5 * uPulse + 0.3 * uTouch;
    for (int i = 0; i < N; i++) {
      vec3 pos = n + rd * t;
      vec3 dp = uPtr - pos;
      float pull = uTouch * exp(-dot(dp, dp) * 1.1);
      vec3 w = uTilt * (pos - dp * pull * 0.42);
      float rr = length(pos - lean);
      float env = smoothstep(1.02, 0.2, rr);
      vec2 g = gas(w);
      float den = clamp(g.x, 0.0, 1.4); den = den * den * env * env;
      vec3 c = mix(vec3(0.16, 0.20, 0.95), vec3(0.62, 0.26, 1.0), smoothstep(-0.8, 0.8, g.y));
      c = mix(IND * 0.7, c, smoothstep(0.0, 0.9, g.x)) + LAV * den * den * 0.5;
      float a = 1.0 - exp(-den * dt * 3.2);
      vec3 lit = T * c * a * (1.0 + pull * 1.6 + uThink * 0.25);
      acc += lit * 1.9; accL += lit; wL += T * a;
      float k = T * exp(-rr * rr * coreK) * dt * coreG;
      acc += vec3(0.74, 0.62, 1.0) * k; core += k;
      T *= 1.0 - a * 0.85;
      t += dt;
    }
    // the stars on three depth shells: true parallax through the lens
    float sk = clamp((rad / 236.0) * (rad / 236.0), 0.25, 1.6), st = 0.0;
    for (int i = 0; i < 3; i++) {
      float fi = float(i);
      vec3 sp = uTilt * (n + rd * chord * (0.22 + 0.27 * fi));
      sp.xz = rot(uSwirl * 0.3 * (1.0 - fi * 0.3) + fi * 2.1) * sp.xz;
      st += star(sp.xy * (4.5 + fi * 1.5) + fi * 17.3, sk) * (1.0 - fi * 0.22);
    }
    // the glass shell: fresnel, a rim lit from the top left, a crescent of the nebula's light bottom right, the specular
    float fres = pow(1.0 - z, 2.6);
    vec2 nx = p / max(r, 1e-4);
    vec3 L = normalize(vec3(-0.5, 0.72, 0.48));
    vec3 R = vec3(2.0 * z * n.xy, 2.0 * z * z - 1.0);
    float sp2 = max(dot(R, L), 0.0);
    float spec = pow(sp2, 48.0) * 0.42 + pow(sp2, 8.0) * 0.05;
    float rimTop = fres * (0.25 + 0.75 * smoothstep(-0.3, 0.9, dot(nx, normalize(vec2(-0.5, 0.8)))));
    float cres = smoothstep(0.55, 1.0, r) * pow(max(dot(nx, normalize(vec2(0.45, -0.85))), 0.0), 2.5);
    float it2 = uIntro * uIntro;
    inD = acc * it2 * (1.0 - 0.3 * fres);
    inD += vec3(0.92, 0.9, 1.0) * st * mix(1.0, T, 0.85) * uIntro;
    inD += vec3(0.010, 0.008, 0.026);
    inD += vec3(0.75, 0.72, 1.0) * rimTop * 0.55;
    inD += vec3(0.50, 0.38, 1.0) * cres * 0.42 * energy * mix(0.5, 1.0, uIntro);
    inD += vec3(0.60, 0.55, 1.0) * smoothstep(0.9, 1.0, r) * 0.10;
    inD += vec3(1.0) * spec;
    // in daylight: the gas's own colour over a pale shell, the core a white glow, the rim's edge a violet line
    vec3 gc = accL / max(wL, 1e-3);
    inL = mix(vec3(0.95, 0.95, 1.0), gc * 1.05, (1.0 - T) * 0.9 * it2);
    inL = mix(inL, vec3(1.0, 0.97, 1.0), clamp(core * 0.8 * it2, 0.0, 1.0));
    inL += vec3(1.0) * st * (1.0 - T) * 0.8 * uIntro;
    inL = mix(inL, vec3(0.42, 0.36, 0.85), fres * 0.35);
    inL += vec3(1.0) * rimTop * 0.25;
    inL = mix(inL, vec3(0.50, 0.38, 1.0), clamp(cres * 0.5 * energy, 0.0, 1.0));
    inL += vec3(1.0) * spec;
    mask = smoothstep(1.0, 1.0 - 1.5 / rad, r);
  }
  // premultiplied out: dark, tonemapped, its glow as opaque as it is bright; light, the tint over the day
  vec3 cD = 1.0 - exp(-mix(outD, inD, mask) * 1.3);
  vec4 colD = vec4(cD, max(mask, max(cD.r, max(cD.g, cD.b))));
  vec4 colL = vec4(clamp(inL, 0.0, 1.0), 1.0) * mask + outL * (1.0 - mask);
  vec4 col = mix(colD, colL, uLight);
  col.rgb += (hash(fc + fract(uTime)) - 0.5) / 255.0 * col.a; // dither: no bands in the soft light
  gl_FragColor = vec4(max(col.rgb, 0.0), col.a);
}`;

  let run: Run | null = null;
  const can = !weak() && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  let failed = $state(false); // this opening keeps the CSS orb
  // the eased state the shader reads (Fable's): thinking, a touch and where it is, the tilt after it, the gas's turns
  let think = 0, touch = 0, touchT = 0, px = 0, py = 0, tx = 0, ty = 0, tiltX = 0, tiltY = 0, swirl = 0, flow = 0, beat = 0, intro = 0;
  const tilt = new Float32Array(9);
  const damp = (v: number, to: number, k: number, dt: number) => v + (to - v) * (1 - Math.exp(-k * dt));
  function frame({ gl, u }: Shader, t: number, dt: number) {
    think = damp(think, energy >= 1 ? 1 : energy * 0.3, 1.7, dt); // a draft stirs it a little, an answer on its way fully
    touch = damp(touch, touchT, touchT > touch ? 6 : 2.2, dt);
    px = damp(px, tx, 8, dt); py = damp(py, ty, 8, dt);
    intro = Math.min(1, intro + dt / 2.6);
    swirl += dt * (0.07 + 0.5 * think); flow += dt * (0.16 + 0.36 * think); beat += dt * (Math.PI * 2 / 1.7);
    // the parallax tilt: after the finger, and a slow idle sway
    tiltX = damp(tiltX, px * 0.38 * touch + Math.sin(t * 0.23) * 0.08, 5, dt);
    tiltY = damp(tiltY, py * 0.38 * touch + Math.cos(t * 0.17) * 0.06, 5, dt);
    const c = Math.cos(-tiltX), s = Math.sin(-tiltX), cb = Math.cos(tiltY), sb = Math.sin(tiltY);
    tilt.set([c, sb * s, -cb * s, 0, cb, sb, s, -sb * c, cb * c]);
    const pl = Math.min(px * px + py * py, 1);
    gl.uniform1f(u('uSwirl'), swirl);
    gl.uniform1f(u('uFlow'), flow);
    gl.uniform1f(u('uThink'), think);
    gl.uniform1f(u('uPulse'), think * (0.3 + 0.7 * (0.5 - 0.5 * Math.cos(beat))));
    gl.uniform1f(u('uTouch'), touch);
    gl.uniform1f(u('uIntro'), 1 - (1 - intro) ** 3);
    gl.uniform1f(u('uLight'), theme.current === 'light' ? 1 : 0);
    gl.uniform3f(u('uPtr'), px, py, Math.sqrt(1 - pl) * 0.55 + 0.1);
    gl.uniformMatrix3fv(u('uTilt'), false, tilt);
  }
  // a finger near the ball: the gas leans toward it and the sphere tilts after it (fading out from 1.15 to 2.1 radii);
  // a mouse over it does the same, softer
  let down = false;
  let host: HTMLElement | null = null;
  const near = (e: PointerEvent) => {
    if (!host) return 0;
    const b = host.getBoundingClientRect(), R = b.width / 3.2;
    let x = (e.clientX - b.left - b.width / 2) / R, y = -(e.clientY - b.top - b.width / 2) / R;
    const l = Math.hypot(x, y);
    if (l > 1) { x /= l; y /= l; }
    if (touch < 0.02) { px = x; py = y; }
    tx = x; ty = y;
    const k = Math.max(0, Math.min(1, (l - 1.15) / 0.95));
    return 1 - k * k * (3 - 2 * k);
  };
  const press = (e: PointerEvent) => { if (e.button) return; down = true; touchT = near(e); };
  const move = (e: PointerEvent) => { if (down || e.pointerType === 'mouse') touchT = near(e) * (down ? 1 : 0.6); };
  const up = (e: PointerEvent) => { down = false; touchT = e.pointerType === 'mouse' ? near(e) * 0.6 : 0; };

  // the run, while the box is in its place and nothing says no; again from a fresh canvas when power saving ends
  const glow = (el: HTMLElement) => {
    if (!start || !can || failed || power.lite) return;
    host = el;
    const c = document.createElement('canvas'); // a fresh one each run: a released context can't be built on again
    let id = setTimeout(() => {
      el.append(c);
      run = shade(c, FRAG, { frame, ready: () => (on = true), fail: () => { on = false; failed = true; } });
      run.hold(hold);
    }, 160); // after the first paint and the landing, in a quiet moment
    document.addEventListener('pointerdown', press, { passive: true });
    document.addEventListener('pointermove', move, { passive: true });
    document.addEventListener('pointerup', up, { passive: true });
    document.addEventListener('pointercancel', up, { passive: true });
    return () => {
      clearTimeout(id);
      document.removeEventListener('pointerdown', press);
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
      document.removeEventListener('pointercancel', up);
      const r = run;
      run = null;
      // the CSS orb is back at once under it; this fades out over it, then the context goes
      on = false;
      id = setTimeout(() => { r?.stop(); c.remove(); }, 700);
    };
  };
  $effect(() => { run?.hold(hold); });
</script>

<i class="live" class:on {@attach glow} aria-hidden="true"></i>

<style>
  /* 1.6 balls wide, 1.75 tall: room for the halo round it and the pool under it. Its first frames run at 1% (timed,
     not seen), then it comes in slowly over the CSS orb while the nebula blooms inside */
  .live { position: absolute; inset: -30% -30% -45%; display: block; pointer-events: none; opacity: 0.01; transition: opacity 700ms cubic-bezier(.4, 0, .2, 1); }
  .live.on { opacity: 1; transition: opacity 1600ms cubic-bezier(.22, 1, .36, 1); }
  .live :global(canvas) { display: block; width: 100%; height: 100%; }
</style>
