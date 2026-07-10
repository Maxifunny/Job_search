# Rejestruje lub usuwa zadanie Windows Task Scheduler dla codziennego job search.
# Wymaga uruchomienia PowerShell jako Administrator (rejestracja zadania).
#
# Instalacja:
#   .\scripts\windows\register_scheduled_task.ps1 -Sector data -Profile config\profiles\default.json
#
# Odinstalowanie:
#   .\scripts\windows\register_scheduled_task.ps1 -Unregister

[CmdletBinding()]
param(
    [string]$TaskName = "JobSearch-Daily",

    [string]$Sector = "data",

    [string]$Profile = "config\profiles\default.json",

    [string]$Source = "justjoin",

    [int]$MaxOffers = 30,

    [int]$MatchLimit = 20,

    [switch]$SyncVectors,

    [int]$Hour = 8,

    [int]$Minute = 0,

    [switch]$RunAsUser,

    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

# Katalog repozytorium
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunScript = Join-Path $RepoRoot "scripts\windows\run_job_search.ps1"

if (-not (Test-Path $RunScript)) {
    Write-Host "BLAD: Nie znaleziono skryptu: $RunScript" -ForegroundColor Red
    exit 1
}

# Usuwanie zadania (nie wymaga uprawnien administratora, ale moze zawiesc bez nich)
if ($Unregister) {
    $Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $Existing) {
        Write-Host "Zadanie '$TaskName' nie istnieje - nic do usuniecia." -ForegroundColor Yellow
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Usunieto zadanie harmonogramu: $TaskName" -ForegroundColor Green
    exit 0
}

# Rejestracja wymaga uprawnien administratora
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $IsAdmin) {
    Write-Host "BLAD: Rejestracja zadania wymaga PowerShell uruchomionego jako Administrator." -ForegroundColor Red
    Write-Host ""
    Write-Host "Kliknij prawym na PowerShell -> Uruchom jako administrator, nastepnie:" -ForegroundColor Red
    Write-Host "  cd $RepoRoot"
    Write-Host "  .\scripts\windows\register_scheduled_task.ps1 -Sector $Sector -Profile $Profile"
    exit 1
}

# Argumenty dla run_job_search.ps1 (sciezki w cudzyslowie - spacje w katalogach)
$ActionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`" " +
    "-Sector `"$Sector`" -Profile `"$Profile`" -Source `"$Source`" " +
    "-MaxOffers $MaxOffers -MatchLimit $MatchLimit"
if ($SyncVectors) {
    $ActionArgs += " -SyncVectors"
}
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $ActionArgs `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date -Hour $Hour -Minute $Minute -Second 0)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

if ($RunAsUser) {
    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Write-Host "Tryb: uruchomienie jako uzytkownik $env:USERNAME (wymaga zalogowania)." -ForegroundColor Cyan
}
else {
    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
    Write-Host "Tryb: uruchomienie niezaleznie od sesji uzytkownika ($env:USERNAME)." -ForegroundColor Cyan
}

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $Existing) {
    Write-Host "Aktualizacja istniejacego zadania: $TaskName" -ForegroundColor Yellow
    Set-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal | Out-Null
}
else {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal | Out-Null
}

Write-Host ""
Write-Host "Zarejestrowano zadanie harmonogramu Windows." -ForegroundColor Green
Write-Host ""
Write-Host "  Nazwa:       $TaskName"
Write-Host "  Harmonogram: codziennie o $($Hour.ToString('00')):$($Minute.ToString('00'))"
Write-Host "  Skrypt:      $RunScript"
Write-Host "  Sektor:      $Sector"
Write-Host "  Profil:      $Profile"
Write-Host ""
Write-Host "Sprawdz w: Harmonogram zadan (taskschd.msc) -> Biblioteka harmonogramu zadan -> $TaskName"
Write-Host ""
Write-Host "Reczny test:"
Write-Host "  powershell.exe -ExecutionPolicy Bypass -File `"$RunScript`" -Sector $Sector -Profile $Profile"
Write-Host ""
Write-Host "Odinstalowanie:"
Write-Host "  .\scripts\windows\register_scheduled_task.ps1 -Unregister -TaskName $TaskName"
