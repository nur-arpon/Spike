<#
Refreshes the exploded-view copies on the website after a CAD re-export.
Run from anywhere:  powershell -File docs\tools\sync_exploded.ps1
Copies (never deletes) :
  shared-components\exploded-view\exploded-view.js  ->  docs\assets\components\
  preview_3d\exploded_v3_4g\{manifest.json,geometry.json,models\*} -> docs\assets\products\spike\
Pass -Content to use another export folder, e.g. -Content preview_3d\exploded_v3_4d
A GLB that was removed from the CAD stays in docs\assets\products\spike\models until you delete it by hand.
#>
param(
  [string]$Content = "preview_3d\exploded_v3_4g",
  [string]$Component = "..\shared-components\exploded-view\exploded-view.js"
)
$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$src  = Join-Path $repo $Content
$comp = Join-Path $repo $Component
$dstC = Join-Path $repo "docs\assets\components"
$dstP = Join-Path $repo "docs\assets\products\spike"
foreach ($p in @($comp, "$src\manifest.json", "$src\geometry.json", "$src\models")) {
  if (-not (Test-Path $p)) { throw "Missing: $p" }
}
New-Item -ItemType Directory -Force $dstC, "$dstP\models" | Out-Null
Copy-Item $comp $dstC -Force
Copy-Item "$src\manifest.json", "$src\geometry.json" $dstP -Force
Copy-Item "$src\models\*" "$dstP\models" -Force
$n = (Get-ChildItem "$dstP\models").Count
$mb = [math]::Round(((Get-ChildItem "$dstP\models" | Measure-Object Length -Sum).Sum / 1MB), 2)
Write-Host "Done. component + manifest + geometry + $n models ($mb MB) copied into docs\assets."
