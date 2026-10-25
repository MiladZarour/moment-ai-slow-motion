$ErrorActionPreference = 'Stop'
$appUrl = 'http://127.0.0.1:8765'
try { $health = Invoke-RestMethod "$appUrl/api/health" -TimeoutSec 2 } catch { $health = $null }
if (-not $health) {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    $serverPath = Join-Path $PSScriptRoot 'server.py'
    Start-Process -FilePath $pythonPath -ArgumentList @('"' + $serverPath + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server-error.log') | Out-Null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { $health = Invoke-RestMethod "$appUrl/api/health" -TimeoutSec 1; break } catch {}
    }
}
if (-not $health.engine) { throw 'The AI engine could not start. See server-error.log in the project folder.' }
Start-Process $appUrl
