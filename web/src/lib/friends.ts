// My one invite link: r_<link code>, the same for "Invite friends" and "Add a friend", in a QR or as our
// bot's card (a line and a button, never a bare link; a plain t.me share only where Telegram is older than Bot API
// 8.0). Opened, it lands on my card with "Add as a friend": one tap, friends; a newcomer counts as my referral.
import { shareCard } from './tg';
import { api, type PersonRef } from './api';

export const inviteUrl = (code: string): string => `https://t.me/KBTUappBot?startapp=r_${code}`;

export const shareInvite = (ready?: () => void): Promise<boolean> => shareCard({ kind: 'rf', id: '0' }, ready);

/** The invite QR watches one response at a time; closing it ignores any response still on its way. */
export function watchFriends(joined: (person: PersonRef) => void, paused: () => boolean): () => void {
  let since: number | null = null, busy = false, stopped = false;
  const watch = setInterval(async () => {
    if (stopped || busy || document.hidden || paused()) return;
    busy = true;
    try {
      const r = await api.friendJoined(since ?? 0), first = since === null;
      if (stopped || paused()) return;
      since = r.at;
      if (r.usedBy && !first) joined(r.usedBy);
    } catch { /* offline for a moment: the next round asks again */ }
    finally { busy = false; }
  }, 2500);
  return () => { stopped = true; clearInterval(watch); };
}
