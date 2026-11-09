// A struck medal's back (owner, Nov 9: the drawn medals get the First 500's and the initiation's). No three.js here: the
// CSS coin of AwardSheet paints it in the main bundle, coin3d.ts uses the same grey for its map and bump.

/** polished metal, fine concentric guilloché and the app's colonnade (the icon's five columns) struck in low relief,
 *  on a 1024 px grey canvas: both the shading and the bump */
export function drawCoinBack(bg: CanvasRenderingContext2D) {
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
}

// the metal as a room reflects it, top left to bottom right: FACE of tools/medals.mjs without its pale peaks, the 3D
// coin's saturated tint (l: its HOLO foil)
const METAL: Record<string, string[]> = {
  b: ['#E8A673', '#CC7F45', '#A5602F', '#D9945C', '#8A4C24'],
  s: ['#E6EAF2', '#C6CDDB', '#98A2B8', '#DAE0EA', '#838DA3'],
  g: ['#FFC95A', '#E9A92F', '#C98A1C', '#EFB23C', '#B87A14'],
  l: ['#E0249A', '#FF8AE0', '#FFE8FB', '#9A6BFF', '#4A38D8', '#3FC0FF', '#E2FBFF', '#2FD9AE', '#129A6E', '#C4F566', '#FFFCD8', '#FFB036', '#E2513A', '#E0249A'],
};

/** the back in a metal (b, s, g, l) on a canvas, once: a flat picture, so the flip costs one layer */
export function paintCoinBack(c: HTMLCanvasElement, metal: string) {
  const S = 660; // 3x of the 220 px medal
  c.width = c.height = S;
  const g = c.getContext('2d')!, grey = document.createElement('canvas');
  grey.width = grey.height = 1024;
  drawCoinBack(grey.getContext('2d')!);
  g.beginPath(); g.arc(S / 2, S / 2, S / 2, 0, Math.PI * 2); g.clip();
  const shine = g.createLinearGradient(0, 0, S, S), stops = METAL[metal];
  stops.forEach((col, i) => shine.addColorStop(i / (stops.length - 1), col));
  g.fillStyle = shine; g.fillRect(0, 0, S, S);
  g.globalCompositeOperation = 'multiply'; g.drawImage(grey, 0, 0, S, S);
  // and again, half strength, as overlay: multiply alone left the guilloché and the columns fainter than on the 3D coin
  g.globalCompositeOperation = 'overlay'; g.globalAlpha = 0.5; g.drawImage(grey, 0, 0, S, S);
}
