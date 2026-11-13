# relay-restore.ps1
# Restores the 127.0.0.1:19300 LLM relay that msx-clone depends on.
#
# The relay chain is:
#   YonyouBridge.exe (智能交付 client)  ->  spawns codex-app-server.exe (per-run token + dynamic upstream port in config.toml)
#   -> forwarder.js (DSH .dsh\yonyou-relay, listens 127.0.0.1:19300, must be a YonyouBridge descendant)
#   -> mvp.py Brain (OPENAI_BASE_URL=http://127.0.0.1:19300/v1)
#
# Failure mode seen 2026-11-12: YonyouBridge.exe IS running, but codex-app-server.exe
# is NOT (config.toml not rewritten, upstream port 53404 dead) -> start-yonyou-relay.ps1
# throws "codex-app-server.exe not found" -> 19300 never comes up -> exam answers fail.
#
# codex-app-server is spawned lazily by the bridge: it appears only after the user opens
# a session in the 智能交付 UI (or logs in). This script therefore:
#   1. waits for codex-app-server.exe to appear (poll, up to WaitSeconds)
#   2. runs the DSH Ensure-Relay pass (start-yonyou-relay.ps1)
#   3. verifies 127.0.0.1:19300/healthz and reports the resolved upstream
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File relay-restore.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File relay-restore.ps1 -WaitSeconds 120
#
# Exit codes: 0 healthy, 1 no bridge, 2 timeout waiting codex-app-server, 3 relay still down.

param(
    [int]$WaitSeconds = 90,
    [switch]$NoWait
)

$ErrorActionPreference = 'Continue'
$StartScript = "C:\Users\liuxi\.dsh\yonyou-relay\start-yonyou-relay.ps1"
$HealthUrl   = "http://127.0.0.1:19300/healthz"

function Write-Step([string]$m) { Write-Host "[relay-restore] $m" }

function Test-RelayHealthy {
    try {
        $r = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3
        if ($r.ok -and $r.bridgeAlive -ne $false) { return $r }
    } catch { }
    return $null
}

function Find-CodexAppServer {
    $p = Get-CimInstance Win32_Process -Filter "Name='codex-app-server.exe'" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($p) { return $p }
    return $null
}

# --- 0. is the bridge up? -----------------------------------------------------
$bridge = Get-Process -Name YonyouBridge -ErrorAction SilentlyContinue |
    Sort-Object StartTime -Descending | Select-Object -First 1
if (-not $bridge) {
    Write-Step "YonyouBridge.exe is NOT running - start the 智能交付 client first"
    exit 1
}
Write-Step "bridge pid $($bridge.Id) running (started $($bridge.StartTime))"

# --- 1. wait for codex-app-server.exe -----------------------------------------
if ($NoWait) {
    if (-not (Find-CodexAppServer)) {
        Write-Step "codex-app-server.exe not running (NoWait)"
        exit 2
    }
} else {
    Write-Step "waiting for codex-app-server.exe (up to ${WaitSeconds}s) - open a session in the 智能交付 client if it never appears..."
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Find-CodexAppServer) { break }
        Start-Sleep -Milliseconds 1500
    }
    if (-not (Find-CodexAppServer)) {
        Write-Step "TIMEOUT: codex-app-server.exe never appeared in ${WaitSeconds}s"
        Write-Step "=> open the 智能交付 client (window '智能交付'), make sure it is logged in, and start a chat/session;"
        Write-Step "   codex-app-server.exe then spawns and this script can proceed. Re-run this script afterwards."
        exit 2
    }
    $ca = Find-CodexAppServer
    Write-Step "codex-app-server.exe up (pid $($ca.ProcessId))"
}

# --- 2. run the DSH Ensure-Relay pass -----------------------------------------
Write-Step "running start-yonyou-relay.ps1 ..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StartScript
if ($LASTEXITCODE -ne 0) {
    Write-Step "start-yonyou-relay.ps1 exited $LASTEXITCODE (see forwarder.log)"
} else {
    Write-Step "Ensure-Relay pass OK"
}

# --- 3. verify 19300 ----------------------------------------------------------
$h = Test-RelayHealthy
if ($h) {
    Write-Step "HEALTHY: 127.0.0.1:19300 -> upstream $($h.upstream) (tokenLoaded=$($h.tokenLoaded), bridgeAlive=$($h.bridgeAlive))"
    exit 0
}
Write-Step "relay still not healthy after repair; see C:\Users\liuxi\.dsh\yonyou-relay\forwarder.log"
exit 3
