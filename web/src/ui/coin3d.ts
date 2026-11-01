// A real 3D coin for the award view (owner, Nov 1: the CSS layers read as "a picture moving to emulate 3D").
// three.js lives only in this lazy chunk. A cylinder ~9.5% thick: the drawn medal is the front cap, a mirrored darker
// copy the back, the edge milled metal (a canvas normal map) in the medal's metal; RoomEnvironment gives the
// reflections that move as it turns. Renders only when the tilt or the spin changed.
import {
  ACESFilmicToneMapping, CanvasTexture, Color, CylinderGeometry, Mesh, MeshPhysicalMaterial, MeshStandardMaterial,
  PerspectiveCamera, PMREMGenerator, RepeatWrapping, Scene, SRGBColorSpace, Texture, WebGLRenderer,
} from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export type CoinState = () => { x: number; y: number; spin: number }; // tilt -1..1, spin in degrees
export const PAD = 1.3; // the canvas is this much bigger than the coin: room for the rim when it turns

/** Mounts the coin into `host`; resolves once the first frame is drawn. Throws without WebGL. */
export async function mountCoin(host: HTMLElement, o: { src: string; tint: string; size: number; state: CoinState }): Promise<() => void> {
  const renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1));
  const px = Math.round(o.size * PAD);
  renderer.setSize(px, px);
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.outputColorSpace = SRGBColorSpace;

  const scene = new Scene();
  const pmrem = new PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const env = pmrem.fromScene(room, 0.04).texture;
  scene.environment = env;
  const camera = new PerspectiveCamera(30, 1, 0.1, 50);
  camera.position.z = PAD / Math.tan((15 * Math.PI) / 180); // a coin of radius 1 spans `size` px face on

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
  scene.add(coin);

  const canvas = renderer.domElement;
  canvas.style.cssText = `position:absolute;left:50%;top:50%;width:${px}px;height:${px}px;translate:-50% -50%;pointer-events:none`;
  host.append(canvas);

  const deg = Math.PI / 180;
  let shown = '', raf = 0;
  const frame = () => {
    raf = requestAnimationFrame(frame);
    const s = o.state(), key = `${s.x.toFixed(3)},${s.y.toFixed(3)},${s.spin.toFixed(2)}`;
    if (key === shown) return; // nothing moved: no draw
    shown = key;
    coin.rotation.set(s.y * 22 * deg, (s.x * 26 + s.spin) * deg, 0, 'YXZ');
    renderer.render(scene, camera);
  };
  frame();
  return () => {
    cancelAnimationFrame(raf);
    for (const x of [geo, edge, top, bottom, front, back, ridges, env, pmrem, renderer]) x.dispose();
    room.dispose();
    renderer.forceContextLoss();
    canvas.remove();
  };
}
