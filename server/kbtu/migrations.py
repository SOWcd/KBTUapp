"""Numbered changes after the frozen schema.sql baseline."""

BASE = 267

# Append the next (user_version, SQL) step here, starting at BASE + 1.
MIGRATIONS: list[tuple[int, str]] = [
    # certificates an org issues in bulk (logic/certs.py): a template's background (a JPEG, in the row: backed up and
    # gone with it), each run's field layout as it was (a later edit never changes what was issued), one row per
    # certificate; its PDF is drawn again on download, never kept
    (268, """CREATE TABLE IF NOT EXISTS cert_templates (
      id         INTEGER PRIMARY KEY,
      org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      name       TEXT NOT NULL,
      image      BLOB NOT NULL,
      w          INTEGER NOT NULL,
      h          INTEGER NOT NULL,
      fields     TEXT NOT NULL DEFAULT '[]',        -- JSON: [{key, x, y, size, align, color, bold, width}]
      created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS cert_templates_by_org ON cert_templates(org_id);
    CREATE TABLE IF NOT EXISTS cert_runs (
      id          INTEGER PRIMARY KEY,
      org_id      INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      template_id INTEGER NOT NULL REFERENCES cert_templates(id),
      fields      TEXT NOT NULL,
      count       INTEGER NOT NULL,
      by          INTEGER REFERENCES users(id) ON DELETE SET NULL,
      at          INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS cert_runs_by_org ON cert_runs(org_id, at);
    CREATE TABLE IF NOT EXISTS certs (
      id          INTEGER PRIMARY KEY,
      org_id      INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      run_id      INTEGER NOT NULL REFERENCES cert_runs(id) ON DELETE CASCADE,
      template_id INTEGER NOT NULL REFERENCES cert_templates(id),
      code        TEXT NOT NULL UNIQUE,              -- the public /c/<code>
      number      TEXT NOT NULL,
      name        TEXT NOT NULL,
      program     TEXT NOT NULL,
      date        TEXT NOT NULL,                     -- as the list gave it
      revoked_at  INTEGER,
      created_at  INTEGER NOT NULL,
      UNIQUE (org_id, number)
    ) STRICT;
    CREATE INDEX IF NOT EXISTS certs_by_run ON certs(run_id);
    CREATE INDEX IF NOT EXISTS certs_by_org ON certs(org_id, created_at);
    CREATE INDEX IF NOT EXISTS certs_by_template ON certs(template_id);"""),
]
