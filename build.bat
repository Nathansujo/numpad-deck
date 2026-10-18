@echo off
rem Gera dist\NumpadDeck.exe (opcional: o GitHub tambem faz isso sozinho, veja .github\workflows\build.yml)
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconsole --onefile --name NumpadDeck --add-data "web;web" --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 --hidden-import PIL._tkinter_finder --hidden-import websocket main.py
echo.
echo Pronto: dist\NumpadDeck.exe  (copie para a Area de Trabalho)
pause
