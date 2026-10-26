[CmdletBinding()]
param([string]$VenvPath = '.venv', [ValidateRange(1024, 65535)][int]$Port = 8000)
. (Join-Path $PSScriptRoot 'windows-common.ps1')
try {
    $venvPython = Get-RoadLensVenvPython $VenvPath
    Push-Location -LiteralPath $script:RoadLensRoot
    try { Invoke-RoadLensCommand $venvPython @('-m', 'uvicorn', 'roadlens.api:app', '--host', '127.0.0.1', '--port', "$Port") }
    finally { Pop-Location }
} catch {
    Write-Error "Backend failed: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
