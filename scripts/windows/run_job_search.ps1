# Uruchamia pipeline job search z logowaniem do logs/.
# Użycie: .\scripts\windows\run_job_search.ps1 -Sector data -Profile config\profiles\default.json

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Sector,

    [string]$Profile = "config\profiles\default.json",

    [string]$Source = "justjoin",

    [int]$MaxOffers = 30,

    [int]$MatchLimit = 20,

    [switch]$SyncVectors
)

$ErrorActionPreference = "Stop"

# Katalog repozytorium (scripts/windows -> dwa poziomy w górę)
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

# Logi
$LogsDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir | Out-Null
}
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogsDir "job_search_$Timestamp.log"

function Write-Log {
    param([string]$Message)
    $Line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    Write-Host $Line
}

Write-Log "Start job search — repo: $RepoRoot"
Write-Log "Parametry: Sector=$Sector Profile=$Profile Source=$Source MaxOffers=$MaxOffers MatchLimit=$MatchLimit SyncVectors=$($SyncVectors.IsPresent)"

# Wirtualne środowisko Python
$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    $Msg = @"
BŁĄD: Nie znaleziono środowiska wirtualnego Python.
Oczekiwana ścieżka: $VenvActivate

Utwórz venv w katalogu repozytorium:
  cd $RepoRoot
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
"@
    Write-Log $Msg
    Write-Host $Msg -ForegroundColor Red
    exit 1
}

Write-Log "Aktywacja venv: $VenvActivate"
. $VenvActivate

# Budowa komendy CLI
$CliArgs = @(
    "-m", "job_search.cli", "run",
    "--sector", $Sector,
    "--profile", $Profile,
    "--source", $Source,
    "--max-offers", $MaxOffers,
    "--match-limit", $MatchLimit
)

if (-not $SyncVectors) {
    $CliArgs += "--no-sync-vectors"
}

Write-Log "Uruchamianie: python $($CliArgs -join ' ')"

try {
    $Output = & python @CliArgs 2>&1
    $ExitCode = $LASTEXITCODE
    if ($null -eq $ExitCode) { $ExitCode = 0 }
    $Output | Tee-Object -FilePath $LogFile -Append
}
catch {
    Write-Log "BŁĄD wykonania: $_"
    Write-Host $_ -ForegroundColor Red
    exit 1
}

Write-Log "Zakończono z kodem wyjścia: $ExitCode"
Write-Host "Log zapisany: $LogFile" -ForegroundColor Cyan
exit $ExitCode
