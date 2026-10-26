[CmdletBinding()]
param([string]$VenvPath = '.venv', [switch]$BackendOnly, [switch]$FrontendOnly)
. (Join-Path $PSScriptRoot 'windows-common.ps1')
try {
    if ($BackendOnly -and $FrontendOnly) { throw 'Choose BackendOnly or FrontendOnly, not both.' }
    if (-not $FrontendOnly) {
        $venvPython = Get-RoadLensVenvPython $VenvPath
        Push-Location -LiteralPath $script:RoadLensRoot
        try {
            Invoke-RoadLensCommand $venvPython @('scripts\check_release.py')
            Invoke-RoadLensCommand $venvPython @('-m', 'pytest')
        }
        finally { Pop-Location }
    }
    if (-not $BackendOnly) {
        $nodeChoice = Get-RoadLensNode
        $frontend = Get-RoadLensFrontend
        Push-Location -LiteralPath $frontend
        try { Invoke-RoadLensCommand $nodeChoice.Npm @('test') }
        finally { Pop-Location }
    }
} catch {
    Write-Error "Tests failed: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
