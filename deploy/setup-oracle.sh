#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Bootstrap de uma VM Oracle Cloud Always Free (Ubuntu 22.04, ARM/aarch64)
# para rodar o Fly Bot v5 em Docker.
#
# Uso (dentro da pasta do repo já clonado):
#   bash deploy/setup-oracle.sh
#
# É idempotente — pode rodar de novo sem quebrar nada.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"
echo ">>> Repo: $REPO_DIR"

echo ">>> [1/5] Pacotes base"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl git nano

echo ">>> [2/5] Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
else
  echo "    docker já instalado: $(docker --version)"
fi
sudo usermod -aG docker "$USER" || true
sudo systemctl enable --now docker

echo ">>> [3/5] Swap de 4G (protege o Chromium contra OOM)"
if ! sudo swapon --show | grep -q '/swapfile'; then
  sudo fallocate -l 4G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=4096
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
else
  echo "    swap já configurado"
fi
sudo sysctl -w vm.swappiness=10 >/dev/null
grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf >/dev/null

echo ">>> [4/5] Pasta de dados (banco persistente)"
mkdir -p "$REPO_DIR/data"

echo ">>> [5/5] .env"
if [ ! -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  echo "    criado .env a partir do exemplo — EDITE antes de subir:"
  echo "      nano $REPO_DIR/.env"
else
  echo "    .env já existe, mantido"
fi

echo
echo "=================================================================="
echo " Pronto. Próximos passos:"
echo
echo "   1) Saia e entre de novo no SSH (para o grupo 'docker' valer),"
echo "      ou rode:  newgrp docker"
echo
echo "   2) Edite os segredos:   nano ~/fly-bot/.env"
echo
echo "   3) (opcional) copie o banco antigo para ~/fly-bot/data/bot.db"
echo
echo "   4) Suba:                cd ~/fly-bot && docker compose up -d --build"
echo "      Acompanhe:           docker compose logs -f"
echo "=================================================================="
