# Speed audit (PLAN 83), Oct 25

This audit only measures; it changes no code. Main at 78f0d21.

## How it was measured

- The real server (`server/tools/qa.py`, port 8792) with its made-up database. Built web/dist served from it, also with
  source maps (`vite build --sourcemap`) so profiles name source lines.
- Chrome 156 headless, Playwright `iPhone 13` profile (390x664, DPR 3, touch), **CPU throttled 4x** (a mid phone).
  Cold start also on a 9 Mbit/s, 40 ms network with the cache off.
- Every step is a real CDP touch (held 100-250 ms) or a click. Each step records a 1.2-3.5 s window with:
  rAF frame intervals (p50, p95, max, dropped frames), `long-animation-frame` entries with their
  script / style+layout / render split and the scripts behind them, a sampled CPU profile mapped to source lines,
  backdrop-filter elements on screen, the compositor layer count and running non-composited animations.
- Each step ran 3 times. The table gives medians.
- Overlays (the policy sheet, award `Unlock`) are closed first. An open `Unlock` changes everything (see cost 5). It
  was open during the item-81 measurements, and that explains the 250-330 ms frames seen then.

**Limits:** headless Chrome rasterizes in software, so paint and compositor costs (backdrop-filter, masks, filters) are
relative, not absolute. iPhone WebKit has a GPU but its own backdrop-filter costs. Script and layout costs with a 4x
throttle are a fair proxy for a mid phone. The QA database is small (2 events, 0 posts), so costs that grow with data
(lists, the cache snapshot) are lower bounds.

## Results

### Cold start (4x CPU, 6 runs)

| | median | range |
|---|---|---|
| first paint | 0.72 s | 0.62-0.83 |
| first contentful paint | 1.55 s | 1.35-1.70 |
| DOMContentLoaded | 1.47 s | 1.28-1.62 |
| main chunk evaluation (one task) | 0.53 s | 0.41-0.66 |
| first render of the data (`api` `Response.json.then`, one task) | 0.30 s | 0.27-0.97 |

Boot payload (index.html's module preloads + CSS): **739 kB raw / 224 kB gzip** in 13 files. The largest:

| chunk | raw | gzip | what |
|---|---|---|---|
| `Icon-*.js` | 296 kB | 91 kB | named after lucide's Icon, but it is mostly **all three dictionaries** `i18n/ru.ts`, `kk.ts`, `en.ts` (ru 33 kB, kk 31 kB, en 26 kB gzip as source) |
| `index-*.js` | 237 kB | 77 kB | App, all three tabs' first pages, EventSheet (48 kB source), PersonSheet, ClubSheet, Hero, map.ts |
| `index-*.css` | 114 kB | 22 kB | |
| `disclose-version-*.js` | 61 kB | 23 kB | the Svelte runtime |

Growth: the boot payload was 618 kB / 190 kB gzip at 1.0 (32c09fc, Oct 17), 708 / 215 at a173178 (Oct 24),
739 / 224 now (+18 % gzip in 8 days).

What the first data render spends its time on (CPU profile, self time at 4x): `List.svelte:70` effect 181 ms (a
`scrollLeft` write that forces a full layout of the half-built page), `Pager.svelte:35` `W()` 80 ms (`clientWidth`, the
same kind of forced layout), `time.ts:38` `fmt` 63 ms (Intl formatting + a regex per call), `Capsule.svelte:106` 30 ms.

### Interactions (4x CPU, medians of 3 runs)

| step | p95 frame | max frame | dropped | long frames ms | script | style+layout | render | backdrop on screen | layers |
|---|---|---|---|---|---|---|---|---|---|
| idle List | 16.8 | 17 | 0 | 0 | 0 | 0 | 0 | 3 | 33 |
| swipe List > Feed | 16.8 | 33 | 1 | 0 | 0 | 0 | 0 | 3 | 27 |
| idle Feed | 16.7 | 17 | 0 | 0 | 0 | 0 | 0 | 3 | 29 |
| Feed: Going | 16.8 | 117 | 7 | 116 | 94 | 9 | 17 | 3 | 29 |
| Feed: Save | 16.8 | 33 | 2 | 0 | 0 | 0 | 0 | 3 | 29 |
| swipe Feed > List | 16.8 | 50 | 3 | 0 | 0 | 0 | 0 | 3 | 25 |
| swipe List > News | 16.7 | 17 | 0 | 0 | 0 | 0 | 0 | 3 | 25 |
| swipe News > List | 16.8 | 17 | 0 | 0 | 0 | 0 | 0 | 3 | 25 |
| event sheet open | 16.8 | 133 | 8 | 112 | 97 | 4 | 6 | 2 | 23 |
| event sheet close | 16.8 | 17 | 0 | 0 | 0 | 0 | 0 | 3 | 27 |
| tab Clubs (first visit) | 16.8 | 167 | 10 | 158 | 138 | 6 | 9 | 3 | 27 |
| tab Profile (first visit) | 16.8 | 183 | 17 | 283 | 259 | 11 | 16 | 3 | 27 |
| idle Profile | 16.8 | 17 | 0 | 0 | 0 | 0 | 0 | 3 | 29 |
| map open | 33.4 | 100 | 17 | 101 | 86 | 3 | 7 | 6 | 30 |
| map close | 33.3 | 33 | 10 | 0 | 0 | 0 | 0 | 3 | 29 |
| swipe to Settings | 16.7 | 17 | 0 | 0 | 0 | 0 | 0 | 3 | 25 |
| theme switch | 16.8 | 17 | 0 | 0 | 0 | 0 | 0 | 3 | 27 |
| tab Afisha (back) | 16.7 | 67 | 3 | 54 | 12 | 36 | 36 | 3 | 25 |

Times are in ms. "Long frames ms" is the sum of long animation frames (> 50 ms) in the window. Swipes and idle screens
are smooth. The cost is in what a tap builds: first visits, sheets, the map, the response to Going.

Backdrop-filter at rest: 3 on screen (capsule, nav, map button); 2-3 more for a sheet (scrim, sheet); 6 with the map
(rail, bar, exit, 2 round buttons). No infinite animation on a non-composited property at rest. One infinite animation
runs on a hidden page: the Feed's end-slide emoji `float` keeps ticking while the Feed page is hidden (`Feed.svelte:161`,
small).

### Item 3: the 250-330 ms render-only frame after a tap (item 81)

It does not reproduce once overlays are closed. After a Save tap at 4x, the worst long frame was a median of **52 ms**
(53 / 52 / 0). Toggling candidates by injected CSS (3 runs each, worst long frame): no toast backdrop 0 / 0 / 155;
toast animations off 56 / 0 / 59; text blur off 54 / 0 / 67; confetti hidden 82 / 0 / 0; toast hidden 0 / 0 / 0;
all backdrop off 0 / 0 / 0. So the toast's glass backdrop (and maybe the burst) is a ~50 ms item that doesn't appear
every time, not 250-330 ms.

The big frames came from the award `Unlock` overlay that was open during those runs (Bota, fresh, no throttle, 3 s idle
window with it up): **72-114 dropped frames**, long frames up to 863 ms. With `.shine::after` (the sweep) off: 19 / 1
dropped. With the sweep and the scrim's backdrop both off: 0 / 0. With the overlay hidden: 0 / 0. See cost 5.

## Top 5 costs, ranked by measured impact

1. **Cold start: one 0.4-0.66 s evaluation task, then a 0.27-0.97 s first render; 224 kB gzip on the critical path.**
   - Culprits: `web/src/lib/i18n/index.svelte.ts:4-6` imports ru, kk and en statically. About 57 kB gzip (~190 kB raw to
     parse) is a language nobody on that device uses (25 % of the boot payload). `index-*.js` also carries EventSheet,
     PersonSheet and ClubSheet, which no first screen shows. The first render forces layouts: `List.svelte:70` (181 ms)
     and `Pager.svelte:35` (80 ms).
   - Fix:
     - Import the active dictionary only and `import()` the others on a language switch (ru stays as the fallback type
       source).
     - Lazy-load the three sheets like the other sheets.
     - In `List.svelte:70`, skip the `scrollLeft = 0` write on the first run (the stack is already at 0).
     - Measure `Pager`'s width in `onMount` after a frame or from a ResizeObserver, not mid-flush.
   - Expected gain: about -60 kB gzip and -150-250 ms of evaluation, plus -150-250 ms off the first render (forced
     layouts) at 4x; FCP about 1.55 s -> ~1.2 s (estimate).

2. **Forced synchronous layout in the Capsule's title fit: 48-115 ms on every first visit of a tab** (it is the
   `MutationCallback` in the Clubs and Profile long frames: 82 / 48 ms and 115 / 77 ms of `clientWidth`).
   - Culprit: `web/src/ui/Capsule.svelte:105-112` `fit()`. A MutationObserver runs `run()` as a microtask right after a
     new title is set, while Svelte is still mounting the new tab's page. Reading `clientWidth/scrollWidth` forces layout
     of all of it, then the `fontSize` write invalidates it again. Added in d9b6cd3 (Oct 23).
   - Fix: run the measure in `requestAnimationFrame` (one per frame, coalesced), or use ResizeObserver on the text span
     alone, or a CSS-only fit (container query units on the title).
   - Expected gain: -50-110 ms per first tab visit and per title change (tab Profile 283 -> ~180 ms, Clubs 158 -> ~90).

3. **Map iris: a forced layout and a mask repaint of a backdrop-filter element on every frame of the open and close.**
   - Measured: map open 101 ms of long frames, 90-108 ms in `offsetWidth`, 65-84 ms in `getBoundingClientRect` per open.
     p95 frame 33 ms and 10-17 dropped frames on open and on close: the only steps whose p95 is above 16.7.
   - Culprit: `web/src/screens/map/CampusMap.svelte:409-428` `split()`/`frame()`. Each frame reads `h.offsetWidth` and
     two `getBoundingClientRect`s, then writes a `radial-gradient` `mask` on the real capsule (`.glass`, a
     `backdrop-filter`) and on its copy, so the blurred backdrop is repainted every frame. Added in cfa2572 (Oct 25).
     Also the `import()` of CampusMap on the tap: 72-130 ms (`App.svelte:108`).
   - Fix:
     - Read both rects once when the iris starts (the capsule is fixed).
     - Take the radius from the clip animation's own timing (`anim.currentTime` -> same easing) instead of `offsetWidth`.
     - While the iris runs, put the mask on a capsule copy without `backdrop-filter` (a solid tinted copy for those
       480 ms).
     - Prefetch the CampusMap chunk on the map button's `pointerdown` or at idle.
   - Expected gain: -150-190 ms of main-thread work per open/close and p95 back to ~16.7 ms. The chunk prefetch removes
     another ~70-130 ms from the tap.

4. **The app-wide cache effect: a deep read on every change, a 63 ms task a second later.**
   - Culprit: `web/src/App.svelte:270-275`. `JSON.stringify(snap)` inside an `$effect` reads every field of me, events,
     orgs, schedule, posts, friends, news, studio and team through Svelte proxies. It subscribes to all of them, so any
     change anywhere re-runs it inside that change's flush. Then `$state.snapshot` (a structuredClone through the
     proxies) + `JSON.stringify` + `localStorage.setItem` run in one timer task.
   - Measured on Going: the post-response flush is 94-104 ms (`Response.json.then`), 28 ms of it `clone`, and then a
     63 ms `TimerHandler` at `App.svelte:275`. The same data as plain objects stringifies in 0.2 ms and clones in 1.1 ms,
     so the cost is the proxies. With real data (dozens of events, posts, news) it grows.
   - Fix: write the cache from the places that load data (after `loadAfisha` / `put` / the refetches) with `untrack`,
     or only on `visibilitychange` -> hidden and `pagehide`. In either case use `requestIdleCallback` and read the
     plain values once.
   - Expected gain: -60-90 ms per data change at 4x (Going goes from 116 ms to ~40 ms of long frames), more with real
     data.

5. **Award `Unlock` overlay: 72-114 dropped frames in 3 s even without throttling.**
   - Culprit: `web/src/screens/sheets/Unlock.svelte` styles. The `.shine::after` sweep (infinite, 2.6 s) under
     `mix-blend-mode: soft-light`, inside `.medal`, which has two large `drop-shadow` filters (34 px and 30 px). So the
     filtered medal is re-rasterized every frame, over a full-screen `.scrim` with `backdrop-filter: blur(16px)`.
   - Measured: sweep off -> 19 / 1 dropped; sweep and backdrop off -> 0 / 0; overlay hidden -> 0 / 0. It is up only until
     the student taps OK, but it is the first thing a new student with an award sees, and it is what made the item-81
     runs look slow.
   - Fix: run the sweep on a separate layer outside the filtered element (a sibling over the medal with `will-change:
     transform`), drop the blend mode or pre-render the shine. Bake the drop-shadow glow into the medal image or use a
     static blurred pseudo-element. Lower the scrim to a darker solid with a smaller blur.
   - Expected gain: ~0 dropped frames while the award is up.

## Smaller items seen

- **Tab Profile's first visit:** `Hero.svelte:35` imports the QR encoder and draws the code at once: 63-93 ms
  (`qrcode-generator` `getLostPoint`/`isDark`). It could wait for idle or the first time the code is visible.
- **Event sheet open:** 97-135 ms, mostly Svelte mounting EventSheet in one flush, plus `getBoundingClientRect` 24-43 ms
  (`App.svelte:423`, `Sheet.svelte:35`). Rendering the sheet's lower sections after the open settles (as B4 did for the
  person sheet) would halve it.
- **Toast:** its glass backdrop is a ~50 ms item that doesn't appear every time (item 3). `Toast.svelte` also animates
  `width` during a morph (one 420 ms tween per new phrase, layout every frame; fine at that size).
- **`time.ts:38` `fmt`:** 63 ms during the first render. The regex `replace` runs on every formatted date. Caching the
  formatted string per (lang, opts, minute) would make it free.
- **Feed `float` animation** keeps ticking on the hidden Feed page (`Feed.svelte:161`). It could pause when the page is
  hidden (the `shown` derived already exists).

## Commits that likely regressed (last 2 weeks of web/, 123 commits)

- d9b6cd3 (Oct 23) Capsule title fit: cost 2.
- cfa2572 (Oct 25) Map iris capsule cut: cost 3, the per-frame split.
- abd70fe (Oct 24) Toast morph and grow: the width tween and clip-path entrance; small (item 3).
- 73e6b27 (Oct 21) `List.svelte:70` scrollLeft reset: a forced layout at boot and at each Going.
- 08bcc07, 7c3a0e2 (Oct 24) News as stories and the news page: more code in the boot chunk.
- The dictionaries grew from 99 kB to 115 kB of source (ru) since 1.0. Since 1.0 the boot payload grew +34 kB gzip
  (+18 %).
- a173178 (Oct 24) "springy press": the 450 ms bounce on every button (the root of item 81, fixed in ba4cbd2/78f0d21).
