<#
.SYNOPSIS
    Uruchamia dzienny pipeline Job Search na Azure VM (Run Command).

.DESCRIPTION
    Runbook dla Azure Automation — wywoływany raz dziennie przez harmonogram.
    Wymaga: Automation Account z tożsamością zarządzaną i rolą VM Contributor.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$VMName,

    [string]$RunUser = "azureuser",

    [string]$ScriptPath = "/home/azureuser/Job_search/infra/azure/run_daily_pipeline.sh"
)

$ErrorActionPreference = "Stop"

Write-Output "Job Search daily pipeline — RG=$ResourceGroupName VM=$VMName"

if (-not (Get-Module -ListAvailable -Name Az.Compute)) {
    throw "Zainstaluj moduł Az: Install-Module Az -Scope CurrentUser"
}

Import-Module Az.Accounts, Az.Compute -ErrorAction Stop

$command = "sudo -u $RunUser bash -lc '$ScriptPath'"

$result = Invoke-AzVMRunCommand `
    -ResourceGroupName $ResourceGroupName `
    -VMName $VMName `
    -CommandId RunShellScript `
    -ScriptString $command

$stdout = $result.Value | Where-Object { $_.Code -eq "stdout" } | Select-Object -ExpandProperty Message
$stderr = $result.Value | Where-Object { $_.Code -eq "stderr" } | Select-Object -ExpandProperty Message

Write-Output "=== stdout ==="
Write-Output $stdout
if ($stderr) {
    Write-Output "=== stderr ==="
    Write-Output $stderr
}

Write-Output "Run Command zakończony."
