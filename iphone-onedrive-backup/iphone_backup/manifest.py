"""SQLite-backed record of what has already been uploaded.

The point of this file is incremental backup: on each run we only upload
photos we have not uploaded before. A file is considered "already uploaded"
when a row exists for its source path whose size and mtime match and whose
status is 'done'. Matching on (path, size, mtime) is fast and correct for
the append-only way a camera roll grows.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
    source_key   TEXT PRIMARY KEY,   -- path relative to the source root
    size         INTEGER NOT NULL,
    mtime_ns     INTEGER NOT NULL,
    sha1         TEXT,
    remote_path  TEXT,
    status       TEXT NOT NULL,       -- 'done' | 'failed'
    error        TEXT,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
"""


class Manifest:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Manifest":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def is_uploaded(self, source_key: str, size: int, mtime_ns: int) -> bool:
        row = self._conn.execute(
            "SELECT size, mtime_ns, status FROM uploads WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        if row is None:
            return False
        return (
            row["status"] == "done"
            and row["size"] == size
            and row["mtime_ns"] == mtime_ns
        )

    def has_done(self, source_key: str) -> bool:
        """True if this device path was already uploaded successfully.

        Used when we know the file's identity (its path) before downloading it,
        so we can skip the transfer entirely. New photos always have new paths.
        """
        row = self._conn.execute(
            "SELECT status FROM uploads WHERE source_key = ?", (source_key,)
        ).fetchone()
        return row is not None and row["status"] == "done"

    def mark_done(
        self,
        source_key: str,
        size: int,
        mtime_ns: int,
        remote_path: str,
        sha1: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO uploads
                (source_key, size, mtime_ns, sha1, remote_path, status, error, updated_at)
            VALUES (?, ?, ?, ?, ?, 'done', NULL, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                size=excluded.size, mtime_ns=excluded.mtime_ns, sha1=excluded.sha1,
                remote_path=excluded.remote_path, status='done', error=NULL,
                updated_at=excluded.updated_at
            """,
            (source_key, size, mtime_ns, sha1, remote_path, _now()),
        )
        self._conn.commit()

    def mark_failed(self, source_key: str, size: int, mtime_ns: int, error: str) -> None:
        self._conn.execute(
            """
            INSERT INTO uploads
                (source_key, size, mtime_ns, sha1, remote_path, status, error, updated_at)
            VALUES (?, ?, ?, NULL, NULL, 'failed', ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                size=excluded.size, mtime_ns=excluded.mtime_ns,
                status='failed', error=excluded.error, updated_at=excluded.updated_at
            """,
            (source_key, size, mtime_ns, error[:2000], _now()),
        )
        self._conn.commit()

    def counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM uploads GROUP BY status"
        ).fetchall()
        out = {"done": 0, "failed": 0}
        for r in rows:
            out[r["status"]] = r["n"]
        return out

    def clear(self) -> None:
        self._conn.execute("DELETE FROM uploads")
        self._conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
