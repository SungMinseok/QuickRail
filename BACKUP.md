### QuickRail `quickrail.db` 백업 플로우(권장)

QuickRail 기본 DB는 SQLite(`instance/quickrail.db`)입니다. SQLite는 단순 파일 복사도 가능하지만, 앱이 실행 중일 때는 WAL/락 이슈로 **일관성 있는 스냅샷**을 얻기 어려울 수 있습니다.  
따라서 QuickRail에서는 `sqlite3`의 **Online Backup API** 기반 백업을 권장합니다.

### 구현된 백업 스크립트
- **`tools/sqlite_backup.py`**
  - Online Backup API로 스냅샷 생성
  - `PRAGMA integrity_check`로 무결성 검사
  - `.sha256` 해시 파일 생성
  - 보관 정책(최근 N개/최근 N일) 로테이션
- **`scripts/backup_quickrail.ps1`**
  - Windows Task Scheduler에서 바로 실행 가능한 래퍼

### 수동 백업(추천)

```powershell
cd "C:\Users\mssung\OneDrive - KRAFTON\PyProject\QuickRail"
python tools\sqlite_backup.py --db instance\quickrail.db --backup-dir backups\quickrail.db --keep-last 30 --keep-days 14
```

### 백업 대상 DB 경로 주의

환경 변수 `DATABASE_URL`을 사용 중이면 실제 DB 파일이 `quickrail.db`가 아닐 수 있습니다.
그 경우 아래처럼 `--db-url` 또는 `--db`를 명시하세요.

```powershell
python tools\sqlite_backup.py --db-url "sqlite:///instance/quickrail.db"
```

### 스케줄 백업(Windows Task Scheduler 예시)

- Program/script: `powershell.exe`
- Arguments:
  - `-ExecutionPolicy Bypass -File "C:\...\QuickRail\scripts\backup_quickrail.ps1"`
- Start in:
  - `C:\...\QuickRail`

### 복구(restore) 권장 절차

1. QuickRail 서버 중지
2. 현재 `quickrail.db`를 다른 이름으로 이동(비상 복구용)
3. 백업 파일을 `quickrail.db`로 복사
4. 서버 재시작

SQLite 복구는 단순 파일 교체로 가능하지만, 운영 환경에서는 “서버 중지 → 교체”를 권장합니다.


