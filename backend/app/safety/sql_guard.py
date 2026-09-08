"""SQL safety gate.

The agent generates SQL that runs against our database. Before any generated
SQL executes we parse it into an AST with sqlglot and check its structure —
string-matching for "DROP" is not validation and is easy to defeat.

Rules enforced here (defense-in-depth on top of the read-only DB role):
  1. Exactly one statement (blocks stacked "SELECT ...; DROP ...").
  2. The statement is a read: SELECT (optionally with CTEs) or a set operation
     of SELECTs. Anything else — INSERT/UPDATE/DELETE/DDL/COPY/GRANT/etc. — is
     rejected because its AST node type is not an allowed read root, or because
     a forbidden node appears anywhere in the tree.
  3. `SELECT ... INTO` is rejected (it writes a table).
  4. Referenced tables must be in the analytics allow-list (plus any CTE names
     defined in the same query). Blocks pg_catalog / information_schema probing.
  5. A small block-list of dangerous functions (pg_sleep, pg_read_file, dblink,
     …) is rejected.

Raises SqlNotAllowed with a short, safe reason. Callers translate that into a
structured error the agent can see.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.db.models import ANALYTICS_TABLES

DIALECT = "postgres"

# Read roots we accept as the top-level statement.
_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)

# Node types that mean a write, DDL, or an out-of-band command. `Command` is
# sqlglot's catch-all for statements it doesn't model (SET, COPY, VACUUM, …).
_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge,
    exp.Create, exp.Drop, exp.Alter, exp.TruncateTable,
    exp.Grant, exp.Command, exp.Into,
)

# Functions that can read files, sleep, or reach the network.
_FORBIDDEN_FUNCTIONS = {
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir",
    "lo_import", "lo_export", "dblink", "copy", "set_config", "current_setting",
}

_ALLOWED_TABLES = set(ANALYTICS_TABLES)


class SqlNotAllowed(ValueError):
    """The generated SQL failed the safety gate."""


def validate(sql: str) -> str:
    """Validate one read-only SQL statement. Returns the SQL if it passes,
    otherwise raises SqlNotAllowed with a safe, short reason."""
    try:
        statements = sqlglot.parse(sql, read=DIALECT)
    except Exception as e:  # sqlglot parse failure -> not valid SQL we will run
        raise SqlNotAllowed(f"Could not parse SQL: {e}") from e

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SqlNotAllowed("Exactly one SQL statement is allowed.")

    root = statements[0]
    if not isinstance(root, _ALLOWED_ROOTS):
        raise SqlNotAllowed("Only a single read-only SELECT statement is allowed.")

    _reject_forbidden_nodes(root)
    _reject_forbidden_functions(root)
    _reject_unknown_tables(root)
    return sql


def _reject_forbidden_nodes(root: exp.Expression) -> None:
    for node in root.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlNotAllowed("Only read-only SELECT statements are allowed.")


def _reject_forbidden_functions(root: exp.Expression) -> None:
    for func in root.find_all(exp.Func):
        name = (func.sql_name() or "").lower() if hasattr(func, "sql_name") else ""
        # exp.Anonymous covers functions sqlglot doesn't know by name.
        if isinstance(func, exp.Anonymous):
            name = (func.name or "").lower()
        if name in _FORBIDDEN_FUNCTIONS:
            raise SqlNotAllowed(f"Function '{name}' is not allowed.")


def _reject_unknown_tables(root: exp.Expression) -> None:
    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        # Schema-qualified access (e.g. pg_catalog.*) is rejected outright.
        if table.db and table.db.lower() != "public":
            raise SqlNotAllowed(f"Schema '{table.db}' is not accessible.")
        name = table.name.lower()
        if name not in _ALLOWED_TABLES and name not in cte_names:
            raise SqlNotAllowed(f"Table '{table.name}' is not accessible.")
