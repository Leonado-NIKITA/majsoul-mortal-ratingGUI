@echo off
rem Build installer -> dist\MajsoulRating-Setup-<version>.exe
rem Needs: Python (uses .venv if present), Inno Setup 6.5+ (winget install JRSoftware.InnoSetup)
setlocal
cd /d "%~dp0"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

"%PY%" -m pip install -q -r requirements.txt pyinstaller pillow || goto :fail
"%PY%" -m PyInstaller --noconfirm --clean MajsoulRating.spec || goto :fail

rem version.py: __version__ = "x.y.z"
for /f "tokens=2 delims==" %%v in ('findstr /b "__version__" version.py') do set "VER=%%~v"
set "VER=%VER: =%"
set "VER=%VER:"=%"
if not defined VER goto :fail

set "ISCC="
for %%d in ("%LOCALAPPDATA%\Programs\Inno Setup 6" "%ProgramFiles(x86)%\Inno Setup 6" "%ProgramFiles%\Inno Setup 6") do (
  if exist "%%~d\ISCC.exe" set "ISCC=%%~d\ISCC.exe"
)
if not defined ISCC (
  echo Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup
  goto :fail
)

"%ISCC%" /Q /DMyAppVersion=%VER% installer\MajsoulRating.iss || goto :fail
echo.
echo Done: dist\MajsoulRating-Setup-%VER%.exe
if not defined CI pause
exit /b 0

:fail
echo.
echo Build failed.
if not defined CI pause
exit /b 1
