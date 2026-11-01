"""SQLite 数据访问层。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import PoemRecord, PoemSummary, SearchPage


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _excerpt(content: str, limit: int = 112) -> str:
    first = ""
    for line in content.splitlines():
        line = line.strip()
        if line:
            first = line
            break
    if len(first) > limit:
        return first[:limit].rstrip() + "…"
    return first


class PoemRepository:
    """只读的诗文仓库。每次调用使用独立连接，线程安全。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        # as_uri 会正确处理 Windows 盘符、空格与中文路径。
        uri = self.db_path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn

    def count_all(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM poems").fetchone()
        return int(row["n"]) if row else 0

    def search(self, query: str, offset: int = 0, limit: int = 60) -> SearchPage:
        query = query.strip()
        if not query:
            return SearchPage(items=[], total=0)

        escaped = _escape_like(query)
        contains = f"%{escaped}%"
        prefix = f"{escaped}%"
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), 200))

        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM poems WHERE title LIKE ? ESCAPE '\\'",
                (contains,),
            ).fetchone()["n"]
            rows = conn.execute(
                """
                SELECT rowid AS id, title, author, dynasty, content
                FROM poems
                WHERE title LIKE ? ESCAPE '\\'
                ORDER BY
                    CASE
                        WHEN title = ? THEN 0
                        WHEN title LIKE ? ESCAPE '\\' THEN 1
                        ELSE 2
                    END,
                    length(title),
                    rowid
                LIMIT ? OFFSET ?
                """,
                (contains, query, prefix, limit, offset),
            ).fetchall()

        items = [
            PoemSummary(
                id=int(row["id"]),
                title=row["title"],
                author=row["author"],
                dynasty=row["dynasty"],
                excerpt=_excerpt(row["content"]),
            )
            for row in rows
        ]
        return SearchPage(items=items, total=int(total))

    def get(self, poem_id: int) -> PoemRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT rowid AS id, title, author, dynasty, content, translation, annotation
                FROM poems
                WHERE rowid = ?
                """,
                (int(poem_id),),
            ).fetchone()
        if row is None:
            return None
        return PoemRecord(
            id=int(row["id"]),
            title=row["title"],
            author=row["author"],
            dynasty=row["dynasty"],
            content=row["content"],
            translation=row["translation"],
            annotation=row["annotation"],
        )
