"""
services/pagamento.py — Integração com Asaas para geração de Pix.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import uuid
import requests
from datetime import datetime, timedelta
from typing import Optional

from config import ASAAS_API_KEY, ASAAS_BASE_URL, PLANOS, get_logger

log = get_logger(__name__)


def _headers():
    return {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json",
    }


def _criar_ou_buscar_cliente(chat_id: str, nome: str) -> Optional[str]:
    """Cria ou busca cliente no Asaas. Retorna customer_id."""
    # Busca por externalReference
    r = requests.get(
        f"{ASAAS_BASE_URL}/customers",
        headers=_headers(),
        params={"externalReference": str(chat_id)},
        timeout=10,
    )
    if r.status_code == 200:
        data = r.json()
        if data.get("data"):
            return data["data"][0]["id"]

    # Cria novo cliente
    nome_parts = nome.strip().split() if nome else ["Usuario"]
    r2 = requests.post(
        f"{ASAAS_BASE_URL}/customers",
        headers=_headers(),
        json={
            "name":              nome or "Usuario FlyBot",
            "externalReference": str(chat_id),
            "email":             f"flybot_{chat_id}@flybot.app",
            "notificationDisabled": True,
        },
        timeout=10,
    )
    if r2.status_code in (200, 201):
        return r2.json().get("id")

    log.error(f"Asaas criar cliente erro {r2.status_code}: {r2.text[:200]}")
    return None


def gerar_pix(chat_id: str, nome: str, plano: str) -> Optional[dict]:
    """
    Gera cobrança Pix no Asaas.
    Retorna {payment_id, pix_code, valor, expira_em} ou None.
    """
    if not ASAAS_API_KEY:
        log.error("ASAAS_API_KEY não configurado!")
        return None

    plano_info = PLANOS.get(plano, PLANOS["60dias"])

    customer_id = _criar_ou_buscar_cliente(chat_id, nome)
    if not customer_id:
        return None

    due_date = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d")

    r = requests.post(
        f"{ASAAS_BASE_URL}/payments",
        headers=_headers(),
        json={
            "customer":          customer_id,
            "billingType":       "PIX",
            "value":             plano_info["valor"],
            "dueDate":           due_date,
            "description":       plano_info["descricao"],
            "externalReference": f"{chat_id}:{plano}",
            "postalService":     False,
        },
        timeout=15,
    )

    if r.status_code not in (200, 201):
        log.error(f"Asaas criar cobrança erro {r.status_code}: {r.text[:200]}")
        return None

    payment = r.json()
    payment_id = payment.get("id")

    # Busca QR Code Pix
    r2 = requests.get(
        f"{ASAAS_BASE_URL}/payments/{payment_id}/pixQrCode",
        headers=_headers(),
        timeout=10,
    )

    if r2.status_code != 200:
        log.error(f"Asaas QR Code erro {r2.status_code}: {r2.text[:200]}")
        return None

    pix_data = r2.json()
    return {
        "payment_id": payment_id,
        "pix_code":   pix_data.get("payload", ""),
        "qr_base64":  pix_data.get("encodedImage", ""),
        "valor":      plano_info["valor"],
        "plano":      plano,
        "expira_em":  "24 horas",
    }


def verificar_pagamento(payment_id: str) -> Optional[str]:
    """Retorna status da cobrança: CONFIRMED, PENDING, OVERDUE, etc."""
    if not ASAAS_API_KEY:
        return None
    try:
        r = requests.get(
            f"{ASAAS_BASE_URL}/payments/{payment_id}",
            headers=_headers(),
            timeout=10,
        )
        return r.json().get("status")
    except Exception as e:
        log.error(f"Asaas verificar_pagamento erro: {e}")
        return None


def processar_webhook(body: dict) -> Optional[dict]:
    """
    Processa notificação de webhook do Asaas.
    Retorna {chat_id, plano, payment_id} se confirmado, senão None.
    """
    evento = body.get("event", "")
    # PAYMENT_CONFIRMED ou PAYMENT_RECEIVED
    if evento not in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        return None

    payment   = body.get("payment", {})
    payment_id = payment.get("id", "")
    ref       = payment.get("externalReference", "")

    if not ref:
        log.warning(f"Webhook sem externalReference: {payment_id}")
        return None

    partes  = ref.split(":")
    chat_id = partes[0] if partes else ""
    plano   = partes[1] if len(partes) > 1 else "60dias"

    log.info(f"Webhook Asaas: pagamento confirmado chat_id={chat_id} plano={plano}")
    return {"chat_id": chat_id, "plano": plano, "payment_id": payment_id}
