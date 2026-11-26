// End-to-end: the real app (web/dist) on a real server (server/tools/qa.py, a fresh seeded database per test) in
// iPhone-sized windows, both themes, WebKit and Chromium. `npm run e2e` builds first; e2e/fixtures.ts has the harness,
// e2e/README.md how to run it, the screen snapshots and the a11y check (snap-* projects, e2e/snap.spec.ts, e2e/a11y.spec.ts).
import { defineConfig, devices } from '@playwright/test';

const phones = [
  { name: '375', viewport: { width: 375, height: 812 } },
  { name: '320', viewport: { width: 320, height: 568 } },
];
const browsers = [
  { name: 'webkit', device: devices['iPhone 13'] },
  { name: 'chromium', device: devices['Pixel 7'] },
];
const themes = ['dark', 'light'] as const;
// the snapshots' clock: Wednesday 25 Nov 2026, 10:00 in Almaty (qa.py --now)
const SNAP_AT = 1795582800;
// PW_WS: the browser in Playwright's Linux image (e2e/linux.sh); the app's servers stay on this machine, reached through it
const remote = process.env.PW_WS ? { wsEndpoint: process.env.PW_WS, exposeNetwork: '<loopback>' } : undefined;

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/results',
  timeout: 90_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never', outputFolder: 'e2e/report' }]] : [['list'], ['html', { open: 'never', outputFolder: 'e2e/report' }]],
  snapshotPathTemplate: '{testDir}/snapshots/{arg}-{projectName}{ext}', // one Linux browser makes them: no platform suffix
  // 300 px is 0.1% of a screen: a crest's antialiasing wobbles by ~250, a real slip moves thousands
  expect: { timeout: 10_000, toHaveScreenshot: { maxDiffPixels: 300, threshold: 0.2, animations: 'disabled', caret: 'hide' } },
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    reducedMotion: 'no-preference', // animations run, as on a phone
    serviceWorkers: 'block',
    connectOptions: remote,
  },
  projects: [
  // every flow in every browser, phone size and theme: 8 projects
  ...browsers.flatMap((b) => phones.flatMap((p) => themes.map((theme) => ({
    name: `${b.name}-${p.name}-${theme}`,
    testIgnore: /(snap|a11y)\.spec\.ts$/,
    use: {
      ...b.device,
      browserName: b.device.defaultBrowserType,
      viewport: p.viewport,
      colorScheme: theme,
      // a real phone's touch screen; the device's own user agent stays (iPhone / Android)
      hasTouch: true,
      isMobile: b.name === 'chromium', // WebKit has no isMobile
    },
    metadata: { theme },
  })))),
  // the key screens' pictures: Chromium at 375x812, motion reduced, on the fixed clock
  ...themes.map((theme) => ({
    name: `snap-${theme}`,
    testMatch: /(snap|a11y)\.spec\.ts$/, // and the a11y check, on the same screens and clock
    use: {
      ...devices['Pixel 7'],
      viewport: phones[0].viewport,
      deviceScaleFactor: 1, // light pictures in the repo; the bugs they catch are bigger than a pixel
      colorScheme: theme,
      hasTouch: true,
      reducedMotion: 'reduce' as const,
    },
    metadata: { theme, now: SNAP_AT },
  })),
  ],
});
