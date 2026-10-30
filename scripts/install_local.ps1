# ============================================================================
#  aiacting 本地安装脚本（Windows，不需要 GitHub）
#
#  作用：
#    1. 在项目目录建 .venv 虚拟环境
#    2. 以「可编辑模式」安装 aiacting（改源码立刻生效）
#    3. 在 %USERPROFILE%\bin 放一个 aiacting.cmd 入口
#    4. 确保该目录在用户 PATH 里，之后任何终端直接敲 aiacting 就能用
#
#  用法（在项目根目录）：
#    powershell -ExecutionPolicy Bypass -File scripts\install_local.ps1
# ============================================================================

param(
    [string]$KitPath = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$BinDir  = "$env:USERPROFILE\bin"
)

$ErrorActionPreference = 'Stop'

function Test-VenvCapable {
    param([string]$Exe)
    $dir = Split-Path $Exe -Parent
    # Python 3.11 的部分安装包缺这两个 launcher，`python -m venv` 会直接失败
    return (Test-Path (Join-Path $dir 'venvlauncher.exe')) -or
           (Test-Path (Join-Path $dir 'venvwlauncher.exe'))
}

function Get-PythonVersion {
    param([string]$Exe, [string[]]$Pre = @())
    try {
        $all = @($Pre) + @('-c', 'import sys;print(".".join(map(str,sys.version_info[:3])))')
        $r = & $Exe @all 2>$null
        if ($LASTEXITCODE -eq 0 -and $r -match '^\d+\.\d+') { return $r.Trim() }
    } catch { }
    return $null
}

Write-Output "== 1/5 检查项目目录 =="
if (-not (Test-Path "$KitPath\pyproject.toml")) {
    throw "找不到 $KitPath\pyproject.toml，请在项目根目录运行"
}
Write-Output "   $KitPath"

$venv    = Join-Path $KitPath ".venv"
$hasVenv = Test-Path "$venv\Scripts\python.exe"

Write-Output "== 2/5 选择 Python =="
$py  = $null
$pre = @()
if ($hasVenv) {
    Write-Output "   已有 .venv，跳过选型"
} else {
    $candidates = @(
        @{ Exe = 'py';      Pre = @('-3.13') },
        @{ Exe = 'py';      Pre = @('-3.12') },
        @{ Exe = 'python';  Pre = @() },
        @{ Exe = 'python3'; Pre = @() },
        @{ Exe = 'py';      Pre = @('-3.11') },
        @{ Exe = 'py';      Pre = @() }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $ver = Get-PythonVersion -Exe $cmd.Source -Pre $c.Pre
        if (-not $ver) { continue }
        if (-not (Test-VenvCapable $cmd.Source)) {
            Write-Output "   跳过 $($cmd.Source) $($c.Pre -join ' ') ($ver)：缺 venv launcher"
            continue
        }
        $py  = $cmd.Source
        $pre = $c.Pre
        Write-Output "   $py $($pre -join ' ') ($ver)"
        break
    }
    if (-not $py) { throw "没找到能创建虚拟环境的 Python 3.9+，请安装 Python 3.12/3.13" }
}

Write-Output "== 3/5 创建虚拟环境 =="
if (-not $hasVenv) {
    $all = @($pre) + @('-m', 'venv', $venv)
    & $py @all
    if (-not (Test-Path "$venv\Scripts\python.exe")) { throw "venv 创建失败" }
    Write-Output "   已创建 $venv"
} else {
    Write-Output "   已存在，跳过"
}
$vpy = "$venv\Scripts\python.exe"

Write-Output "== 4/5 安装依赖与命令入口 =="
$pipOk = $true
& $vpy -m pip install -q pyyaml edge-tts yt-dlp
if ($LASTEXITCODE -ne 0) { $pipOk = $false; Write-Warning "依赖安装失败（多半是网络）。已有的包仍可用。" }
& $vpy -m pip install -q -e $KitPath
if ($LASTEXITCODE -ne 0) { $pipOk = $false; Write-Warning "可编辑安装失败。" }
if (-not (Test-Path "$venv\Scripts\aiacting.exe")) {
    throw "命令入口没有生成，检查 pyproject.toml 的 [project.scripts]"
}
Write-Output "   $venv\Scripts\aiacting.exe"

Write-Output "== 5/5 注册全局命令 =="
if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Path $BinDir -Force | Out-Null }
$shim = Join-Path $BinDir "aiacting.cmd"
@"
@echo off
setlocal
set "AIACTING_HOME=$KitPath"
if not exist "%AIACTING_HOME%\.venv\Scripts\aiacting.exe" goto missing
"%AIACTING_HOME%\.venv\Scripts\aiacting.exe" %*
exit /b %ERRORLEVEL%
:missing
echo [aiacting] installation not found: %AIACTING_HOME%\.venv
exit /b 1
"@ | Set-Content -Path $shim -Encoding ASCII
Write-Output "   $shim"

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) { $userPath = '' }
if (($userPath -split ';') -notcontains $BinDir) {
    $trimmed = $userPath.TrimEnd(';')
    $newPath = if ($trimmed) { "$trimmed;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    Write-Output "   已把 $BinDir 加入用户 PATH（需要新开终端生效）"
} else {
    Write-Output "   $BinDir 已在 PATH 中"
}

Write-Output ""
Write-Output "== 自检 =="
$out  = & "$venv\Scripts\aiacting.exe" au AU7
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Output "   $_" }
if ($code -ne 0) { throw "自检失败：命令跑不起来（exit $code）" }
Write-Output ""
Write-Output "安装完成。新开一个终端，随便在哪个目录都能用："
Write-Output "  aiacting check examples\what-about-my-life.yml"
Write-Output "  aiacting build examples\what-about-my-life.yml -o prompt.txt"
if (-not $pipOk) { Write-Output "(注意：本次依赖安装有失败，联网后重跑本脚本即可)" }
