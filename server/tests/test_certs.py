"""Certificates (logic/certs.py): the org's head and up run them, a list is issued all or none (numbers once per org),
the daily cap and the audit log hold the bulk run, downloads are signed links, and the public page says valid with
whose, revoked with the number only, or none."""
from __future__ import annotations

import io
import json
import zipfile

from PIL import Image

from kbtu.logic import certs
from test_ako import HEAD, MEMBER, STRANGER, _jpeg, _pdf, _setup
from test_core import env, set_clock, tma  # noqa: F401  (env is a fixture)

FIELDS = [{"key": "name", "x": 0.5, "y": 0.45, "size": 0.06, "bold": True, "width": 0.8},
          {"key": "program", "x": 0.5, "y": 0.58, "size": 0.035},
          {"key": "date", "x": 0.1, "y": 0.9, "size": 0.025, "align": "left"},
          {"key": "number", "x": 0.9, "y": 0.9, "size": 0.025, "align": "right", "color": "#333333"},
          {"key": "qr", "x": 0.9, "y": 0.75, "size": 0.15, "align": "right"}]
# Russian and Kazakh written as \u escapes (the hook keeps Cyrillic out of tests)
RU_HEAD = "\u0424\u0418\u041e;\u041f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430;\u0414\u0430\u0442\u0430;\u041d\u043e\u043c\u0435\u0440"
ALIYA = "\u04d8\u043b\u0438\u044f \u049a\u0430\u0441\u044b\u043c\u043e\u0432\u0430"  # Kazakh letters: UTF-8 only
ALIA = "\u0410\u043b\u0438\u044f \u041a\u0430\u0441\u044b\u043c\u043e\u0432\u0430"  # Russian: fits cp1251


def _template(c, oid, fields=FIELDS) -> int:
    r = c.post(f"/api/orgs/{oid}/certs/templates?name=Mini%20MBA", headers=tma(HEAD), content=_jpeg(1600, 1131))
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    assert c.patch(f"/api/orgs/{oid}/certs/templates/{tid}", headers=tma(HEAD), json={"fields": fields}).status_code == 200
    return tid


def _run(c, oid, tid, body: bytes, dry=False):
    return c.post(f"/api/orgs/{oid}/certs/runs?template={tid}{'&dry=1' if dry else ''}", headers=tma(HEAD), content=body)


def _csv(*rows: str) -> bytes:
    return "\n".join(rows).encode()


def test_only_the_head_runs_certificates(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    for who in (MEMBER, STRANGER):  # a reviewer of admissions, a plain member: nothing
        assert c.get(f"/api/orgs/{oid}/certs", headers=tma(who)).status_code == 403
        assert c.post(f"/api/orgs/{oid}/certs/templates", headers=tma(who), content=_jpeg()).status_code == 403
    tid = _template(c, oid)
    d = c.get(f"/api/orgs/{oid}/certs", headers=tma(HEAD)).json()
    assert [t["id"] for t in d["templates"]] == [tid] and d["templates"][0]["fields"][0]["key"] == "name"
    assert c.get(f"/api/orgs/{oid}/certs/templates/{tid}/preview", headers=tma(MEMBER)).status_code == 403
    p = c.get(f"/api/orgs/{oid}/certs/templates/{tid}/preview", headers=tma(HEAD))
    assert p.status_code == 200 and p.headers["content-type"] == "image/jpeg" and Image.open(io.BytesIO(p.content)).width == 1600


def test_a_pdf_template_keeps_its_first_page(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    r = c.post(f"/api/orgs/{oid}/certs/templates", headers=tma(HEAD), content=_pdf())
    assert r.status_code == 200, r.text
    assert r.json()["h"] > r.json()["w"] and r.json()["name"] == "Certificate"
    assert c.post(f"/api/orgs/{oid}/certs/templates", headers=tma(HEAD), content=b"%PDF-1.4 broken").status_code == 400
    assert c.post(f"/api/orgs/{oid}/certs/templates", headers=tma(HEAD), content=b"<svg/>").status_code == 400


def test_fields_are_checked(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tid = _template(c, oid)
    for bad in ([{"key": "email", "x": 0.5, "y": 0.5, "size": 0.05}], [{"key": "name", "x": 1.5, "y": 0.5, "size": 0.05}],
                [{"key": "name", "x": 0.5, "y": 0.5, "size": 0.05, "color": "red"}], [{"key": "name", "x": True, "y": 0.5, "size": 0.05}],
                "name", [FIELDS[0]] * 13):
        assert c.patch(f"/api/orgs/{oid}/certs/templates/{tid}", headers=tma(HEAD), json={"fields": bad}).status_code == 400, bad


def test_a_list_is_issued_all_or_none(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tid = _template(c, oid)
    # Excel from a Russian Windows: cp1251, semicolons, the header in Russian, columns in its own order
    body = (RU_HEAD + "\n" + f"{ALIA};Mini MBA;28.11.2026;AKO-1\n\n" + "Erlan S;Executive MBA;28.11.2026;AKO-2\n").encode("cp1251")
    dry = _run(c, oid, tid, body, dry=True)
    assert dry.status_code == 200, dry.text
    assert [(r["row"], r["name"], r["number"]) for r in dry.json()["rows"]] == [(2, ALIA, "AKO-1"), (4, "Erlan S", "AKO-2")]
    assert dry.json()["errors"] == [] and con.execute("SELECT COUNT(*) FROM certs").fetchone()[0] == 0
    r = _run(c, oid, tid, body)
    assert r.status_code == 200 and r.json()["count"] == 2, r.text
    log = con.execute("SELECT data FROM audit_log WHERE action = 'cert_run'").fetchone()
    assert json.loads(log[0]) == {"run": r.json()["run"], "template": tid, "count": 2}
    # again: both numbers are issued, a third row is fine, and nothing of it is issued
    again = _run(c, oid, tid, _csv("Dana K,Mini MBA,1.12.2026,AKO-3", "Erlan S,Executive MBA,28.11.2026,AKO-2"))
    assert again.status_code == 400 and again.json()["errors"] == [{"row": 2, "field": "number", "why": "issued"}]
    assert con.execute("SELECT COUNT(*) FROM certs").fetchone()[0] == 2


def test_a_lists_mistakes_come_back_by_row(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tid = _template(c, oid)
    r = _run(c, oid, tid, _csv("A,P,D,N1", "B,,D,N2", "C,P,D,N1", "x" * 121 + ",P,D,N3"), dry=True)  # no header: name, program, date, number
    assert r.json()["errors"] == [{"row": 2, "field": "program", "why": "empty"}, {"row": 3, "field": "number", "why": "repeated", "first": 1},
                                  {"row": 4, "field": "name", "why": "long"}]
    assert _run(c, oid, tid, _csv("A,P,D,N1", "B,,D,N2")).status_code == 400
    assert _run(c, oid, tid, b"\n\n").json()["message"] == "cert_empty"
    # a header naming only some columns is refused, never issued as a certificate
    part = _run(c, oid, tid, _csv("", "Name,Program,Date", "A,P,D"), dry=True)
    assert part.status_code == 400 and part.json()["message"] == "cert_columns", part.text
    assert _run(c, oid, tid, b'A,"P,D,N1\n' + b"x" * 200_000).json()["message"] == "bad_file"  # an unclosed quote
    # Excel's "Unicode text": UTF-16 with tabs, a header after a blank line
    u16 = _run(c, oid, tid, ("\n" + RU_HEAD.replace(";", "\t") + f"\n{ALIYA}\tMini MBA\t28.11.2026\tAKO-9\n").encode("utf-16"), dry=True)
    assert [(r["row"], r["name"]) for r in u16.json()["rows"]] == [(3, ALIYA)] and u16.json()["errors"] == [], u16.text
    assert _run(c, oid, tid, _csv(*[f"A,P,D,N{i}" for i in range(certs.MAX_ROWS + 1)])).json()["message"] == "cert_too_many"
    bare = c.post(f"/api/orgs/{oid}/certs/templates", headers=tma(HEAD), content=_jpeg(1600, 1131)).json()["id"]
    assert _run(c, oid, bare, _csv("A,P,D,N1")).json()["message"] == "cert_no_fields"  # nothing placed: a blank page
    assert _run(c, oid, 999, _csv("A,P,D,N1")).status_code == 404


def test_the_daily_cap_counts_runs(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    monkeypatch.setattr(certs, "CERTS_A_DAY", 3)
    tid = _template(c, oid)
    assert _run(c, oid, tid, _csv("A,P,D,1", "B,P,D,2")).status_code == 200
    cid = con.execute("SELECT id FROM certs WHERE number = '1'").fetchone()[0]
    assert c.delete(f"/api/orgs/{oid}/certs/{cid}", headers=tma(HEAD)).status_code == 204  # deleting gives no room back
    r = _run(c, oid, tid, _csv("C,P,D,3", "D,P,D,4"))
    assert r.status_code == 429 and r.json()["message"] == "cert_runs"
    set_clock(monkeypatch, lambda: t0 + 86401)
    assert _run(c, oid, tid, _csv("C,P,D,3", "D,P,D,4")).status_code == 200


def test_the_public_page(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tid = _template(c, oid)
    assert _run(c, oid, tid, _csv(f"{ALIYA},Mini MBA <b>,28.11.2026,AKO-7", "<script>x</script>,P,D,AKO-8")).status_code == 200
    (cid, code), (cid2, code2) = con.execute("SELECT id, code FROM certs ORDER BY id").fetchall()
    r = c.get(f"/c/{code.lower()}", headers={"Accept-Language": "kk-KZ,ru;q=0.8"})
    assert r.status_code == 200 and ALIYA in r.text and "Mini MBA &lt;b&gt;" in r.text and "AKO-7" in r.text and 'lang="kk"' in r.text
    assert r.headers["x-robots-tag"] == "noindex" and r.headers["cache-control"] == "no-cache" and "default-src 'none'" in r.headers["content-security-policy"]
    assert "<script>x" not in c.get(f"/c/{code2}").text
    assert c.get("/c/ABCDEFGHJK").status_code == 404 and c.get("/c/AKO-7").status_code == 404  # never by its number
    assert c.patch(f"/api/orgs/{oid}/certs/{cid}", headers=tma(HEAD), json={"revoked": True}).status_code == 204
    gone = c.get(f"/c/{code}", headers={"Accept-Language": "en"})
    assert gone.status_code == 200 and "revoked" in gone.text and "AKO-7" in gone.text and ALIYA not in gone.text
    assert c.patch(f"/api/orgs/{oid}/certs/{cid}", headers=tma(HEAD), json={"revoked": False}).status_code == 204  # the undo
    assert ALIYA in c.get(f"/c/{code}").text
    assert [a[0] for a in con.execute("SELECT action FROM audit_log WHERE action LIKE 'cert_re%' ORDER BY id")] == ["cert_revoke", "cert_restore"]


def test_downloads_are_signed_links_of_the_org(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tid = _template(c, oid)
    rid = _run(c, oid, tid, _csv(f"{ALIYA},Mini MBA,28.11.2026,AKO/1", "Erlan S,Mini MBA,28.11.2026,AKO-2", "Dana,Mini MBA,1.1.2027,AKO-3")).json()["run"]
    cid = con.execute("SELECT id FROM certs WHERE number = 'AKO-2'").fetchone()[0]
    assert c.get(f"/api/orgs/{oid}/certs/{cid}/link", headers=tma(MEMBER)).status_code == 403
    url = c.get(f"/api/orgs/{oid}/certs/{cid}/link", headers=tma(HEAD)).json()["url"]
    pdf = c.get(url)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-" and "AKO-2 Erlan S.pdf" in pdf.headers["content-disposition"]
    assert c.get(url.replace("s=", "s=0")).status_code == 404 and c.get(url.replace(f"/f/{cid}", f"/f/{cid + 1}")).status_code == 404
    other = con.execute("""INSERT INTO orgs (slug, kind, name, short, emoji, official, created_at)
        VALUES ('x', 'club', 'X', 'X', 'briefcase_3d', 0, 1)""").lastrowid
    con.commit()
    assert c.get(f"/api/orgs/{other}/certs/{cid}/link", headers=tma(HEAD)).status_code == 403
    first = con.execute("SELECT id FROM certs WHERE number = 'AKO/1'").fetchone()[0]
    early = c.get(f"/api/orgs/{oid}/certs/{first}/link", headers=tma(HEAD)).json()["url"]
    c.patch(f"/api/orgs/{oid}/certs/{first}", headers=tma(HEAD), json={"revoked": True})
    no = c.get(f"/api/orgs/{oid}/certs/{first}/link", headers=tma(HEAD))  # never printed while its page says revoked
    assert no.status_code == 409 and no.json()["message"] == "cert_revoked"
    assert c.get(early).status_code == 404  # a link made before the revoke prints nothing either
    z = c.get(c.get(f"/api/orgs/{oid}/certs/runs/{rid}/link", headers=tma(HEAD)).json()["url"])
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert sorted(names) == ["AKO-2 Erlan S.pdf", "AKO-3 Dana.pdf"]  # the revoked one left out; no "/" ever in a name
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'cert_download'").fetchone()[0] == 3
    set_clock(monkeypatch, lambda: t0 + certs.LINK_TTL + 1)
    assert c.get(url).status_code == 404


def test_templates_in_use_stay_and_revoked_certificates_go(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tid = _template(c, oid)
    spare = c.post(f"/api/orgs/{oid}/certs/templates", headers=tma(HEAD), content=_jpeg(1600, 1131)).json()["id"]
    _run(c, oid, tid, _csv("A,P,D,1", "B,P,D,2"))
    assert c.delete(f"/api/orgs/{oid}/certs/templates/{tid}", headers=tma(HEAD)).status_code == 409
    assert c.delete(f"/api/orgs/{oid}/certs/templates/{spare}", headers=tma(HEAD)).status_code == 204
    one_id = con.execute("SELECT id FROM certs WHERE number = '1'").fetchone()[0]
    c.patch(f"/api/orgs/{oid}/certs/{one_id}", headers=tma(HEAD), json={"revoked": True})
    set_clock(monkeypatch, lambda: t0 + certs.REVOKED_KEEP + 1)
    certs.sweep(con)
    assert [r[0] for r in con.execute("SELECT number FROM certs")] == ["2"]
