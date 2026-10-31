<#
  Template of a custom NSClient++ check (doc/checks/nrpe.md).
  Copy to C:\Program Files\NSClient++\scripts\ and declare it in
  nsclient.ini under [/settings/external scripts/wrapped scripts].

  Contract with Shinken: print ONE line "<STATE> - text | perfdata" and exit
  with 0 (OK), 1 (WARNING), 2 (CRITICAL) or 3 (UNKNOWN).
  This example checks the age of the newest file of a backup folder.
#>
param(
    [string]$Path = 'D:\Backups',
    [double]$MaxAgeHours = 26
)

try {
    $newest = Get-ChildItem -Path $Path -File -ErrorAction Stop |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $newest) {
        Write-Output "CRITICAL - no backup file in $Path"
        exit 2
    }
    $age = [math]::Round(((Get-Date) - $newest.LastWriteTime).TotalHours, 1)
    $perf = "age=${age}h;$MaxAgeHours;$($MaxAgeHours * 2);0"
    if ($age -gt $MaxAgeHours * 2) {
        Write-Output "CRITICAL - last backup $($newest.Name) is $age h old | $perf"; exit 2
    }
    if ($age -gt $MaxAgeHours) {
        Write-Output "WARNING - last backup $($newest.Name) is $age h old | $perf"; exit 1
    }
    Write-Output "OK - last backup $($newest.Name) is $age h old | $perf"
    exit 0
} catch {
    Write-Output "UNKNOWN - $($_.Exception.Message)"
    exit 3
}
