<#
.SYNOPSIS
    启动《我不是股神》Windows 本地预览（/game，默认 8091）。

.DESCRIPTION
    数据源为 scripts/win/game_preview_sample.py 的确定性合成样本
    （store 契约与 tests/test_trading_game_web.py::FakeStore 一致），
    跑仓库真实游戏代码：不连接任何数据库，不依赖 WSL 文件路径。

    SaaS 页面预览仍用 start-ui-preview.ps1；两者默认同端口 8091，
    不能同时运行（需要同时预览时给其中一个换 -Port）。

.PARAMETER Port
    监听端口，默认 8091。8080/8081 被 WSL 实例经 localhost 转发占用，
    见 .claude/skills/ui-preview/SKILL.md 的已知坑。
#>
[CmdletBinding()]
param(
    [int]$Port = 8091
)

$ErrorActionPreference = "Stop"
# Windows 默认 GBK：强制 UTF-8，避免中文模板/日志解码问题（与 WSL 行为对齐）
$env:PYTHONUTF8 = "1"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

# 端口占用预检（与 start-ui-preview.ps1 同一做法）
$probe = New-Object System.Net.Sockets.TcpClient
try {
    $probe.Connect("127.0.0.1", $Port)
    $probe.Close()
    throw "端口 $Port 已被占用（可能是 SaaS 预览或 WSL 转发）。请换一个 -Port。"
}
catch [System.Net.Sockets.SocketException] {
    # 连接被拒 = 端口空闲，符合预期
}

Write-Host "==> 我不是股神 Windows 预览：http://127.0.0.1:$Port/game"
Write-Host "    数据: 本地合成样本（零数据库连接，不碰生产库）"
Write-Host ""

# uv 可能不在当前 shell 的 PATH 里，退化为 python -m uv
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) { & $uv.Source run python scripts/win/start-game-preview.py --port $Port }
else     { python -m uv run python scripts/win/start-game-preview.py --port $Port }