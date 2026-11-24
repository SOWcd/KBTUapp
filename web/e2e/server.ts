// One seeded qa.py server (server/tools/qa.py): a temp database, a free port, the postman off. Its output gives a signed
// link per made-up person; every spec file gets a fresh one (fixtures.ts), so flows never see each other's taps.
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

export const SERVER_DIR = resolve(import.meta.dirname, '../../server');
const PYTHON = process.env.E2E_PYTHON || (existsSync(join(SERVER_DIR, '.venv/bin/python')) ? join(SERVER_DIR, '.venv/bin/python') : 'python3');

/** qa.py's made-up people (PEOPLE there): Dana runs the Open Mic club, Ali and Bota are her friends, Bota moderates. */
export type Person = 'Dana' | 'Ali' | 'Bota';

export interface QaServer {
  base: string;
  /** the signed link qa.py printed, as it printed it */
  links: Record<Person, string>;
  /** its database file */
  db: string;
  /** The API as a made-up person (their signed initData, as the app sends it): a flow's setup, never the step under test. */
  api<R = Record<string, unknown>>(who: Person, method: string, path: string, body?: unknown): Promise<R>;
  /** Python on its database with the server's own rules (`con`, `db`, `logic` in scope): what no screen does, like
   *  the nightly sweep. */
  py(code: string): void;
  stop(): Promise<void>;
}

function freePort(): Promise<number> {
  return new Promise((ok, fail) => {
    const s = createServer();
    s.unref();
    s.on('error', fail);
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address() as { port: number };
      s.close(() => ok(port));
    });
  });
}

export async function startQa(extraEnv: Record<string, string> = {}): Promise<QaServer> {
  const port = await freePort();
  const dir = mkdtempSync(join(tmpdir(), 'kbtu-e2e-')), db = join(dir, 'qa.db');
  // detached: qa.py runs uvicorn as its own child, so the whole group is stopped together
  const proc: ChildProcess = spawn(PYTHON, ['tools/qa.py', '--port', String(port), '--db', db], {
    cwd: SERVER_DIR, detached: true, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, ...extraEnv },
  });
  let out = '';
  proc.stdout!.on('data', (d) => { out += d; });
  proc.stderr!.on('data', (d) => { out += d; });
  const stop = async () => {
    if (proc.exitCode == null) {
      try { process.kill(-proc.pid!, 'SIGTERM'); } catch { /* gone */ }
      await new Promise((r) => { proc.once('exit', r); setTimeout(r, 3000); });
      try { process.kill(-proc.pid!, 'SIGKILL'); } catch { /* gone */ }
    }
    rmSync(dir, { recursive: true, force: true });
  };
  const base = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 60_000;
  for (;;) {
    if (proc.exitCode != null) { await stop(); throw new Error(`qa.py exited (${proc.exitCode}):\n${out}`); }
    if (Date.now() > deadline) { await stop(); throw new Error(`qa.py did not come up in 60 s:\n${out}`); }
    if (/^Bota: /m.test(out)) {
      try { if ((await fetch(base + '/')).ok) break; } catch { /* not listening yet */ }
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  const links = Object.fromEntries([...out.matchAll(/^(\w+): (http\S+)$/gm)].map((m) => [m[1], m[2]])) as Record<Person, string>;
  const api = async <R>(who: Person, method: string, path: string, body?: unknown): Promise<R> => {
    const auth = new URLSearchParams(new URL(links[who]).hash.slice(1)).get('tgWebAppData');
    const r = await fetch(`${base}/api${path}`, {
      method, headers: { Authorization: `tma ${auth}`, 'Content-Type': 'application/json' }, body: body == null ? undefined : JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${who}: ${method} ${path} -> ${r.status} ${await r.text()}`);
    return (r.status === 204 ? {} : await r.json()) as R;
  };
  const py = (code: string) => {
    const r = spawnSync(PYTHON, ['-c', `import sys\nfrom kbtu import db, logic\ncon = db.connect(sys.argv[1])\n${code}\ncon.commit()`, db], { cwd: SERVER_DIR, encoding: 'utf8' });
    if (r.status !== 0) throw new Error(r.stderr);
  };
  return { base, links, db, api, py, stop };
}
