param([string]$Tag = "x", [string]$Serial = "emulator-5554")
# 用 uiautomator 读出当前界面上的所有文字 (Qt 把文字放在 content-desc 里)
$adb = "D:\adb\adb.exe"
$d = $PSScriptRoot
& $adb -s $Serial shell uiautomator dump /sdcard/ui.xml 2>&1 | Out-Null
& $adb -s $Serial pull /sdcard/ui.xml "$d\ui_$Tag.xml" 2>&1 | Out-Null
$x = [IO.File]::ReadAllText("$d\ui_$Tag.xml", [Text.Encoding]::UTF8)
$t = [regex]::Matches($x, '(?:text|content-desc)="([^"]+)"') |
    ForEach-Object { [Net.WebUtility]::HtmlDecode($_.Groups[1].Value) } | Select-Object -Unique
[IO.File]::WriteAllLines("$d\ui_$Tag.txt", $t, [Text.Encoding]::UTF8)
