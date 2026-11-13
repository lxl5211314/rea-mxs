# 启动 msx-clone
#   .\run.ps1                      用当前环境变量启动
#   .\run.ps1 -Key sk-xxx          临时指定 key
param(
    [string]$Key = $env:OPENAI_API_KEY,
    [string]$BaseUrl = $(if ($env:OPENAI_BASE_URL) { $env:OPENAI_BASE_URL } else { "https://api.deepseek.com/v1" }),
    [string]$Model = $(if ($env:LLM_MODEL) { $env:LLM_MODEL } else { "deepseek-chat" }),
    [string]$Role = $(if ($env:ROLE) { $env:ROLE } else { "后端工程师" }),
    [string]$Resume = $env:RESUME,
    [string]$AsrModel = $(if ($env:ASR_MODEL) { $env:ASR_MODEL } else { "small" })
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $Key) {
    Write-Host "缺少 OPENAI_API_KEY：加 -Key sk-xxx，或先设置 `$env:OPENAI_API_KEY" -ForegroundColor Yellow
    Write-Host "只测采集和 ASR 可以跑：python selftest.py e2e -w `"C:\Program Files\msx-client\resources\self-test-interviewer.wav`"" -ForegroundColor Gray
    exit 1
}

$env:OPENAI_API_KEY = $Key
$env:OPENAI_BASE_URL = $BaseUrl
$env:LLM_MODEL = $Model
$env:ROLE = $Role
$env:RESUME = $Resume
$env:ASR_MODEL = $AsrModel
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "role=$Role  model=$Model  asr=$AsrModel" -ForegroundColor Cyan
Write-Host "热键：F8 显隐 / Tab 强制作答 / F9 穿透 / F10 透明度 / Esc 清屏" -ForegroundColor Cyan
python mvp.py
