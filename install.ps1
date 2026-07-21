# iglegais one-liner (Windows PowerShell):
#   irm https://raw.githubusercontent.com/Cintu07/iglegais/main/install.ps1 | iex
# or with flags:
#   & ([scriptblock]::Create((irm ...))) -Yes -Key "csk-..."

param(
    [string]$Key = "",
    [switch]$Yes,
    [switch]$NoMcp,
    [switch]$SkipHelix
)

$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "  iglegais installer"
Write-Host ""

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Error "Python 3.10+ required. Install from https://python.org then re-run."
}

Write-Host "  · pip install iglegais"
& $py.Source -m pip install -U iglegais

$setupArgs = @()
if ($Key) { $setupArgs += @("--key", $Key) }
if ($Yes) { $setupArgs += "-y" }
if ($NoMcp) { $setupArgs += "--no-mcp" }
if ($SkipHelix) { $setupArgs += "--skip-helix" }

Write-Host "  · running iglegais-setup"
& $py.Source -m iglegais.setup_cmd @setupArgs
