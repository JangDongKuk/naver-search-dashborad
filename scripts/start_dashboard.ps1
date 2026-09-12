# 대시보드를 백그라운드로 띄운다. 이미 떠 있으면 아무것도 하지 않는다.
# Claude Code 세션과 무관하게 독립 프로세스로 실행되므로, 세션이 끝나도 계속 떠 있는다.
$ErrorActionPreference = "SilentlyContinue"

$Root = "C:\Users\admin\Desktop\naver-search-dashborad"
$Uv = "C:\Users\admin\.local\bin\uv.exe"
$LogDir = Join-Path $Root "data"
$Log = Join-Path $LogDir "streamlit.log"
$Port = 8501

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$Port/_stcore/health" -TimeoutSec 2 -UseBasicParsing
    if ($resp.StatusCode -eq 200) {
        Write-Output "이미 실행 중: http://localhost:$Port"
        exit 0
    }
} catch {}

Set-Location $Root
$args = @("run", "streamlit", "run", "src\app.py", "--server.port", "$Port", "--server.headless", "true")
Start-Process -FilePath $Uv -ArgumentList $args -WorkingDirectory $Root `
    -WindowStyle Hidden -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"

Write-Output "시작함: http://localhost:$Port (로그: $Log)"
