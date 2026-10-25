// The instant re-open (CONTEXT, "Speed"): the last /api/me and the lists stay on the phone, one copy per Telegram account,
// are shown the moment the app starts and are replaced as soon as the server answers. A week old at most; deleting the
// account clears it.
import type { ClassItem, EventCard, Friends, Me, Org, PersonCard, Post, TeamMember } from '../api';
import { tg } from '../tg';

export interface Snapshot { me: Me | null; events: EventCard[]; orgs: Org[]; schedule: ClassItem[]; posts: Post[]; friends?: Friends | null; myCard?: PersonCard | null; news?: { casts: Post[]; posts: Post[] } | null;
  studio?: Record<number, EventCard[]>; team?: Record<number, TeamMember[]> }
const VERSION = 3, MAX_AGE = 7 * 86400 * 1000;
const key = () => (tg.user ? `kb-cache-${tg.user.id}` : null);

export function readCache(): Snapshot | null {
  const k = key();
  if (!k) return null;
  try {
    const c = JSON.parse(localStorage.getItem(k) ?? 'null');
    return c && c.v === VERSION && Date.now() - c.at < MAX_AGE ? (c.data as Snapshot) : null;
  } catch { return null; }
}

/** data: the Snapshot already as JSON (App serializes it anyway to watch for changes) */
export function writeCache(data: string): void {
  const k = key();
  if (!k) return;
  try { localStorage.setItem(k, `{"v":${VERSION},"at":${Date.now()},"data":${data}}`); } catch { /* storage full or blocked: next time from the network */ }
}

export function clearCache(): void {
  const k = key();
  if (k) try { localStorage.removeItem(k); } catch { /* nothing kept */ }
}
