"""
main.py — Ponto de entrada do bot v5.

Inicia:
  - Banco de dados (SQLite + WAL)
  - Thread de polling do Telegram
  - Thread do loop de ciclos individuais (2h + slots matinais)
  - Schedule diário de assinaturas (09h)
"""

import sys
import os

# Garante que a raiz do projeto está sempre no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
import time
import schedule

from config import TELEGRAM_TOKEN, ADMIN_CHAT_ID, get_logger
from db.database import init_db, migrar_json_para_sqlite
from telegram.bot import enviar, loop_polling
from services.monitor import loop_ciclos, ciclo_assinaturas
from webhook import iniciar_em_thread as iniciar_webhook

log = get_logger(__name__)


def main():
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_TOKEN não configurado!"); return
    if not ADMIN_CHAT_ID:
        log.error("ADMIN_CHAT_ID não configurado!"); return

    # Banco
    init_db()
    migrar_json_para_sqlite()

    log.info(f"Bot v5 iniciado. Admin: {ADMIN_CHAT_ID}")
    enviar(ADMIN_CHAT_ID,
        "🤖 *Bot v5 iniciado!*\n\n"
        "`/liberar <id>` — ativa/renova\n"
        "`/bloquear <id>` — suspende\n"
        "`/usuarios` — lista todos\n"
        "`/vencendo` — assinaturas vencendo\n"
        "`/forcarbusca` — busca imediata\n"
        "`/broadcast <msg>` — envia para todos\n"
        "`/msg <id> <msg>` — envia para um usuário\n\n"
        "_Ciclos individuais a cada 2h | Slots matinais: 05-08h_"
    )

    # Threads
    iniciar_webhook()  # recebe notificações do Mercado Pago
    threading.Thread(target=loop_polling, daemon=True).start()
    threading.Thread(target=loop_ciclos,  daemon=True).start()

    # Ciclo diário de assinaturas
    schedule.every().day.at("09:00").do(ciclo_assinaturas)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
