// A real 3D medal for the award view (owner, Nov 1: the CSS layers read as "a picture moving to emulate 3D"; then
// "make these coins like medals"; then "the straps look 2D, not attached"). three.js lives only in this lazy chunk.
// The chain, top to bottom: a satin V-ribbon hanging from the neck (two thick straps, stripes woven in, draped,
// gathered where they loop under the jump ring's top bar), the jump ring, a lug on the medal's rim, the medal (a
// cylinder ~9.5% thick: the drawn art in front, polished metal with guilloché and the app's mark behind, a milled
// edge). It all swings as one pendulum from the neck; the ribbon's lower part follows the swing and the turn, its top
// stays put. RoomEnvironment lights the metal and the satin alike. Renders only while something moves.
import {
  ACESFilmicToneMapping, BoxGeometry, BufferAttribute, CanvasTexture, Color, CylinderGeometry, DoubleSide, Group,
  LinearMipmapLinearFilter, Matrix4, Mesh, MeshPhysicalMaterial, MeshStandardMaterial, PerspectiveCamera, PMREMGenerator,
  RepeatWrapping, Scene, SRGBColorSpace, Texture, TorusGeometry, Vector3, WebGLRenderer,
} from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export type CoinState = () => { x: number; y: number; spin: number }; // tilt -1..1, spin in degrees
// the canvas round the medal, in medal sizes: wide enough for the swing, tall above for the ribbon
const W = 1.55, UP = 1.42, DOWN = 0.62;
// the chain in medal radii (the medal's centre at 0): lug, jump ring, the bar the ribbon loops under, the neck
const LUG = 1.05, RING_R = 0.13, TUBE = 0.028, RING_Y = LUG + RING_R - 0.02, NECK = 2.38;
const WID = 0.6, THICK = 0.016, GATHER = 0.2; // a strap's width, its thickness, its width where it loops the ring

const smooth = (a: number, b: number, x: number) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const canvas2d = (w: number, h: number) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return [c, c.getContext('2d')!] as const; };

/** Mounts the medal into `host`; resolves once the first frame is drawn. Throws without WebGL. */
export async function mountCoin(host: HTMLElement, o: { src: string; tint: string; ribbon: string[]; size: number; state: CoinState; onLand?: () => void }): Promise<() => void> {
  const renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1));
  const w = Math.round(o.size * W), up = Math.round(o.size * UP), h = up + Math.round(o.size * DOWN);
  renderer.setSize(w, h);
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.outputColorSpace = SRGBColorSpace;
  const aniso = Math.min(8, renderer.capabilities.getMaxAnisotropy());

  const scene = new Scene();
  const pmrem = new PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const env = pmrem.fromScene(room, 0.04).texture;
  scene.environment = env;
  // a frame symmetric round the medal (2 × up tall) of which the canvas shows the top: the medal stays where the flat
  // art was, at `size` px face on (radius 1 = size / 2 px)
  const camera = new PerspectiveCamera(2 * Math.atan(((2 * up) / o.size) / 7) * (180 / Math.PI), w / (2 * up), 0.1, 50);
  camera.position.z = 7;
  camera.setViewOffset(w, 2 * up, 0, 0, w, h);

  const face = await new Promise<HTMLImageElement>((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = o.src; });
  const front = new Texture(face); front.colorSpace = SRGBColorSpace; front.anisotropy = aniso; front.needsUpdate = true;

  const metal = new Color(`rgb(${o.tint})`);
  const tex: Texture[] = [front];
  const own = <T extends Texture>(t: T) => { t.anisotropy = aniso; t.minFilter = LinearMipmapLinearFilter; tex.push(t); return t; };

  // milled ridges round the edge: a normal map tilting along it
  const [rc, rg] = canvas2d(64, 4);
  for (let x = 0; x < 64; x++) {
    const n = Math.sin((x / 8) * Math.PI * 2) * 0.75;
    rg.fillStyle = `rgb(${Math.round((n * 0.5 + 0.5) * 255)}, 128, ${Math.round((Math.sqrt(1 - n * n) * 0.5 + 0.5) * 255)})`;
    rg.fillRect(x, 0, 1, 4);
  }
  const ridges = own(new CanvasTexture(rc)); ridges.wrapS = RepeatWrapping; ridges.repeat.set(26, 1);

  // the back: polished metal, fine concentric guilloché and the app's colonnade (the icon's five columns) struck in
  // low relief; one grey canvas is both the shading and the bump
  const [bc, bg] = canvas2d(1024, 1024);
  bg.fillStyle = 'rgb(200, 200, 200)'; bg.fillRect(0, 0, 1024, 1024);
  for (let r = 470; r > 250; r -= 5) { bg.strokeStyle = r % 10 ? 'rgb(178, 178, 178)' : 'rgb(226, 226, 226)'; bg.lineWidth = 2; bg.beginPath(); bg.arc(512, 512, r, 0, Math.PI * 2); bg.stroke(); }
  bg.strokeStyle = 'rgb(150, 150, 150)'; bg.lineWidth = 10; bg.beginPath(); bg.arc(512, 512, 490, 0, Math.PI * 2); bg.stroke();
  bg.strokeStyle = 'rgb(236, 236, 236)'; bg.lineWidth = 6; bg.beginPath(); bg.arc(512, 512, 250, 0, Math.PI * 2); bg.stroke();
  const mark = (fill: string, dx: number, dy: number) => {
    bg.fillStyle = fill;
    const box = (x: number, y: number, ww: number, hh: number) => { bg.beginPath(); bg.roundRect(512 - 196 + dx + x * 14, 512 - 165 + dy + y * 14, ww * 14, hh * 14, 18); bg.fill(); };
    box(1, 1.5, 26, 4); for (const x of [2, 7.25, 12.5, 17.75, 23]) box(x, 7, 3, 11); box(0, 19.5, 28, 3);
  };
  mark('rgb(236, 236, 236)', -3, -3); mark('rgb(120, 120, 120)', 3, 3); mark('rgb(192, 192, 192)', 0, 0); // light above, shade below: struck
  const backMap = own(new CanvasTexture(bc)); backMap.colorSpace = SRGBColorSpace;
  backMap.center.set(0.5, 0.5); backMap.rotation = Math.PI; backMap.wrapS = RepeatWrapping; backMap.repeat.x = -1; // upright from behind
  const backBump = own(new CanvasTexture(bc)); backBump.center.set(0.5, 0.5); backBump.rotation = Math.PI; backBump.wrapS = RepeatWrapping; backBump.repeat.x = -1;

  const rim = new MeshStandardMaterial({ color: metal.clone().multiplyScalar(0.72), metalness: 1, roughness: 0.3, normalMap: ridges });
  const top = new MeshPhysicalMaterial({ map: front, metalness: 0.6, roughness: 0.32, clearcoat: 0.7, clearcoatRoughness: 0.12 });
  const bottom = new MeshStandardMaterial({ map: backMap, bumpMap: backBump, bumpScale: 2.5, color: metal, metalness: 1, roughness: 0.26 });
  const steel = new MeshStandardMaterial({ color: metal.clone().multiplyScalar(0.9), metalness: 1, roughness: 0.2 });
  const coinGeo = new CylinderGeometry(1, 1, 0.19, 192, 1);
  coinGeo.rotateX(Math.PI / 2).rotateZ(Math.PI / 2); // caps toward the camera, the art upright
  const coin = new Mesh(coinGeo, [rim, top, bottom]);
  // the lug: a small eye on the rim, across the medal, that the jump ring passes through
  const lugGeo = new TorusGeometry(0.075, 0.03, 20, 40); lugGeo.rotateY(Math.PI / 2);
  const lug = new Mesh(lugGeo, steel); lug.position.y = LUG;
  const medal = new Group(); medal.add(coin, lug);
  const medalPivot = new Group(); medalPivot.position.y = RING_Y; medal.position.y = -RING_Y; medalPivot.add(medal);
  // the jump ring, in the medal's plane; the fold of the ribbon under its top bar
  const ringGeo = new TorusGeometry(RING_R, TUBE, 24, 64);
  const ring = new Mesh(ringGeo, steel);

  // satin: stripes woven across the width (mipmapped, anisotropic: no shimmer), a sheen, the same room for light
  const [sc, sg] = canvas2d(512, 8);
  o.ribbon.forEach((col, i) => { sg.fillStyle = `rgb(${col})`; sg.fillRect(Math.round((i * 512) / o.ribbon.length), 0, Math.ceil(512 / o.ribbon.length) + 1, 8); });
  sg.globalAlpha = 0.06; for (let x = 0; x < 512; x += 2) { sg.fillStyle = x % 4 ? 'rgb(0, 0, 0)' : 'rgb(255, 255, 255)'; sg.fillRect(x, 0, 1, 8); } // the weave
  const stripes = own(new CanvasTexture(sc)); stripes.colorSpace = SRGBColorSpace;
  const foldStripes = own(new CanvasTexture(sc)); foldStripes.colorSpace = SRGBColorSpace; foldStripes.center.set(0.5, 0.5); foldStripes.rotation = Math.PI / 2;
  // it fades out before the capsule: transparent at the top of the strap, solid from a third of the way down
  const [fc, fg] = canvas2d(4, 256);
  const grad = fg.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0, 'rgb(0, 0, 0)'); grad.addColorStop(0.1, 'rgb(0, 0, 0)'); grad.addColorStop(0.5, 'rgb(255, 255, 255)'); grad.addColorStop(1, 'rgb(255, 255, 255)');
  fg.fillStyle = grad; fg.fillRect(0, 0, 4, 256);
  const fade = own(new CanvasTexture(fc));
  const satinOf = (map: Texture, faded: boolean) => new MeshPhysicalMaterial({ map, vertexColors: faded, alphaMap: faded ? fade : null, transparent: faded,
    side: DoubleSide, roughness: 0.5, sheen: 0.6, sheenRoughness: 0.3, sheenColor: new Color(0.32, 0.32, 0.36), clearcoat: 0.1, clearcoatRoughness: 0.45 });
  const none = new MeshStandardMaterial({ visible: false }); // a strap's cut ends: never drawn (they'd show as lines)
  const satin = satinOf(stripes, true), foldSatin = satinOf(foldStripes, false);
  foldSatin.color.setScalar(0.62); // inside the ring, in its shadow

  // the fold: the ribbon under the ring's top bar, front to back, gathered narrow
  const foldR = TUBE + THICK * 1.5;
  const foldGeo = new CylinderGeometry(foldR, foldR, GATHER, 24, 1, true, Math.PI, Math.PI);
  foldGeo.rotateZ(Math.PI / 2);
  const fold = new Mesh(foldGeo, foldSatin); fold.position.y = RING_R;
  const ringPivot = new Group(); ringPivot.position.y = RING_Y; ringPivot.add(ring, fold);

  const chain = new Group(); chain.add(medalPivot, ringPivot); chain.position.y = -NECK;
  const pend = new Group(); pend.position.y = NECK; pend.add(chain); // the whole chain swings from the neck
  scene.add(pend);

  // the two straps: thick boxes bent every frame along a curve from the fold (moving with the chain) to the neck
  // (fixed): gathered at the bottom, a drape toward the viewer, curved across the width, a slight twist
  const SEG = 48;
  const strapBase = new BoxGeometry(WID, 1, THICK, 8, SEG, 1).toNonIndexed();
  strapBase.translate(0, 0.5, 0);
  const base = (strapBase.attributes.position.array as Float32Array).slice();
  const straps = [-1, 1].map((side) => {
    const g = strapBase.clone();
    // shade: darker near the ring (its contact shadow) and, for the back strap, where the front one covers it
    const cols = new Float32Array(base.length);
    for (let i = 0; i < base.length; i += 3) {
      const v = base[i + 1];
      const k = 0.55 + 0.45 * smooth(0, 0.22, v) - (side > 0 ? 0.22 * (1 - smooth(0.05, 0.35, v)) : 0);
      cols[i] = cols[i + 1] = cols[i + 2] = k;
    }
    g.setAttribute('color', new BufferAttribute(cols, 3));
    const m = new Mesh(g, [satin, satin, none, none, satin, satin]); // box faces: ±x sides, ±y ends, ±z faces
    m.renderOrder = side > 0 ? 0 : 1; m.frustumCulled = false; // bent every frame: its bounds go stale
    scene.add(m);
    return { side, g, m };
  });

  const P0 = new Vector3(), P1 = new Vector3(), P2 = new Vector3(), P3 = new Vector3(), T = new Vector3(), Wd = new Vector3(), N = new Vector3(), C = new Vector3();
  const wB = new Vector3(), tmp = new Vector3(), mtx = new Matrix4();
  const bend = (s: typeof straps[number], drop: number) => {
    // bottom: on the fold's top edge (front strap in front of the bar, back strap behind), pointing up; across: the fold's axis
    mtx.copy(fold.matrixWorld);
    P0.set(0, 0, s.side < 0 ? foldR : -foldR).applyMatrix4(mtx);
    T.set(0, 1, 0).transformDirection(mtx);
    wB.set(1, 0, 0).transformDirection(mtx);
    P3.set(s.side * 0.6, NECK + drop, -0.18); // the neck: fixed (it falls in with the medal on the entrance)
    P1.copy(P0).addScaledVector(T, 0.32);
    P2.copy(P3).add(tmp.set(-s.side * 0.04, -0.42, 0.06));
    const pos = s.g.attributes.position.array as Float32Array;
    for (let i = 0; i < base.length; i += 3) {
      const x = base[i], v = base[i + 1], z = base[i + 2], u = 1 - v;
      C.set(0, 0, 0).addScaledVector(P0, u * u * u).addScaledVector(P1, 3 * u * u * v).addScaledVector(P2, 3 * u * v * v).addScaledVector(P3, v * v * v);
      T.set(0, 0, 0).addScaledVector(P0, -3 * u * u).addScaledVector(P1, 3 * u * u - 6 * u * v).addScaledVector(P2, 6 * u * v - 3 * v * v).addScaledVector(P3, 3 * v * v).normalize();
      tmp.set(T.y, -T.x, 0).normalize(); if (tmp.dot(wB) < 0) tmp.negate(); // across, in the picture's plane, as the fold's
      Wd.copy(wB).lerp(tmp, smooth(0, 0.35, v)).addScaledVector(T, -Wd.dot(T)).normalize();
      N.crossVectors(Wd, T).normalize();
      const half = x / (WID / 2), width = GATHER / WID + (1 - GATHER / WID) * smooth(0, 0.42, v);
      const drape = 0.07 * Math.sin(Math.PI * Math.min(1, v * 1.4)) - 0.035 * half * half * smooth(0.15, 0.5, v) + 0.012 * Math.sin(half * 3 + v * 9) * smooth(0.1, 0.6, v);
      pos[i] = C.x + Wd.x * x * width + N.x * (z + drape);
      pos[i + 1] = C.y + Wd.y * x * width + N.y * (z + drape);
      pos[i + 2] = C.z + Wd.z * x * width + N.z * (z + drape);
    }
    s.g.attributes.position.needsUpdate = true;
    s.g.computeVertexNormals();
  };

  const canvas = renderer.domElement;
  canvas.style.cssText = `position:absolute;left:50%;top:${o.size / 2 - up}px;width:${w}px;height:${h}px;translate:-50% 0;pointer-events:none`;
  host.append(canvas);

  const deg = Math.PI / 180;
  // the pendulum from the neck: damped springs toward where the tilt pulls it (sideways, toward/away)
  const sw = { z: 4, vz: 0, x: 0, vx: 0 }; // the entrance starts it swinging
  // the entrance (owner, Nov 1: "super beautiful"): lowered from above on a damped spring (a slight overshoot),
  // 1.5 turns that slow to face front, a glint across the metal as it settles; ~1.2 s. Added on top of the tilt and
  // the finger, so nothing jumps when it ends
  const t0 = performance.now(), ZETA = 0.7, OMEGA = 5.5, WD = OMEGA * Math.sqrt(1 - ZETA * ZETA);
  let landed = false, shown = '', raf = 0;
  const frame = () => {
    raf = requestAnimationFrame(frame);
    const t = (performance.now() - t0) / 1000, s = o.state();
    const drop = t > 1.6 ? 0 : 3.4 * Math.exp(-ZETA * OMEGA * t) * Math.cos(WD * t);
    if (!landed && drop <= 0) { landed = true; o.onLand?.(); }
    const turn = 540 * (1 - Math.min(1, t / 1.05)) ** 3;
    const glint = t > 0.45 && t < 1.25 ? Math.sin(((t - 0.45) / 0.8) * Math.PI) : 0;
    sw.vz = (sw.vz + (-s.x * 5 - sw.z) * 0.045) * 0.92; sw.z += sw.vz;
    sw.vx = (sw.vx + (s.y * 5 - sw.x) * 0.045) * 0.92; sw.x += sw.vx;
    const yaw = s.x * 26 + s.spin + turn;
    const key = `${sw.z.toFixed(2)},${sw.x.toFixed(2)},${yaw.toFixed(2)},${s.y.toFixed(3)},${drop.toFixed(3)},${glint.toFixed(3)}`;
    if (key === shown) return; // nothing moved: no draw
    shown = key;
    pend.position.y = NECK + drop;
    pend.rotation.set(sw.x * deg, 0, sw.z * deg);
    medalPivot.rotation.set(s.y * 14 * deg, yaw * deg, 0, 'YXZ'); // the medal turns on the ring, showing its rim
    ringPivot.rotation.y = Math.max(-0.5, Math.min(0.5, Math.sin(yaw * deg) * 0.35)); // the ring and fold follow a little
    scene.environmentRotation.y = glint * 0.9; // the room's lights slide across the metal
    renderer.toneMappingExposure = 1 + glint * 0.22;
    scene.updateMatrixWorld();
    for (const st of straps) bend(st, drop);
    renderer.render(scene, camera);
  };
  frame();
  return () => {
    cancelAnimationFrame(raf);
    for (const x of [coinGeo, lugGeo, ringGeo, foldGeo, strapBase, ...straps.map((s) => s.g), rim, top, bottom, steel, satin, foldSatin, none, ...tex, env, pmrem, renderer]) x.dispose();
    room.dispose();
    renderer.forceContextLoss();
    canvas.remove();
  };
}
