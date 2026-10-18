@echo off
rem Baixa a versao mais nova do GitHub e atualiza as bibliotecas. Nao precisa gerar .exe.
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 (
  echo Git nao encontrado. Instale em https://git-scm.com/download/win
  pause
  exit /b 1
)
echo Feche o Numpad Deck antes (painel: Opcoes ^> Encerrar o programa).
pause
git pull --ff-only
if errorlevel 1 (
  echo.
  echo Nao consegui atualizar. Se voce mexeu em arquivos do programa neste computador, guarde ou descarte a mudanca e tente de novo.
  pause
  exit /b 1
)
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Atualizado. Abra de novo com iniciar.bat
pause
