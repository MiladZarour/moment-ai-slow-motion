$ErrorActionPreference = 'Stop'
$appUrl = 'http://127.0.0.1:8766'
try { $health = Invoke-RestMethod "$appUrl/api/health" -TimeoutSec 2 } catch { $health = $null }
if ($health -and $health.apiVersion -ne 4) {
    try { Invoke-RestMethod "$appUrl/api/stop" -Method Post -Headers @{'X-Moment-Client'='1'} -TimeoutSec 5 | Out-Null }
    catch { throw 'The older engine is still processing a video. Release Hold and let any save finish, then run Start Moment.cmd again.' }
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 200
        try { $null = Invoke-RestMethod "$appUrl/api/health" -TimeoutSec 1 }
        catch { $health = $null; break }
    }
    if ($health) { throw 'The older engine has not stopped yet. Try Start Moment.cmd again in a moment.' }
}
if (-not $health) {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    $serverPath = Join-Path $PSScriptRoot 'server.py'
    Start-Process -FilePath $pythonPath -ArgumentList @('"' + $serverPath + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server-error.log') | Out-Null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { $health = Invoke-RestMethod "$appUrl/api/health" -TimeoutSec 1; break } catch {}
    }
}
if (-not $health.engine -or $health.apiVersion -ne 4) { throw 'The updated AI engine could not start. See server-error.log in the project folder.' }
Start-Process $appUrl
