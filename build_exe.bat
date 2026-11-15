@echo off
rem Build desktop app -> dist\MajsoulRating\MajsoulRating.exe
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller pillow || exit /b 1
python -m PyInstaller --noconfirm --clean --windowed --name MajsoulRating ^
  --add-data "turtle.png;." ^
  --add-data "assets;assets" ^
  --collect-submodules playwright ^
  gui.py || exit /b 1
echo.
echo Done: dist\MajsoulRating\MajsoulRating.exe  (needs Edge or Chrome installed)
pause
