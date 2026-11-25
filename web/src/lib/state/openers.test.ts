// The deep links' table (openDeepLink): every prefix App.deepLink took before it (main, Nov 25), and which opener each
// one calls, with what. The list was written from that deepLink before the refactor.
import { beforeEach, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => {
  const log: unknown[][] = [];
  const rec = (name: string) => (...a: unknown[]) => { log.push([name, ...a]); };
  const answers: Record<string, unknown> = {};
  return {
    log, rec, answers,
    tg: { in: true },
    detailsFail: false,
    session: { me: null as unknown, channel: true },
    ui: { tab: 'afisha', club: null as number | null },
    channel: { focus: undefined as number | null | undefined },
    sheets: new Proxy({}, { get: (_, k: string) => rec(`sheets.${k}`) }),
    api: new Proxy({}, { get: (_, k: string) => (...a: unknown[]) => { log.push([`api.${k}`, ...a]); return Promise.resolve(answers[k]); } }),
  };
});
vi.mock('./sheets', () => ({ sheets: h.sheets }));
// the chunks a link opens itself (lazy() is real: it opens them with their stat and key)
vi.mock('../../screens/sheets/EventSheet.svelte', () => ({ default: 'EventSheet' }));
vi.mock('../../screens/club/StudioPane.svelte', () => ({ default: 'StudioPane' }));
vi.mock('./session.svelte', () => ({
  session: h.session,
  loadMe: () => Promise.resolve(),
  asStudent: (action: () => void, ...again: unknown[]) => { h.log.push(['asStudent', ...again]); action(); },
}));
vi.mock('./ui.svelte', () => ({ ui: h.ui, say: h.rec('say'), open: h.rec('open') }));
vi.mock('./subjects.svelte', () => ({ loadSubjects: () => Promise.resolve() }));
vi.mock('./channel.svelte', () => ({ channel: h.channel }));
vi.mock('./data.svelte', () => ({
  keepRef: h.rec('keepRef'),
  loadMyCard: () => Promise.resolve(),
  eventDetails: (id: number) => { h.log.push(['eventDetails', id]); return h.detailsFail ? Promise.reject(new Error('gone')) : Promise.resolve(); },
}));
vi.mock('../api', async () => ({ api: h.api, ApiErr: (await import('../api/errors')).ApiErr }));
vi.mock('../i18n/index.svelte', () => ({ t: (k: string) => k }));
vi.mock('../tg', () => ({ get inTelegram() { return h.tg.in; }, haptic: { ok: () => {}, error: () => {} }, tgTry: () => {} }));
vi.mock('../teamConsent', () => ({ setTeamConsent: h.rec('setTeamConsent') }));
vi.mock('../perms', () => ({ may: (m: { role: string } | undefined) => m?.role === 'president' }));
vi.mock('../awards', () => ({ achItem: (a: { code: string }) => `item:${a.code}` }));
vi.mock('../map', () => ({ warmMap: () => {} }));
vi.mock('../stats', () => ({ count: () => {} }));
vi.mock('../../ui/burst', () => ({ burst: () => {} }));

import { openDeepLink } from './openers';

const H10 = 'ABCDEFGHIJ', H16 = '0123456789abcdef', H24 = '0123456789abcdef01234567', H32 = H16 + H16;
const app = {
  join: h.rec('app.join'), president: h.rec('app.president'), msBack: h.rec('app.msBack'),
  checkIn: h.rec('app.checkIn'), helpRun: h.rec('app.helpRun'), takeDoor: h.rec('app.takeDoor'),
};
const tick = () => new Promise((r) => setTimeout(r));
async function run(p: string, afterSignIn = false) {
  const opened = openDeepLink(p, app, afterSignIn);
  await tick(); await tick();
  return { opened, log: h.log.splice(0) };
}

beforeEach(() => {
  h.log.splice(0);
  h.tg.in = true; h.detailsFail = false;
  h.session.me = { id: 7, student: { ms: true }, memberships: [{ org: { id: 3 }, role: 'president' }, { org: { id: 6 }, role: 'member' }], appeals: {}, ask: {} };
  h.session.channel = true;
  h.ui.tab = 'afisha'; h.ui.club = null;
  h.channel.focus = undefined;
  Object.assign(h.answers, {
    event: { title: 'T' }, meetupSession: { org: 3 },
    person: { awards: { achievements: [{ code: 'init', level: 1, variants: [{ code: 'init26f' }] }] } },
    linkCard: { friendship: 'none', person: { id: 9 }, registered: true },
  });
});

// [start parameter, what it calls, the tab it leaves] (in the order deepLink checked them)
const cases: [string, unknown[][], string?][] = [
  [`join_12_${H24}`, [['app.join', 12, H24]]],
  [`pres_12_${H24}`, [['app.president', 12, H24]]],
  [`gl_${H24}`, [['asStudent', `gl_${H24}`], ['api.useGrantLink', H24]], 'profile'],
  [`bq_${H24}_123_${H16}`, [['asStudent', `bq_${H24}_123_${H16}`], ['api.claimBadgeQr', `bq_${H24}_123_${H16}`]], 'profile'],
  [`gq_club.${H24}`, [['asStudent', `gq_club.${H24}`], ['api.guardJoin', `club.${H24}`], ['say', 'guard.in', 'party_popper_3d']]],
  [`ms_${H24}`, [['api.msClaim', H24], ['say', 'login.msDone', 'sparkles_3d'], ['app.msBack', true]]],
  ['apl_5', [['sheets.myAppeal', 5]], 'forum'],
  ['ask_5', [['sheets.myAsk', 5]], 'profile'],
  ['ph_5', [['sheets.event', 5, null, true]]],
  ['cp_5', [['asStudent'], ['sheets.comments', 'post', 5, 'cm.title']]],
  ['cm_5', [['sheets.event', 5], ['asStudent'], ['api.event', 5], ['sheets.comments', 'event', 5, 'T']]],
  ['aw_init26f', [['asStudent'], ['sheets.awards'], ['api.person', 7], ['sheets.award', 'item:init', true]], 'profile'],
  [`ci_1_2_${H16}`, [['app.checkIn', `ci_1_2_${H16}`]]],
  [`hq_1_2_3_${H16}`, [['asStudent', `hq_1_2_3_${H16}`], ['app.helpRun', `hq_1_2_3_${H16}`]]],
  [`et_${H24}`, [['sheets.teamInvite', H24]]],
  [`vh_${H32}`, [['asStudent', `vh_${H32}`], ['app.takeDoor', H32]]],
  ['meet_5', [['asStudent', 'meet_5'], ['api.meetupSession', 5], ['sheets.screens', undefined, undefined, { org: 3 }, 3]], 'club'],
  [`sh_${H16}`, [['asStudent'], ['sheets.screens', H16]]],
  ['fp', [], 'forum'],
  ['fp_5', [], 'forum'],
  ['sj_0123abcdef', [['sheets.subject', '0123abcdef']]],
  ['fa_5', [['asStudent'], ['sheets.forum', 5]]],
  [`r_${H10}`, [['api.refer', H10], ['api.linkCard', H10], ['sheets.person', 9, { code: H10, card: { friendship: 'none', person: { id: 9 }, registered: true }, alreadyRegistered: true }]]],
  ['ce_5', [['asStudent'], ['sheets.clubEdit', 5, 'chats']]],
  ['rc_5', [['asStudent'], ['sheets.roundApply', 5, 'link']]],
  ['iv_5', [['asStudent'], ['sheets.roundApply', 5, 'bot']]],
  ['tc_5', [['asStudent'], ['open', 'EventSheet', { id: 5 }, 'sheet.event', undefined], ['setTeamConsent', true]]],
  ['memo_5', [['asStudent'], ['sheets.memo', 5]]],
  ['ev_5', [['sheets.event', 5]]],
  [`ev_5_${H10}`, [['keepRef', 5, H10], ['sheets.event', 5]]],
  ['tk_5', [['sheets.ticket', 5]]],
  [`tk_5_${H10}`, [['sheets.ticket', 5]]],
  ['cl_5', [['sheets.club', 5]]],
  [`cl_5_${H10}`, [['sheets.club', 5]]],
  ['jr_5', [['sheets.joinInbox', 5]]],
  ['u_5', [['sheets.person', 5]]],
  [`u_5_${H10}`, [['api.refer', `5_${H10}`], ['sheets.person', 5]]],
  ['tm_3', [['open', 'StudioPane', { org: 3 }, 'sheet.studio', undefined], ['sheets.team']], 'club'],
  ['tm_4', [['sheets.club', 4]]],
  ['st_3', [['open', 'StudioPane', { org: 3 }, 'sheet.studio', undefined]], 'club'],
  ['st_4', [['sheets.club', 4]]],
  ['sn_3', [['open', 'StudioPane', { org: 3 }, 'sheet.studio', undefined], ['sheets.santaHi', 3]], 'club'],
  ['sn_6', [['open', 'StudioPane', { org: 6 }, 'sheet.studio', undefined]], 'club'], // a member who may not start it: the Studio alone
  ['sn_4', [['sheets.club', 4]]],
  ['mg_5', [['asStudent'], ['eventDetails', 5], ['sheets.manage', 5]]],
];

it.each(cases)('%s opens what it did before', async (p, calls, tab = 'afisha') => {
  const { opened, log } = await run(p);
  expect(opened).toBe(true);
  expect(log).toEqual(calls);
  expect(h.ui.tab).toBe(tab);
});

it('tm_ and st_ put the club in front of its Studio', async () => {
  await run('tm_3');
  expect(h.ui.club).toBe(3);
  h.ui.club = null;
  await run('st_3');
  expect(h.ui.club).toBe(3);
});

it('fp_<id> brings that post into view; bare fp only the tab', async () => {
  await run('fp_5');
  expect(h.channel.focus).toBe(5);
  await run('fp');
  expect(h.channel.focus).toBe(null);
  h.session.channel = false; h.ui.tab = 'afisha';
  await run('fp_6');
  expect(h.channel.focus).toBe(6);
  expect(h.ui.tab).toBe('afisha');
});

it('apl_ goes to Profile without the forum, and opens nothing without appeals; ask_ the same without the desk', async () => {
  h.session.channel = false;
  (h.session.me as { appeals?: unknown; ask?: unknown }).appeals = undefined;
  (h.session.me as { appeals?: unknown; ask?: unknown }).ask = undefined;
  expect(await run('apl_5')).toEqual({ opened: true, log: [] });
  expect(h.ui.tab).toBe('profile');
  expect(await run('ask_5')).toEqual({ opened: true, log: [] });
});

it('ms_ lands only in Telegram: elsewhere it is a link the app does not know', async () => {
  h.tg.in = false;
  expect(await run(`ms_${H24}`)).toEqual({ opened: false, log: [] });
});

it('r_ right after the sign-in: not "already registered"; my own link opens nothing', async () => {
  const { log } = await run(`r_${H10}`, true);
  expect(log.at(-1)).toEqual(['sheets.person', 9, { code: H10, card: h.answers.linkCard, alreadyRegistered: false }]);
  h.answers.linkCard = { friendship: 'self', person: { id: 7 }, registered: true };
  expect((await run(`r_${H10}`)).log).toEqual([['api.refer', H10], ['api.linkCard', H10]]);
});

it('mg_ falls back to the event when its details fail', async () => {
  h.detailsFail = true;
  expect((await run('mg_5')).log).toEqual([['asStudent'], ['eventDetails', 5], ['sheets.event', 5]]);
});

it.each([
  'zz_1', 'ev_x', 'ev_', 'ev', 'ph_5_ABCDEFGHIJ', 'cp_x', `et_${H16}`, `sh_${H24}`, 'sj_0123', 'r_abcdefghij', `vh_${H24}`,
  `join_12_${H16}`, `bq_${H24}_123`, 'aw_', 'fp_', 'fp_x', 'ask', 'go_5', 'constructor_1', 'toString_1', '__proto___1', 'Ev_5', '',
])('%s is not a link the table knows', async (p) => {
  expect(await run(p)).toEqual({ opened: false, log: [] });
});
