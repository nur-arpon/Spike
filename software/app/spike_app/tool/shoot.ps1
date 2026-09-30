# Development screenshots of the desktop app: opens the release build at a page, sizes the window's
# CLIENT area to each size, captures only that window (tool/capture_window.ps1), closes it again.
# The built-in brain runs from a scratch data folder with its speaker and microphone off.
#   .\tool\shoot.ps1 -Route /home -Sizes 1280x800,1366x768,1920x1080 -OutDir <folder> [-Prefix home]
param([string]$Route = '/home', [string[]]$Sizes = @('1366x768'), [Parameter(Mandatory)][string]$OutDir,
      [string]$Prefix = '', [int]$Wait = 14, [string]$Theme = '')
$ErrorActionPreference = 'Stop'
$Sizes = ($Sizes -join ',').Split(',') | Where-Object { $_ }
$app = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$scratch = Join-Path $env:TEMP 'spike_shoot'
$home_ = Join-Path $scratch 'brain_home'
New-Item -ItemType Directory -Force $home_, $OutDir | Out-Null
[IO.File]::WriteAllText((Join-Path $home_ 'spike_settings.toml'), "[audio]`noutput = `"none`"`n[life]`ngreet_on_start = false`n")  # no BOM
$env:SPIKE_BRAIN_PYTHON = Join-Path $app '..\..\laptop\.venv-desktop\Scripts\python.exe' | Resolve-Path
$env:SPIKE_BRAIN_DIR = Join-Path $app '..\..\laptop' | Resolve-Path
$env:SPIKE_BRAIN_HOME = $home_
$exe = Join-Path $app 'build\windows\x64\runner\Release\spike_app.exe'
# one copy at a time (the app hands a second launch to the first one)
for ($i = 0; $i -lt 20 -and (Get-Process spike_app -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
$p = Start-Process $exe -ArgumentList "--route=$Route" -PassThru
try {
  Start-Sleep $Wait
  if ($p.HasExited) { throw 'the app exited' }
  foreach ($s in $Sizes) {
    $w, $h = $s.Split('x') | ForEach-Object { [int]$_ }
    $name = if ($Prefix) { "$Prefix`_$s.png" } else { "$($Route.Trim('/'))_$s.png" }
    & (Join-Path $app 'tool\capture_window.ps1') -ProcessId $p.Id -Out (Join-Path $OutDir $name) -Width $w -Height $h
  }
} finally {
  Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
  Start-Sleep 3
}
