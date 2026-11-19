// The one door to data: screens import `api` from here (SPEC §8). No in-browser mock behind it (a second
// copy of the server's rules drifts); screens are checked on the real server with made-up people
// (server/tools/qa.py).
import { server } from './client';

export * from './types';
export { ApiErr } from './errors';
export { localize, original, staffEvents, staffOrg, translated } from './client';
export const api = server;
