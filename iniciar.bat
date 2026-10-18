@echo off
rem Abre o Numpad Deck (sem janela preta). Se ainda nao instalou, roda o instalar.bat antes.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  call instalar.bat
)
start "" ".venv\Scripts\pythonw.exe" main.py
