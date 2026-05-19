"""
webhook.py — Servidor HTTP para receber webhooks do Mercado Pago.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta

from config import ADMIN_CHAT_ID, PLANOS, get_logger
from services.pagamento import processar_webhook
from services.monitor import atribuir_slot_manha, dias_plano
from db.database import init_db
from db.usuarios import carregar_usuario, salvar_usuario
from db.parceiros import init_parceiros, confirmar_venda, get_ou_criar_parceiro
from db.financeiro import init_financeiro, registrar_receita, registrar_comissao

log = get_logger(__name__)
PORT = int(os.getenv("PORT", 8080))


class WebhookHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Fly Bot OK")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length) or b"{}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            threading.Thread(target=_processar_notificacao, args=(body,), daemon=True).start()
        except Exception as e:
            log.error(f"Webhook handler erro: {e}")
            self.send_response(500)
            self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()


def _processar_notificacao(body: dict):
    from telegram.bot import enviar

    resultado = processar_webhook(body)
    if not resultado:
        return

    chat_id    = resultado["chat_id"]
    plano      = resultado["plano"]
    payment_id = resultado["payment_id"]

    # Carrega ou cria usuario
    dados = carregar_usuario(chat_id) or {
        "nome": "Usuário", "status": "aguardando_pagamento",
        "config": {}, "historico": {}, "historico_precos": {},
        "liberado_em": None, "plano": plano,
        "proxima_busca": None, "slot_manha": None,
    }

    era_renovacao        = dados.get("liberado_em") is not None
    dados["status"]      = "setup_origem"
    dados["plano"]       = plano
    dados["liberado_em"] = datetime.now().isoformat()
    dados["slot_manha"]  = atribuir_slot_manha()
    salvar_usuario(chat_id, dados)

    p      = PLANOS.get(plano, PLANOS.get("60dias", {}))
    label  = p.get("label", plano)
    valor  = float(p.get("valor", 0))
    expira = (datetime.now() + timedelta(days=dias_plano(plano))).strftime("%d/%m/%Y")
    nome   = dados.get("nome", "Usuário")
    tipo   = "Renovação" if era_renovacao else "Novo acesso"

    log.info(f"Acesso liberado: {chat_id} | {plano} | payment={payment_id}")

    # Registra receita
    try:
        registrar_receita(chat_id, nome, plano, valor, payment_id)
    except Exception as e:
        log.error(f"Erro registrar_receita: {e}")

    # Credita comissao ao parceiro que indicou (se houver)
    try:
        venda = confirmar_venda(chat_id, plano)
        if venda:
            parceiro_id   = venda["parceiro_id"]
            parceiro_nome = venda["parceiro_nome"]
            comissao      = venda["comissao"]

            registrar_comissao(parceiro_id, parceiro_nome, nome, plano, comissao, payment_id)

            enviar(int(parceiro_id),
                f"🎉 *Comissão creditada!*\n\n"
                f"Sua indicação assinou o plano *{label}* "
                f"e você ganhou *R$ {comissao:.2f}*!\n\n"
                "Use /carteira para ver seu saldo."
            )
            enviar(ADMIN_CHAT_ID,
                f"💰 Comissao gerada\n"
                f"Parceiro: {parceiro_nome} ({parceiro_id})\n"
                f"Indicado: {nome} ({chat_id})\n"
                f"Plano: {label} | Comissao: R$ {comissao:.2f}"
            )
    except Exception as e:
        log.error(f"Erro creditar comissao parceiro: {e}")

    # Garante registro de parceiro para o novo usuario
    try:
        get_ou_criar_parceiro(chat_id, nome)
    except Exception as e:
        log.error(f"Erro get_ou_criar_parceiro: {e}")

    # Avisa admin
    enviar(ADMIN_CHAT_ID,
        f"{'🔄' if era_renovacao else '✅'} *{tipo} — {nome}*\n"
        f"ID: `{chat_id}`\n"
        f"Plano: {label} | Expira: {expira}\n"
        f"Valor: R$ {valor:.2f} | Payment: `{payment_id}`\n"
        "_Liberado automaticamente pelo MP_"
    )

    # Mensagem para o usuario com botoes
    markup = {"inline_keyboard": [
        [{"text": "🛠 Configurar Minha Rota", "callback_data": "configurar_rota"}],
        [{"text": "💰 Indique e Ganhe",        "callback_data": "ver_indique"}],
    ]}
    enviar(int(chat_id),
        f"✅ *Pagamento confirmado!*\n\n"
        f"Seu plano de *{label}* está ativo até *{expira}*.\n\n"
        "O que você deseja fazer agora?",
        reply_markup=markup
    )


def iniciar_servidor():
    init_db()
    init_financeiro()
    init_parceiros()
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    log.info(f"Webhook server rodando na porta {PORT}")
    server.serve_forever()


def iniciar_em_thread():
    t = threading.Thread(target=iniciar_servidor, daemon=True)
    t.start()
    return t
