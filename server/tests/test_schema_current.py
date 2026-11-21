from tools.schema_dump import OUT, dump


def test_schema_current_is_fresh():
    """schema.current.sql is what agents read for today's tables: regenerate it with tools/schema_dump.py."""
    assert OUT.read_text() == dump(), "stale: run .venv/bin/python tools/schema_dump.py"
