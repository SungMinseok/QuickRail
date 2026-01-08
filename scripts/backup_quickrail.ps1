param(
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$DbPath = "",
  [string]$BackupDir = ""
)

# QuickRail SQLite 백업 실행 스크립트 (Windows Task Scheduler용)
# - venv가 있으면 사용
# - tools/sqlite_backup.py를 호출하여 온라인 백업 + 무결성 검사 + 로테이션 수행

Set-Location $ProjectRoot

$python = "python"
if (Test-Path "$ProjectRoot\\venv\\Scripts\\python.exe") {
  $python = "$ProjectRoot\\venv\\Scripts\\python.exe"
}

if ($DbPath -eq "") {
  $DbPath = "$ProjectRoot\\instance\\quickrail.db"
}

if ($BackupDir -eq "") {
  $BackupDir = "$ProjectRoot\\backups\\quickrail.db"
}

& $python "$ProjectRoot\\tools\\sqlite_backup.py" --db "$DbPath" --backup-dir "$BackupDir" --keep-last 30 --keep-days 14
exit $LASTEXITCODE


