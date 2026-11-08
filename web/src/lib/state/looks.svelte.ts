// The lanyard picker's facts, shared by the settings row (its value) and its page (screens/profile/LookPage.svelte);
// call inside a $derived. And my card as the hero shows it (Me, the page's preview).
import type { PersonCard } from '../api';
import { session } from './session.svelte';
import { data } from './data.svelte';
import { ui } from './ui.svelte';
import { byRank } from '../perms';
import { nameOf, schoolOf } from '../short';
import { skinOf, skinned, STRAP, comingLooks } from '../awards';

export function lookData() {
  const me = session.me;
  // the lanyards: my clubs' by my role in them (owner, Oct 13: "no chaos"), then every other club's under a lock (owner,
  // Oct 31: a club's lanyard is its members' alone; the server holds it too, `_skin_ok`), KBTU's last; SOWER first for the founder
  // a school's lanyard is its students' alone, even for a member of its org (staff are): only my own school's (server: _skin_ok)
  const mine = me ? [...me.memberships].sort(byRank).map((m) => m.org).filter((o) => skinned(o) && o.kind !== 'school') : [];
  // my school's lanyard: mine with no joining, nobody else's (the server holds it too: logic.school_slug); others' schools
  // show locked, to try on
  const school = schoolOf(me?.student?.school);
  // once each: a member of my school's org (staff often are) had it twice, a duplicate key that blanked Settings (Nov 2)
  const own = [...mine, ...(school && skinned(school) && !mine.some((o) => o.id === school.id) ? [school] : [])];
  const skins = [...own, ...data.orgs.filter((o) => skinned(o) && !own.some((x) => x.id === o.id)), ...comingLooks()]
    .filter((o, i, all) => all.findIndex((x) => x.id === o.id) === i);  // a key twice blanks the list: never
  // the creator wears any (owner, Nov 2; the server holds it too)
  const swatches = [...(me?.founder ? [{ id: 'sower' as const, kind: 'sower', name: 'SOWER', word: 'SOWER' }] : []),
    ...skins.map((o) => ({ id: o.id, kind: skinOf(o)!, name: nameOf(o), word: STRAP[skinOf(o)!], locked: o.id < 0 || !me?.founder && !own.some((x) => x.id === o.id) })),
    { id: null, kind: 'kbtu', name: 'KBTU', word: 'KBTU' }];
  type Sw = (typeof swatches)[number];
  const kindOf = (k: Sw) => data.orgs.find((o) => o.id === k.id)?.kind;
  // two rows (owner, Nov 2: three pushed the card off the screen): organisations (SOWER, mine, KBTU, the rest locked),
  // then the schools (mine first)
  const isMine = (k: Sw) => typeof k.id !== 'number' || own.some((o) => o.id === k.id);
  const orgs = swatches.filter((k) => kindOf(k) !== 'school');
  const sorted = [...orgs.filter((k) => isMine(k) && k.id !== null), ...orgs.filter((k) => k.id === null), ...orgs.filter((k) => !isMine(k))];
  const rows = ([['look.gClubs', sorted], ['look.gSchools', swatches.filter((k) => kindOf(k) === 'school')]] as const).filter(([, ks]) => ks.length);
  // a locked one can be tried on: the lanyard wears it, the check then says it isn't mine (Me) and turns it back
  const worn = skinNow();
  return { skins, swatches, rows, kindOf, worn, wornName: swatches.find((k) => k.id === (worn ?? null))?.name ?? 'KBTU' };
}

// the hero shows at once from what the app already knows; numbers and awards fill in when the card arrives
export function myShown(): PersonCard | null {
  const me = session.me, card = data.myCard;
  return card ? { ...card, skin: skinNow(), frame: frameNow() } : (me?.student ? {
    id: me.id, name: me.name, nick: me.nick, realName: me.nick ? `${me.student.firstName} ${[...me.student.lastName][0] ?? ''}`.trim() : undefined, avatar: me.avatar, founder: me.founder, staff: me.role === 'user' ? null : me.role, no: me.no, course: me.student.course, school: me.student.school, bio: me.bio,
    attended: -1, clubs: me.memberships, past: [], showcase: [], shelf: [], awards: { achievements: [], badges: [] }, friendship: 'none', friendsSince: null, going: [], skin: skinNow(), frame: frameNow(),
  } : null);
}

// what the lanyard wears now: a locked one tried on, else the edit not yet saved (ui.look), else mine
const skinNow = () => ui.tryOn?.id ?? (ui.look ? ui.look.skin : session.me?.skin);
const frameNow = () => (ui.look ? ui.look.frame : session.me?.frame);
