#!/usr/bin/env bash
# Atualiza o bot na VM: puxa o código novo, reconstrói e reinicia.
#   bash deploy/update.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo ">>> git pull"
git pull --ff-only

echo ">>> rebuild + restart"
docker compose up -d --build

echo ">>> limpando imagens antigas"
docker image prune -f

echo ">>> logs (Ctrl+C para sair)"
docker compose logs -f --tail=50
