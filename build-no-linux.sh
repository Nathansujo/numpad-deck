#!/usr/bin/env bash
# Gera dist/NumpadDeck.exe (programa de Windows) aqui no Linux, SEM GitHub, usando o Wine.
# Na primeira vez baixa o Python para Windows (~25 MB) e instala dentro de um Wine so para isto
# (pasta ~/.wine-numpad); as proximas vezes sao rapidas.
#
# Antes (uma vez):   sudo apt install wine64 curl
# Uso:               ./build-no-linux.sh
set -euo pipefail
cd "$(dirname "$0")"

PY_VERSAO="3.12.7"
export WINEPREFIX="${WINEPREFIX:-$HOME/.wine-numpad}"
export WINEARCH=win64
export WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree,mshtml="      # nao pede para baixar Mono/Gecko (nao precisa)

WINE="$(command -v wine64 || command -v wine || true)"
[ -n "$WINE" ] || { echo "Falta o Wine:  sudo apt install wine64"; exit 1; }
command -v curl >/dev/null || { echo "Falta o curl:  sudo apt install curl"; exit 1; }

PY="C:\\Python312\\python.exe"
if ! "$WINE" "$PY" --version >/dev/null 2>&1; then
  echo "Primeira vez: instalando o Python $PY_VERSAO para Windows dentro do Wine..."
  "$WINE" wineboot -u >/dev/null 2>&1 || true
  INST="$(mktemp -d)/python-instalador.exe"
  curl -fL -o "$INST" "https://www.python.org/ftp/python/$PY_VERSAO/python-$PY_VERSAO-amd64.exe"
  "$WINE" "$INST" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 TargetDir='C:\Python312'
  "$WINE" "$PY" --version >/dev/null 2>&1 || { echo "A instalacao do Python no Wine falhou."; exit 1; }
fi

echo "Instalando as bibliotecas..."
"$WINE" "$PY" -m pip install --disable-pip-version-check -q -r requirements.txt pyinstaller

echo "Gerando o .exe..."
rm -rf build dist
"$WINE" "$PY" -m PyInstaller --noconsole --onefile --name NumpadDeck --add-data "web;web" \
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 \
  --hidden-import PIL._tkinter_finder --hidden-import websocket main.py

[ -f dist/NumpadDeck.exe ] || { echo "Nao gerou o .exe. Veja as mensagens acima."; exit 1; }
rm -rf build NumpadDeck.spec
echo
echo "Pronto: $(pwd)/dist/NumpadDeck.exe   (copie para o Windows)"
