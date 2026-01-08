from __future__ import annotations

import sqlite3
from pathlib import Path


def probe(db_path: Path) -> dict:
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    try:
        alembic_version = cur.execute("select version_num from alembic_version").fetchone()
    except Exception as e:  # pragma: no cover
        alembic_version = ("<no alembic_version>", str(e))

    try:
        feedback_posts = cur.execute(
            "select name from sqlite_master where type='table' and name='feedback_posts'"
        ).fetchone()
    except Exception as e:  # pragma: no cover
        feedback_posts = ("<err>", str(e))

    try:
        feedback_attachments = cur.execute(
            "select name from sqlite_master where type='table' and name='feedback_attachments'"
        ).fetchone()
    except Exception as e:  # pragma: no cover
        feedback_attachments = ("<err>", str(e))

    con.close()
    st = db_path.stat()
    return {
        "path": str(db_path.resolve()),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "alembic_version": alembic_version,
        "feedback_posts": feedback_posts,
        "feedback_attachments": feedback_attachments,
    }


def main() -> None:
    candidates = [
        Path("quickrail.db"),
        Path("instance") / "quickrail.db",
        Path("instance") / "quickrail-mssung-w.db",
        Path("instance") / "quickrail.db.backup",
    ]

    found = [p for p in candidates if p.exists()]
    if not found:
        print("No DB files found in expected locations.")
        return

    print("DB candidates:")
    for p in found:
        r = probe(p)
        print("-" * 72)
        print("path:", r["path"])
        print("size:", r["size"])
        print("alembic_version:", r["alembic_version"])
        print("feedback_posts:", r["feedback_posts"])
        print("feedback_attachments:", r["feedback_attachments"])


if __name__ == "__main__":
    main()


