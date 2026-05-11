"""
services/pagamento.py — Integração com Mercado Pago para geração de Pix.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import json
import uuid
import requests
from datetime import datetime, timedelta
from typing import Optional

from config import get_logger

log = get_logger(__name__)

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")

PLANOS = {
    "1mes":   {"valor": 14.90, "dias": 30,  "descricao": "Fly Bot - Plano 1 mês"},
    "5meses": {"valor": 29.90, "dias": 90,  "descricao": "Fly Bot - Plano 3 meses"},
}


def gerar_pix(chat_id: str, nome: str, plano: str) -> Optional[dict]:
    """
    Gera um pagamento Pix no Mercado Pago.
    Retorna dict com {payment_id, qr_code, qr_code_base64, valor} ou None.
    """
    if not MP_ACCESS_TOKEN:
        log.error("MP_ACCESS_TOKEN não configurado!")
        return None

    plano_info = PLANOS.get(plano, PLANOS["1mes"])
    idempotency  = str(uuid.uuid4())

    webhook_url = os.getenv("MP_WEBHOOK_URL", "")
    payload = {
        "transaction_amount": plano_info["valor"],
        "description":        plano_info["descricao"],
        "payment_method_id":  "pix",
        "external_reference": f"{chat_id}:{plano}",
        **({"notification_url": webhook_url} if webhook_url.startswith("https://") else {}),
        "date_of_expiration": (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
        "payer": {
            "email": "test_user_123@testuser.com",
        },
    }

    try:
        r = requests.post(
            "https://api.mercadopago.com/v1/payments",
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

        pix_data = resp.get("point_of_interaction", {}).get("transaction_data", {})
        return {
            "payment_id":     resp["id"],
            "qr_code":        pix_data.get("qr_code", ""),
            "qr_code_base64": pix_data.get("qr_code_base64", ""),
            "valor":          plano_info["valor"],
            "plano":          plano,
            "expira_em":      "24 horas",
        }

    except Exception as e:
        log.error(f"MP gerar_pix erro: {e}")
        return None


def verificar_pagamento(payment_id: str) -> Optional[str]:
    """
    Verifica o status de um pagamento no MP.
    Retorna: 'approved', 'pending', 'rejected' ou None.
    """
    if not MP_ACCESS_TOKEN:
        return None
    try:
        r = requests.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
            timeout=10,
        )
        resp = r.json()
        return resp.get("status")
    except Exception as e:
        log.error(f"MP verificar_pagamento erro: {e}")
        return None


def processar_webhook(body: dict) -> Optional[dict]:
    """
    Processa notificação de webhook do MP.
    Retorna {chat_id, plano, payment_id} se pagamento aprovado, senão None.
    """
    try:
        if body.get("type") != "payment":
            return None

        payment_id = body.get("data", {}).get("id")
        if not payment_id:
            return None

        status = verificar_pagamento(payment_id)
        if status != "approved":
            log.info(f"Webhook: payment {payment_id} status={status} (ignorado)")
            return None

        # Pega external_reference = "chat_id:plano"
        r = requests.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
            timeout=10,
        )
        resp       = r.json()
        ref        = resp.get("external_reference", "")
        partes     = ref.split(":")
        chat_id    = partes[0] if partes else ""
        plano      = partes[1] if len(partes) > 1 else "1mes"

        log.info(f"Webhook: pagamento aprovado! chat_id={chat_id} plano={plano}")
        return {"chat_id": chat_id, "plano": plano, "payment_id": payment_id}

    except Exception as e:
        log.error(f"MP processar_webhook erro: {e}")
        return None
