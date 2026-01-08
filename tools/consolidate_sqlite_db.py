from __future__ import annotations

import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ConsolidationResult:
    source: Path
    target: Path
    backup_of_target: Path | None


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _integrity_check(db_path: Path) -> tuple[bool, str]:
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    try:
        row = cur.execute("PRAGMA integrity_check").fetchone()
        msg = row[0] if row else "unknown"
        return (msg == "ok"), msg
    finally:
        con.close()


def _backup_sqlite(source_db: Path, dest_db: Path) -> None:
    """SQLite Online Backup API 기반 복사(실행 중인 DB에서도 비교적 안전)."""
    _ensure_parent(dest_db)
    if dest_db.exists():
        dest_db.unlink()

    src = sqlite3.connect(str(source_db), timeout=30)
    try:
        dst = sqlite3.connect(str(dest_db), timeout=30)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


def consolidate(source: Path, target: Path, keep_backup: bool = True) -> ConsolidationResult:
    if not source.exists():
        raise FileNotFoundError(f"source DB not found: {source}")

    _ensure_parent(target)

    backup_path: Path | None = None
    if keep_backup and target.exists():
        backup_dir = Path("backups") / "db_consolidation"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{target.stem}_before_{ts}{target.suffix}"
        shutil.copy2(target, backup_path)

    tmp = target.with_suffix(target.suffix + ".tmp")
    _backup_sqlite(source, tmp)

    ok, msg = _integrity_check(tmp)
    if not ok:
        try:
            tmp.unlink(missing_ok=True)  # py3.11 ok
        except Exception:
            pass
        raise RuntimeError(f"integrity_check failed for tmp copy: {msg}")

    # atomic-ish replace
    if target.exists():
        target.unlink()
    tmp.replace(target)

    return ConsolidationResult(source=source, target=target, backup_of_target=backup_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="QuickRail SQLite DB 통합(원본 -> 타깃으로 복사)")
    parser.add_argument(
        "--source",
        required=True,
        help="통합 원본 DB 경로 (예: instance/quickrail-mssung-w.db)",
    )
    parser.add_argument(
        "--target",
        default="instance/quickrail.db",
        help="통합 타깃 DB 경로 (기본: instance/quickrail.db)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="타깃 DB 백업(복사본) 생성 생략",
    )
    args = parser.parse_args()

    res = consolidate(Path(args.source), Path(args.target), keep_backup=(not args.no_backup))
    print("[DONE] Consolidated DB")
    print("  source:", res.source.resolve())
    print("  target:", res.target.resolve())
    if res.backup_of_target:
        print("  backup_of_target:", res.backup_of_target.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


