param([string]$Python = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$studioVenv = Join-Path $PSScriptRoot '.venv312/Scripts/python.exe'
if (!(Test-Path -LiteralPath $studioVenv)) {
    if ($Python) { & $Python -m venv .venv312 }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3.12 -m venv .venv312 }
    else { throw 'Install Python 3.12 or pass Setup.ps1 -Python <python.exe>.' }
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python 3.12 environment.' }
}
& $studioVenv -m pip install -r requirements.txt -r requirements-voice.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location -LiteralPath 'frontend'
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
} finally { Pop-Location }
& $studioVenv scripts/prepare.py
if ($LASTEXITCODE -ne 0) { throw 'Resource download failed. See output above.' }
Push-Location -LiteralPath 'frontend'
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path $PSScriptRoot 'models/ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$studioOllama = Join-Path $PSScriptRoot '.runtime/ollama/ollama.exe'
$studioProcess = $null
try {
    try { $null = Invoke-RestMethod 'http://127.0.0.1:11435/api/tags' -TimeoutSec 2 }
    catch {
        $studioProcess = Start-Process -FilePath $studioOllama -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput '.runtime/ollama-out.log' -RedirectStandardError '.runtime/ollama-error.log'
        $studioReady = $false
        for ($studioAttempt = 0; $studioAttempt -lt 30; $studioAttempt++) {
            try { $null = Invoke-RestMethod 'http://127.0.0.1:11435/api/tags' -TimeoutSec 1; $studioReady = $true; break } catch { Start-Sleep -Seconds 1 }
        }
        if (!$studioReady) { throw 'Ollama did not start.' }
    }
    & $studioOllama pull qwen3:4b-instruct-2507-q4_K_M
    if ($LASTEXITCODE -ne 0) { throw 'Qwen model download failed.' }
} finally {
    if ($studioProcess -and !$studioProcess.HasExited) { Stop-Process -Id $studioProcess.Id }
}
& $studioVenv scripts/warmup.py
if ($LASTEXITCODE -ne 0) { throw 'Local speech check failed.' }
Write-Host 'Ready. Run ./Start-Studio.ps1'
