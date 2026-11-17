import { describe, expect, it, vi } from 'vitest';
import type { AdminOrg } from '../api';

const asked: ((l: AdminOrg[]) => void)[] = [];
vi.mock('../api', () => ({ api: { adminOrgs: () => new Promise<AdminOrg[]>((ok) => asked.push(ok)) } }));
vi.mock('../i18n/index.svelte', () => ({ t: (k: string) => k, tn: (k: string) => k }));

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
});
