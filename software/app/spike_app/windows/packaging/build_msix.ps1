# Builds the Windows package (.msix) of the desktop app, with the built-in brain inside.
# (software/app/DESIGN.md "Desktop", software/app/store/PARTNER_CENTER_CHECKLIST.md)
#
#   .\windows\packaging\build_msix.ps1                 Store package (identity from identity.json)
#   .\windows\packaging\build_msix.ps1 -LocalTest      test package for THIS PC (Developer Mode on), installed from
#                                                      its staged folder: Add-AppxPackage -Register ..\local_install\stage\AppxManifest.xml
#   -SkipFlutter / -SkipBrain                          reuse the last builds
#   -CertPfx <file> -CertPassword <pw>                 sign it (e.g. a self-signed test certificate)
#
# Tools: Flutter (D:\flutter), the Windows SDK (makeappx, makepri, signtool), nuget.exe for the plugin builds
# (software/app/tools/nuget), and the brain build venv (software/laptop/.venv-desktop).
param([switch]$LocalTest, [switch]$SkipFlutter, [switch]$SkipBrain, [string]$CertPfx, [string]$CertPassword)
$ErrorActionPreference = 'Stop'

$pack    = Split-Path -Parent $MyInvocation.MyCommand.Path          # spike_app/windows/packaging
$app     = Split-Path -Parent (Split-Path -Parent $pack)             # spike_app
$laptop  = Join-Path $app '..\..\laptop' | Resolve-Path
$flutter = 'D:\flutter\bin\flutter.bat'
$sdkBin  = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Directory | Where-Object { Test-Path "$($_.FullName)\x64\makeappx.exe" } |
           Sort-Object Name -Descending | Select-Object -First 1 | ForEach-Object { "$($_.FullName)\x64" }
if (-not $sdkBin) { throw 'Windows SDK (makeappx.exe) not found' }

# ---- names, identity, version: each from its one place
$brand    = Get-Content (Join-Path $app 'brand.json') -Raw | ConvertFrom-Json
$identity = Get-Content (Join-Path $pack 'identity.json') -Raw | ConvertFrom-Json
$pubspec  = Get-Content (Join-Path $app 'pubspec.yaml') -Raw
if ($pubspec -notmatch '(?m)^version:\s*(\d+)\.(\d+)\.(\d+)\+(\d+)') { throw 'pubspec.yaml needs version: MAJOR.MINOR.PATCH+BUILD' }
$version  = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"      # the Store wants the 4th part = 0 (VERSIONING.md)
$publisher = if ($LocalTest) { $identity.localTestPublisher } else { $identity.publisher }
$pkgName   = if ($LocalTest) { $identity.localTestPackageName } else { $identity.packageName }
if (-not $LocalTest -and $identity.packageName -like 'PLACEHOLDER*') {
  Write-Warning 'identity.json still has the placeholders: fill them from Partner Center before uploading.'
}
function Esc([string]$s) { [Security.SecurityElement]::Escape($s) }

# ---- 1. the Flutter app (release)
if (-not $SkipFlutter) {
  $env:PATH = "$(Join-Path $app '..\tools\nuget');$env:PATH"
  Push-Location $app
  & D:\flutter\bin\dart.bat run tool/sync_brand.dart
  & $flutter build windows --release
  if ($LASTEXITCODE -ne 0) { throw 'flutter build windows failed' }
  Pop-Location
}
# ---- 2. the built-in brain (PyInstaller, CPU only)
if (-not $SkipBrain) {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $laptop 'desktop_build\build_brain.ps1')
  if ($LASTEXITCODE -ne 0) { throw 'brain build failed' }
}

# ---- 3. stage the package folder
$out   = Join-Path $app 'build\msix'
# The local test package is registered FROM its staged folder, so that folder is the installed app: it lives
# outside build\ (flutter clean must not delete an installed app) in software\app\local_install\stage.
$stage = if ($LocalTest) { Join-Path $app '..\local_install\stage' } else { Join-Path $out 'stage' }
New-Item -ItemType Directory -Force (Split-Path $stage) | Out-Null
$stage = Join-Path (Resolve-Path (Split-Path $stage)).Path 'stage'
if ($LocalTest -and (Get-Process spike_app, spike_brain -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($stage + '\') })) {
  throw 'Spike is running from the local test install: quit it (tray > Quit) before rebuilding it.'
}
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }          # our own build output only
New-Item -ItemType Directory -Force $stage | Out-Null
robocopy (Join-Path $app 'build\windows\x64\runner\Release') $stage /E /NFL /NDL /NJH /NJS | Out-Null
robocopy (Join-Path $laptop 'desktop_build\dist\brain') (Join-Path $stage 'brain') /E /NFL /NDL /NJH /NJS | Out-Null
robocopy (Join-Path $pack 'Assets') (Join-Path $stage 'Assets') /E /NFL /NDL /NJH /NJS | Out-Null
# the Visual C++ runtime next to the app (app-local, as Microsoft's redistributable licence allows), so the
# package needs no separate VCLibs framework
$crt = Get-ChildItem 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Redist\MSVC' -Directory |
       Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'x64\Microsoft.VC143.CRT' } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $crt) { throw 'Visual C++ redistributable folder (Microsoft.VC143.CRT) not found' }
Copy-Item "$crt\*.dll" $stage
if (-not (Test-Path (Join-Path $stage 'brain\spike_brain.exe'))) { throw 'the brain is missing from the package' }

# ---- 4. the manifest
$desc = "$($brand.productName), $($brand.tagline)."
$m = Get-Content (Join-Path $pack 'AppxManifest.template.xml') -Raw
$m = $m.Replace('{{PACKAGE_NAME}}', (Esc $pkgName)).Replace('{{PUBLISHER}}', (Esc $publisher))
$m = $m.Replace('{{VERSION}}', $version).Replace('{{STORE_NAME}}', (Esc $brand.storeName))
$m = $m.Replace('{{PUBLISHER_DISPLAY_NAME}}', (Esc $brand.publisherDisplayName)).Replace('{{START_MENU_NAME}}', (Esc $brand.startMenuName))
$m = $m.Replace('{{DESCRIPTION}}', (Esc $desc))
if ($m -match '\{\{[A-Z_]+\}\}') { throw "manifest token left: $($Matches[0])" }
[IO.File]::WriteAllText((Join-Path $stage 'AppxManifest.xml'), $m, (New-Object Text.UTF8Encoding $false))

# ---- 5. resources.pri (the logo scale / target-size variants), indexed from the logos only
$pri = Join-Path $out 'pri'
if (Test-Path $pri) { Remove-Item $pri -Recurse -Force }
New-Item -ItemType Directory -Force $pri | Out-Null
robocopy (Join-Path $pack 'Assets') (Join-Path $pri 'Assets') /E /NFL /NDL /NJH /NJS | Out-Null
Copy-Item (Join-Path $stage 'AppxManifest.xml') $pri
& "$sdkBin\makepri.exe" createconfig /cf (Join-Path $pri 'priconfig.xml') /dq en-US /pv 10.0.0 /o | Out-Null
& "$sdkBin\makepri.exe" new /pr $pri /cf (Join-Path $pri 'priconfig.xml') /mn (Join-Path $pri 'AppxManifest.xml') /of (Join-Path $stage 'resources.pri') /o | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'makepri failed' }

# ---- 6. pack (and sign if asked)
$displayVersion = $version -replace '\.0$', ''   # file name uses 1.0.0; the manifest keeps the 4-part 1.0.0.0 the Store requires
$name = "Spike_$($displayVersion)_x64$(if ($LocalTest) { '_localtest' })"
$msix = Join-Path $out "$name.msix"
& "$sdkBin\makeappx.exe" pack /d $stage /p $msix /o | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'makeappx failed' }
if ($CertPfx) {
  & "$sdkBin\signtool.exe" sign /fd SHA256 /f $CertPfx /p $CertPassword $msix
  if ($LASTEXITCODE -ne 0) { throw 'signing failed' }
}
$mb = [math]::Round((Get-Item $msix).Length / 1MB, 1)
$inst = [math]::Round(((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "package: $msix ($mb MB download, $inst MB installed), version $version, publisher $publisher"
