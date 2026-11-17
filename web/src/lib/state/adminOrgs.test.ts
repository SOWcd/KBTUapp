import { describe, expect, it, vi } from 'vitest';
import type { AdminOrg } from '../api';

const asked: ((l: AdminOrg[]) => void)[] = [];
vi.mock('../api', () => ({ api: { adminOrgs: () => new Promise<AdminOrg[]>((ok) => asked.push(ok)) } }));
vi.mock('../i18n/index.svelte', () => ({ t: (k: string) => k, tn: (k: string) => k }));
const session = { me: { role: 'admin' } as { role: string } | null };
vi.mock('./session.svelte', () => ({ session }));

const org = (id: number, official = false) => ({ id, name: 'c' + id, official, team: [], members: 0, hidden: false, shortLinks: ['a', 'b'] }) as unknown as AdminOrg;

describe('adminOrgs', () => {
  it('an answer older than a change is dropped and asked again; loads never overlap; a patch merges into the current one', async () => {
    const { adminOrgs, loadAdminOrgs, putOrg, patchOrg } = await import('./adminOrgs.svelte');
    const first = loadAdminOrgs();
    void loadAdminOrgs();
    expect(asked.length).toBe(1);                 // one request for two callers
    asked[0]([org(1)]);
    await first;
    expect(adminOrgs.list).toEqual([org(1)]);

    const second = loadAdminOrgs();               // a refresh starts...
    putOrg({ ...org(1), members: 5 });            // ...a role is given meanwhile...
    asked[1]([org(1)]);                           // ...and the older answer comes: not shown
    await vi.waitFor(() => expect(asked.length).toBe(3));
    expect(adminOrgs.list![0].members).toBe(5);
    asked[2]([{ ...org(1), members: 5 }]);
    await second;

    patchOrg(1, () => ({ official: true }));
    patchOrg(1, (o) => ({ shortLinks: o.shortLinks.filter((s) => s !== 'a') }));
    expect(adminOrgs.list![0]).toMatchObject({ official: true, members: 5, shortLinks: ['b'] });
  });

  it('a decision makes the list in flight old: it is asked again', async () => {
    const { adminOrgs, loadAdminOrgs, refreshAdminOrgs } = await import('./adminOrgs.svelte');
    const n = asked.length;
    void loadAdminOrgs();                         // held: a snapshot from before the decision
    const done = refreshAdminOrgs();              // a club approved: the same request, but its answer is old now
    asked[n]([org(1)]);
    await vi.waitFor(() => expect(asked.length).toBe(n + 2));
    asked[n + 1]([org(1), org(2)]);
    await done;
    expect(adminOrgs.list!.map((o) => o.id)).toEqual([1, 2]);
  });

  it('the role gone: the list clears, and no answer on its way is written back, even after the role returns', async () => {
    const { adminOrgs, loadAdminOrgs } = await import('./adminOrgs.svelte');
    const { staffStill } = await import('./staffAccess.svelte');
    const n = asked.length;
    const still = staffStill(), staff = staffStill('staff');
    const load = loadAdminOrgs();
    session.me = { role: 'moderator' };           // demoted while both are on their way
    expect(still()).toBe(false);
    expect(staff()).toBe(false);                  // an inbox asked as an admin holds the admin's cards: dropped too
    expect(staffStill('staff')()).toBe(true);     // a moderator's own next request goes on
    expect(adminOrgs.list).toBe(null);
    asked[n]([org(1)]);
    await load;
    expect(adminOrgs.list).toBe(null);
    session.me = { role: 'admin' };
    expect(still()).toBe(false);                  // asked under the old role: an epoch behind
    expect(staffStill()()).toBe(true);
    session.me = null;
    expect(staffStill('staff')()).toBe(false);
  });
});
