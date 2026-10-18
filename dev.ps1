param(
    [switch]$CheckOnly
)

# 任何一步出错就立刻停下，别带着半截环境继续开窗口。
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# 1. 依赖检查：缺什么一次性列全，而不是撞一个报一个。
$missing = @()
if (-not (Test-Path (Join-Path $root "backend\.venv\Scripts\python.exe"))) {
    $missing += "backend\.venv\Scripts\python.exe（在 backend 下跑：python -m venv .venv，再 pip install -r requirements.txt）"
}
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    $missing += "frontend\node_modules（在 frontend 下跑：npm install）"
}
if (-not (Test-Path (Join-Path $root "personal-site\node_modules"))) {
    $missing += "personal-site\node_modules（在 personal-site 下跑：npm install）"
}

if ($missing.Count -gt 0) {
    Write-Host "缺少以下依赖，先装好再重试：" -ForegroundColor Red
    foreach ($item in $missing) {
        Write-Host "  - $item" -ForegroundColor Red
    }
    exit 1
}

# 2. 检查 backend\.env。只提醒，绝不自动创建或覆盖——里面是密钥。
$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "警告：backend\.env 不存在，后端会退回代码里的默认值（SECRET_KEY=change_me）。" -ForegroundColor Yellow
    Write-Host "建议：copy backend\.env.example backend\.env，再把 SECRET_KEY 换成自己的值。" -ForegroundColor Yellow
}

# 3. -CheckOnly：只验证环境，不跑迁移也不开窗口。
if ($CheckOnly) {
    Write-Host "检查通过" -ForegroundColor Green
    return
}

# 4. 跑数据库迁移。Push-Location / Pop-Location 配对，成功失败都回到原目录。
Push-Location (Join-Path $root "backend")
try {
    & ".\.venv\Scripts\python.exe" -m alembic upgrade head
    # $ErrorActionPreference 只管 cmdlet，管不住 python.exe 这类原生命令。
    # 原生命令失败只会把退出码放进 $LASTEXITCODE，不会抛异常，
    # 所以必须手动检查，否则迁移挂了脚本还会继续往下开窗口。
    if ($LASTEXITCODE -ne 0) {
        Write-Host "数据库迁移失败，已停止。" -ForegroundColor Red
        exit 1
    }
}
finally {
    Pop-Location
}

# 5. 各开一个新的 PowerShell 窗口跑服务。
#    -NoExit 让窗口在服务退出后留着，方便看报错。
#    路径用双引号包住，因为仓库路径可能含空格；`" 是转义后传给子进程的引号。
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$root\scripts\run-backend.ps1`""
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$root\scripts\run-frontend.ps1`""
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$root\scripts\run-personal-site.ps1`""

# 6. 地址汇总和停止方式。
Write-Host ""
Write-Host "backend        http://127.0.0.1:8000/health"
Write-Host "frontend       http://localhost:5173"
Write-Host "personal-site  http://localhost:4321"
Write-Host "在每个窗口按 Ctrl+C 停止对应服务。"
