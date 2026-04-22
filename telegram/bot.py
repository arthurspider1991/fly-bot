"""
telegram/bot.py — Funções de envio de mensagens e loop de polling.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import json
import time
import requests

from config import TELEGRAM_TOKEN, get_logger

log = get_logger(__name__)

_ultimo_update_id = 0

# ── Envio ─────────────────────────────────────────────────────────────────────

def enviar(chat_id, texto: str, reply_markup=None):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     texto,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": False,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"Erro enviar {chat_id}: {e}")
        return None


def encaminhar_foto_para_admin(chat_id_destino, file_id: str, caption: str, reply_markup=None):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {"chat_id": chat_id_destino, "photo": file_id,
               "caption": caption, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"Erro foto admin: {e}")


def encaminhar_documento_para_admin(chat_id_destino, file_id: str, caption: str, reply_markup=None):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    payload = {"chat_id": chat_id_destino, "document": file_id,
               "caption": caption, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"Erro doc admin: {e}")


def responder_callback(callback_query_id, texto: str = ""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id, "text": texto}, timeout=10)
    except Exception as e:
        log.error(f"Erro answerCallback: {e}")


def editar_mensagem_markup(chat_id, message_id: int, reply_markup=None):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageReplyMarkup"
    payload = {
        "chat_id":      chat_id,
        "message_id":   message_id,
        "reply_markup": json.dumps(reply_markup if reply_markup else {"inline_keyboard": []}),
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log.error(f"Erro editar markup: {e}")


def is_admin(chat_id) -> bool:
    from config import ADMIN_CHAT_ID
    return int(chat_id) == ADMIN_CHAT_ID

# ── Polling ───────────────────────────────────────────────────────────────────

def processar_updates() -> None:
    global _ultimo_update_id
    from telegram.handlers import processar_mensagem

    POLL_TIMEOUT = 30
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r = requests.get(
            url,
            params={"timeout": POLL_TIMEOUT, "offset": _ultimo_update_id + 1},
            timeout=POLL_TIMEOUT + 10,
        )
        r.raise_for_status()
        for update in r.json().get("result", []):
            _ultimo_update_id = update["update_id"]

            if "callback_query" in update:
                cq           = update["callback_query"]
                chat_id      = cq["message"]["chat"]["id"]
                nome         = cq.get("from", {}).get("first_name", "Usuário")
                cb_data      = cq.get("data", "")
                msg_original = cq.get("message", {})
                responder_callback(cq["id"])
                try:
                    processar_mensagem(chat_id, "", nome, msg_obj=msg_original, callback_data=cb_data)
                except Exception as e:
                    log.error(f"Erro callback {chat_id}: {e}")
                continue

            msg = update.get("message") or update.get("channel_post")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            nome    = msg.get("from", {}).get("first_name", "Usuário")
            texto   = msg.get("text", "").strip()
            try:
                processar_mensagem(chat_id, texto, nome, msg_obj=msg)
            except Exception as e:
                log.error(f"Erro msg {chat_id}: {e}")

    except requests.exceptions.ReadTimeout:
        log.warning("Polling: timeout, reconectando...")
    except requests.exceptions.ConnectionError:
        log.warning("Polling: sem conexão, aguardando 15s...")
        time.sleep(15)
    except Exception as e:
        log.error(f"getUpdates: {e}")
        time.sleep(5)


def loop_polling() -> None:
    log.info("Polling iniciado.")
    while True:
        processar_updates()
