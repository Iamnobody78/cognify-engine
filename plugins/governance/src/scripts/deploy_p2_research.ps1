# Deploy P2 gpt-researcher (standalone path) for agent-governance-v2
# ASCII-only (PS5.1 constraint). DeepSeek LLM + DuckDuckGo retriever (free, no key).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_p2_research.ps1 [-DryRun]
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_p2_research.ps1 -RunQuery "agent governance survey"
# Requires: Python >= 3.12 (gpt-researcher 0.16.0 constraint), network, ~2GB disk.
# After deploy: edit .env -> set DEEPSEEK_API_KEY -> python scripts\p2_env.py validate

param(
    [switch]$DryRun = $false,
    [string]$Query = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvDir  = Join-Path $RepoRoot ".venv-research"
$EnvFile  = Join-Path $RepoRoot ".env"

# Governance disk thresholds: Yellow 130GB / Red 135GB free
$YellowGB = 130
$RedGB = 135

function Write-Step([string]$Msg) {
    Write-Host "== $Msg =="
}

function Check-Disk {
    $free = (Get-PSDrive -Name (Split-Path -Qualifier $RepoRoot).TrimEnd(':')).Free / 1GB
    Write-Host ("Disk free: {0:N1} GB" -f $free)
    if ($free -lt $RedGB) { throw "RED: disk free below ${RedGB}GB - abort deploy" }
    if ($free -lt $YellowGB) { Write-Host "WARN: disk free below ${YellowGB}GB (yellow) - proceed with caution" }
}

function Find-Python312Plus {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $v = & $c -c "import sys; print(sys.version.split()[0])" 2>$null
            if ($v -and $v -match '^3\.(1[2-9]|[2-9][0-9])') { return $c }
        }
    }
    # Fallback: `py` launcher
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $v = & py -3.13 -c "import sys; print(sys.version.split()[0])" 2>$null
        if ($v -and $v -match '^3\.(1[2-9]|[2-9][0-9])') { return "py -3.13" }
    }
    throw "No Python >= 3.12 found (gpt-researcher 0.16.0 requires it). Install Python 3.13 first."
}

function Run-OrPrint([string]$Cmd, [string[]]$Args) {
    if ($DryRun) {
        Write-Host "  [dry] $Cmd $($Args -join ' ')"
        return
    }
    & $Cmd @Args
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Cmd $($Args -join ' ') (exit $LASTEXITCODE)" }
}

Write-Step "P2 gpt-researcher deploy (standalone path)"
Write-Step "Preflight"
Check-Disk
$Py = Find-Python312Plus
Write-Host "Python: $Py"
if (Test-Path (Join-Path $VenvDir "Scripts\python.exe")) {
    Write-Host "Venv exists: $VenvDir (reuse)"
} else {
    Write-Step "Create isolated venv (.venv-research, gitignored via .venv*/)"
    if (-not $DryRun) { Run-OrPrint $Py @("-m", "venv", $VenvDir) }
}

$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    if (-not $DryRun) { throw "venv creation failed: $VenvPy missing" }
    # DryRun: 展示真实预期路径, 不回落 "python" (避免误导)
}

Write-Step "Install gpt-researcher + ddgs (DuckDuckGo retriever)"
Run-OrPrint $VenvPy @("-m", "pip", "install", "--upgrade", "pip")
Run-OrPrint $VenvPy @("-m", "pip", "install", "gpt-researcher", "ddgs")

Write-Step "Generate .env template (never overwrites)"
Run-OrPrint $VenvPy @("$PSScriptRoot\p2_env.py", "write-template", "--env", $EnvFile)

Write-Step "Verify imports"
Run-OrPrint $VenvPy @("-c", "import gpt_researcher, ddgs; print('imports OK')")

Write-Step "Validate config"
Run-OrPrint $VenvPy @("$PSScriptRoot\p2_env.py", "validate", "--env", $EnvFile)

if ($Query) {
    Write-Step "Run research query (standalone)"
    Run-OrPrint $VenvPy @("-m", "gpt_researcher", "--report-type", "research_report", "--query", $Query)
} else {
    Write-Host ""
    Write-Host "Deploy complete. Next steps:"
    Write-Host "  1. Edit $EnvFile -> set DEEPSEEK_API_KEY (sk-...)"
    Write-Host "  2. python scripts\p2_env.py validate"
    Write-Host "  3. $VenvPy -m gpt_researcher --report-type research_report --query `"your question`""
    Write-Host "  MCP wrapper path: see .aionui\protocols\p2_research_integration.md"
}
Write-Host "P2 deploy finished (exit 0)"
