# P9 acceptance runner (native Windows PowerShell)
# Starts stub LLM (:8000) + governance gateway (:9000) -> runs 3 examples ->
# verifies governance evidence -> cleans up.
# Usage: powershell -ExecutionPolicy Bypass -File examples/run_examples.ps1
$ErrorActionPreference = "Stop"

$ROOT = Split-Path -Parent $PSScriptRoot
$PY_B1 = Join-Path $ROOT ".venv-b1\Scripts\python.exe"   # langchain SDK
$PY_B2 = Join-Path $ROOT ".venv-b2\Scripts\python.exe"   # autogen SDK + gateway
$Script:Pass = 0
$Script:Fail = 0

Write-Host "=== [1/4] start stub LLM (:8000) + governance gateway (:9000) ==="
$stub = Start-Process -FilePath $PY_B2 -ArgumentList @("examples\_stub_llm.py") `
    -WorkingDirectory $ROOT -PassThru -WindowStyle Hidden
$gw = Start-Process -FilePath $PY_B2 -ArgumentList @("-m", "src.main") `
    -WorkingDirectory $ROOT -PassThru -WindowStyle Hidden
try {
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        $code = & curl.exe -s -o NUL -w "%{http_code}" "http://127.0.0.1:9000/v1/health" 2>$null
        if ($code -eq "200") { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { Write-Host "FAIL: gateway not ready in 30s"; exit 1 }
    Write-Host "OK: gateway + stub LLM ready"

    function Invoke-Check([string]$name, [string]$py, [string]$script) {
        Write-Host ""
        Write-Host "--- [$name] ---"
        $out = (& $py $script 2>&1 | Out-String)
        $code = $LASTEXITCODE
        if ($code -eq 0) { Write-Host "PASS: $name (exit 0)"; $Script:Pass++ }
        else { Write-Host "FAIL: $name (exit $code)"; $Script:Fail++ }
        Write-Host $out
        return $out
    }

    Write-Host "=== [2/4] generic Python agent (in-process agent_tools) ==="
    $demo = Invoke-Check "external_agent_demo" $PY_B2 (Join-Path $ROOT "examples\external_agent_demo.py")

    Write-Host "=== [3/4] LangChain agent (zero-touch base_url, real SDK) ==="
    $lc = Invoke-Check "langchain_agent" $PY_B1 (Join-Path $ROOT "examples\langchain_agent.py")

    Write-Host "=== [4/4] AutoGen agent (zero-touch base_url, real SDK) ==="
    $ac = Invoke-Check "autogen_agent" $PY_B2 (Join-Path $ROOT "examples\autogen_agent.py")

    Write-Host ""
    Write-Host "=== governance evidence check ==="
    if ($lc -match "DENY")     { Write-Host "PASS: LangChain triggers DENY" }     else { Write-Host "FAIL: no DENY"; $Script:Fail++ }
    if ($lc -match "ESCALATE") { Write-Host "PASS: LangChain triggers ESCALATE" } else { Write-Host "FAIL: no ESCALATE"; $Script:Fail++ }
    if ($ac -match "DENY")     { Write-Host "PASS: AutoGen triggers DENY" }       else { Write-Host "FAIL: no DENY"; $Script:Fail++ }
    if ($ac -match "trace_id") { Write-Host "PASS: AutoGen traceable" }           else { Write-Host "FAIL: no trace_id"; $Script:Fail++ }
} finally {
    Stop-Process -Id $stub.Id, $gw.Id -Force -ErrorAction SilentlyContinue
    Write-Host "=== processes cleaned up ==="
}

Write-Host ""
Write-Host "=== SUMMARY: PASS=$Script:Pass FAIL=$Script:Fail ==="
exit $Script:Fail
