Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:RoadLensRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

function Resolve-RoadLensPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $script:RoadLensRoot $Path))
}

function Invoke-RoadLensCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @()
    )
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

function Get-RoadLensCommand {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) { throw "Required command '$Name' was not found. Install it and reopen PowerShell." }
    return $command.Source
}

function Assert-RoadLensPython {
    param([string]$Executable, [string[]]$Prefix = @())
    $output = & $Executable @Prefix -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Could not run Python: $Executable" }
    $pythonVersion = [version]([string]($output | Select-Object -Last 1))
    if ($pythonVersion -lt [version]'3.12' -or $pythonVersion -ge [version]'3.14') {
        throw "Python 3.12-3.13 is required by the release dependency lock; found $pythonVersion."
    }
    return $pythonVersion
}

function Find-RoadLensPython {
    param([string]$Python)
    if ($Python) {
        $executable = Get-RoadLensCommand $Python
        $version = Assert-RoadLensPython $executable
        return @{ Executable = $executable; Prefix = @(); Version = $version }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        foreach ($minor in @('3.13', '3.12')) {
            try {
                $version = Assert-RoadLensPython $launcher.Source @("-$minor")
                return @{ Executable = $launcher.Source; Prefix = @("-$minor"); Version = $version }
            } catch { }
        }
    }
    $executable = Get-RoadLensCommand 'python.exe'
    $version = Assert-RoadLensPython $executable
    return @{ Executable = $executable; Prefix = @(); Version = $version }
}

function Get-RoadLensNode {
    $node = Get-RoadLensCommand 'node.exe'
    $output = & $node --version
    if ($LASTEXITCODE -ne 0) { throw 'Node.js could not run.' }
    $nodeVersion = [version](([string]$output).Trim().TrimStart('v'))
    if ($nodeVersion -lt [version]'22.12.0') {
        throw "Node.js 22.12 or newer is required; found $nodeVersion."
    }
    $npm = Get-RoadLensCommand 'npm.cmd'
    $npmVersion = & $npm --version
    if ($LASTEXITCODE -ne 0) { throw 'npm could not run. Install Node.js with npm and reopen PowerShell.' }
    return @{ Node = $node; Npm = $npm; Version = $nodeVersion; NpmVersion = $npmVersion }
}

function Get-RoadLensVenvPython {
    param([string]$VenvPath = '.venv')
    $directory = Resolve-RoadLensPath $VenvPath
    $executable = Join-Path $directory 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath (Join-Path $directory 'pyvenv.cfg') -PathType Leaf) -or
        -not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "No Python environment at '$directory'. Run .\scripts\setup.ps1 -VenvPath '$VenvPath' first."
    }
    $null = Assert-RoadLensPython $executable
    return $executable
}

function Get-RoadLensFrontend {
    $directory = Join-Path $script:RoadLensRoot 'frontend'
    if (-not (Test-Path -LiteralPath (Join-Path $directory 'node_modules') -PathType Container)) {
        throw 'Frontend dependencies are missing. Run .\scripts\setup.ps1 first.'
    }
    return $directory
}
