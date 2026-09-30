# Captures ONE app window's client area (no title bar, no taskbar, nothing else on screen) to a PNG,
# with PrintWindow(PW_RENDERFULLCONTENT) so GPU-drawn Flutter/WebView2 content is included.
# Used for the Store screenshots (software/app/store/screenshots): only our own window is read.
#   .\tool\capture_window.ps1 -ProcessId 1234 -Out shot.png [-Width 1920 -Height 1080]
param([Parameter(Mandatory)][int]$ProcessId, [Parameter(Mandatory)][string]$Out, [int]$Width = 0, [int]$Height = 0)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
"@
[W]::SetProcessDPIAware() | Out-Null
$h = (Get-Process -Id $ProcessId).MainWindowHandle
if ($h -eq [IntPtr]::Zero) { throw "process $ProcessId has no visible window" }
if ($Width -gt 0) {
  [W]::ShowWindow($h, 9) | Out-Null   # SW_RESTORE: a maximized window cannot be sized
  Start-Sleep -Milliseconds 600
  for ($i = 0; $i -lt 4; $i++) {
    # size the window so its CLIENT area is exactly Width x Height (the frame measured each time)
    $wr = New-Object W+RECT; $cr = New-Object W+RECT
    [W]::GetWindowRect($h, [ref]$wr) | Out-Null; [W]::GetClientRect($h, [ref]$cr) | Out-Null
    if ($cr.R -eq $Width -and $cr.B -eq $Height) { break }
    $fw = ($wr.R - $wr.L) - $cr.R; $fh = ($wr.B - $wr.T) - $cr.B
    [W]::SetWindowPos($h, [IntPtr]::Zero, 24, 24, $Width + $fw, $Height + $fh, 0x0004) | Out-Null  # NOZORDER
    Start-Sleep -Milliseconds 1200
  }
  Start-Sleep -Milliseconds 1500
}
$wr = New-Object W+RECT; [W]::GetWindowRect($h, [ref]$wr) | Out-Null
$cr = New-Object W+RECT; [W]::GetClientRect($h, [ref]$cr) | Out-Null
$p = New-Object W+POINT; [W]::ClientToScreen($h, [ref]$p) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ($wr.R - $wr.L), ($wr.B - $wr.T)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$dc = $g.GetHdc(); [W]::PrintWindow($h, $dc, 2) | Out-Null; $g.ReleaseHdc($dc); $g.Dispose()
$ox = $p.X - $wr.L; $oy = $p.Y - $wr.T
$client = $bmp.Clone((New-Object System.Drawing.Rectangle $ox, $oy, $cr.R, $cr.B), $bmp.PixelFormat)
$client.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose(); $client.Dispose()
"saved $Out ($($cr.R)x$($cr.B))"
