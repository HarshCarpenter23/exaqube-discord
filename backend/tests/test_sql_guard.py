"""Tests for the SQL safety gate — the security boundary for generated SQL.

These are the adversarial cases from docs/07: the gate must accept genuine
read-only queries and reject writes, DDL, stacked statements, schema probing,
and dangerous functions — structurally, not by string matching.
"""

import pytest

from app.safety.sql_guard import SqlNotAllowed, validate

VALID = [
    "SELECT * FROM messages",
    "SELECT channel_id, count(*) FROM messages GROUP BY channel_id ORDER BY 2 DESC LIMIT 10",
    "WITH per_day AS (SELECT date_trunc('day', ts) d, count(*) c FROM messages GROUP BY 1) "
    "SELECT * FROM per_day",
    "SELECT server_id FROM servers UNION SELECT server_id FROM channels",
    "SELECT m.user_id FROM messages m JOIN members mem "
    "ON m.server_id = mem.server_id AND m.user_id = mem.user_id",
]

REJECTED = [
    "SELECT 1; DROP TABLE messages",                       # stacked statements
    "DROP TABLE messages",                                 # DDL
    "DELETE FROM messages",                                # DML
    "UPDATE members SET is_bot = true",                    # DML
    "INSERT INTO servers(server_id, server_name) VALUES ('x','y')",  # DML
    "SELECT * INTO evil FROM messages",                    # SELECT INTO writes
    "SELECT * FROM pg_catalog.pg_tables",                  # schema probing
    "SELECT * FROM information_schema.tables",             # schema probing
    "SELECT * FROM secret_table",                          # not in allow-list
    "SELECT pg_sleep(10)",                                 # dangerous function
    "TRUNCATE messages",                                   # DDL
    "GRANT SELECT ON messages TO agent_ro",                # privilege change
]


@pytest.mark.parametrize("sql", VALID)
def test_valid_queries_pass(sql):
    assert validate(sql) == sql


@pytest.mark.parametrize("sql", REJECTED)
def test_unsafe_queries_are_rejected(sql):
    with pytest.raises(SqlNotAllowed):
        validate(sql)
