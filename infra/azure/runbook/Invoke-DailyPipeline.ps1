<#
.SYNOPSIS
    Uruchamia dzienny pipeline Job Search na Azure VM (start → run → stop).

.DESCRIPTION
    Runbook dla Azure Automation — wywoływany raz dziennie przez harmonogram.
    Domyślnie: włącza VM (jeśli wyłączona), czeka na agenta, uruchamia pipeline,
    następnie wyłącza VM (deallocate) — oszczędza kredyty studenckie / free tier.

    Wymaga: Automation Account z tożsamością zarządzaną i rolą VM Contributor.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$VMName,

    [string]$RunUser = "azureuser",

    [string]$ScriptPath = "/home/azureuser/Job_search/infra/azure/run_daily_pipeline.sh",

    [bool]$StopVMAfterRun = $true,

    [bool]$StartVMIfStopped = $true,

    [int]$AgentReadyWaitSeconds = 90
)

$ErrorActionPreference = "Stop"

function Get-VmPowerState {
    param([string]$Rg, [string]$Name)
    $vmStatus = Get-AzVM -ResourceGroupName $Rg -Name $Name -Status
    ($vmStatus.Statuses | Where-Object { $_.Code -like "PowerState/*" }).Code
}

function Wait-VmRunning {
    param([string]$Rg, [string]$Name, [int]$TimeoutSeconds = 300)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $state = Get-VmPowerState -Rg $Rg -Name $Name
        if ($state -eq "PowerState/running") {
            return
        }
        if ((Get-Date) -gt $deadline) {
            throw "VM $Name nie przeszła w stan running w ciągu ${TimeoutSeconds}s (stan: $state)."
        }
        Start-Sleep -Seconds 15
    } while ($true)
}

Write-Output "Job Search daily pipeline — RG=$ResourceGroupName VM=$VMName"
Write-Output "StartVMIfStopped=$StartVMIfStopped StopVMAfterRun=$StopVMAfterRun"

if (-not (Get-Module -ListAvailable -Name Az.Compute)) {
    throw "Zainstaluj moduł Az: Install-Module Az -Scope CurrentUser"
}

Import-Module Az.Accounts, Az.Compute -ErrorAction Stop

$vmWasStartedByRunbook = $false
$initialState = Get-VmPowerState -Rg $ResourceGroupName -Name $VMName
Write-Output "Stan VM przed runbook: $initialState"

try {
    if ($StartVMIfStopped -and $initialState -ne "PowerState/running") {
        Write-Output "Uruchamianie VM (deallocate → running)..."
        Start-AzVM -ResourceGroupName $ResourceGroupName -Name $VMName | Out-Null
        $vmWasStartedByRunbook = $true
        Wait-VmRunning -Rg $ResourceGroupName -Name $VMName
        Write-Output "Czekam ${AgentReadyWaitSeconds}s na agenta VM (Run Command)..."
        Start-Sleep -Seconds $AgentReadyWaitSeconds
    }

    $command = "sudo -u $RunUser bash -lc '$ScriptPath'"

    Write-Output "Run Command: $ScriptPath"
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
}
finally {
    if ($StopVMAfterRun) {
        $state = Get-VmPowerState -Rg $ResourceGroupName -Name $VMName
        if ($state -eq "PowerState/running") {
            Write-Output "Wyłączanie VM (deallocate — brak opłat za compute)..."
            Stop-AzVM -ResourceGroupName $ResourceGroupName -Name $VMName -Force -SkipShutdown | Out-Null
            Write-Output "VM wyłączona."
        }
    }
}
