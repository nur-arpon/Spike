# Builds Spike's LIGHT brain for the Windows desktop app (software/app/DESIGN.md "Desktop").
#   .\desktop_build\build_brain.ps1            (from software/laptop, or anywhere)
# Needs software/laptop/.venv-desktop (CPU-only; see desktop_build/requirements-desktop.txt).
# Output: desktop_build/dist/brain/  = spike_brain.exe, _internal/, models/, THIRD_PARTY_NOTICES.txt
$ErrorActionPreference = 'Stop'
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$laptop = Split-Path -Parent $here
$py     = Join-Path $laptop '.venv-desktop\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "missing $py - create it: python -m venv .venv-desktop; pip install -r desktop_build\requirements-desktop.txt" }

$dist = Join-Path $here 'dist'
$work = Join-Path $here 'build'
& $py -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $here 'spike_brain_desktop.spec')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

# the models the light brain uses (read-only, next to the exe): wake words, speech recognition, voice activity
$out    = Join-Path $dist 'brain'
$models = Join-Path $out 'models'
$src    = Join-Path $laptop 'models'
New-Item -ItemType Directory -Force (Join-Path $models 'vosk'), (Join-Path $models 'whisper'), (Join-Path $models 'openwakeword') | Out-Null
robocopy (Join-Path $src 'vosk\vosk-model-small-en-us-0.15') (Join-Path $models 'vosk\vosk-model-small-en-us-0.15') /E /NFL /NDL /NJH /NJS | Out-Null
robocopy (Join-Path $src 'whisper\base.en') (Join-Path $models 'whisper\base.en') /E /XD .cache /NFL /NDL /NJH /NJS | Out-Null
Copy-Item (Join-Path $src 'openwakeword\silero_vad.onnx') (Join-Path $models 'openwakeword\silero_vad.onnx') -Force
Copy-Item (Join-Path $here 'THIRD_PARTY_NOTICES.txt') $out -Force

$mb = [math]::Round(((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "brain built: $out ($mb MB)"
