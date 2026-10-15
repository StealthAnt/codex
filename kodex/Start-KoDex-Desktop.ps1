$ErrorActionPreference = 'Stop'
$app = Join-Path $PSScriptRoot 'desktop_app.py'
if (-not (Test-Path -LiteralPath $app)) {
    throw "KoDex desktop files were not found at $PSScriptRoot."
}

$python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command 'python' -ErrorAction SilentlyContinue }
if (-not $python) {
    throw 'Python 3 was not found. Install Python for Windows and start KoDex again.'
}

$pythonw = Join-Path (Split-Path -Parent $python.Source) 'pythonw.exe'
if (Test-Path -LiteralPath $pythonw) {
    Start-Process -FilePath $pythonw -ArgumentList @("`"$app`"") -WorkingDirectory $PSScriptRoot
} else {
    Start-Process -FilePath $python.Source -ArgumentList @("`"$app`"") -WorkingDirectory $PSScriptRoot
}
