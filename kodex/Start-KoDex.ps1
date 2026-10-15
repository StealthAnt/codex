param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CodexArguments,
    [switch] $LocalModel
)

$ErrorActionPreference = 'Stop'
$env:CODEX_HOME = Join-Path $env:LOCALAPPDATA 'KoDex'
New-Item -ItemType Directory -Path $env:CODEX_HOME -Force | Out-Null

$binary = Get-Command 'codex.exe' -ErrorAction SilentlyContinue
if (-not $binary) {
    $binary = Get-Command 'codex' -ErrorAction SilentlyContinue
}
if (-not $binary) {
    throw @'
KoDex's launcher is ready, but the Codex engine is not installed yet.
This source repository builds on Windows through WSL2; see docs/install.md.
After building or installing the engine, make codex.exe available on PATH and run this launcher again.
'@
}

$arguments = @($CodexArguments)
if ($LocalModel -and $arguments -notcontains '--oss') {
    $arguments = @('--oss') + $arguments
}
& $binary.Source @arguments
exit $LASTEXITCODE
