// The motion tokens (tokens.css) for script-driven animation: WAAPI can't read var(). Read once for the app: a computed
// style read at every sheet's mount restyled the document inside the tap that opened it.
type Motion = { press: number; fast: number; base: number; slow: number; spring: number; ease: string; easeIn: string; easeSpring: string; easeBounce: string };
let read: Motion | null = null;
export function motion(): Motion {
  if (read) return read;
  const root = getComputedStyle(document.documentElement);
  const ms = (name: string, d: number) => { const v = root.getPropertyValue(name).trim(); return (parseFloat(v) || d / 1000) * (v.endsWith('ms') ? 1 : 1000); }; // the browser may hand it back in seconds
  const curve = (name: string) => root.getPropertyValue(name).trim() || 'ease-out';
  return (read = { press: ms('--t-press', 80), fast: ms('--t-fast', 120), base: ms('--t-base', 220), slow: ms('--t-slow', 380), spring: ms('--t-spring', 420),
    ease: curve('--ease'), easeIn: curve('--ease-in'), easeSpring: curve('--ease-spring'), easeBounce: curve('--ease-bounce') });
}
