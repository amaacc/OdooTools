# PowerShell Script to Schedule Daily Odoo to DuckDB Sync Task

$TaskName = "Odoo_DuckDB_Daily_Sync"
$WorkingDirectory = "c:\OdooDB"
$ScriptPath = "$WorkingDirectory\odoo_duckdb_sync.py"
$PythonPath = (Get-Command python).Source

if (-not $PythonPath) {
    $PythonPath = "python.exe"
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Creating Windows Daily Task: $TaskName " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`"" -WorkingDirectory $WorkingDirectory
$Trigger = New-ScheduledTaskTrigger -Daily -At 02:00AM
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily sync of Odoo 17 products catalog to DuckDB database" -User $env:USERNAME -Force
    Write-Host "Task '$TaskName' successfully registered! It will run daily at 02:00 AM." -ForegroundColor Green
} catch {
    Write-Host "Failed to register task. Make sure you run PowerShell as Administrator." -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
}
