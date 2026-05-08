"""
config.py — Variáveis de ambiente e constantes globais.
Importado por todos os outros módulos.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
ADMIN_CHAT_ID   = int(os.getenv("ADMIN_CHAT_ID", "0"))

# ── Pix / Planos ──────────────────────────────────────────────────────────────
PIX_KEY_1MES     = os.getenv("PIX_KEY_1MES",   os.getenv("PIX_KEY", ""))
PIX_KEY_5MESES   = os.getenv("PIX_KEY_5MESES", os.getenv("PIX_KEY", ""))
PIX_VALOR_1MES   = os.getenv("PIX_VALOR_1MES",   "R$ 14,90")
PIX_VALOR_5MESES = os.getenv("PIX_VALOR_5MESES", "R$ 29,90")  # 3 meses

# ── Banco ─────────────────────────────────────────────────────────────────────
DB_FILE    = os.getenv("DB_FILE", "bot.db")

# ── Monitoramento ─────────────────────────────────────────────────────────────
ALERTA_PERCENT = 3.0          # % mínimo para alertar variação de preço
SLOTS_MANHA    = ["05:00", "06:00", "07:00", "08:00"]

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler()],
)

def get_logger(name: str):
    return logging.getLogger(name)
