"""
services/pagamento.py — Integração com Mercado Pago para geração de Pix copia e cola.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import uuid
import requests
from datetime import datetime, timedelta
from typing import Optional

from config import MP_ACCESS_TOKEN, PLANOS, get_logger

log = get_logger(__name__)

MP_BASE_URL = "https://api.mercadopago.com"

def _headers():
    return {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
        "X-Idempotency-Key": str(uuid.uuid4()),
    }

def gerar_pix(chat_id: str, nome: str, plano: str) -> Optional[dict]:
    """
    Gera cobrança Pix no Mercado Pago.
    Retorna {payment_id, pix_code, valor, expira_em} ou None.
    """
    if not MP_ACCESS_TOKEN:
        log.error("MP_ACCESS_TOKEN não configurado!")
        return None

    plano_info = PLANOS.get(plano, PLANOS["60dias"])
    expira = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

    payload = {
        "transaction_amount": float(plano_info["valor"]),
        "description":        plano_info["descricao"],
        "payment_method_id":  "pix",
        "date_of_expiration": expira,
        "payer": {
            "email":           f"flybot_{chat_id}@flybot.app",
            "first_name":      (nome or "Usuario").split()[0],
            "last_name":       "FlyBot",
            "identification":  {"type": "CPF", "number": "00000000000"},
        },
        "external_reference": f"{chat_id}:{plano}",
        "notification_url":   os.getenv("MP_WEBHOOK_URL", ""),
    }

    try:
        r = requests.post(
            f"{MP_BASE_URL}/v1/payments",
            headers=_headers(),
            json=payload,
            timeout=20,
        )
    except Exception as e:
        log.error(f"MP gerar_pix request erro: {e}")
        return None

    log.info(f"MP resposta status: {r.status_code}")
    if r.status_code not in (200, 201):
        log.error(f"MP criar pagamento erro {r.status_code}: {r.text[:500]}")
        return None

    data       = r.json()
    log.info(f"MP resposta keys: {list(data.keys())}")
    payment_id = data.get("id")
    status_mp  = data.get("status", "")
    log.info(f"MP payment_id={payment_id} status={status_mp}")
    pix_info   = data.get("point_of_interaction", {}).get("transaction_data", {})
    pix_code   = pix_info.get("qr_code", "")
    log.info(f"MP pix_code presente: {bool(pix_code)} | point_of_interaction: {bool(data.get('point_of_interaction'))}")

    if not pix_code:
        log.error(f"MP pix_code vazio. Resposta completa: {data}")
        return None

    log.info(f"MP Pix gerado: payment_id={payment_id} plano={plano} chat_id={chat_id}")
    return {
        "payment_id": str(payment_id),
        "pix_code":   pix_code,
        "valor":      plano_info["valor"],
        "plano":      plano,
        "expira_em":  "24 horas",
    }


def verificar_pagamento(payment_id: str) -> Optional[str]:
    """
    Consulta status do pagamento no MP.
    Retorna: 'approved', 'pending', 'rejected', etc.
    """
    if not MP_ACCESS_TOKEN:
        return None
    try:
        r = requests.get(
            f"{MP_BASE_URL}/v1/payments/{payment_id}",
            headers=_headers(),
            timeout=10,
        )
        status = r.json().get("status", "")
        log.info(f"MP verificar_pagamento {payment_id}: {status}")
        return status
    except Exception as e:
        log.error(f"MP verificar_pagamento erro: {e}")
        return None


def processar_webhook(body: dict) -> Optional[dict]:
    """
    Processa notificação de webhook do Mercado Pago.
    Retorna {chat_id, plano, payment_id} se aprovado, senão None.
    """
    # MP envia {"action": "payment.updated", "data": {"id": "123"}}
    action     = body.get("action", "")
    payment_id = str(body.get("data", {}).get("id", ""))

    if not payment_id or action not in ("payment.created", "payment.updated"):
        return None

    # Consulta o pagamento para pegar status e external_reference
    try:
        r = requests.get(
            f"{MP_BASE_URL}/v1/payments/{payment_id}",
            headers=_headers(),
            timeout=10,
        )
        data   = r.json()
        status = data.get("status", "")
        ref    = data.get("external_reference", "")
    except Exception as e:
        log.error(f"MP webhook consulta erro: {e}")
        return None

    if status != "approved":
        log.info(f"MP webhook: payment_id={payment_id} status={status} — ignorado")
        return None

    if not ref:
        log.warning(f"MP webhook: sem external_reference em {payment_id}")
        return None

    partes  = ref.split(":")
    chat_id = partes[0] if partes else ""
    plano   = partes[1] if len(partes) > 1 else "60dias"

    log.info(f"MP webhook: pagamento aprovado chat_id={chat_id} plano={plano}")
    return {"chat_id": chat_id, "plano": plano, "payment_id": payment_id}
