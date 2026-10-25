@echo off
powershell.exe -NoProfile -Command "try { $reply = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/stop' -Method Post -Headers @{'X-Moment-Client'='1'}; Write-Host $reply.message } catch { Write-Host 'Unable to stop Moment. It may be offline or still processing a video.'; exit 1 }"
if errorlevel 1 pause
