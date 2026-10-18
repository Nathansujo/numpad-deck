@echo off
rem Prepara o Numpad Deck neste computador (so precisa rodar uma vez, e de novo se o requirements.txt mudar).
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale o Python 3.10 ou mais novo em https://www.python.org/downloads/
  echo e marque "Add python.exe to PATH" na instalacao.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Pronto. Para abrir, de dois cliques em iniciar.bat
pause
