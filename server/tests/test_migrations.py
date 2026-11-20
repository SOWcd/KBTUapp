"""Migrations apply by number (db.py: those above PRAGMA user_version), so a gap or a repeat would make a later one be
skipped on a live database: two branches that took the same number, merged in the wrong order (Nov 6)."""
import sqlite3

from kbtu.db import MIGRATIONS


def test_numbers_run_one_by_one():
    nums = [n for n, _ in MIGRATIONS]
    assert nums == list(range(nums[0], nums[0] + len(nums))), nums


def test_bracket_migration_preserves_results_and_retired_match_ids():
    con = sqlite3.connect(":memory:", isolation_level=None)
    with con:
        con.executescript("""PRAGMA foreign_keys = ON;
            CREATE TABLE events (id INTEGER PRIMARY KEY);
            CREATE TABLE users (id INTEGER PRIMARY KEY);
            CREATE TABLE event_teams (id INTEGER PRIMARY KEY);
            INSERT INTO events VALUES (1);
            INSERT INTO users VALUES (1);
            INSERT INTO event_teams VALUES (1), (2), (3);""")
        migrations = dict(MIGRATIONS)
        con.executescript(migrations[195])
        con.executescript("""INSERT INTO ev_groups (id, event_id, name, position) VALUES (1, 1, 'A', 0);
            INSERT INTO ev_matches (id, group_id, home, away, home_score, away_score, played_at, updated_by)
              VALUES (3, 1, 1, 2, 2, 2, 100, 1), (8, 1, 1, 3, NULL, NULL, NULL, NULL);
            DELETE FROM ev_matches WHERE id = 8;""")
        con.executescript(f"BEGIN;\n{migrations[196]}\nCOMMIT;")
        assert con.execute("SELECT id, event_id, stage, group_id, home_score, away_score, played_at, updated_by FROM ev_matches").fetchall() == [
            (3, 1, "group", 1, 2, 2, 100, 1)]
        assert con.execute("INSERT INTO ev_matches (event_id, group_id, home, away) VALUES (1, 1, 1, 3)").lastrowid > 8
        con.execute("DELETE FROM event_teams WHERE id = 2")
        assert con.execute("SELECT COUNT(*) FROM ev_matches WHERE id = 3").fetchone()[0] == 0
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
