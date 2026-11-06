param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$studioPython = Join-Path $PSScriptRoot '.venv312/Scripts/python.exe'
$studioOllama = Join-Path $PSScriptRoot '.runtime/ollama/ollama.exe'
if (!(Test-Path -LiteralPath $studioPython)) { throw 'Run Setup.ps1 first (Python 3.12 required).' }
if (!(Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Frontend missing. Run Setup.ps1.' }
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path $PSScriptRoot 'models/ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:PYTHONUTF8 = '1'
$studioProcess = $null
$studioApiProcess = $null
$studioBindHost = '127.0.0.1'
if (Test-Path -LiteralPath '.runtime/lan.json') {
    $studioLan = Get-Content -LiteralPath '.runtime/lan.json' -Raw | ConvertFrom-Json
    if ($studioLan.host -and $studioLan.access_token) {
        $studioBindHost = '0.0.0.0'
        Write-Host ("LAN URL: http://" + $studioLan.host + ":8765/?access=" + $studioLan.access_token)
    }
}
try {
    $studioExisting = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 3
    if ($studioExisting.local_only -or $studioExisting.lan_enabled) {
        Write-Host 'Studio is already running at http://127.0.0.1:8765'
        if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
        return
    }
} catch { }
try {
    try { $null = Invoke-RestMethod 'http://127.0.0.1:11435/api/tags' -TimeoutSec 2 }
    catch {
        if (!(Test-Path -LiteralPath $studioOllama)) { throw 'Portable Ollama missing. Run Setup.ps1.' }
        $studioProcess = Start-Process -FilePath $studioOllama -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput '.runtime/ollama-out.log' -RedirectStandardError '.runtime/ollama-error.log'
    }
    Write-Host 'Xiaolan Studio: http://127.0.0.1:8765'
    $studioApiProcess = Start-Process -FilePath $studioPython -ArgumentList '-m','uvicorn','backend.app:app','--host',$studioBindHost,'--port','8765','--no-access-log' -WindowStyle Hidden -PassThru -RedirectStandardOutput '.runtime/api-out.log' -RedirectStandardError '.runtime/api-error.log'
    $studioReady = $false
    for ($studioAttempt = 0; $studioAttempt -lt 30; $studioAttempt++) {
        if ($studioApiProcess.HasExited) { throw 'Studio startup failed. See .runtime/api-error.log.' }
        try { $null = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 3; $studioReady = $true; break }
        catch { Start-Sleep -Seconds 1 }
    }
    if (!$studioReady) { throw 'Studio did not become ready.' }
    if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
    Write-Host 'Keep this window open. Close it or press Ctrl+C to stop the studio.'
    Wait-Process -Id $studioApiProcess.Id
} finally {
    if ($studioApiProcess -and !$studioApiProcess.HasExited) { Stop-Process -Id $studioApiProcess.Id }
    if ($studioProcess -and !$studioProcess.HasExited) { Stop-Process -Id $studioProcess.Id }
}
