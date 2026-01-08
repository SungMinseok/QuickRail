from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class BackupResult:
    source_db: Path
    backup_file: Path
    sha256_file: Path


def _project_root() -> Path:
    # tools/ 아래에 위치하므로 상위가 프로젝트 루트
    return Path(__file__).resolve().parents[1]


def _parse_sqlite_url(db_url: str) -> Path:
    """
    Supports:
      - sqlite:///relative/path.db  (project root 기준)
      - sqlite:////absolute/path.db
    """
    if not db_url.startswith("sqlite:"):
        raise ValueError(f"지원하지 않는 DB URL 입니다: {db_url}")

    # SQLAlchemy 스타일 sqlite:///...
    if db_url.startswith("sqlite:////"):
        # 절대 경로
        p = Path(db_url[len("sqlite:////") :])
        return p

    if db_url.startswith("sqlite:///"):
        rel = db_url[len("sqlite:///") :]
        return _project_root() / rel

    # sqlite:// 는 드물지만 상대 경로로 들어올 수 있음
    if db_url.startswith("sqlite://"):
        rel = db_url[len("sqlite://") :]
        return _project_root() / rel.lstrip("/")

    raise ValueError(f"sqlite URL 파싱 실패: {db_url}")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_integrity_check(path: Path) -> Tuple[bool, str]:
    con = sqlite3.connect(str(path))
    try:
        row = con.execute("PRAGMA integrity_check;").fetchone()
        msg = row[0] if row else ""
        return (str(msg).lower() == "ok"), str(msg)
    finally:
        con.close()


def backup_sqlite_db(
    source_db: Path,
    backup_dir: Path,
    keep_last: int = 30,
    keep_days: int = 14,
    prefix: str = "quickrail",
) -> BackupResult:
    source_db = source_db.resolve()
    backup_dir = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not source_db.exists():
        raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {source_db}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{prefix}_{ts}.db"
    tmp_file = backup_dir / f".{prefix}_{ts}.db.tmp"

    # SQLite Online Backup API로 일관성 있는 스냅샷 생성
    src = sqlite3.connect(str(source_db), timeout=30)
    try:
        # WAL 모드라면 체크포인트를 한 번 시도(실패해도 백업은 가능)
        try:
            src.execute("PRAGMA wal_checkpoint(FULL);")
        except Exception:
            pass

        dst = sqlite3.connect(str(tmp_file))
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()

    # 임시 파일 -> 최종 파일(atomic-ish)
    if backup_file.exists():
        backup_file.unlink()
    tmp_file.replace(backup_file)

    # 무결성 체크
    ok, msg = _sqlite_integrity_check(backup_file)
    if not ok:
        raise RuntimeError(f"백업 무결성 검사 실패: {msg}")

    # SHA256 생성
    sha = _sha256_file(backup_file)
    sha_file = backup_file.with_suffix(backup_file.suffix + ".sha256")
    sha_file.write_text(f"{sha}  {backup_file.name}\n", encoding="utf-8")

    # 로테이션
    rotate_backups(backup_dir, prefix=prefix, keep_last=keep_last, keep_days=keep_days)

    return BackupResult(source_db=source_db, backup_file=backup_file, sha256_file=sha_file)


def rotate_backups(backup_dir: Path, prefix: str, keep_last: int, keep_days: int) -> None:
    backup_dir = backup_dir.resolve()
    if not backup_dir.exists():
        return

    # 파일명: prefix_YYYYmmdd_HHMMSS.db
    backups = sorted(backup_dir.glob(f"{prefix}_*.db"), reverse=True)

    # keep_last 초과분 삭제
    for f in backups[keep_last:]:
        try:
            sha = f.with_suffix(f.suffix + ".sha256")
            if sha.exists():
                sha.unlink()
            f.unlink()
        except Exception:
            pass

    # keep_days 초과분 삭제
    cutoff = datetime.now() - timedelta(days=keep_days)
    for f in sorted(backup_dir.glob(f"{prefix}_*.db")):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                sha = f.with_suffix(f.suffix + ".sha256")
                if sha.exists():
                    sha.unlink()
                f.unlink()
        except Exception:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="QuickRail SQLite DB 백업")
    parser.add_argument(
        "--db",
        dest="db_path",
        default=str(_project_root() / "instance" / "quickrail.db"),
        help="백업할 DB 파일 경로(기본: instance/quickrail.db)",
    )
    parser.add_argument(
        "--db-url",
        dest="db_url",
        default=None,
        help="SQLAlchemy DATABASE_URL (sqlite:///... 형태). 지정 시 --db보다 우선",
    )
    parser.add_argument(
        "--backup-dir",
        dest="backup_dir",
        default=str(_project_root() / "backups" / "quickrail.db"),
        help="백업 파일 저장 디렉토리",
    )
    parser.add_argument("--keep-last", type=int, default=30, help="최근 N개 백업 유지")
    parser.add_argument("--keep-days", type=int, default=14, help="최근 N일 백업 유지")
    parser.add_argument("--prefix", type=str, default="quickrail", help="백업 파일 prefix")

    args = parser.parse_args(argv)

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if db_url:
        source = _parse_sqlite_url(db_url)
    else:
        source = Path(args.db_path)

    res = backup_sqlite_db(
        source_db=source,
        backup_dir=Path(args.backup_dir),
        keep_last=args.keep_last,
        keep_days=args.keep_days,
        prefix=args.prefix,
    )

    print(f"[DONE] Backup created: {res.backup_file}")
    print(f"[DONE] SHA256 saved:  {res.sha256_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


