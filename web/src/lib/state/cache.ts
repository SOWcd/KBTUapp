// The instant re-open: show the last lists from this Telegram account while the server answers.
import type { AlbumPhoto, GalleryAlbum, ClassItem, EventCard, Friends, Me, Org, PersonCard, Post, TeamMember } from '../api';
import { tg } from '../tg';
import { DRAFT_AGE, recovery } from './recovery';

export interface Snapshot { me: Me | null; events: EventCard[]; orgs: Org[]; schedule: ClassItem[]; posts: Post[]; castings?: Post[]; friends?: Friends | null; myCard?: PersonCard | null; news?: { casts: Post[]; posts: Post[] } | null;
  gallery?: AlbumPhoto[]; galleryAlbums?: GalleryAlbum[]; galleryPost?: { events: { id: number; title: string }[] } | null; studio?: Record<number, EventCard[]>; team?: Record<number, TeamMember[]> }
const KEY = 'snapshot';

export function readCache(): Snapshot | null {
  const snap = recovery.read<Snapshot>(recovery.peek(tg.user?.id), KEY, DRAFT_AGE);
  return snap?.me?.tg.id === tg.user?.id ? snap : null;
}

/** data: the Snapshot already as JSON (App serializes it anyway to watch for changes) */
export function writeCache(data: string): void {
  recovery.write(recovery.scope(), KEY, data);
}

export function clearCache(): void {
  recovery.clear(recovery.scope(), KEY);
}
