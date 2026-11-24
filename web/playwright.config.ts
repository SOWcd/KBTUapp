// End-to-end: the built app on a fresh seeded qa.py server per spec file (e2e/fixtures.ts), on iPhone-sized screens.
// Four projects cover each browser, size and theme at least once; E2E_FULL=1 runs all eight combinations.
import { defineConfig, devices, type Project } from '@playwright/test';

const sizes = { '375': { width: 375, height: 812 }, '320': { width: 320, height: 568 } } as const;
type Combo = [browser: 'chromium' | 'webkit', size: keyof typeof sizes, theme: 'dark' | 'light'];
const pairs: Combo[] = [['chromium', '375', 'dark'], ['chromium', '320', 'light'], ['webkit', '375', 'light'], ['webkit', '320', 'dark']];
const all: Combo[] = (['chromium', 'webkit'] as const).flatMap((b) => (['375', '320'] as const).flatMap((s) => (['dark', 'light'] as const).map((t): Combo => [b, s, t])));

const project = ([browser, size, theme]: Combo): Project => ({
  name: `${browser}-${size}-${theme}`,
  use: {
    ...devices['iPhone 13'],
    defaultBrowserType: browser,
    viewport: sizes[size],
    colorScheme: theme,
  },
});

export default defineConfig({
  testDir: 'e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // a spec file's tests share its server, in order
  workers: process.env.CI ? 2 : undefined,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list'], ['html', { open: 'never' }]],
  outputDir: 'test-results',
  use: { trace: 'retain-on-failure', screenshot: 'only-on-failure', actionTimeout: 10_000 },
  projects: (process.env.E2E_FULL ? all : pairs).map(project),
});
