// Telegram on Android (issue #71), the `android` project: the app opened the way Telegram for Android opens it
// (tgWebAppPlatform=android, Telegram's Android user agent with its performance class), 360x800 (the most common
// Android width), the CPU 4x slower (a mid phone). It checks where the tab bar sits under Telegram's insets (gesture
// and 3-button navigation), that a LOW phone gets the light look, and measures what the stats say stutters on Android
// (`admin stats-week`: sheet.news the slowest, p75 under 2 s): a 100-post News, its tap to the first frame and how long
// it holds the main thread after. The numbers go to the job summary, to compare a change before and after.
import { appendFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect, type Phone } from './fixtures';
import en from '../src/lib/i18n/en';

const tr = (k: keyof typeof en) => en[k] as string;
const report = (lines: string[]) => {
  const text = lines.join('\n');
  console.log(text);
  test.info().annotations.push({ type: 'android numbers', description: text });
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${text}\n\n`);
};
const english = (page: Page) => page.addInitScript(() => { try { localStorage.setItem('kb-lang', 'en'); } catch { /* storage blocked */ } });
const tgEvent = (page: Page, type: string, data: unknown) => page.evaluate(([t, d]) =>
  (window as unknown as { Telegram: { WebView: { receiveEvent: (e: string, d: unknown) => void } } }).Telegram.WebView.receiveEvent(t as string, d), [type, data]);

test('the tab bar sits 10 px over the bottom under any Telegram inset', async ({ open }) => {
  const p = await open('Ali');
  await expect(p.page.locator('html')).toHaveAttribute('data-android', '');
  const nav = p.page.locator('nav.nav');
  await expect(nav).toBeVisible();
  const gaps: string[] = [];
  // what Telegram for Android reports (stats-layout: 0, 9-16 with gestures, 33-48 with the 3 buttons); its web view
  // already ends above the system bar, so the bar stays where it is (tokens.css [data-android])
  for (const bottom of [0, 16, 48]) {
    await tgEvent(p.page, 'safe_area_changed', { top: 32, bottom, left: 0, right: 0 });
    await tgEvent(p.page, 'content_safe_area_changed', { top: 48, bottom: 0, left: 0, right: 0 });
    await p.page.waitForTimeout(400);
    const gap = await p.page.evaluate(() => Math.round(innerHeight - document.querySelector('nav.nav')!.parentElement!.getBoundingClientRect().bottom));
    gaps.push(`inset ${bottom}: ${gap} px`);
    expect(gap, `the tab bar's gap with Telegram's bottom inset ${bottom}`).toBe(10);
  }
  report([`**Android tab bar gap** (10 by design): ${gaps.join(' · ')}`]);
});

test('News with 100 posts: tap to first frame, main thread after', async ({ page, qa, open }) => {
  // a hundred club posts, as on production (the server's cap), each long enough to fold
  qa.sql(`INSERT INTO posts (org_id, author_id, title, body, created_at)
    WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 100)
    SELECT 1, 1, 'Club news ' || i, substr(replace(hex(zeroblob(20)), '00', 'Rehearsal moves to the Atrium this week, bring friends. '), 1, 400),
      CAST(strftime('%s', 'now') AS INTEGER) - i * 3600 FROM n;`);
  await english(page);
  const p: Phone = await open('Ali');
  const more = p.page.locator('[data-more]'); // News opens from the Afisha's "More" (its menu)
  await expect(more).toBeVisible();
  await p.page.waitForTimeout(4000); // the News chunk warmed in an idle moment (App warmPages), as on a phone a few seconds in
  await p.page.evaluate(() => {
    const w = window as unknown as { __long: { start: number; duration: number }[] };
    w.__long = [];
    new PerformanceObserver((l) => { for (const e of l.getEntries()) w.__long.push({ start: e.startTime, duration: e.duration }); }).observe({ type: 'longtask' });
  });
  // five opens (one run's single number wobbles by tens of ms), each: the tap to the frame after the sheet's first post
  // is on the screen (lib/stats.ts timed()), the long tasks in the 3 s after, the last post scrolled to, then Back
  const runs: { tti: number; max: number; tbt: number; posts: number; last: number }[] = [];
  for (let i = 0; i < 5; i++) {
    await more.click(); // the menu first, outside the measure: the tap timed is the one on "News"
    await expect(p.page.getByRole('menuitem', { name: tr('page.news'), exact: true })).toBeVisible();
    const { tti, t0 } = await p.page.evaluate(async (label) => {
      const b = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].find((x) => x.textContent?.trim() === label)!;
      const t0 = performance.now();
      b.click();
      await new Promise<void>((done) => {
        const tick = () => document.querySelector('[role="dialog"] article.post') ? requestAnimationFrame(() => done()) : requestAnimationFrame(tick);
        requestAnimationFrame(tick);
      });
      return { tti: performance.now() - t0, t0 };
    }, tr('page.news'));
    await p.page.waitForTimeout(3000);
    const after = await p.page.evaluate(async (t0) => {
      const long = (window as unknown as { __long: { start: number; duration: number }[] }).__long.filter((e) => e.start >= t0);
      const posts = document.querySelectorAll('[role="dialog"] article.post').length;
      // scrolled to the end: is the last post shown at once (not still fading in on a delay)?
      const body = document.querySelector<HTMLElement>('[role="dialog"] .body')!;
      body.scrollTop = body.scrollHeight;
      await new Promise((r) => setTimeout(r, 300));
      const cards = document.querySelectorAll<HTMLElement>('[role="dialog"] article.post');
      return { max: Math.max(0, ...long.map((e) => e.duration)), tbt: long.reduce((s, e) => s + e.duration - 50, 0), posts,
        last: Number(getComputedStyle(cards[cards.length - 1].parentElement!).opacity) };
    }, t0);
    runs.push({ tti, ...after });
    await p.back.press();
    await expect(p.page.locator('[role="dialog"]')).toHaveCount(0);
    await p.page.waitForTimeout(1000);
  }
  const med = (k: 'tti' | 'max' | 'tbt') => Math.round(runs.map((r) => r[k]).sort((x, y) => x - y)[2]);
  const all = (k: 'tti' | 'max' | 'tbt') => runs.map((r) => Math.round(r[k])).join('/');
  report([
    `**Android News, 100 posts, CPU 4x, median of 5** · tap → first frame ${med('tti')} ms (${all('tti')}) · in the 3 s after: the longest task ${med('max')} ms (${all('max')}), blocking ${med('tbt')} ms (${all('tbt')}) · the last post's opacity 0.3 s after scrolling to it: ${runs.map((r) => r.last).join('/')}`,
  ]);
  for (const r of runs) {
    expect(r.posts, 'every post drawn within 3 s').toBe(100);
    expect(r.last, 'the last post is there when scrolled to, not fading in on a delay').toBe(1);
  }
});

test.describe('a phone Telegram marks LOW', () => {
  test.use({ userAgent: 'Mozilla/5.0 (Linux; Android 11; SM-A125F Build/RP1A.200720.012; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36 Telegram-Android/11.5.3 (Samsung SM-A125F; Android 11; SDK 30; LOW)' });
  test('gets the light look: no live blur anywhere', async ({ open }) => {
    const p = await open('Ali');
    await expect(p.page.locator('html')).toHaveClass(/lowfx/);
    const blurred = await p.page.evaluate(() => [...document.querySelectorAll('*')].filter((el) => {
      const s = getComputedStyle(el);
      return (s.backdropFilter && s.backdropFilter !== 'none') || ((s as unknown as Record<string, string>).webkitBackdropFilter ?? 'none') !== 'none';
    }).length);
    expect(blurred, 'elements with a live blur on a LOW phone').toBe(0);
  });
});
