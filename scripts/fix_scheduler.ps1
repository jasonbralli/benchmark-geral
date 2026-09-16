[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

$taskNames = @(
    'Benchmark Geral - Diario',
    'Benchmark Geral - Iniciar'
)

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = Join-Path $baseDir 'scripts/run_push_github.bat'
$workingDir = $baseDir

if (-not (Test-Path $batPath)) {
    Write-Output "ERRO: .bat nao encontrado em: $batPath"
    exit 1
}

# Remove tarefas antigas se existirem
foreach ($name in $taskNames) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        try {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction Stop
            Write-Output "Removida tarefa antiga: $name"
        } catch {
            Write-Output "AVISO: nao foi possivel remover $name : $_"
        }
    } else {
        Write-Output "Tarefa inexistente (ok): $name"
    }
}

# Cria tarefa Diario: diaria as 08:00
try {
    $dailyTrigger = New-ScheduledTaskTrigger -Daily -At '08:00'
    $dailyTrigger.Enabled = $true

    $action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $workingDir

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5)

    Register-ScheduledTask -TaskName 'Benchmark Geral - Diario' -Action $action -Trigger $dailyTrigger -Settings $settings | Out-Null
    Write-Output "Criada tarefa: Benchmark Geral - Diario"
} catch {
    Write-Output "ERRO ao criar tarefa Diario: $_"
    exit 1
}

# Cria tarefa Iniciar: na abertura de sessao
try {
    $logonTrigger = New-ScheduledTaskTrigger -AtLogOn
    $logonTrigger.Enabled = $true

    $action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $workingDir

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5)

    Register-ScheduledTask -TaskName 'Benchmark Geral - Iniciar' -Action $action -Trigger $logonTrigger -Settings $settings | Out-Null
    Write-Output "Criada tarefa: Benchmark Geral - Iniciar"
} catch {
    Write-Output "ERRO ao criar tarefa Iniciar: $_"
    exit 1
}

Write-Output ''
Write-Output 'Resumo:'
foreach ($name in $taskNames) {
    $info = Get-ScheduledTaskInfo -TaskName $name
    $state = (Get-ScheduledTask -TaskName $name).State
    Write-Output "$name | State=$state | LastRun=$($info.LastRunTime) | NextRun=$($info.NextRunTime)"
}