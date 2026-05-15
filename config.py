"""
config.py — Variáveis de ambiente e constantes globais.
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ADMIN_CHAT_ID  = int(os.getenv("ADMIN_CHAT_ID", "0"))

# ── Asaas ─────────────────────────────────────────────────────────────────────
ASAAS_API_KEY  = os.getenv("ASAAS_API_KEY", "")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3")  # produção
# Sandbox: https://sandbox.asaas.com/api/v3

# ── Planos ────────────────────────────────────────────────────────────────────
PLANOS = {
    "60dias": {
        "label":      "60 dias",
        "valor":      14.90,
        "dias":       60,
        "comissao":   5.00,
        "descricao":  "Fly Bot — Plano 60 dias",
    },
    "5meses": {
        "label":      "5 meses",
        "valor":      29.90,
        "dias":       150,
        "comissao":   10.00,
        "descricao":  "Fly Bot — Plano 5 meses",
    },
    "1ano": {
        "label":      "1 ano",
        "valor":      49.90,
        "dias":       365,
        "comissao":   20.00,
        "descricao":  "Fly Bot — Plano 1 ano",
    },
}

# ── Afiliados ─────────────────────────────────────────────────────────────────
COMISSAO_MINIMO_SAQUE = 10.00  # saldo mínimo para solicitar saque

# ── Monitoramento ─────────────────────────────────────────────────────────────
ALERTA_PERCENT = 3.0
SLOTS_MANHA    = ["05:00", "06:00", "07:00", "08:00"]

# ── Banco ─────────────────────────────────────────────────────────────────────
DB_FILE = os.getenv("DB_FILE", "bot.db")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler()],
)

def get_logger(name: str):
    return logging.getLogger(name)
