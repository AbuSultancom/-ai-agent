"""Database Tool — execute SQL against SQLite or PostgreSQL."""

import logging
import os
import re
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

_BLOCKED_SQL = re.compile(
    r"(--.*$"                          # inline comment (SQL injection)
    r"|;\s*(DROP|DELETE|UPDATE|INSERT)"  # stacked queries
    r"|UNION\s+SELECT"                 # union injection
    r"|'\s*OR\s+'?\d"                  # classic OR injection
    r"|xp_cmdshell"                    # MSSQL command exec
    r")",
    re.IGNORECASE | re.MULTILINE,
)

_DEFAULT_DB = os.path.join("data", "agent.db")


class DBTools:
    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL", "")
        self._is_pg = self.db_url.startswith("postgresql://") or self.db_url.startswith("postgres://")

    # ── Safety ────────────────────────────────────────────────────────────────

    def _check_safe(self, sql: str) -> None:
        if _BLOCKED_SQL.search(sql):
            raise ValueError("Blocked SQL detected. Use the API carefully.")

    # ── Connection ────────────────────────────────────────────────────────────

    def _sqlite_conn(self, path: str = _DEFAULT_DB):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return sqlite3.connect(path)

    def _pg_conn(self):
        try:
            import psycopg2
            return psycopg2.connect(self.db_url)
        except ImportError:
            raise RuntimeError("psycopg2 not installed. pip install psycopg2-binary")

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, sql: str, params: list | None = None,
                db_path: str = _DEFAULT_DB) -> dict[str, Any]:
        self._check_safe(sql)
        params = params or []
        try:
            if self._is_pg:
                conn = self._pg_conn()
            else:
                conn = self._sqlite_conn(db_path)

            with conn:
                cur = conn.cursor()
                cur.execute(sql, params)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, row)) for row in cur.fetchmany(500)]
                    return {"columns": cols, "rows": rows, "rowcount": len(rows)}
                return {"rowcount": cur.rowcount, "rows": []}
        except Exception as exc:
            logger.exception("DB error")
            return {"error": str(exc)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def list_tables(self, db_path: str = _DEFAULT_DB) -> list[str]:
        if self._is_pg:
            result = self.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
        else:
            result = self.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
                db_path=db_path,
            )
        if "error" in result:
            return []
        return [r.get("name") or r.get("table_name") for r in result["rows"]]

    def describe_table(self, table: str, db_path: str = _DEFAULT_DB) -> dict:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table):
            return {"error": "invalid table name"}
        if self._is_pg:
            result = self.execute(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_name = %s ORDER BY ordinal_position",
                [table],
            )
        else:
            result = self.execute(f"PRAGMA table_info({table})", db_path=db_path)
        return result
