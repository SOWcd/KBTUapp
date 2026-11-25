import { test, expect } from './fixtures';

test('the app opens as a student', async ({ open }) => {
  const ali = await open('Ali');
  await expect(ali.page.getByText('Open Mic: stand-up and music').first()).toBeVisible();
  await ali.look('home');
});
