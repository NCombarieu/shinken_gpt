<#
.SYNOPSIS
  Run local checks on a Windows host and push the results to Shinken over SSH
  (passive checks). See doc/checks/ssh-passif.md.

.DESCRIPTION
  Uses the OpenSSH client shipped with Windows 10 / Server 2019 and later
  (ssh.exe). Each check is a PowerShell script block returning a hashtable
  @{ Rc = 0..3; Output = "..." }. Results are sent in send_nsca format:
  <host>TAB<service>TAB<rc>TAB<output>, one per line.

  Scheduled task (every 5 minutes, as SYSTEM or a dedicated account):
    schtasks /Create /TN "Shinken passive" /SC MINUTE /MO 5 /RU SYSTEM `
      /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\shinken-passive\shinken-passive-send.ps1"

.NOTES
  Configuration: C:\ProgramData\shinken-passive\client.psd1, for example
    @{
      Server     = 'shinken.example.lan'
      Port       = 2222
      HostName   = 'srv-win01'          # host_name of THIS machine in Shinken
      Key        = 'C:\ProgramData\shinken-passive\id_ed25519'
      KnownHosts = 'C:\ProgramData\shinken-passive\known_hosts'
    }
  The private key must only be readable by the account running the task
  (icacls), otherwise ssh.exe refuses it.
#>
param(
    [string]$ConfigFile = 'C:\ProgramData\shinken-passive\client.psd1'
)

$ErrorActionPreference = 'Stop'
$config = Import-PowerShellDataFile -Path $ConfigFile

function Test-Threshold([double]$Value, [double]$Warn, [double]$Crit) {
    if ($Value -ge $Crit) { return 2 }
    if ($Value -ge $Warn) { return 1 }
    return 0
}

# --- Checks: service_description => script block -------------------------
# Edit this list. Service names must exist in Shinken on this host and use
# the passive-service template.
$checks = [ordered]@{

    'Disk C' = {
        $d = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
        $used = [math]::Round(100 - ($d.FreeSpace / $d.Size * 100), 1)
        $rc = Test-Threshold $used 85 95
        @{ Rc = $rc; Output = "C: $used% used | used=$used%;85;95;0;100" }
    }

    'Memory' = {
        $os = Get-CimInstance Win32_OperatingSystem
        $used = [math]::Round(100 - ($os.FreePhysicalMemory / $os.TotalVisibleMemorySize * 100), 1)
        $rc = Test-Threshold $used 90 95
        @{ Rc = $rc; Output = "memory $used% used | used=$used%;90;95;0;100" }
    }

    'Auto services' = {
        $stopped = Get-CimInstance Win32_Service -Filter "StartMode='Auto' AND State<>'Running'" |
            Where-Object { $_.Name -notin @('sppsvc', 'gupdate', 'MapsBroker', 'edgeupdate') }
        if ($stopped) {
            @{ Rc = 2; Output = "stopped: " + (($stopped | ForEach-Object Name) -join ', ') }
        } else {
            @{ Rc = 0; Output = 'all automatic services are running' }
        }
    }

    # Custom script returning a Nagios exit code and printing one line:
    # 'Backup' = {
    #     $out = & 'C:\Scripts\check_backup.ps1' 2>&1 | Select-Object -First 1
    #     @{ Rc = $LASTEXITCODE; Output = "$out" }
    # }
}

# --- Run checks and build send_nsca lines ---------------------------------
$lines = foreach ($name in $checks.Keys) {
    try {
        $r = & $checks[$name]
        $rc = [int]$r.Rc
        if ($rc -lt 0 -or $rc -gt 3) { $rc = 3 }
        $out = [string]$r.Output
    } catch {
        $rc = 3
        $out = "UNKNOWN - check failed: $($_.Exception.Message)"
    }
    $out = ($out -replace "[`t`r`n]+", ' ').Trim()
    if (-not $out) { $out = '(no output)' }
    "{0}`t{1}`t{2}`t{3}" -f $config.HostName, $name, $rc, $out
}

# --- Push over SSH --------------------------------------------------------
$sshArgs = @(
    '-T', '-p', $config.Port, '-i', $config.Key,
    '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=15',
    '-o', "UserKnownHostsFile=$($config.KnownHosts)", '-o', 'StrictHostKeyChecking=yes',
    "shinken@$($config.Server)"
)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$lines | & ssh.exe @sshArgs
exit $LASTEXITCODE
