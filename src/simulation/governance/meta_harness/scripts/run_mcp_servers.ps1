# run_mcp_servers.ps1 — Sprint 13 A1: MCP server standalone deployment (Windows host)
#
# Primary launcher (Windows host, Ollama reachable at 127.0.0.1:11434).
# Bash twin: run_mcp_servers.sh (WSL fallback; requires WSL-side Ollama).
#
# Servers:
#   - meta_cognition        : metacognition (hypothesis stats / reasoning / gate) -> :18010
#   - semantic_retrieval    : semantic retrieval (bge-m3 via Ollama)             -> :18011
#   - environment_bootstrap : env bootstrap (snapshot / write-scope validation)  -> :18012
#
# Usage:
#   .\run_mcp_servers.ps1 start [http|stdio]   # start all (default http)
#   .\run_mcp_servers.ps1 start-one <name> [http|stdio]
#   .\run_mcp_servers.ps1 stop [<name>]        # stop all or one
#   .\run_mcp_servers.ps1 status               # process/port status
#   .\run_mcp_servers.ps1 probe                # curl HTTP health probe
param(
    [string]$Action = "status",
    [string]$Name = "",
    [string]$Mode = "http"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = "python"
$Ports = @{
    "meta_cognition"        = 18010
    "semantic_retrieval"    = 18011
    "environment_bootstrap" = 18012
}
$ServerNames = @("meta_cognition", "semantic_retrieval", "environment_bootstrap")
$PidDir = Join-Path $ScriptDir ".mcp_pids"

function Get-PidFile([string]$n) { Join-Path $PidDir "$n.pid" }

function Test-Running([string]$pf) {
    if (-not (Test-Path $pf)) { return $false }
    $procId = Get-Content $pf -ErrorAction SilentlyContinue
    if (-not $procId) { return $false }
    try { Get-Process -Id $procId -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

function Start-One([string]$n, [string]$transport) {
    New-Item -ItemType Directory -Force -Path $PidDir | Out-Null
    $pf = Get-PidFile $n
    if (Test-Running $pf) {
        Write-Host "[run_mcp_servers] $n already running (pid $(Get-Content $pf))"
        return
    }
    $mcpArgs = @("-m", "mcp_servers", "--server", $n)
    $label = "stdio"
    if ($transport -eq "http") {
        $mcpArgs += @("--transport", "streamable-http", "--host", "127.0.0.1", "--port", "$($Ports[$n])")
        $label = "http://127.0.0.1:$($Ports[$n])/mcp"
    }
    $log = Join-Path $ScriptDir ".mcp_logs_$n.log"
    $p = Start-Process -FilePath $Py -ArgumentList $mcpArgs -WorkingDirectory $ScriptDir `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
        -WindowStyle Hidden -PassThru
    Set-Content -Path $pf -Value $p.Id
    Start-Sleep -Seconds 2
    if (-not (Test-Running $pf)) {
        Write-Host "[run_mcp_servers] $n failed to start; see $log"
        return
    }
    if ($transport -eq "http") {
        $ok = $false
        for ($i = 0; $i -lt 20; $i++) {
            try {
                $tcp = New-Object System.Net.Sockets.TcpClient
                $tcp.Connect("127.0.0.1", $Ports[$n])
                $tcp.Close()
                $ok = $true
                break
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if ($ok) { Write-Host "[run_mcp_servers] $n ready @ $label (pid $($p.Id))" }
        else { Write-Host "[run_mcp_servers] $n HTTP port not ready; see $log" }
    } else {
        Write-Host "[run_mcp_servers] $n ready @ $label (pid $($p.Id))"
    }
}

function Stop-One([string]$n) {
    $pf = Get-PidFile $n
    if (-not (Test-Running $pf)) {
        Write-Host "[run_mcp_servers] $n not running"
        Remove-Item $pf -ErrorAction SilentlyContinue
        return
    }
    $p = Get-Process -Id (Get-Content $pf) -ErrorAction SilentlyContinue
    if ($p) { Stop-Process -Id $p.Id -Force; Write-Host "[run_mcp_servers] $n stopped (pid $($p.Id))" }
    Remove-Item $pf -ErrorAction SilentlyContinue
}

function Show-Status {
    $any = $false
    foreach ($n in $ServerNames) {
        $pf = Get-PidFile $n
        if (Test-Running $pf) {
            Write-Host "  [RUN ] $n pid=$(Get-Content $pf) port=$($Ports[$n])"
            $any = $true
        } else {
            Write-Host "  [STOP] $n"
        }
    }
    if (-not $any) { Write-Host "  (none running)" }
}

function Probe-All {
    foreach ($n in $ServerNames) {
        $port = $Ports[$n]
        Write-Host "--- $n @ http://127.0.0.1:$port/mcp ---"
        curl.exe -sS -m 5 "http://127.0.0.1:$port/mcp" -H "Accept: application/json, text/event-stream"
        Write-Host ""
    }
}

switch ($Action.ToLower()) {
    "start" {
        $mode = if ($Mode) { $Mode } else { "http" }
        foreach ($n in $ServerNames) { Start-One $n $mode }
    }
    "start-one" {
        if (-not $Name) { Write-Host "Usage: run_mcp_servers.ps1 start-one <name> [http|stdio]"; exit 1 }
        $mode = if ($Mode) { $Mode } else { "http" }
        Start-One $Name $mode
    }
    "stop" {
        if ($Name) { Stop-One $Name } else { foreach ($n in $ServerNames) { Stop-One $n } }
    }
    "status" { Show-Status }
    "probe" { Probe-All }
    default {
        Write-Host "Usage: run_mcp_servers.ps1 {start [http|stdio]|start-one <name> [http|stdio]|stop [<name>]|status|probe}"
    }
}
