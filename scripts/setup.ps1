<#
.SYNOPSIS
Install RoadLens locally without requiring an existing environment.
.EXAMPLE
.\scripts\setup.ps1 -Python 'C:\Program Files\Python313\python.exe' -VenvPath '.venv'
#>
[CmdletBinding()]
param(
    [string]$Python,
    [string]$VenvPath = '.venv',
    [switch]$CheckOnly
)

. (Join-Path $PSScriptRoot 'windows-common.ps1')

try {
    $pythonChoice = Find-RoadLensPython $Python
    $nodeChoice = Get-RoadLensNode
    Write-Host "Python $($pythonChoice.Version); Node.js $($nodeChoice.Version); npm $($nodeChoice.NpmVersion)"
    if ($CheckOnly) {
        Write-Host 'Prerequisites are available. No files were installed or changed.'
        exit 0
    }

    $environmentDirectory = Resolve-RoadLensPath $VenvPath
    if (Test-Path -LiteralPath $environmentDirectory) {
        $venvPython = Get-RoadLensVenvPython $VenvPath
        Write-Host "Using existing environment: $environmentDirectory"
    } else {
        Invoke-RoadLensCommand $pythonChoice.Executable ($pythonChoice.Prefix + @('-m', 'venv', $environmentDirectory))
        $venvPython = Get-RoadLensVenvPython $VenvPath
    }

    Push-Location -LiteralPath $script:RoadLensRoot
    try {
        Invoke-RoadLensCommand $venvPython @('-m', 'pip', 'install', '-r', 'requirements-build.lock')
        Invoke-RoadLensCommand $venvPython @('-m', 'pip', 'install', '-r', 'requirements-dev.lock')
        Invoke-RoadLensCommand $venvPython @('-m', 'pip', 'install', '--no-build-isolation', '--no-deps', '-e', '.')
        Invoke-RoadLensCommand $venvPython @('-m', 'pip', 'check')
        Invoke-RoadLensCommand $venvPython @('scripts\download_model.py')
        Push-Location -LiteralPath (Join-Path $script:RoadLensRoot 'frontend')
        try { Invoke-RoadLensCommand $nodeChoice.Npm @('ci') }
        finally { Pop-Location }
    } finally { Pop-Location }

    $quotedVenv = $VenvPath.Replace("'", "''")
    Write-Host ''
    Write-Host 'Setup complete. From the repository directory, run in separate PowerShell windows:'
    Write-Host ".\scripts\start-backend.ps1 -VenvPath '$quotedVenv'"
    Write-Host '.\scripts\start-frontend.ps1'
    Write-Host 'Open http://127.0.0.1:5173 and choose Guided showcase.'
    Write-Host "Verify: .\scripts\test.ps1 -VenvPath '$quotedVenv'"
    Write-Host 'Build:  .\scripts\build.ps1'
} catch {
    Write-Error "Setup failed: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
