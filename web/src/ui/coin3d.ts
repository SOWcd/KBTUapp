// A real 3D medal for the award view (owner, Nov 1: the CSS layers read as "a picture moving to emulate 3D"; then
// "make these coins like medals"; then "the straps look 2D, not attached"). three.js lives only in this lazy chunk.
// The chain, top to bottom: a satin V-ribbon hanging from the neck (two thick straps, stripes woven in, draped,
// gathered where they loop under the jump ring's top bar), the jump ring, a lug on the medal's rim, the medal (a
// cylinder ~9.5% thick: the drawn art in front, polished metal with guilloché and the app's mark behind, a milled
// edge). It all swings as one pendulum from the neck; the ribbon's lower part follows the swing and the turn, its top
// stays put. RoomEnvironment lights the metal and the satin alike. Renders only while something moves.
import { onAndroid } from '../lib/tg';
import {
  BoxGeometry, BufferAttribute, CanvasTexture, Color, CylinderGeometry, DoubleSide, Group,
  LinearMipmapLinearFilter, Matrix4, Mesh, MeshPhysicalMaterial, MeshStandardMaterial, NeutralToneMapping, PerspectiveCamera, PMREMGenerator,
  RepeatWrapping, Scene, SRGBColorSpace, Texture, TorusGeometry, Vector2, Vector3, WebGLRenderer,
} from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { springStep } from './tilt';
import { drawCoinBack } from './coinback';

export type CoinState = () => { x: number; y: number; spin: number }; // tilt -1..1, spin in degrees
// the canvas round the medal, in medal sizes: wide enough for the swing, tall above for the ribbon
const W = 1.55, UP = 1.42, DOWN = 0.8; // DOWN: room under the medal for a tilt toward me while it turns (owner, Nov 3: at 0.62 its bottom was cut flat)
// the chain in medal radii (the medal's centre at 0): lug, jump ring, the bar the ribbon loops under, the neck
const LUG = 1.05, RING_R = 0.13, TUBE = 0.028, RING_Y = LUG + RING_R - 0.02, NECK = 2.38;
const WID = 0.6, THICK = 0.016, GATHER = 0.2; // a strap's width, its thickness, its width where it loops the ring
const PARALLAX = 0.014; // how deep the enamel sits under the gold, in face widths (~3 px on a 220 px medal)
const EXPOSURE = 0.92;
const ENAMEL = 0.7; // the enamel's albedo under the room's light: deeper, or the blue goes pale (tone mapping desaturates it)

const smooth = (a: number, b: number, x: number) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const canvas2d = (w: number, h: number) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return [c, c.getContext('2d')!] as const; };

/** Mounts the medal into `host`; resolves once the first frame is drawn. Throws without WebGL. */
export async function mountCoin(host: HTMLElement, o: { src: string; tint: string; ribbon: string[]; size: number; state: CoinState; onLand?: () => void; watch?: HTMLElement }): Promise<() => void> {
  const renderer = new WebGLRenderer({ antialias: !onAndroid, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(onAndroid ? 2 : 3, devicePixelRatio || 1)); // Android: 3x + MSAA lost the medal's face and the page's layers (video, Nov 6) // 3x phones too: at 2 the edge stepped (owner, Nov 3: "no pixels")
  const w = Math.round(o.size * W), up = Math.round(o.size * UP), h = up + Math.round(o.size * DOWN);
  renderer.setSize(w, h);
  renderer.toneMapping = NeutralToneMapping; // ACES pushed the blue enamel toward lavender and the gold to cream
  renderer.toneMappingExposure = EXPOSURE;
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

  // the back: one grey canvas (ui/coinback) is both the shading and the bump
  const [bc, bg] = canvas2d(1024, 1024);
  drawCoinBack(bg);
  const backMap = own(new CanvasTexture(bc)); backMap.colorSpace = SRGBColorSpace;
  backMap.center.set(0.5, 0.5); backMap.rotation = Math.PI; backMap.wrapS = RepeatWrapping; backMap.repeat.x = -1; // upright from behind
  const backBump = own(new CanvasTexture(bc)); backBump.center.set(0.5, 0.5); backBump.rotation = Math.PI; backBump.wrapS = RepeatWrapping; backBump.repeat.x = -1;

  // the face's relief, read off the art's colours (owner, Nov 1: the gold should stand in front of the enamel): warm =
  // struck gold, raised and metal; blue enamel and the white peaks sunk and glassy; the dark rim letters cut into the
  // gold. A silver medal: whatever isn't blue is its metal. One texture: R height (softened: a bevel for the bump),
  // G roughness, B metalness (three's ORM channels)
  const cool = metal.b > metal.r;
  const [hc, hg] = canvas2d(512, 512);
  hg.drawImage(face, 0, 0, 512, 512);
  const px = hg.getImageData(0, 0, 512, 512), d = px.data;
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i] / 255, g = d[i + 1] / 255, b = d[i + 2] / 255;
    const gold = cool ? 1 - smooth(0.1, 0.28, b - r) : smooth(0.02, 0.2, r - b), lum = 0.3 * r + 0.59 * g + 0.11 * b;
    d[i] = Math.round(255 * gold * (0.35 + 0.65 * smooth(0.1, 0.4, lum)));
    d[i + 1] = Math.round(255 * (0.5 - 0.17 * gold)); // gold polished, enamel satin under the lacquer
    d[i + 2] = Math.round(255 * (0.04 + 0.96 * gold));
    d[i + 3] = 255;
  }
  hg.putImageData(px, 0, 0);
  const [rc2, rg2] = canvas2d(512, 512);
  rg2.filter = 'blur(1.5px)'; rg2.drawImage(hc, 0, 0); // no canvas filter (old Safari): a sharp bevel, still fine
  const relief = own(new CanvasTexture(rc2));

  // ridges half as deep: at full depth the milling sparkled into coloured specks at a glancing angle (owner, Nov 3: "pixels")
  const rim = new MeshStandardMaterial({ color: metal.clone().multiplyScalar(0.72), metalness: 1, roughness: 0.34, normalMap: ridges, normalScale: new Vector2(0.5, 0.5) });
  // a thin, wide-lobed lacquer: the room's lights glance off it without blanking the enamel (owner, Nov 1: at some
  // tilts the blue went lavender and the gold cream)
  const top = new MeshPhysicalMaterial({ map: front, metalnessMap: relief, roughnessMap: relief, bumpMap: relief, bumpScale: 3, metalness: 1, roughness: 1,
    clearcoat: 0.1, clearcoatRoughness: 0.35, specularIntensity: 0.35, envMapIntensity: 0.7 });
  // parallax: the sunk enamel is read a little behind the gold along the view, so the gold's side shows as the medal
  // tilts (one extra height read per pixel; the bump above gives the bevel its light). Gradients from the unshifted
  // uv: no mip seam where the shift jumps at an edge
  top.onBeforeCompile = (sh) => {
    sh.uniforms.relief = { value: relief };
    sh.fragmentShader = sh.fragmentShader
      .replace('void main() {', 'uniform sampler2D relief;\nvoid main() {')
      .replace('#include <map_fragment>', /* glsl */ `
        vec2 pdx = dFdx(vMapUv), pdy = dFdy(vMapUv);
        vec3 pq0 = dFdx(-vViewPosition), pq1 = dFdy(-vViewPosition), pN = normalize(vNormal);
        vec3 pT = cross(pq1, pN) * pdx.x + cross(pN, pq0) * pdy.x, pB = cross(pq1, pN) * pdx.y + cross(pN, pq0) * pdy.y;
        float pS = inversesqrt(max(max(dot(pT, pT), dot(pB, pB)), 1e-12));
        vec3 pV = normalize(vViewPosition);
        vec3 pVt = vec3(dot(pV, pT) * pS, dot(pV, pB) * pS, dot(pV, pN));
        float pH = textureGrad(relief, vMapUv, pdx, pdy).r;
        vec2 pUv = vMapUv - pVt.xy / max(pVt.z, 0.45) * (1.0 - pH) * ${PARALLAX.toFixed(4)};
        float pWall = smoothstep(0.3, 0.7, textureGrad(relief, pUv, pdx, pdy).r) * (1.0 - smoothstep(0.3, 0.7, pH));
        diffuseColor *= textureGrad(map, pUv, pdx, pdy);
        diffuseColor.rgb *= 1.0 - 0.3 * pWall; // the gold's side, out of the light
        diffuseColor.rgb *= mix(${ENAMEL.toFixed(2)}, 1.0, smoothstep(0.1, 0.5, pH)); // the art's enamel has its light painted in`)
      .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = roughness * textureGrad(roughnessMap, pUv, pdx, pdy).g;')
      .replace('#include <metalnessmap_fragment>', 'float metalnessFactor = metalness * textureGrad(metalnessMap, pUv, pdx, pdy).b;');
  };
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
  const sz = { x: 4, v: 0 }, sx = { x: 0, v: 0 }; // sideways and toward/away; the entrance starts it swinging
  // the entrance (owner, Nov 1: "super beautiful"): lowered from above on a damped spring (a slight overshoot),
  // 1.5 turns that slow to face front, a glint across the metal as it settles; ~1.2 s. Added on top of the tilt and
  // the finger, so nothing jumps when it ends
  const t0 = performance.now(), ZETA = 0.7, OMEGA = 5.5, WD = OMEGA * Math.sqrt(1 - ZETA * ZETA);
  let landed = false, shown = '', raf = 0, prev = t0 - 1000 / 60;
  const frame = () => {
    raf = requestAnimationFrame(frame);
    const now = performance.now(), k = Math.min(4, (now - prev) / (1000 / 60)), t = (now - t0) / 1000, s = o.state();
    prev = now;
    const drop = t > 1.6 ? 0 : 3.4 * Math.exp(-ZETA * OMEGA * t) * Math.cos(WD * t);
    if (!landed && drop <= 0) { landed = true; o.onLand?.(); }
    const turn = 540 * (1 - Math.min(1, t / 1.05)) ** 3;
    const glint = t > 0.45 && t < 1.25 ? Math.sin(((t - 0.45) / 0.8) * Math.PI) : 0;
    springStep(sz, -s.x * 5, k); springStep(sx, s.y * 5, k); // by the time passed: the same swing at 60 and 120 Hz
    // still (the entrance over, the pendulum at rest where the tilt pulls it): the loop sleeps until `watch` changes
    // (the tilt light and the finger's spin are written there as styles); it ran every frame while the sheet was open
    if (o.watch && t > 1.6 && Math.max(Math.abs(sz.v), Math.abs(sx.v), Math.abs(sz.x + s.x * 5), Math.abs(sx.x - s.y * 5)) < 1e-4) { cancelAnimationFrame(raf); raf = 0; }
    const yaw = s.x * 26 + s.spin + turn;
    const key = `${sz.x.toFixed(2)},${sx.x.toFixed(2)},${yaw.toFixed(2)},${s.y.toFixed(3)},${drop.toFixed(3)},${glint.toFixed(3)}`;
    if (key === shown) return; // nothing moved: no draw
    shown = key;
    pend.position.y = NECK + drop;
    pend.rotation.set(sx.x * deg, 0, sz.x * deg);
    medalPivot.rotation.set(s.y * 14 * deg, yaw * deg, 0, 'YXZ'); // the medal turns on the ring, showing its rim
    ringPivot.rotation.y = Math.max(-0.5, Math.min(0.5, Math.sin(yaw * deg) * 0.35)); // the ring and fold follow a little
    scene.environmentRotation.y = glint * 0.9; // the room's lights slide across the metal
    renderer.toneMappingExposure = EXPOSURE + glint * 0.12;
    scene.updateMatrixWorld();
    for (const st of straps) bend(st, drop);
    renderer.render(scene, camera);
  };
  frame();
  const mo = new MutationObserver(() => { if (!raf) { prev = performance.now() - 1000 / 60; raf = requestAnimationFrame(frame); } });
  if (o.watch) mo.observe(o.watch, { attributes: true, attributeFilter: ['style'], subtree: true });
  return () => {
    mo.disconnect();
    cancelAnimationFrame(raf);
    for (const x of [coinGeo, lugGeo, ringGeo, foldGeo, strapBase, ...straps.map((s) => s.g), rim, top, bottom, steel, satin, foldSatin, none, ...tex, env, pmrem, renderer]) x.dispose();
    room.dispose();
    renderer.forceContextLoss();
    canvas.remove();
  };
}
