[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'windows-common.ps1')
try {
    $nodeChoice = Get-RoadLensNode
    $frontend = Get-RoadLensFrontend
    Push-Location -LiteralPath $frontend
    try { Invoke-RoadLensCommand $nodeChoice.Npm @('run', 'dev') }
    finally { Pop-Location }
} catch {
    Write-Error "Frontend failed: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
