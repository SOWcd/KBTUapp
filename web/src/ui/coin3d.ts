// A real 3D coin for the award view (owner, Nov 1: the CSS layers read as "a picture moving to emulate 3D").
// three.js lives only in this lazy chunk. A cylinder ~9.5% thick: the drawn medal is the front cap, a mirrored darker
// copy the back, the edge milled metal (a canvas normal map) in the medal's metal; RoomEnvironment gives the
// reflections that move as it turns. A medal, not a coin (owner, Nov 1): it hangs by a jump ring from a striped satin
// V-ribbon that fades out upward; the tilt swings it like a pendulum round the ring (damped) and turns it to show the
// rim; a flick spins it and the ribbon twists a little. Renders only while something moves.
import {
  ACESFilmicToneMapping, CanvasTexture, Color, CylinderGeometry, DoubleSide, Group, Mesh, MeshPhysicalMaterial,
  MeshStandardMaterial, PerspectiveCamera, PlaneGeometry, PMREMGenerator, RepeatWrapping, Scene, SRGBColorSpace, Texture,
  TorusGeometry, WebGLRenderer,
} from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export type CoinState = () => { x: number; y: number; spin: number }; // tilt -1..1, spin in degrees
// the canvas round the coin, in coin sizes: wide enough for the swing, tall above for the ribbon
const W = 1.55, UP = 1.2, DOWN = 0.62;

/** Mounts the coin into `host`; resolves once the first frame is drawn. Throws without WebGL. */
export async function mountCoin(host: HTMLElement, o: { src: string; tint: string; ribbon: string[]; size: number; state: CoinState; onLand?: () => void }): Promise<() => void> {
  const renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1));
  const w = Math.round(o.size * W), up = Math.round(o.size * UP), h = up + Math.round(o.size * DOWN);
  renderer.setSize(w, h);
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.outputColorSpace = SRGBColorSpace;

  const scene = new Scene();
  const pmrem = new PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const env = pmrem.fromScene(room, 0.04).texture;
  scene.environment = env;
  // a frame symmetric round the coin (2 × up tall) of which the canvas shows the top: the coin stays where the flat
  // art was, at `size` px face on (radius 1 = size / 2 px)
  const camera = new PerspectiveCamera(2 * Math.atan(((2 * up) / o.size) / 7) * (180 / Math.PI), w / (2 * up), 0.1, 50);
  camera.position.z = 7;
  camera.setViewOffset(w, 2 * up, 0, 0, w, h);

  const face = await new Promise<HTMLImageElement>((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = o.src; });
  const front = new Texture(face); front.colorSpace = SRGBColorSpace; front.anisotropy = 4; front.needsUpdate = true;
  const back = front.clone(); back.wrapS = back.wrapT = RepeatWrapping; back.repeat.x = -1; back.center.set(0.5, 0.5); back.rotation = Math.PI; back.needsUpdate = true; // mirrored left to right, upright

  // milled ridges: one ridge per 8 px of a 64 px strip, repeated round the rim; a normal map tilting along the edge
  const c = document.createElement('canvas'); c.width = 64; c.height = 4;
  const g = c.getContext('2d')!;
  for (let x = 0; x < 64; x++) {
    const n = Math.sin((x / 8) * Math.PI * 2) * 0.75;
    g.fillStyle = `rgb(${Math.round((n * 0.5 + 0.5) * 255)}, 128, ${Math.round((Math.sqrt(1 - n * n) * 0.5 + 0.5) * 255)})`;
    g.fillRect(x, 0, 1, 4);
  }
  const ridges = new CanvasTexture(c); ridges.wrapS = RepeatWrapping; ridges.repeat.set(26, 1); // 26 × 8 ridges ≈ 208

  const metal = new Color(`rgb(${o.tint})`);
  const edge = new MeshStandardMaterial({ color: metal.clone().multiplyScalar(0.72), metalness: 1, roughness: 0.3, normalMap: ridges });
  const top = new MeshPhysicalMaterial({ map: front, metalness: 0.6, roughness: 0.32, clearcoat: 0.7, clearcoatRoughness: 0.12 });
  const bottom = new MeshPhysicalMaterial({ map: back, color: new Color(0.05, 0.05, 0.05), metalness: 0.6, roughness: 0.55 });
  const geo = new CylinderGeometry(1, 1, 0.19, 160, 1);
  geo.rotateX(Math.PI / 2).rotateZ(Math.PI / 2); // caps toward the camera, the art upright
  const coin = new Mesh(geo, [edge, top, bottom]);

  // the jump ring on the top edge, the rim's metal, in the coin's plane
  const RING = 1.13; // the pivot: the ring's centre
  const ringGeo = new TorusGeometry(0.12, 0.032, 16, 48);
  const ringMat = new MeshStandardMaterial({ color: metal.clone().multiplyScalar(0.85), metalness: 1, roughness: 0.22 });
  const ring = new Mesh(ringGeo, ringMat); ring.position.y = RING;
  const medal = new Group(); medal.add(coin, ring); medal.position.y = -RING; // yaw round the vertical through the ring
  const hang = new Group(); hang.add(medal); hang.position.y = RING; // the pendulum swings round the ring
  scene.add(hang);

  // the V-ribbon: two satin straps from the ring up and out, stripes of the medal's colours across, a gentle drape
  // (curved across the width), fading out toward the top so it never meets the capsule above
  const sc = document.createElement('canvas'); sc.width = 256; sc.height = 4;
  const sg = sc.getContext('2d')!;
  o.ribbon.forEach((col, i) => { sg.fillStyle = `rgb(${col})`; sg.fillRect(Math.floor((i * 256) / o.ribbon.length), 0, Math.ceil(256 / o.ribbon.length), 4); });
  const stripes = new CanvasTexture(sc); stripes.colorSpace = SRGBColorSpace; stripes.anisotropy = 4;
  const fc = document.createElement('canvas'); fc.width = 4; fc.height = 128;
  const fg = fc.getContext('2d')!, grad = fg.createLinearGradient(0, 0, 0, 128);
  grad.addColorStop(0, 'rgb(0, 0, 0)'); grad.addColorStop(0.15, 'rgb(0, 0, 0)'); grad.addColorStop(0.6, 'rgb(255, 255, 255)'); grad.addColorStop(1, 'rgb(255, 255, 255)');
  fg.fillStyle = grad; fg.fillRect(0, 0, 4, 128);
  const fade = new CanvasTexture(fc);
  const satin = new MeshPhysicalMaterial({ map: stripes, alphaMap: fade, transparent: true, side: DoubleSide, roughness: 0.55,
    sheen: 0.45, sheenRoughness: 0.35, sheenColor: new Color(0.8, 0.8, 0.85), clearcoat: 0.15, clearcoatRoughness: 0.5 });
  const LEN = 1.6, WID = 0.62; // up to the canvas's top edge (2.4 above the centre), where it has faded out
  const strapGeo = new PlaneGeometry(WID, LEN, 12, 24);
  strapGeo.translate(0, LEN / 2, 0);
  const pos = strapGeo.attributes.position;
  for (let i = 0; i < pos.count; i++) { const x = pos.getX(i) / (WID / 2); pos.setZ(i, -0.07 * x * x); } // satin bows across
  strapGeo.computeVertexNormals();
  const ribbon = new Group();
  for (const [side, z] of [[-1, -0.06], [1, -0.1]] as const) {
    const s = new Mesh(strapGeo, satin);
    s.rotation.z = side * 0.36; s.position.set(side * 0.04, 0.02, z);
    ribbon.add(s);
  }
  ribbon.position.y = RING;
  scene.add(ribbon);

  const canvas = renderer.domElement;
  canvas.style.cssText = `position:absolute;left:50%;top:${o.size / 2 - up}px;width:${w}px;height:${h}px;translate:-50% 0;pointer-events:none`;
  host.append(canvas);

  const deg = Math.PI / 180;
  // the pendulum: damped springs toward where the tilt pulls it (sideways and toward/away)
  const sw = { z: 9, vz: 0, x: 0, vx: 0 }; // the entrance starts it swinging
  // the entrance (owner, Nov 1: "super beautiful"): lowered from above on its ribbon on a damped spring (a slight
  // overshoot), 1.5 turns that slow to face front, a glint across the metal as it settles; ~1.2 s. Added on top of the
  // tilt and the finger, so nothing jumps when it ends
  const t0 = performance.now(), ZETA = 0.7, OMEGA = 5.5, WD = OMEGA * Math.sqrt(1 - ZETA * ZETA);
  let landed = false;
  let shown = '', raf = 0;
  const frame = () => {
    raf = requestAnimationFrame(frame);
    const t = (performance.now() - t0) / 1000, s = o.state();
    const drop = t > 1.6 ? 0 : 3.4 * Math.exp(-ZETA * OMEGA * t) * Math.cos(WD * t);
    if (!landed && drop <= 0) { landed = true; o.onLand?.(); }
    const p = Math.min(1, t / 1.05), turn = 540 * (1 - p) ** 3;
    const glint = t > 0.45 && t < 1.25 ? Math.sin(((t - 0.45) / 0.8) * Math.PI) : 0; // 0 → 1 → 0 round the settle
    hang.position.y = RING + drop; ribbon.position.y = RING + drop;
    scene.environmentRotation.y = glint * 0.9; // the room's lights slide across the metal
    renderer.toneMappingExposure = 1 + glint * 0.22;
    sw.vz = (sw.vz + (-s.x * 10 - sw.z) * 0.05) * 0.9; sw.z += sw.vz;
    sw.vx = (sw.vx + (s.y * 14 - sw.x) * 0.05) * 0.9; sw.x += sw.vx;
    const yaw = s.x * 26 + s.spin + turn;
    const key = `${sw.z.toFixed(2)},${sw.x.toFixed(2)},${yaw.toFixed(2)},${drop.toFixed(3)},${glint.toFixed(3)}`;
    if (key === shown) return; // nothing moved: no draw
    shown = key;
    hang.rotation.set(sw.x * deg, 0, sw.z * deg);
    medal.rotation.y = yaw * deg;
    ribbon.rotation.y = Math.sin(yaw * deg) * 0.18; // the ribbon twists a little with the medal
    renderer.render(scene, camera);
  };
  frame();
  return () => {
    cancelAnimationFrame(raf);
    for (const x of [geo, edge, top, bottom, front, back, ridges, ringGeo, ringMat, strapGeo, satin, stripes, fade, env, pmrem, renderer]) x.dispose();
    room.dispose();
    renderer.forceContextLoss();
    canvas.remove();
  };
}
