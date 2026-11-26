<script lang="ts">
  // KRI's light, alive: a small fragment shader (lib/gl.ts) laid over the CSS orb (ui/Orb) in the same box, 1.6 times
  // its size for the halo and the glow on the floor. A glass ball with a soft nebula inside, marched through in a few
  // steps, drifting slowly; it breathes, leans its light toward a touch and swells a little, and stirs faster while
  // the student types (energy). The CSS orb is what the screen opens with: the shader builds after the first paint and
  // the landing, runs its first frames unseen to time them, then fades in over it. It stays the CSS orb on a weak
  // phone, with less motion, under power saving (which also covers Telegram's LOW class and a low battery), with no
  // WebGL, or when the first frames are too slow.
  //   start   the box is in its place (not flying in): it may begin
  //   energy  0 at rest, 0.5 listening (a draft in the field), 1 thinking
  //   hold    nothing to draw for now (covered by another sheet, faded for the keyboard): frames stop
  //   on      out: the shader is showing (the parent hides its CSS orb under it)
  import { shade, weak, type Run, type Shader } from '../../lib/gl';
  import { power } from '../../lib/state/power.svelte';
  import { theme } from '../../lib/state/theme.svelte';

  let { start, energy = 0, hold = false, on = $bindable(false) }: { start: boolean; energy?: number; hold?: boolean; on?: boolean } = $props();

  // GLSL 100: WebGL1 and 2 both take it. The canvas spans -1..1 on its short side; the ball's radius is R
  const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 uRes;
uniform float uTime, uPress, uEnergy, uLight;
uniform vec2 uTouch;
const float R = 0.625;
float hash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float noise(vec3 x) {
  vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x), mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x), mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float fbm(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 3; i++) { s += a * noise(p); p = p * 2.03 + vec3(1.7, 9.2, 3.1); a *= 0.5; } return s; }
void main() {
  vec2 p = (gl_FragCoord.xy * 2.0 - uRes) / min(uRes.x, uRes.y);
  float t = uTime, br = 0.5 + 0.5 * sin(t * 0.52); // one breath in ~12 s
  float r = R * (0.988 + 0.024 * br + 0.025 * uPress);
  vec2 q = (p - vec2(0.0, 0.016 * (br - 0.5))) / r;
  float d = length(q), px = 3.0 / (min(uRes.x, uRes.y) * r);
  vec3 violet = vec3(0.55, 0.33, 1.0), blue = vec3(0.23, 0.42, 1.0), teal = vec3(0.19, 0.69, 0.78);
  vec3 hot = mix(vec3(0.81, 0.84, 1.0), vec3(1.0), uLight);
  // the light it throws round itself and on the floor under it (premultiplied)
  float hA = mix(0.36, 0.2, uLight) * (0.85 + 0.15 * br + 0.3 * uEnergy) * exp(-2.6 * max(d - 1.0, 0.0)) * smoothstep(1.58, 1.0, d);
  vec3 hC = mix(blue, violet, 0.5 + 0.5 * sin(t * 0.21));
  vec2 fq = vec2(p.x / (0.8 * R), (p.y + 1.36 * R) / (0.13 * R));
  float fA = exp(-dot(fq, fq) * 1.6) * mix(0.34, 0.2, uLight) * (1.1 - 0.3 * br);
  vec3 fC = mix(vec3(0.38, 0.42, 1.0), vec3(0.09, 0.14, 0.35), uLight);
  vec4 back = vec4(hC * hA + fC * fA, hA + fA);
  vec4 col = back;
  if (d < 1.0) {
    float z = sqrt(1.0 - d * d);
    vec3 n = vec3(q, z);
    // the nebula: from the front of the ball to its back in five steps, front to back
    float sp = 1.0 + 1.6 * uEnergy;
    vec3 drift = vec3(t * 0.045, -t * 0.03, t * 0.026) * sp;
    float c = cos(t * 0.07 * sp), s = sin(t * 0.07 * sp);
    vec3 neb = vec3(0.0); float acc = 0.0;
    vec3 tp = vec3(uTouch * 0.55, 0.35);
    for (int i = 0; i < 5; i++) {
      float zz = mix(z, -z, (float(i) + 0.5) / 5.0);
      vec3 pos = vec3(q, zz);
      pos.xz = mat2(c, -s, s, c) * pos.xz;
      float f = fbm(pos * 1.7 + drift);
      float core = exp(-dot(pos.xy - vec2(-0.08, -0.06), pos.xy - vec2(-0.08, -0.06)) * 1.8);
      float den = clamp((f - 0.34) * 1.9, 0.0, 1.0) * (0.35 + 0.75 * core) * 0.42;
      vec3 sc = mix(blue, violet, smoothstep(0.35, 0.72, f + pos.x * 0.35));
      sc = mix(sc, teal, smoothstep(0.55, 1.0, -pos.y + pos.x * 0.4) * 0.45);
      sc = mix(sc, hot, smoothstep(0.62, 0.9, f * core) * 0.8);
      sc += hot * exp(-dot(pos - tp, pos - tp) * 6.0) * uPress * 0.9; // a touch lights it from inside
      neb += (1.0 - acc) * den * sc; acc += (1.0 - acc) * den;
    }
    // the glass: its own tint, the nebula through it, a window light that leans toward a touch, the rim
    vec3 shell = mix(vec3(0.055, 0.06, 0.1), vec3(0.914, 0.925, 0.984), uLight);
    vec3 ball = mix(shell, neb / max(acc, 0.001), acc * mix(1.0, 0.82, uLight) * (1.0 + 0.25 * uEnergy));
    vec3 L = normalize(vec3(vec2(-0.42, 0.62) + uTouch * 0.5, 0.95));
    vec3 h = normalize(L + vec3(0.0, 0.0, 1.0));
    float fr = pow(1.0 - z, 3.0);
    ball += vec3(1.0) * pow(max(dot(n, h), 0.0), 48.0) * mix(0.45, 0.9, uLight);
    ball += vec3(1.0) * pow(max(dot(n, h), 0.0), 6.0) * mix(0.05, 0.12, uLight);
    ball += mix(vec3(1.0, 0.55, 0.85), vec3(0.45, 0.78, 1.0), smoothstep(-0.6, 0.6, q.x)) * fr * mix(0.55, 0.4, uLight);
    ball *= 1.0 - (1.0 - smoothstep(-1.0, 0.25, q.y)) * fr * mix(0.6, 0.22, uLight); // the underside in shade
    float a = (1.0 - smoothstep(1.0 - px, 1.0, d)) * mix(0.95, 1.0, uLight);
    col = vec4(ball * a, a) + back * (1.0 - a);
  }
  col.rgb += (hash(vec3(gl_FragCoord.xy, t)) - 0.5) / 255.0 * col.a; // dither: no bands in the soft light
  gl_FragColor = col;
}`;

  let run: Run | null = null;
  const can = !weak() && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  let failed = $state(false); // this opening keeps the CSS orb
  // the eased values the shader reads: a touch's lean and pulse, the energy
  let tx = 0, ty = 0, gx = 0, gy = 0, press = 0, kick = 0, en = 0;
  function frame({ gl, u }: Shader, _t: number, dt: number) {
    const k = 1 - Math.exp(-dt * 3.2);
    tx += (gx - tx) * k; ty += (gy - ty) * k;
    press += (kick - press) * (1 - Math.exp(-dt * (kick > press ? 9 : 2.2)));
    kick = Math.max(0, kick - dt * 1.4);
    en += (energy - en) * (1 - Math.exp(-dt * 1.8));
    gl.uniform2f(u('uTouch'), tx, ty);
    gl.uniform1f(u('uPress'), press);
    gl.uniform1f(u('uEnergy'), en);
    gl.uniform1f(u('uLight'), theme.current === 'light' ? 1 : 0);
  }
  // a touch anywhere on the screen: the light leans toward it (clamped near the ball) and the ball swells a little
  let down = false;
  let host: HTMLElement | null = null;
  const lean = (e: PointerEvent) => {
    if (!host) return;
    const b = host.getBoundingClientRect(), h = b.width / 2;
    const x = (e.clientX - b.left - h) / h, y = -(e.clientY - b.top - b.height / 2) / h, l = Math.hypot(x, y), m = l > 1.2 ? 1.2 / l : 1;
    gx = x * m; gy = y * m;
  };
  const press0 = (e: PointerEvent) => { down = true; kick = 1; lean(e); };
  const move = (e: PointerEvent) => { if (down) lean(e); };
  const up = () => { down = false; gx = gy = 0; };

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
    document.addEventListener('pointerdown', press0, { passive: true });
    document.addEventListener('pointermove', move, { passive: true });
    document.addEventListener('pointerup', up, { passive: true });
    document.addEventListener('pointercancel', up, { passive: true });
    return () => {
      clearTimeout(id);
      document.removeEventListener('pointerdown', press0);
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
  /* 1.6 times the ball: room for its halo and its glow on the floor. Its first frames run at 1% (timed, not seen) */
  .live { position: absolute; inset: -30%; display: block; pointer-events: none; opacity: 0.01; transition: opacity 700ms cubic-bezier(.4, 0, .2, 1); }
  .live.on { opacity: 1; transition: opacity 900ms cubic-bezier(.16, 1, .3, 1); }
  .live :global(canvas) { display: block; width: 100%; height: 100%; }
</style>
