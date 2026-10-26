[CmdletBinding()]
param([switch]$Showcase, [string]$Base = './')
. (Join-Path $PSScriptRoot 'windows-common.ps1')
try {
    $nodeChoice = Get-RoadLensNode
    $frontend = Get-RoadLensFrontend
    $task = if ($Showcase) { 'build:showcase' } else { 'build' }
    Push-Location -LiteralPath $frontend
    try { Invoke-RoadLensCommand $nodeChoice.Npm @('run', $task, '--', '--base', $Base) }
    finally { Pop-Location }
} catch {
    Write-Error "Build failed: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
