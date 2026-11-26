// One small WebGL canvas that runs a fragment shader over its whole box (KRI's orb first; anything later may reuse it).
// No library: raw WebGL2, else WebGL1, a GLSL 100 shader that both take. The drawing buffer follows the box at the
// screen's density capped at 2; frames run only while the canvas is on screen and the page is shown (and not held);
// stop() gives the context back at once. Not on weak phones (`weak()`), nor when the first frames come too slowly:
// then fail() is called and the caller keeps its CSS picture. Uniforms the caller doesn't declare: uRes (px), uTime (s).

/** a phone that should keep the CSS picture: few cores or little memory (the browser's own words, where it says them) */
// iOS WebKit reports few cores even on new iPhones (owner saw no WebGL orb): only 2 or fewer counts as weak; the first-frames budget catches the rest
export const weak = () => (navigator.hardwareConcurrency || 8) <= 2 || ((navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8) <= 3;

export type Shader = {
  gl: WebGLRenderingContext;
  /** a uniform's location, looked up once */
  u: (name: string) => WebGLUniformLocation | null;
};
type Opts = {
  /** each frame, before the draw: set the uniforms (t: seconds since the start, dt: since the last frame) */
  frame: (s: Shader, t: number, dt: number) => void;
  /** the first frames are drawn and kept to the budget: the canvas may be shown */
  ready?: () => void;
  /** no WebGL, a shader that won't build, a lost context, or the first frames over budget: the canvas is released */
  fail?: () => void;
  /** the median frame interval over the first frames above this, ms, fails it (default 26: under ~40 fps) */
  budget?: number;
};
export type Run = { stop: () => void; hold: (on: boolean) => void };

const VERT = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
const SAMPLE = 24, SKIP = 4; // frames timed after the first few (the build and the first upload hitch)

export function shade(canvas: HTMLCanvasElement, frag: string, o: Opts): Run {
  const attrs: WebGLContextAttributes = { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false, powerPreference: 'low-power' };
  const gl = (canvas.getContext('webgl2', attrs) ?? canvas.getContext('webgl', attrs)) as WebGLRenderingContext | null;
  let raf = 0, dead = false, seen = true, held = false, t0 = 0, last = 0, n = 0;
  const gaps: number[] = [];
  const fail = () => { if (!dead) { stop(); o.fail?.(); } };
  if (!gl) { queueMicrotask(() => o.fail?.()); return { stop: () => {}, hold: () => {} }; }

  const build = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); return s; };
  const prog = gl.createProgram()!, vs = build(gl.VERTEX_SHADER, VERT), fs = build(gl.FRAGMENT_SHADER, frag);
  gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.bindAttribLocation(prog, 0, 'p'); gl.linkProgram(prog);
  gl.deleteShader(vs); gl.deleteShader(fs);
  const buf = gl.createBuffer();
  const locs = new Map<string, WebGLUniformLocation | null>();
  const s: Shader = { gl, u: (k) => { if (!locs.has(k)) locs.set(k, gl.getUniformLocation(prog, k)); return locs.get(k)!; } };

  const size = () => {
    const d = Math.min(2, devicePixelRatio || 1), w = Math.round(canvas.clientWidth * d), h = Math.round(canvas.clientHeight * d);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  };
  const tick = (now: number) => {
    raf = 0;
    if (dead || !seen || held || document.hidden) return;
    if (!t0) t0 = now - last * 1000; // back from a pause: time goes on where it stopped, no jump
    const t = (now - t0) / 1000, dt = Math.min(0.1, t - last);
    // the first frames' pace: a phone that can't keep up keeps the CSS picture
    if (n > SKIP && n <= SKIP + SAMPLE) gaps.push(dt * 1000);
    if (gaps.length === SAMPLE && n === SKIP + SAMPLE) {
      const m = gaps.sort((a, b) => a - b)[SAMPLE >> 1];
      if (m > (o.budget ?? 26)) return fail();
      o.ready?.();
    }
    last = t;
    size();
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(s.u('uRes'), canvas.width, canvas.height);
    gl.uniform1f(s.u('uTime'), t);
    o.frame(s, t, dt);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    n++;
    go();
  };
  const go = () => { if (!raf && !dead && seen && !held && !document.hidden) raf = requestAnimationFrame(tick); };
  const pause = () => { cancelAnimationFrame(raf); raf = 0; t0 = 0; if (n <= SKIP + SAMPLE) { n = Math.min(n, SKIP); gaps.length = 0; } };
  const vis = () => { if (document.hidden) pause(); else go(); };
  const io = new IntersectionObserver(([e]) => { seen = e.isIntersecting; if (seen) go(); else pause(); });
  const lost = (e: Event) => { e.preventDefault(); fail(); };

  function stop() {
    if (dead) return;
    dead = true;
    cancelAnimationFrame(raf);
    io.disconnect();
    document.removeEventListener('visibilitychange', vis);
    canvas.removeEventListener('webglcontextlost', lost);
    gl!.deleteBuffer(buf); gl!.deleteProgram(prog);
    gl!.getExtension('WEBGL_lose_context')?.loseContext(); // the GPU memory goes now, not at the next GC
  }

  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { queueMicrotask(fail); return { stop, hold: () => {} }; }
  gl.useProgram(prog);
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW); // one triangle over the box
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  io.observe(canvas);
  document.addEventListener('visibilitychange', vis);
  canvas.addEventListener('webglcontextlost', lost);
  go();
  return { stop, hold: (on) => { held = on; if (on) pause(); else go(); } };
}
