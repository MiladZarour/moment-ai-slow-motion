$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$enginePath = Join-Path $PSScriptRoot 'tools/rife-ncnn-vulkan-20221029-windows/rife-ncnn-vulkan.exe'
if (-not (Test-Path -LiteralPath $enginePath)) {
    New-Item -ItemType Directory -Force tools | Out-Null
    $releaseUrl = 'https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip'
    Invoke-WebRequest $releaseUrl -OutFile tools/rife-windows.zip
    Expand-Archive -LiteralPath tools/rife-windows.zip -DestinationPath tools -Force
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw 'Install FFmpeg and add ffmpeg and ffprobe to PATH before starting Moment.'
}
Write-Host 'Ready. Open Start Moment.cmd.'
