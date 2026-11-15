"""
MARSCOPE Relational Persistence & Migration Manager
Supports durable ACID SQLite (WAL + strict foreign keys + BEGIN IMMEDIATE) for local
development/testing and validates explicit database configuration in production.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
from typing import Iterator, Optional

from app.core.config import settings


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class DatabaseConfigurationError(RuntimeError):
    """Raised when persistent relational storage is misconfigured or unavailable."""


class MissionDatabase:
    """
    Thread-safe & process-durable relational database wrapper with ordered SQL migrations.
    """

    def __init__(self, database_url: Optional[str] = None, default_sqlite_path: Optional[Path] = None) -> None:
        raw_url = (database_url if database_url is not None else settings.DATABASE_URL) or ""
        raw_url = raw_url.strip()

        if raw_url.startswith(("postgres://", "postgresql://")):
            raise DatabaseConfigurationError(
                "PostgreSQL DATABASE_URL configured, but psycopg/psycopg2 driver is not installed in this runtime. "
                "Install PostgreSQL driver support or configure a local sqlite:/// database path."
            )

        if raw_url == "" and str(settings.ENVIRONMENT).lower() == "production" and default_sqlite_path is None:
            raise DatabaseConfigurationError(
                "DATABASE_URL must be explicitly configured in production; MARSCOPE never falls back silently to ephemeral storage."
            )

        if raw_url.startswith("sqlite:///"):
            path_part = raw_url[len("sqlite:///") :]
            if path_part == ":memory:":
                raise DatabaseConfigurationError("In-memory SQLite (:memory:) is disallowed for persistent mission state.")
            self.db_path = Path(path_part)
        elif raw_url:
            self.db_path = Path(raw_url)
        else:
            if default_sqlite_path is not None:
                self.db_path = Path(default_sqlite_path)
            else:
                repo_root = Path(__file__).resolve().parent.parent.parent.parent
                self.db_path = repo_root / "datasets" / "index" / "marscope_mission.sqlite"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._applied_migrations: list[str] = []
        self.apply_migrations()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def apply_migrations(self) -> list[str]:
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        migration_id TEXT PRIMARY KEY,
                        applied_at_utc TEXT NOT NULL
                    );
                    """
                )
                existing = {
                    row["migration_id"]
                    for row in conn.execute("SELECT migration_id FROM schema_migrations").fetchall()
                }
                applied_now: list[str] = []
                for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
                    mig_id = sql_file.name
                    if mig_id in existing:
                        continue
                    sql_text = sql_file.read_text(encoding="utf-8")
                    # Execute statements inside the active transaction cleanly
                    for stmt in _split_sql_statements(sql_text):
                        conn.execute(stmt)
                    conn.execute(
                        "INSERT INTO schema_migrations (migration_id, applied_at_utc) VALUES (?, ?)",
                        (mig_id, datetime.now(timezone.utc).isoformat()),
                    )
                    applied_now.append(mig_id)
                conn.execute("COMMIT;")
                self._applied_migrations = sorted(existing | set(applied_now))
                return applied_now
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                yield conn
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    def status(self) -> dict[str, object]:
        try:
            with self.read() as conn:
                migs = [
                    r["migration_id"]
                    for r in conn.execute("SELECT migration_id FROM schema_migrations ORDER BY migration_id").fetchall()
                ]
            return {
                "available": True,
                "engine": "sqlite_wal_acid",
                "db_path_configured": True,
                "foreign_keys_enforced": True,
                "applied_migrations": migs,
                "error": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "engine": "unavailable",
                "db_path_configured": False,
                "foreign_keys_enforced": False,
                "applied_migrations": [],
                "error": str(exc),
            }


def _split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    buff: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        buff.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buff).strip()
            if stmt:
                statements.append(stmt)
            buff = []
    tail = "\n".join(buff).strip()
    if tail:
        statements.append(tail)
    return statements
