// The rank rule from SPEC §2, the UI's copy: it hides what you can't do; the server enforces it (logic.py).
import type { ClubLevel, OrgRole, Right } from './api/types';

export const RANK: Record<OrgRole, number> = { member: 1, head: 2, vice: 3, president: 4 };

/** Role titles stay English in every language, as KBTU clubs use them. */
// Club titles stay in English in every language: KBTU clubs print them so on lanyards and badges, and that's
// how students say them (owner, Oct 4)
export const ROLE_NAME: Record<OrgRole, string> = { president: 'President', vice: 'Vice', head: 'Head', member: 'Member' };

/** Highest role first. */
export const byRank = (a: { role: OrgRole }, b: { role: OrgRole }): number => RANK[b.role] - RANK[a.role];

/** A club role's rights (SPEC §2), the toggles of its editor in order, each with the level it needs: the highest one a role
 *  has ranks it (whom it acts on). A level without a club role has its level's (owner, Oct 7: "as in Telegram"). */
export const RIGHTS: { key: Right; level: ClubLevel }[] = [
  { key: 'door', level: 'member' }, { key: 'events', level: 'head' }, { key: 'posts', level: 'head' }, { key: 'people', level: 'head' },
  { key: 'casting', level: 'head' }, { key: 'team', level: 'vice' }, { key: 'money', level: 'vice' }, { key: 'memo', level: 'vice' }, { key: 'profile', level: 'vice' },
];
/** what a level has without a club role (and a role made before the toggles) */
export const levelRights = (l: OrgRole): Right[] => RIGHTS.filter((r) => RANK[r.level] <= RANK[l]).map((r) => r.key);
/** the level a set of rights makes: the highest one's */
export const levelOf = (rights: Right[]): ClubLevel => (['vice', 'head'] as ClubLevel[]).find((l) => RIGHTS.some((r) => r.level === l && rights.includes(r.key))) ?? 'member';
/** I may do this in this club (my membership, or a club with my rights) */
export const may = (m: { rights?: Right[] | null } | null | undefined, right: Right): boolean => !!m?.rights?.includes(right);

/** The rank rule (§2): whoever runs the team manages only people strictly below them. */
export const canManage = (m: { role: OrgRole; rights?: Right[] } | null | undefined, theirs: OrgRole): boolean => may(m, 'team') && RANK[m!.role] > RANK[theirs];

/** The roles you can give: strictly below your own. */
export const canGive = (mine: OrgRole): OrgRole[] => (['vice', 'head', 'member'] as OrgRole[]).filter((r) => RANK[r] < RANK[mine]);

/** Your role in the org is at least `min`. Scan tickets: member; create and edit events, attendees: head. */
export const atLeast = (role: OrgRole | null | undefined, min: OrgRole): boolean => !!role && RANK[role] >= RANK[min];

/** The club's own name for someone's role (§2b), else the level's. */
export const roleName = (role: OrgRole, title?: string | null): string => title || ROLE_NAME[role];
/** an organizer's line: the real name, the nick beside it (owner, Oct 5) */
export const withNick = (real: string, p: { nick?: string | null }): string => (p.nick ? `${real} · ${p.nick}` : real);

/** Colours for the clubs' own roles and tags (§2b): each reads as a dot in both themes. */
export const TEAM_COLORS = ['#3B6BFF', '#7C4DFF', '#FF4FA3', '#F2542D', '#FFB23D', '#2FBF71', '#18A9DB', '#8E8E93'];

/** "people" acts on people strictly below them (tags, probation, strikes, asking to remove; §2b). */
export const isAbove = (m: { role: OrgRole; rights?: Right[] } | null | undefined, theirs: OrgRole): boolean => may(m, 'people') && RANK[m!.role] > RANK[theirs];

/** A club's own event (team-only, a club meeting) or DMP's leaders meeting: people come, nobody checks tickets, so it has
 *  none; the organizers mark who came by name (owner, Oct 6: "why do I need a ticket for a get-together?") */
export const inner = (e: { visibility?: string }): boolean => e.visibility === 'members' || e.visibility === 'leaders';
