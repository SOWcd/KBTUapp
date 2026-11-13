// The rank rule from SPEC §2, the UI's copy: it hides what you can't do; the server enforces it (logic.py).
import type { ClubLevel, Membership, OrgRole, Right } from './api/types';
import { i18n, t } from './i18n/index.svelte';

export const RANK: Record<OrgRole, number> = { member: 1, head: 2, vice: 3, president: 4 };

/** Role titles stay English in every language, as KBTU clubs use them. */
// Club titles stay in English in every language: KBTU clubs print them so on lanyards and badges, and that's
// how students say them
export const ROLE_NAME: Record<OrgRole, string> = { president: 'President', vice: 'Vice', head: 'Head', member: 'Member' };

/** Highest role first. */
export const byRank = (a: { role: OrgRole }, b: { role: OrgRole }): number => RANK[b.role] - RANK[a.role];

/** A club role's rights (SPEC §2), the toggles of its editor in order, each with the level it needs: the highest one a role
 *  has ranks it (whom it acts on). A level without a club role has its level's. */
export const RIGHTS: { key: Right; level: ClubLevel }[] = [
  { key: 'door', level: 'member' }, { key: 'events', level: 'head' }, { key: 'posts', level: 'head' }, { key: 'people', level: 'head' },
  { key: 'casting', level: 'head' }, { key: 'team', level: 'vice' }, { key: 'money', level: 'vice' }, { key: 'memo', level: 'vice' }, { key: 'profile', level: 'vice' },
  // a Vice's by default, yet never ranks a role above Member: a club gives it to its HR (server core.OWN_FROM)
  { key: 'reports', level: 'member' },
];
/** I may do this in this club (my membership, or a club with my rights) */
export const may = (m: { rights?: Right[] | null } | null | undefined, right: Right): boolean => !!m?.rights?.includes(right);

/** Open Studio for people who run the club; a plain member opens its public page. */
export const opensStudio = (m: Pick<Membership, 'role' | 'rights'> | null | undefined): boolean =>
  !!m && (m.role !== 'member' || !!m.rights?.some((r) => r !== 'door'));

/** The rank rule (§2): whoever runs the team manages only people strictly below them. */
export const canManage = (m: { role: OrgRole; rights?: Right[] } | null | undefined, theirs: OrgRole): boolean => may(m, 'team') && RANK[m!.role] > RANK[theirs];

/** The roles you can give: strictly below your own. */
export const canGive = (mine: OrgRole): OrgRole[] => (['vice', 'head', 'member'] as OrgRole[]).filter((r) => RANK[r] < RANK[mine]);

/** Anyone but the President can leave a club, whatever its kind (the server's remove_member; Team's Leave). */
export const canLeave = (m: { role: OrgRole }): boolean => m.role !== 'president';

/** The club's own name for someone's role (§2b), else the level's. */
export const roleName = (role: OrgRole, title?: string | null): string => title || ROLE_NAME[role];
/** A club role's name in the app's language: the club may give it in Kazakh and English too, else its own name. */
export const inLang = <T extends string | null | undefined>(name: T, kk?: string | null, en?: string | null): string | T =>
  (i18n.lang === 'kk' ? kk : i18n.lang === 'en' ? en : null) || name;
export const titleOf = (x: { title?: string | null; titleKk?: string | null; titleEn?: string | null }) => inLang(x.title, x.titleKk, x.titleEn);
/** My role in the app's language (Clubs' Mine, owner Nov 3): a fixed one translated, a club's own name as typed. */
export const roleLabel = (m: { role: OrgRole; title?: string | null; titleKk?: string | null; titleEn?: string | null }): string => {
  const own = titleOf(m);
  return own && own !== ROLE_NAME[m.role] ? own : t(`role.${m.role}`);
};
/** an organizer's line: the real name, the nick beside it */
export const withNick = (real: string, p: { nick?: string | null }): string => (p.nick ? `${real} · ${p.nick}` : real);

/** Colours for the clubs' own roles and tags (§2b): each reads as a dot in both themes. */
export const TEAM_COLORS = ['#3B6BFF', '#7C4DFF', '#FF4FA3', '#F2542D', '#FFB23D', '#2FBF71', '#18A9DB', '#8E8E93'];

/** "people" acts on people strictly below them (tags, probation, asking to remove; §2b). */
export const isAbove = (m: { role: OrgRole; rights?: Right[] } | null | undefined, theirs: OrgRole): boolean => may(m, 'people') && RANK[m!.role] > RANK[theirs];

/** A club's own event (team-only, a club meeting) or DMP's leaders meeting: people come, nobody checks tickets, so it has
 *  none; the organizers mark who came by name */
export const inner = (e: { visibility?: string }): boolean => e.visibility === 'members' || e.visibility === 'leaders';

/** The host club's own people at its public event: the team, not a guest, unless its President or a Vice said yes
 *  (owner, Nov 7; server seats.team_guest); a President or a Vice needs nobody's yes */
export const onTeam = (e: { org: { id: unknown }; visibility?: string; teamAsk?: string }, ms: { org: { id: unknown }; role: OrgRole }[] | undefined): boolean =>
  !inner(e) && e.teamAsk !== 'yes' && !!ms?.some((m) => m.org.id === e.org.id && m.role !== 'president' && m.role !== 'vice');
