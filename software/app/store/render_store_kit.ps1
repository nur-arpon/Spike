# Renders the Store kit (store/*.md, store/privacy-policy.html) from store/templates/ with the names in
# spike_app/brand.json and the version in spike_app/pubspec.yaml (software/app/RENAMING.md).
#   powershell -File software/app/store/render_store_kit.ps1
$ErrorActionPreference = 'Stop'
$store = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Join-Path (Split-Path -Parent $store) 'spike_app'
$brand = Get-Content (Join-Path $app 'brand.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$pubspec = Get-Content (Join-Path $app 'pubspec.yaml') -Raw
if ($pubspec -notmatch '(?m)^version:\s*(\d+\.\d+\.\d+)\+\d+') { throw 'pubspec.yaml needs version: MAJOR.MINOR.PATCH+BUILD' }
$version = $Matches[1]

function Or-Todo([string]$v, [string]$what) { if ([string]::IsNullOrWhiteSpace($v)) { "[TO FILL: $what in spike_app/brand.json]" } else { $v } }
$tokens = [ordered]@{
  '{{STORE_NAME}}'    = $brand.storeName
  '{{PRODUCT}}'       = $brand.productName
  '{{TAGLINE}}'       = $brand.tagline
  '{{PUBLISHER}}'     = $brand.publisherDisplayName
  '{{COPYRIGHT}}'     = $brand.copyrightHolder
  '{{SUPPORT_EMAIL}}' = Or-Todo $brand.supportEmail 'supportEmail'
  '{{WEBSITE}}'       = Or-Todo $brand.websiteUrl 'websiteUrl'
  '{{PRIVACY_URL}}'   = Or-Todo $brand.privacyPolicyUrl 'privacyPolicyUrl'
  '{{VERSION}}'       = $version
  '{{YEAR}}'          = (Get-Date).Year.ToString()
  '{{DATE}}'          = (Get-Date).ToString('d MMMM yyyy', [Globalization.CultureInfo]::InvariantCulture)
}
$utf8 = New-Object Text.UTF8Encoding($false)   # no BOM
foreach ($t in Get-ChildItem (Join-Path $store 'templates') -File) {
  $s = [IO.File]::ReadAllText($t.FullName, $utf8)
  foreach ($k in $tokens.Keys) {
    $v = [string]$tokens[$k]
    if ($t.Extension -eq '.html') { $v = [Net.WebUtility]::HtmlEncode($v) }
    $s = $s.Replace($k, $v)
  }
  if ($s -match '\{\{[A-Z_]+\}\}') { throw "$($t.Name): unknown token $($Matches[0])" }
  [IO.File]::WriteAllText((Join-Path $store $t.Name), $s, $utf8)
  Write-Host "store/$($t.Name)"
}
