import { afterEach, expect, it, vi } from 'vitest';
import type { AlbumPhoto, ClassItem, EventCard, GalleryPage, Post } from '../api';

const { posts, gallery, events, schedule, castings } = vi.hoisted(() => ({
  posts: vi.fn(), gallery: vi.fn(), events: vi.fn(), schedule: vi.fn(), castings: vi.fn(),
}));
vi.mock('../api', async () => ({
  api: { posts, gallery, events, schedule, castings, orgs: async () => [], pastEvents: async () => [], attendedEvents: async () => [], chats: async () => ({}) },
  ApiErr: (await import('../api/errors')).ApiErr,
}));
vi.mock('./session.svelte', () => ({ session: { me: { id: 1, student: {}, memberships: [{}] } }, asStudent: vi.fn(), loadMe: vi.fn() }));
vi.mock('./ui.svelte', () => ({ close: vi.fn(), overlays: [], say: vi.fn() }));
vi.mock('../i18n/index.svelte', () => ({ t: (k: string) => k, tn: (k: string) => k, subjectOf: vi.fn(), i18n: { lang: 'en' } }));
vi.mock('../tg', () => ({ tg: { initData: '' }, haptic: {}, requestWriteAccess: vi.fn() }));
vi.mock('../stats', () => ({ count: vi.fn(), timed: vi.fn(), failed: vi.fn() }));
vi.mock('../../ui/burst', () => ({ burst: vi.fn() }));
vi.mock('./cache', () => ({ clearCache: vi.fn() }));
import { data, galleryGone, loadAfisha, loadGallery, loadNews, loadSchedule } from './data.svelte';

function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: Error) => void;
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}
const post = (id: number) => ({ id, photo: null }) as Post;
const photo = (id: number, extra: Partial<AlbumPhoto> = {}): AlbumPhoto => ({ id, url: '', thumb: '', w: 1, h: 1, blur: '', canDelete: true, by: null, mine: true, ...extra });
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.clearAllMocks(); });

it('publishes events and classes while castings are still pending', async () => {
  vi.useFakeTimers();
  const eventsRead = deferred<EventCard[]>(), scheduleRead = deferred<ClassItem[]>(), castingsRead = deferred<Post[]>();
  const event = { id: 1 } as EventCard;
  const lesson = { weekday: 1, begins: '12:00', ends: '13:00', subject: 'Algorithms', room: null, teacher: null, kind: null };
  events.mockReturnValueOnce(eventsRead.promise);
  schedule.mockReturnValueOnce(scheduleRead.promise);
  castings.mockReturnValueOnce(castingsRead.promise);
  posts.mockResolvedValueOnce([]);
  const loading = loadAfisha();
  const week = loadSchedule(true);
  expect(schedule).toHaveBeenCalledTimes(1);
  eventsRead.resolve([event]);
  scheduleRead.resolve([lesson]);
  await week;
  expect(data.eventsReady).toBe(true);
  expect(data.events).toEqual([event]);
  expect(data.schedule).toEqual([lesson]);
  castingsRead.reject(new Error('offline'));
  await loading;
});

it('keeps fresh club posts when broadcasts fail', async () => {
  vi.useFakeTimers();
  const fresh = deferred<Post[]>(), failed = deferred<Post[]>();
  posts.mockImplementation((scope: string) => scope === 'subs' ? fresh.promise : failed.promise);
  data.news = { casts: [post(1)], posts: [post(2)] };
  const loading = loadNews(true);
  expect(loadNews(true)).toBe(loading);
  fresh.resolve([post(3)]);
  await Promise.resolve();
  expect(data.news.posts).toEqual([post(3)]); // visible before broadcasts settle
  failed.reject(new Error('offline'));
  await loading;
  expect(data.news).toEqual({ casts: [post(1)], posts: [post(3)] });
  expect(posts).toHaveBeenCalledTimes(2);
});

it('keeps published gallery pages and local changes when a later page fails', async () => {
  vi.useFakeTimers();
  const first = deferred<GalleryPage>(), second = deferred<GalleryPage>(), stale = deferred<GalleryPage>(), last = deferred<GalleryPage>();
  gallery.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(stale.promise).mockReturnValueOnce(last.promise);
  data.gallery = [photo(-1, { pending: true }), photo(-2, { failed: true }), photo(99)];
  data.galleryState = 'new';
  const loading = loadGallery(true);
  first.resolve({ photos: [photo(5), photo(4)], more: true });
  await Promise.resolve();
  expect(data.galleryState).toBe('ready');
  expect(data.gallery.map((p) => p.id)).toEqual([-1, -2, 5, 4]);
  data.gallery[0] = photo(6); // an upload finishes while page two is on its way
  second.resolve({ photos: [photo(4), photo(3)], more: true });
  await Promise.resolve();
  expect(data.gallery.map((p) => p.id)).toEqual([6, -2, 5, 4, 3]);
  galleryGone(photo(4));
  stale.resolve({ photos: [photo(2)], more: true });
  await Promise.resolve();
  last.reject(new Error('offline'));
  await loading;
  expect(data.gallery.map((p) => p.id)).toEqual([6, -2, 5, 3]);
  expect(data.galleryState).toBe('ready');
  expect(gallery.mock.calls).toEqual([[], [4], [3], [3]]);
});
