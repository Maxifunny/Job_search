<#
.SYNOPSIS
    Konfiguruje Azure Automation: runbook + harmonogram RAZ NA DZIEN (free tier).

.PARAMETER ResourceGroupName
    Grupa zasobów z VM i Automation Account.

.PARAMETER VMName
    Nazwa maszyny wirtualnej z zainstalowanym Job Search.

.PARAMETER AutomationAccountName
    Nazwa konta Automation (utworzy jeśli brak).

.PARAMETER Location
    Region Azure (domyślnie westeurope — blisko Polski).

.PARAMETER ScheduleHour
    Godzina uruchomienia (0-23), domyślnie 8.

.EXAMPLE
    Connect-AzAccount
    ./infra/azure/Setup-DailySchedule.ps1 -ResourceGroupName job-search-rg -VMName job-search-vm
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$VMName,

    [string]$AutomationAccountName = "job-search-automation",

    [string]$Location = "westeurope",

    [int]$ScheduleHour = 8,

    [string]$RunUser = "azureuser",

    [string]$ScriptPath = "/home/azureuser/Job_search/infra/azure/run_daily_pipeline.sh"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "[azure-setup] $msg" -ForegroundColor Cyan }

if (-not (Get-Module -ListAvailable -Name Az.Automation)) {
    throw "Zainstaluj moduł Az: Install-Module Az -Scope CurrentUser"
}

Import-Module Az.Accounts, Az.Resources, Az.Automation, Az.Compute -ErrorAction Stop

$ctx = Get-AzContext
if (-not $ctx) {
    throw "Zaloguj się: Connect-AzAccount"
}

Write-Step "Resource Group: $ResourceGroupName"
$rg = Get-AzResourceGroup -Name $ResourceGroupName -ErrorAction SilentlyContinue
if (-not $rg) {
    Write-Step "Tworzenie grupy zasobów..."
    $rg = New-AzResourceGroup -Name $ResourceGroupName -Location $Location
}

$vm = Get-AzVM -ResourceGroupName $ResourceGroupName -Name $VMName -ErrorAction Stop
Write-Step "VM: $VMName ($($vm.Location))"

$automation = Get-AzAutomationAccount `
    -ResourceGroupName $ResourceGroupName `
    -Name $AutomationAccountName `
    -ErrorAction SilentlyContinue

if (-not $automation) {
    Write-Step "Tworzenie Automation Account: $AutomationAccountName"
    $automation = New-AzAutomationAccount `
        -ResourceGroupName $ResourceGroupName `
        -Name $AutomationAccountName `
        -Location $Location `
        -AssignSystemIdentity
    Start-Sleep -Seconds 15
}

$identityId = $automation.Identity.PrincipalId
if (-not $identityId) {
    throw "Automation Account nie ma tożsamości zarządzanej."
}

Write-Step "Przypisywanie roli Virtual Machine Contributor dla Automation..."
$scope = $vm.Id
New-AzRoleAssignment `
    -ObjectId $identityId `
    -RoleDefinitionName "Virtual Machine Contributor" `
    -Scope $scope `
    -ErrorAction SilentlyContinue | Out-Null

$runbookName = "Invoke-JobSearchDaily"
$runbookPath = Join-Path $PSScriptRoot "runbook/Invoke-DailyPipeline.ps1"
if (-not (Test-Path $runbookPath)) {
    throw "Brak pliku runbook: $runbookPath"
}

$existingRunbook = Get-AzAutomationRunbook `
    -ResourceGroupName $ResourceGroupName `
    -AutomationAccountName $AutomationAccountName `
    -Name $runbookName `
    -ErrorAction SilentlyContinue

if (-not $existingRunbook) {
    Write-Step "Import runbook: $runbookName"
    Import-AzAutomationRunbook `
        -ResourceGroupName $ResourceGroupName `
        -AutomationAccountName $AutomationAccountName `
        -Path $runbookPath `
        -Name $runbookName `
        -Type PowerShell `
        -Published
}
else {
    Write-Step "Aktualizacja runbook: $runbookName"
    Import-AzAutomationRunbook `
        -ResourceGroupName $ResourceGroupName `
        -AutomationAccountName $AutomationAccountName `
        -Path $runbookPath `
        -Name $runbookName `
        -Type PowerShell `
        -Published `
        -Force
}

Publish-AzAutomationRunbook `
    -ResourceGroupName $ResourceGroupName `
    -AutomationAccountName $AutomationAccountName `
    -Name $runbookName | Out-Null

Write-Step "Parametry runbook — ustawiane przy starcie harmonogramu"
$scheduleName = "job-search-daily"
$startTime = (Get-Date).Date.AddDays(1).AddHours($ScheduleHour)
if ($startTime -lt (Get-Date)) {
    $startTime = $startTime.AddDays(1)
}

$existingSchedule = Get-AzAutomationSchedule `
    -ResourceGroupName $ResourceGroupName `
    -AutomationAccountName $AutomationAccountName `
    -Name $scheduleName `
    -ErrorAction SilentlyContinue

if ($existingSchedule) {
    Write-Step "Usuwanie starego harmonogramu..."
    Unregister-AzAutomationScheduledRunbook `
        -ResourceGroupName $ResourceGroupName `
        -AutomationAccountName $AutomationAccountName `
        -RunbookName $runbookName `
        -ScheduleName $scheduleName `
        -ErrorAction SilentlyContinue
    Remove-AzAutomationSchedule `
        -ResourceGroupName $ResourceGroupName `
        -AutomationAccountName $AutomationAccountName `
        -Name $scheduleName `
        -Force
}

Write-Step "Harmonogram: codziennie o ${ScheduleHour}:00 (Europe/Warsaw w VM)"
$tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Central European Standard Time")
$offset = $tz.GetUtcOffset((Get-Date))
$utcHour = ($ScheduleHour - $offset.Hours + 24) % 24
$startTimeUtc = (Get-Date).ToUniversalTime().Date.AddDays(1).AddHours($utcHour)

$schedule = New-AzAutomationSchedule `
    -ResourceGroupName $ResourceGroupName `
    -AutomationAccountName $AutomationAccountName `
    -Name $scheduleName `
    -StartTime $startTimeUtc `
    -DayInterval 1 `
    -TimeZone "Central European Standard Time"

Register-AzAutomationScheduledRunbook `
    -ResourceGroupName $ResourceGroupName `
    -AutomationAccountName $AutomationAccountName `
    -RunbookName $runbookName `
    -ScheduleName $scheduleName `
    -Parameters @{
        ResourceGroupName = $ResourceGroupName
        VMName            = $VMName
        RunUser           = $RunUser
        ScriptPath        = $ScriptPath
    }

Write-Step ""
Write-Step "=== Gotowe ==="
Write-Step "Harmonogram: $scheduleName — raz dziennie o ${ScheduleHour}:00"
Write-Step "Runbook: $runbookName → Run Command na VM $VMName"
Write-Step ""
Write-Step "Test ręczny runbook (portal Azure → Automation → Runbooks → Start):"
Write-Step "  Lub na VM: ./infra/azure/run_daily_pipeline.sh"
Write-Step ""
Write-Step "Logi pipeline: ssh azureuser@<VM_IP> 'tail -100 ~/Job_search/logs/latest.log'"
