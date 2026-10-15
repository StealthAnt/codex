param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CodexArguments,
    [switch] $LocalModel
)

$ErrorActionPreference = 'Stop'
$env:CODEX_HOME = Join-Path $env:LOCALAPPDATA 'KoDex'
New-Item -ItemType Directory -Path $env:CODEX_HOME -Force | Out-Null

# Register the local bridge once, without replacing the user's KoDex config or
# any existing MCP server entries.
$python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command 'python' -ErrorAction SilentlyContinue }
$bridge = Join-Path $PSScriptRoot 'assistant_bridge.py'
$configPath = Join-Path $env:CODEX_HOME 'config.toml'
if ($python -and (Test-Path -LiteralPath $bridge)) {
    $configText = if (Test-Path -LiteralPath $configPath) { Get-Content -LiteralPath $configPath -Raw } else { '' }
    if ($configText -notmatch '(?m)^\[mcp_servers\.kodex_local\]\s*$') {
        $pythonToml = ConvertTo-Json -InputObject $python.Source -Compress
        $bridgeToml = ConvertTo-Json -InputObject $bridge -Compress
        $entry = @"

[mcp_servers.kodex_local]
command = $pythonToml
args = [$bridgeToml]
startup_timeout_sec = 10
default_tools_approval_mode = "prompt"
"@
        Add-Content -LiteralPath $configPath -Value $entry -Encoding utf8
    }
}

$binary = Get-Command 'codex.exe' -ErrorAction SilentlyContinue
if (-not $binary) {
    $binary = Get-Command 'codex' -ErrorAction SilentlyContinue
}

if (-not $python) {
    Write-Warning 'Python was not found, so KoDex app integrations and local task memory are not available. Install Python 3 and relaunch KoDex.'
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
