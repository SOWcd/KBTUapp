// End-to-end: the real app (web/dist) on a real server (server/tools/qa.py, a fresh seeded database per test) in
// iPhone-sized windows, both themes, WebKit and Chromium. `npm run e2e` builds first; e2e/fixtures.ts has the harness.
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

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/results',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never', outputFolder: 'e2e/report' }]] : [['list'], ['html', { open: 'never', outputFolder: 'e2e/report' }]],
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    reducedMotion: 'no-preference', // animations run, as on a phone
    serviceWorkers: 'block',
  },
  // every flow in every browser, phone size and theme: 8 projects
  projects: browsers.flatMap((b) => phones.flatMap((p) => themes.map((theme) => ({
    name: `${b.name}-${p.name}-${theme}`,
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
});
