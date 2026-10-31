// The launch's moments, one at a time (onboarding plan, Oct 31): a sheet or a celebration that isn't the answer to a
// tap waits until nothing is open, with a beat between two; taps and deep links never queue. A moment may return a
// promise (a chunk to fetch, a call): the next one waits for it, so two never land on top of each other.
// ponytail: FIFO with a poll; a priority field if a second launch moment ever needs to jump the line
export function queue(busy: () => boolean, gap = 600, poll = 800): (show: () => unknown) => void {
  const q: (() => unknown)[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined, running = false;
  const pump = (): void => {
    clearTimeout(timer);
    if (running || !q.length) return;
    timer = setTimeout(() => {
      if (busy()) { pump(); return; }
      running = true;
      Promise.resolve().then(q.shift()).catch(() => {}).finally(() => { running = false; pump(); });
    }, busy() ? poll : gap);
  };
  return (show) => { q.push(show); pump(); };
}
