from __future__ import annotations

import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RetireResult:
    source: Path
    backup: Path
    retired: Path | None
    note: str | None


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sqlite_online_backup(source_db: Path, dest_db: Path) -> None:
    if dest_db.exists():
        dest_db.unlink()
    _ensure_dir(dest_db.parent)

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


def _retire_one(path: Path, backup_dir: Path, retired_dir: Path, ts: str) -> RetireResult | None:
    if not path.exists():
        return None

    backup_name = f"{path.name}.{ts}.bak"
    backup_path = backup_dir / backup_name

    # DB는 Online Backup, 그 외는 파일 복사
    note = None
    try:
        if path.suffix.lower() == ".db":
            _sqlite_online_backup(path, backup_path)
        else:
            _ensure_dir(backup_dir)
            shutil.copy2(path, backup_path)
            note = "non-sqlite file copied"
    except Exception as e:
        return RetireResult(source=path, backup=backup_path, retired=None, note=f"backup failed: {e}")

    # 원본 이동(락이면 실패할 수 있음)
    retired_path = retired_dir / f"{path.name}.{ts}.retired"
    try:
        _ensure_dir(retired_dir)
        if retired_path.exists():
            retired_path.unlink()
        path.replace(retired_path)
        return RetireResult(source=path, backup=backup_path, retired=retired_path, note=note)
    except Exception as e:
        return RetireResult(source=path, backup=backup_path, retired=None, note=f"backup ok, retire(move) failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="QuickRail 레거시 DB 파일 백업 후 퇴역(이동)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 파일 이동 없이 대상만 출력",
    )
    args = parser.parse_args()

    root = _project_root()
    backup_dir = root / "backups" / "legacy_dbs"
    retired_dir = backup_dir / "retired"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 표준 DB는 제외
    standard_db = root / "instance" / "quickrail.db"

    candidates = [
        root / "quickrail.db",
        root / "instance" / "quickrail-mssung-w.db",
        root / "instance" / "quickrail.db.backup",
    ]

    print("Standard DB (kept):", standard_db.resolve())
    print("Candidates:")
    for c in candidates:
        print(" -", c.resolve(), "(exists)" if c.exists() else "(missing)")

    if args.dry_run:
        return 0

    results: list[RetireResult] = []
    for c in candidates:
        if c.resolve() == standard_db.resolve():
            continue
        r = _retire_one(c, backup_dir, retired_dir, ts)
        if r:
            results.append(r)

    print("\nResults:")
    for r in results:
        print("-" * 72)
        print("source:", r.source.resolve())
        print("backup:", r.backup.resolve())
        if r.retired:
            print("retired:", r.retired.resolve())
        if r.note:
            print("note:", r.note)

    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


