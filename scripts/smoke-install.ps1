<#
.SYNOPSIS
Copy release source into a new directory, then install and smoke-test it.
.DESCRIPTION
Uses the same computer and installed Python/Node executables. Existing environments,
media, model weights and node_modules are not copied. Nothing is deleted afterward.
#>
[CmdletBinding()]
param(
    [string]$Python,
    [string]$DestinationDirectory,
    [switch]$PrepareOnly,
    [switch]$InstallOnly
)
. (Join-Path $PSScriptRoot 'windows-common.ps1')

function Copy-ReleaseSource {
    param([string]$SourceDirectory, [string]$TargetDirectory)
    New-Item -ItemType Directory -Path $TargetDirectory -Force | Out-Null
    foreach ($entry in Get-ChildItem -LiteralPath $SourceDirectory -Force) {
        if ($entry.LinkType -in @('SymbolicLink', 'Junction')) { continue }
        if ($entry.PSIsContainer) {
            if ($entry.Name -in @('.git', 'node_modules', 'dist', 'dist-showcase', '__pycache__', '.pytest_cache',
                                 '.mypy_cache', '.ruff_cache', '.cache', 'coverage', 'htmlcov', 'test-results', 'playwright-report') -or
                $entry.Name -like '.venv*' -or $entry.Name -like '*.egg-info') { continue }
            Copy-ReleaseSource $entry.FullName (Join-Path $TargetDirectory $entry.Name)
        } elseif ($entry.Name -notlike '*.pyc' -and $entry.Name -notlike '*.pyo' -and
                  $entry.Name -notlike '*.tsbuildinfo' -and $entry.Name -notlike '*.log' -and
                  $entry.Name -notlike '.env*' -and $entry.Name -notlike '.coverage*') {
            Copy-Item -LiteralPath $entry.FullName -Destination (Join-Path $TargetDirectory $entry.Name)
        }
    }
}

try {
    if ($PrepareOnly -and $InstallOnly) { throw 'PrepareOnly and InstallOnly cannot be combined.' }
    if (-not $DestinationDirectory) {
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff')
        $DestinationDirectory = Join-Path 'data\release-smoke' "$stamp isolated checkout"
    }
    $destination = Resolve-RoadLensPath $DestinationDirectory
    foreach ($sourceName in @('.github', 'backend', 'frontend', 'scripts', 'docs', 'examples', 'third_party')) {
        $sourceRoot = Join-Path $script:RoadLensRoot $sourceName
        if ($destination.Equals($sourceRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
            $destination.StartsWith($sourceRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'The smoke destination cannot be inside a source directory being copied. Use data\release-smoke or a separate temporary directory.'
        }
    }
    if (Test-Path -LiteralPath $destination) {
        throw "The smoke destination already exists: $destination. Choose a new directory; existing files are never removed."
    }
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    foreach ($name in @('.github', 'backend', 'frontend', 'scripts', 'docs', 'examples', 'third_party')) {
        $sourceDirectory = Join-Path $script:RoadLensRoot $name
        if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
            Copy-ReleaseSource $sourceDirectory (Join-Path $destination $name)
        }
    }
    foreach ($name in @('.gitignore', '.gitattributes', 'LICENSE', 'README.md', 'CHANGELOG.md', 'pyproject.toml', 'requirements-dev.lock', 'requirements-build.lock')) {
        $sourceFile = Join-Path $script:RoadLensRoot $name
        if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
            Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $destination $name)
        }
    }
    Write-Host "Source-only smoke directory: $destination"
    if ($PrepareOnly) {
        Write-Host 'Source copy prepared. Dependencies, model, tests and builds were not run.'
        exit 0
    }

    $powershell = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $powershell)) { $powershell = Get-RoadLensCommand 'pwsh.exe' }
    $setupArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $destination 'scripts\setup.ps1'))
    if ($Python) { $setupArguments += @('-Python', $Python) }
    Invoke-RoadLensCommand $powershell $setupArguments
    $isolatedPython = Join-Path $destination '.venv\Scripts\python.exe'
    Invoke-RoadLensCommand $isolatedPython @((Join-Path $destination 'scripts\smoke_release.py'))
    if (-not $InstallOnly) {
        Invoke-RoadLensCommand $powershell @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $destination 'scripts\build.ps1'))
        Invoke-RoadLensCommand $powershell @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $destination 'scripts\build.ps1'), '-Showcase')
    }
    Write-Host 'Isolated installation and API/model/synthetic smoke passed.'
    if ($InstallOnly) { Write-Host 'Production builds were skipped by InstallOnly.' }
    else { Write-Host 'Full application and static showcase production builds passed.' }
    Write-Host 'This is an isolated local source copy, not an external clean-machine test. Artifacts were retained.'
} catch {
    Write-Error "Isolated smoke failed: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
