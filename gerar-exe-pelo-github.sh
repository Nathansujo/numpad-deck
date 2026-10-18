#!/usr/bin/env bash
# Gera o NumpadDeck.exe (para Windows) a partir do Linux.
# O .exe precisa ser montado por um Windows de verdade; aqui quem faz isso e o GitHub Actions (gratis):
# o script manda o projeto para um repositorio SEU (privado), dispara a montagem e baixa o .exe em ./dist
#
# Antes (uma vez):  sudo apt install git gh     e     gh auth login
# Uso:              ./gerar-exe-pelo-github.sh [nome-do-repositorio]
set -euo pipefail
cd "$(dirname "$0")"
REPO="${1:-numpad-deck}"

for cmd in git gh; do
  command -v "$cmd" >/dev/null || { echo "Falta instalar o '$cmd' (sudo apt install git gh)."; exit 1; }
done
gh auth status >/dev/null 2>&1 || { echo "Entre na sua conta do GitHub primeiro:  gh auth login"; exit 1; }

[ -d .git ] || git init -q -b main
git config user.name  >/dev/null 2>&1 || git config user.name  "Numpad Deck"
git config user.email >/dev/null 2>&1 || git config user.email "numpad-deck@localhost"
git add -A
git diff --cached --quiet || git commit -q -m "Numpad Deck"

if git remote get-url origin >/dev/null 2>&1; then
  git push -q -u origin HEAD
else
  echo "Criando o repositorio privado '$REPO' na sua conta do GitHub..."
  gh repo create "$REPO" --private --source=. --remote=origin --push
fi

echo "Pedindo ao GitHub para montar o .exe..."
for tentativa in 1 2 3 4 5 6; do
  gh workflow run build.yml && break
  [ "$tentativa" = 6 ] && { echo "Nao consegui iniciar a montagem. Abra a aba Actions do repositorio e rode 'Gerar executavel' manualmente."; exit 1; }
  sleep 5
done

sleep 8
RUN_ID=""
for _ in 1 2 3 4 5 6; do
  RUN_ID=$(gh run list --workflow=build.yml --event=workflow_dispatch --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || true)
  [ -n "$RUN_ID" ] && break
  sleep 5
done
[ -n "$RUN_ID" ] || { echo "Nao achei a execucao. Veja a aba Actions do repositorio."; exit 1; }

echo "Montando no Windows do GitHub (leva uns 3 a 6 minutos)..."
gh run watch "$RUN_ID" --exit-status || { echo "A montagem falhou. Detalhes:  gh run view $RUN_ID --log-failed"; exit 1; }

rm -rf dist && mkdir -p dist
gh run download "$RUN_ID" -n NumpadDeck -D dist
echo
echo "Pronto: $(pwd)/dist/NumpadDeck.exe  (copie para o Windows)"
