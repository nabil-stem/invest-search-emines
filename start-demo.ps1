<#
  start-demo.ps1 - One-command launcher for the Invest Search demo.
  Starts: Ollama (qwen2.5) + FastAPI on 0.0.0.0:8000 + ngrok tunnel,
  then prints the public ngrok URL to paste into Vercel (BACKEND_URL).

  Usage (from the repo root):
      powershell -ExecutionPolicy Bypass -File .\start-demo.ps1 -BackendKey "my-long-secret"
  -> Put the SAME BackendKey value in the Vercel env var "BACKEND_KEY".
  If you don't pass one, the script generates and prints it.
#>
param(
  [string]$BackendKey = $env:BACKEND_KEY,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

# 1. Project Python interpreter (.api310, else the venv outside OneDrive).
$py = Join-Path $repo ".api310\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = Join-Path $env:USERPROFILE ".investsearch_venv\Scripts\python.exe" }
if (-not (Test-Path $py)) {
  throw "Python venv not found (.api310 or ~/.investsearch_venv). Create it and: pip install -r requirements-vercel.txt"
}

# 2. Shared secret with Vercel (protects your PC behind the tunnel).
if ([string]::IsNullOrWhiteSpace($BackendKey)) {
  $BackendKey = [guid]::NewGuid().ToString("N")
  Write-Host "Generated BACKEND_KEY: $BackendKey" -ForegroundColor Yellow
}
$env:BACKEND_KEY = $BackendKey

# 3. Ollama: start + ensure models present.
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { throw "Ollama is not installed (https://ollama.com)." }
if (-not (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)) {
  Write-Host "Starting Ollama..." -ForegroundColor Cyan
  Start-Process -WindowStyle Minimized ollama -ArgumentList "serve"
  Start-Sleep 3
}
Write-Host "Checking models (qwen2.5:7b, nomic-embed-text)..." -ForegroundColor Cyan
try { ollama pull qwen2.5:7b; ollama pull nomic-embed-text }
catch { Write-Host "  (pull skipped - offline? models must already be present)" -ForegroundColor DarkYellow }

# 4. FastAPI on 0.0.0.0 (reachable by the tunnel), in its own window.
Write-Host "Starting FastAPI backend on 0.0.0.0:$Port..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
  "-NoExit","-Command",
  "`$env:BACKEND_KEY='$BackendKey'; Set-Location '$repo'; & '$py' -m uvicorn server:app --host 0.0.0.0 --port $Port"
)
Start-Sleep 5

# 5. ngrok tunnel, in its own window.
if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) { throw "ngrok not found in PATH." }
Write-Host "Opening ngrok tunnel..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @("-NoExit","-Command","ngrok http $Port")
Start-Sleep 6

# 6. Read the public URL from ngrok's local API; print the Vercel values.
$url = $null
try {
  $tunnels = (Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop).tunnels
  $url = ($tunnels | Where-Object { $_.public_url -like "https*" } | Select-Object -First 1).public_url
} catch { }

Write-Host ""
Write-Host "=================== DEMO READY ===================" -ForegroundColor Green
if ($url) { Write-Host "Public URL : $url" -ForegroundColor Green }
else      { Write-Host "Public URL : see the ngrok window (or http://127.0.0.1:4040)" -ForegroundColor Green }
Write-Host ""
Write-Host "In Vercel (Project -> Settings -> Environment Variables), set:" -ForegroundColor Green
if ($url) { Write-Host "  BACKEND_URL = $url" -ForegroundColor White }
Write-Host "  BACKEND_KEY = $BackendKey" -ForegroundColor White
Write-Host "Then redeploy the frontend. (The free ngrok URL changes each run.)" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
