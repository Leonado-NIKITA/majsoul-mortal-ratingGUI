param([string]$Tag = "w", [string]$Serial = "emulator-5554")
# 每 15s 读一次「日志」页 / 状态栏文字, 直到出现完成或失败, 最多 ~12 分钟
$adb = "D:\adb\adb.exe"; $s = $Serial
$d = Split-Path -Parent $MyInvocation.MyCommand.Path
for ($i = 0; $i -lt 48; $i++) {
    Start-Sleep 15
    & "$d\uitext.ps1" -Tag $Tag -Serial $Serial | Out-Null
    $f = "$d\ui_$Tag.xml"
    if (-not (Test-Path $f)) { continue }
    $x = [IO.File]::ReadAllText($f, [Text.Encoding]::UTF8)
    $st = ([regex]::Match($x, 'text="([^"]*)" resource-id="" class="android.widget.TextView"[^>]*bounds="\[14,46\]')).Groups[1].Value
    if (-not $st) { $st = ([regex]::Match($x, '<node [^>]*text="([^"]+)"[^>]*bounds="\[14,46\]')).Groups[1].Value }
    "{0:HH:mm:ss} {1}" -f (Get-Date), $st
    if ($st -match '完成|未完成|失败|出错|已停止|就绪') { break }
}
