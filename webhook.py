"""
webhook.py — Servidor HTTP simples para receber webhooks do Mercado Pago.
Roda junto com o bot na mesma porta que o Railway expõe.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta

from config import ADMIN_CHAT_ID, get_logger
from services.pagamento import processar_webhook
from db.usuarios import carregar_usuario, salvar_usuario
from services.monitor import atribuir_slot_manha, dias_plano

log = get_logger(__name__)

PORT = int(os.getenv("PORT", 8080))


class WebhookHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # silencia logs do servidor HTTP

    def do_GET(self):
        # Health check para o Railway
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

            # Processa em thread separada para não bloquear o servidor
            threading.Thread(
                target=_processar_notificacao,
                args=(body,),
                daemon=True,
            ).start()

        except Exception as e:
            log.error(f"Webhook handler erro: {e}")
            self.send_response(500)
            self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()


def _processar_notificacao(body: dict):
    """Libera acesso automaticamente quando MP confirma pagamento."""
    from telegram.bot import enviar
    from telegram.teclados import teclado_paises

    resultado = processar_webhook(body)
    if not resultado:
        return

    chat_id    = resultado["chat_id"]
    plano      = resultado["plano"]
    payment_id = resultado["payment_id"]

    dados = carregar_usuario(chat_id) or {
        "nome": "Usuário", "status": "aguardando_pagamento",
        "config": {}, "historico": {}, "historico_precos": {},
        "liberado_em": None, "plano": plano,
        "proxima_busca": None, "slot_manha": None,
    }

    # Já era ativo? Renovação
    era_renovacao = dados.get("liberado_em") is not None

    dados["status"]      = "setup_origem"
    dados["plano"]       = plano
    dados["liberado_em"] = datetime.now().isoformat()
    dados["slot_manha"]  = atribuir_slot_manha()
    salvar_usuario(chat_id, dados)

    from config import PLANOS
    p      = PLANOS.get(plano, PLANOS.get("60dias", {}))
    label  = p.get("label", plano)
    expira = (datetime.now() + timedelta(days=dias_plano(plano))).strftime("%d/%m/%Y")
    nome   = dados.get("nome", "Usuário")
    tipo   = "🔄 Renovação" if era_renovacao else "✅ Novo acesso"

    # Avisa o admin
    enviar(ADMIN_CHAT_ID,
        f"{tipo} — *{nome}*\n"
        f"ID: `{chat_id}`\n"
        f"Plano: {label} | Expira: {expira}\n"
        f"Payment ID: `{payment_id}`\n"
        "_Liberado automaticamente pelo MP_ ✅"
    )

    from db.usuarios import buscar_afiliado, criar_afiliado, confirmar_comissao
    from config import PLANOS as _PLANOS

    # Registra receita
    _valor_plano = float(_PLANOS.get(plano, {}).get("valor", 0))
    registrar_receita(chat_id, nome, plano, _valor_plano, payment_id)

    # Credita comissão ao afiliado que indicou (se houver)
    try:
        resultado_comissao = confirmar_comissao(chat_id)
        if resultado_comissao:
            afiliado_id = resultado_comissao["afiliado_id"]
            comissao    = resultado_comissao["comissao"]
            af_dados = buscar_afiliado(afiliado_id)
            af_nome  = af_dados.get("nome", "afiliado") if af_dados else "afiliado"
            log.info(f"Comissão creditada: R$ {comissao:.2f} para {afiliado_id} ({af_nome})")
            registrar_comissao(afiliado_id, af_nome, nome, plano, comissao, payment_id)
            # Avisa o afiliado
            enviar(int(afiliado_id),
                f"🎉 *Comissão creditada!*\n\n"
                f"Sua indicação assinou o plano *{label}* e você ganhou *R$ {comissao:.2f}*!\n\n"
                "Use /carteira para ver seu saldo."
            )
            # Avisa o admin
            enviar(ADMIN_CHAT_ID,
                f"💰 *Comissão gerada*\n"
                f"Afiliado: {af_nome} (`{afiliado_id}`)\n"
                f"Indicado: {nome} (`{chat_id}`)\n"
                f"Plano: {label} | Comissão: R$ {comissao:.2f}"
            )
    except Exception as e:
        log.error(f"Erro ao creditar comissão: {e}")

    # Garante que o novo usuário já tem registro de afiliado
    buscar_afiliado(chat_id) or criar_afiliado(chat_id)

    # Manda mensagem de confirmação com botões
    markup_pos_pagamento = {"inline_keyboard": [
        [{"text": "🛠 Configurar Minha Rota", "callback_data": "configurar_rota"}],
        [{"text": "💰 Indique e Ganhe",        "callback_data": "ver_indique"}],
    ]}
    enviar(int(chat_id),
        f"✅ *Pagamento confirmado!*\n\n"
        f"Seu plano de *{label}* está ativo até *{expira}*.\n\n"
        "O que você deseja fazer agora? Escolha uma das opções abaixo:",
        reply_markup=markup_pos_pagamento
    )

    log.info(f"Acesso liberado automaticamente via MP: {chat_id} plano={plano}")


def iniciar_servidor():
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    log.info(f"Webhook server rodando na porta {PORT}")
    server.serve_forever()


def iniciar_em_thread():
    t = threading.Thread(target=iniciar_servidor, daemon=True)
    t.start()
    return t
