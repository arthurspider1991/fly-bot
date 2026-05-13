"""
services/pagamento.py — Integração Checkout Pro Mercado Pago.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import uuid
import requests
from datetime import datetime, timedelta
from typing import Optional

from config import get_logger

log = get_logger(__name__)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")

PLANOS = {
    "1mes":   {"valor": 1.00, "dias": 30,  "descricao": "Fly Bot - Plano 1 mes"},
    "5meses": {"valor": 1.00, "dias": 90,  "descricao": "Fly Bot - Plano 3 meses"},
}


def gerar_checkout(chat_id: str, nome: str, plano: str) -> Optional[dict]:
    """
    Gera link de Checkout Pro no Mercado Pago.
    Funciona com CPF (pessoa fisica).
    Retorna dict com {preference_id, link, valor} ou None.
    """
    if not MP_ACCESS_TOKEN:
        log.error("MP_ACCESS_TOKEN nao configurado!")
        return None

    plano_info  = PLANOS.get(plano, PLANOS["1mes"])
    idempotency = str(uuid.uuid4())
    webhook_url = os.getenv("MP_WEBHOOK_URL", "")
    base_url    = webhook_url.replace("/webhook", "") if webhook_url else "https://flybot.app"

    payload = {
        "items": [{
            "id":          f"flybot_{plano}",
            "title":       plano_info["descricao"],
            "quantity":    1,
            "currency_id": "BRL",
            "unit_price":  plano_info["valor"],
        }],
        "payer": {
            "email": f"flybot_{chat_id}@flybot.app",
        },
        "external_reference": f"{chat_id}:{plano}",
        "expires":            True,
        "expiration_date_to": (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
        "back_urls": {
            "success": f"{base_url}/success",
            "pending": f"{base_url}/pending",
            "failure": f"{base_url}/failure",
        },
        "auto_return":          "approved",
        "payment_methods": {
            "excluded_payment_types": [
                {"id": "credit_card"},
                {"id": "debit_card"},
                {"id": "ticket"},
                {"id": "bank_transfer"},
                {"id": "atm"},
                {"id": "prepaid_card"},
            ],
            "installments": 1,
        },
        "statement_descriptor": "FLYBOT",
    }

    if webhook_url.startswith("https://"):
        payload["notification_url"] = webhook_url

    try:
        r = requests.post(
            "https://api.mercadopago.com/checkout/preferences",
            json=payload,
            headers={
                "Authorization":     f"Bearer {MP_ACCESS_TOKEN}",
                "Content-Type":      "application/json",
                "X-Idempotency-Key": idempotency,
            },
            timeout=15,
        )
        resp = r.json()

        if r.status_code not in (200, 201):
            log.error(f"MP erro {r.status_code}: {resp}")
            return None

        link = resp.get("init_point") or resp.get("sandbox_init_point")
        log.info(f"Checkout gerado: {link}")
        return {
            "preference_id": resp["id"],
            "link":          link,
            "valor":         plano_info["valor"],
            "plano":         plano,
        }

    except Exception as e:
        log.error(f"MP gerar_checkout erro: {e}")
        return None


def verificar_pagamento(payment_id: str) -> Optional[str]:
    """Verifica status de um pagamento."""
    if not MP_ACCESS_TOKEN:
        return None
    try:
        r = requests.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
            timeout=10,
        )
        return r.json().get("status")
    except Exception as e:
        log.error(f"MP verificar_pagamento erro: {e}")
        return None


def processar_webhook(body: dict) -> Optional[dict]:
    """
    Processa notificacao de webhook do MP.
    Retorna {chat_id, plano, payment_id} se aprovado, senão None.
    """
    if not MP_ACCESS_TOKEN:
        return None
    try:
        tipo       = body.get("type", "")
        payment_id = body.get("data", {}).get("id")
        if not payment_id:
            return None

        if tipo == "merchant_order":
            r     = requests.get(
                f"https://api.mercadopago.com/merchant_orders/{payment_id}",
                headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
                timeout=10,
            )
            order    = r.json()
            aprovado = any(p.get("status") == "approved" for p in order.get("payments", []))
            if not aprovado:
                log.info(f"Webhook merchant_order {payment_id}: sem pagamento aprovado")
                return None
            ref = order.get("external_reference", "")
        else:
            status = verificar_pagamento(payment_id)
            if status != "approved":
                log.info(f"Webhook: payment {payment_id} status={status} (ignorado)")
                return None
            r    = requests.get(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
                timeout=10,
            )
            ref = r.json().get("external_reference", "")

        partes  = ref.split(":")
        chat_id = partes[0] if partes else ""
        plano   = partes[1] if len(partes) > 1 else "1mes"

        log.info(f"Webhook: pagamento aprovado! chat_id={chat_id} plano={plano}")
        return {"chat_id": chat_id, "plano": plano, "payment_id": payment_id}

    except Exception as e:
        log.error(f"MP processar_webhook erro: {e}")
        return None
