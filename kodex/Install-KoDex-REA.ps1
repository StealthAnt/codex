$ErrorActionPreference = 'Stop'
$KodexDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Node = Get-Command node -ErrorAction SilentlyContinue
$Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $Node -or -not $Npm) {
    throw 'Install Node.js 22.19+, 24.11+, or 26+ with npm before installing REA.'
}
$Version = (& $Node.Source --version).TrimStart('v').Split('.')
$Major = [int]$Version[0]
$Minor = [int]$Version[1]
$Supported = ($Major -eq 22 -and $Minor -ge 19) -or ($Major -eq 24 -and $Minor -ge 11) -or ($Major -ge 26)
if (-not $Supported) {
    throw "Node.js version is not supported by REA: $($Node.Source)"
}
& $Npm.Source ci --prefix (Join-Path $KodexDir 'rea') --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw "REA dependency install failed with exit code $LASTEXITCODE." }
Write-Host 'The pinned official REA package is ready to bundle with KoDex.'
