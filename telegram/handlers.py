"""
telegram/handlers.py — Processamento de mensagens e callbacks do Telegram.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import time
import threading
from datetime import datetime, date, timedelta

import textos as T
from config import ADMIN_CHAT_ID, PIX_KEY_1MES, PIX_KEY_5MESES, PIX_VALOR_1MES, PIX_VALOR_5MESES, get_logger
from db.usuarios import carregar_usuario, salvar_usuario, carregar_todos_usuarios, salvar_lead_internacional, listar_leads_internacionais
from telegram.bot import (
    enviar, encaminhar_foto_para_admin, encaminhar_documento_para_admin,
    editar_mensagem_markup, is_admin,
)
from telegram.teclados import (
    teclado_planos, teclado_paguei, teclado_liberar_admin,
    teclado_paises, teclado_estados, teclado_aeroportos_estado,
    teclado_aeroportos_pais, teclado_data, teclado_dias,
)
from telegram.aeroportos import BRASIL_ESTADOS, OUTROS_PAISES, AEROPORTOS
from services.pagamento import gerar_pix
from services.monitor import (
    executar_ciclo_usuario, atribuir_slot_manha,
    dias_restantes_assinatura, dias_plano,
)

log = get_logger(__name__)

# ── Helpers de data ───────────────────────────────────────────────────────────

def _iso_para_br(data_iso) -> str:
    if not data_iso:
        return "—"
    a, m, d = data_iso.split("-")
    return f"{d}/{m}/{a}"

def _br_para_iso(data_br: str) -> str:
    d, m, a = data_br.strip().split("-")
    return f"{a}-{m}-{d}"

def validar_data_br(texto: str):
    try:
        d, m, a = texto.strip().split("-")
        if len(d) != 2 or len(m) != 2 or len(a) != 4:
            return None
        return datetime.strptime(f"{a}-{m}-{d}", "%Y-%m-%d").date()
    except Exception:
        return None

# ── Pix info ──────────────────────────────────────────────────────────────────

def pix_info(plano: str):
    if plano == "5meses":
        return PIX_KEY_5MESES, PIX_VALOR_5MESES
    return PIX_KEY_1MES, PIX_VALOR_1MES

# ── Mensagens de texto ────────────────────────────────────────────────────────

def msg_boas_vindas(nome: str) -> str:
    return (
        f"👋 Olá, *{nome}*!\n\n"
        "🤖 Monitoro preços de passagens e aviso quando vale comprar — "
        "analisando histórico, tendência e o momento certo.\n\n"
        "━━━━━━━━━━━━━━━\n"
        "💳 *Como funciona:*\n"
        "1️⃣ Escolha o plano abaixo\n"
        "2️⃣ Faça o Pix\n"
        "3️⃣ Clique em *Paguei* e envie o comprovante\n"
        "4️⃣ Configure sua rota e pronto!\n"
        "━━━━━━━━━━━━━━━\n\n"
        "Escolha seu plano:"
    )

def msg_pix(plano: str) -> str:
    pix_key, pix_valor = pix_info(plano)
    label = "1 mês" if plano == "1mes" else "3 meses"
    return (
        f"✅ *Plano {label} selecionado!*\n\n"
        f"💰 Valor: *{pix_valor}*\n\n"
        f"🔑 *Chave Pix:*\n`{pix_key}`\n\n"
        "_Após o pagamento, clique em Paguei:_"
    )

COMANDOS_USUARIO = (
    "ℹ️ *Comandos:*\n"
    "/status — ver monitoramento\n"
    "/reconfigurar — mudar rota ou datas\n"
    "/parar — pausar alertas\n\n"
    ""
)

# ── Finalização de setup ──────────────────────────────────────────────────────

def _finalizar_setup(chat_id, dados: dict, nome: str) -> None:
    cfg        = dados.get("config", {})
    slot       = atribuir_slot_manha()
    dados["slot_manha"] = slot
    salvar_usuario(chat_id, dados)

    origem     = cfg.get("origem", "?")
    destino    = cfg.get("destino", "?")
    data_ida   = _iso_para_br(cfg.get("data_ida"))
    data_volta = _iso_para_br(cfg.get("data_volta")) if cfg.get("data_volta") else "só ida"

    enviar(int(chat_id),
        f"✅ *Monitoramento configurado!*\n\n"
        f"✈️ {origem} → {destino}\n"
        f"📅 Ida: {data_ida} | Volta: {data_volta}\n\n"
        "🔍 Buscando preços e analisando o histórico dos últimos 60 dias...\n"
        "_Em breve você receberá o primeiro relatório completo._"
    )
    enviar(ADMIN_CHAT_ID,
        f"🆕 *Usuário ativo:* {nome}\nID: `{chat_id}`\n"
        f"Rota: {origem}->{destino}\n"
        f"Datas: {data_ida} / {data_volta}\n"
        f"Plano: {dados.get('plano','1mes')} | Slot: {slot}"
    )

    def busca_inicial():
        time.sleep(2)
        executar_ciclo_usuario(chat_id, modo="completo")

    threading.Thread(target=busca_inicial, daemon=True).start()

# ── Handler principal ─────────────────────────────────────────────────────────

def processar_mensagem(chat_id, texto: str, nome: str, msg_obj=None, callback_data=None) -> None:
    chat_id = str(chat_id)
    dados   = carregar_usuario(chat_id)

    if not dados:
        dados = {
            "nome": nome, "status": "aguardando_pagamento",
            "config": {}, "historico": {}, "historico_precos": {},
            "liberado_em": None, "plano": None,
            "proxima_busca": None, "slot_manha": None,
        }
        salvar_usuario(chat_id, dados)
        if not is_admin(chat_id):
            enviar(ADMIN_CHAT_ID, T.ADMIN_NOVO_USUARIO.format(nome=nome, chat_id=chat_id))

    status = dados["status"]

    # ══════════════════════════════════════════════════════════════════════════
    # CALLBACKS
    # ══════════════════════════════════════════════════════════════════════════
    if callback_data:

        # Admin: liberar via botão inline
        if callback_data.startswith("admin_liberar:") and is_admin(chat_id):
            alvo       = callback_data.split(":", 1)[1]
            dados_alvo = carregar_usuario(alvo) or {
                "nome": "Usuário", "status": "aguardando_pagamento",
                "config": {}, "historico": {}, "historico_precos": {},
                "liberado_em": None, "plano": "1mes",
                "proxima_busca": None, "slot_manha": None,
            }
            dados_alvo["status"]      = "setup_origem"
            dados_alvo["liberado_em"] = datetime.now().isoformat()
            salvar_usuario(alvo, dados_alvo)
            expira = (datetime.now() + timedelta(days=dias_plano(dados_alvo.get("plano", "1mes")))).strftime("%d/%m/%Y")
            enviar(chat_id, T.ADMIN_LIBERADO.format(chat_id=alvo, expira=expira))
            enviar(int(alvo), T.SETUP_LIBERADO, reply_markup=teclado_paises("ori"))
            if msg_obj and msg_obj.get("message_id"):
                editar_mensagem_markup(chat_id, msg_obj["message_id"])
            return

        # Voos internacionais
        if callback_data == "internacional":
            dados["status"] = "lead_internacional"
            salvar_usuario(chat_id, dados)
            enviar(chat_id,
                "🌍 *Voos internacionais*\n\n"
                "Este bot é especializado em voos dentro da América do Sul.\n\n"
                "Mas estamos trabalhando para expandir! Me conta sua rota e "
                "você será um dos primeiros avisados quando lançarmos:\n\n"
                "✏️ Digite sua rota no formato:\n"
                "`Cidade de origem → Cidade de destino`\n\n"
                "Ex: `São Paulo → Lisboa`"
            )
            return

        # Campanha — botão "Começar monitoramento"
        if callback_data == "campanha_iniciar":
            dados["plano"] = None
            salvar_usuario(chat_id, dados)
            enviar(chat_id,
                "✅ Ótima escolha!\n\nEscolha o plano que melhor se encaixa para você:",
                reply_markup=teclado_planos()
            )
            return

        # Escolha de plano — gera QR Code Pix via Mercado Pago
        if callback_data.startswith("plano:"):
            plano          = callback_data.split(":")[1]
            dados["plano"] = plano
            salvar_usuario(chat_id, dados)

            import os as _os
            if _os.getenv("MP_ACCESS_TOKEN"):
                # Gera Pix automático
                enviar(chat_id, "⏳ Gerando seu Pix...")
                pix = gerar_pix(chat_id, nome, plano)
                if pix:
                    label = "1 mês" if plano == "1mes" else "3 meses"
                    enviar(chat_id,
                        f"✅ *Pix gerado — Plano {label}*\n\n"
                        f"💰 Valor: *R$ {pix['valor']:.2f}*\n\n"
                        f"📋 *Código Pix (copia e cola):*\n"
                        f"`{pix['qr_code']}`\n\n"
                        f"⏰ Válido por {pix['expira_em']}\n\n"
                        "_Após o pagamento, a liberação é automática!_"
                    )
                    # Salva payment_id para verificação
                    dados["payment_id"] = str(pix["payment_id"])
                    salvar_usuario(chat_id, dados)
                    return
            # Fallback: fluxo manual se MP não configurado
            enviar(chat_id, msg_pix(plano), reply_markup=teclado_paguei())
            return

        # Botão Paguei
        if callback_data == "paguei":
            if status in ("aguardando_pagamento", "bloqueado"):
                dados["status"] = "aguardando_comprovante"
                salvar_usuario(chat_id, dados)
                enviar(chat_id,
                    "📎 *Quase lá!*\n\n"
                    "Envie o *comprovante de pagamento* (foto ou PDF) "
                    "para confirmarmos e liberar seu acesso. 👇"
                )
            else:
                dias = dias_restantes_assinatura(dados)
                info = f" ({dias} dias restantes)" if dias is not None else ""
                enviar(chat_id, T.JA_TEM_ACESSO.format(info=info))
            return

        # Navegação de aeroporto e data
        if ":" in callback_data:
            _processar_navegacao(chat_id, callback_data, dados, nome, status)
            return

    # ══════════════════════════════════════════════════════════════════════════
    # ADMIN — comandos de texto
    # ══════════════════════════════════════════════════════════════════════════
    if is_admin(chat_id):
        _processar_admin(chat_id, texto, nome, dados, msg_obj)
        return

    # ══════════════════════════════════════════════════════════════════════════
    # AGUARDANDO COMPROVANTE (ou reenvio)
    # ══════════════════════════════════════════════════════════════════════════
    if status in ("aguardando_comprovante", "aguardando_liberacao") and msg_obj:
        if msg_obj.get("photo") or msg_obj.get("document"):
            _processar_comprovante(chat_id, msg_obj, dados, nome, status)
            return

    # ══════════════════════════════════════════════════════════════════════════
    # COMANDOS DO USUÁRIO
    # ══════════════════════════════════════════════════════════════════════════
    _processar_usuario(chat_id, texto, dados, nome, status, msg_obj)


# ── Sub-handlers ──────────────────────────────────────────────────────────────

def _processar_navegacao(chat_id, callback_data, dados, nome, status):
    partes  = callback_data.split(":", 2)
    prefixo = partes[0]
    acao    = partes[1]
    valor   = partes[2] if len(partes) > 2 else ""

    # Aeroportos
    if prefixo in ("ori", "dst"):
        titulo = "Aeroporto de ORIGEM" if prefixo == "ori" else "Aeroporto de DESTINO"
        passo  = "1/4" if prefixo == "ori" else "2/4"

        if acao == "voltar" and valor == "paises":
            enviar(chat_id, f"✈️ *Passo {passo} — {titulo}*\n\nSelecione o país:",
                   reply_markup=teclado_paises(prefixo)); return
        if acao == "voltar" and valor == "estados":
            enviar(chat_id, f"✈️ *Passo {passo} — {titulo}*\n\nSelecione o estado:",
                   reply_markup=teclado_estados(prefixo)); return
        if acao == "pais":
            if valor == "BR":
                enviar(chat_id, f"✈️ *Passo {passo} — {titulo}*\n\nSelecione o estado:",
                       reply_markup=teclado_estados(prefixo))
            else:
                if not OUTROS_PAISES.get(valor):
                    enviar(chat_id, "❌ País não encontrado."); return
                enviar(chat_id, f"✈️ *Passo {passo} — {titulo}*\n\nSelecione o aeroporto:",
                       reply_markup=teclado_aeroportos_pais(prefixo, valor))
            return
        if acao == "uf":
            enviar(chat_id,
                f"✈️ *Passo {passo} — {titulo}*\n\n"
                f"Estado: *{BRASIL_ESTADOS.get(valor, valor)}*\nSelecione o aeroporto:",
                reply_markup=teclado_aeroportos_estado(prefixo, valor)); return
        if acao == "iata":
            iata    = valor.upper()
            nome_ae = AEROPORTOS.get(iata, iata)
            if prefixo == "ori":
                dados["config"]["origem"] = iata
                dados["status"] = "setup_destino"
                salvar_usuario(chat_id, dados)
                enviar(chat_id, f"✅ *Origem:* {iata} — {nome_ae}")
                enviar(chat_id, f"✈️ *Passo 2/4 — Aeroporto de DESTINO*\n\nSelecione o país:",
                       reply_markup=teclado_paises("dst"))
            else:
                if iata == dados["config"].get("origem"):
                    enviar(chat_id, T.DESTINO_IGUAL_ORIGEM,
                           reply_markup=teclado_paises("dst")); return
                dados["config"]["destino"] = iata
                dados["status"] = "setup_data_ida"
                salvar_usuario(chat_id, dados)
                enviar(chat_id, f"✅ *Destino:* {iata} — {nome_ae}")
                enviar(chat_id, "📅 *Passo 3/4 — Data de IDA*\n\nEscolha o mês:",
                       reply_markup=teclado_data("ida"))
            return

    # Datas
    if prefixo in ("ida", "volta"):
        if acao == "manual":
            enviar(chat_id, T.SETUP_DATA_MANUAL_IDA if prefixo == "ida" else T.SETUP_DATA_MANUAL_VOLTA); return
        if acao == "semvolta":
            dados["config"]["data_volta"] = None
            dados["status"]           = "ativo"
            dados["historico"]        = {}
            dados["historico_precos"] = {}
            dados["proxima_busca"]    = None
            salvar_usuario(chat_id, dados)
            _finalizar_setup(chat_id, dados, nome); return
        if acao == "mes":
            dados["config"][f"_mes_{prefixo}"] = valor
            salvar_usuario(chat_id, dados)
            enviar(chat_id, "📅 Escolha o dia:", reply_markup=teclado_dias(prefixo, valor)); return
        if acao == "voltames":
            titulo_p = "IDA" if prefixo == "ida" else "VOLTA"
            enviar(chat_id, f"📅 *Data de {titulo_p}* — Escolha o mês:",
                   reply_markup=teclado_data(prefixo)); return
        if acao == "dia":
            dt = datetime.strptime(valor, "%Y-%m-%d").date()
            if prefixo == "ida":
                if dt <= date.today():
                    enviar(chat_id, "❌ Data no passado.", reply_markup=teclado_data("ida")); return
                dados["config"]["data_ida"] = valor
                dados["status"] = "setup_data_volta"
                salvar_usuario(chat_id, dados)
                enviar(chat_id,
                    f"✅ *Ida:* {_iso_para_br(valor)}\n\n"
                    "📅 *Passo 4/4 — Data de VOLTA*\n\nEscolha o mês:",
                    reply_markup=teclado_data("volta"))
            else:
                dt_ida = datetime.strptime(
                    dados["config"].get("data_ida", "2099-01-01"), "%Y-%m-%d"
                ).date()
                if dt <= dt_ida:
                    enviar(chat_id, "❌ Volta deve ser depois da ida.",
                           reply_markup=teclado_data("volta")); return
                dados["config"]["data_volta"] = valor
                dados["status"]           = "ativo"
                dados["historico"]        = {}
                dados["historico_precos"] = {}
                dados["proxima_busca"]    = None
                salvar_usuario(chat_id, dados)
                _finalizar_setup(chat_id, dados, nome)
            return


def _processar_admin(chat_id, texto, nome, dados, msg_obj=None):
    todos = carregar_todos_usuarios()

    if texto.startswith("/liberar"):
        partes = texto.split()
        if len(partes) < 2:
            enviar(chat_id, T.ADMIN_USO_LIBERAR); return
        alvo       = partes[1]
        dados_alvo = carregar_usuario(alvo) or {
            "nome": "Usuário", "status": "aguardando_pagamento",
            "config": {}, "historico": {}, "historico_precos": {},
            "liberado_em": None, "plano": "1mes", "proxima_busca": None, "slot_manha": None,
        }
        dados_alvo["status"]      = "setup_origem"
        dados_alvo["liberado_em"] = datetime.now().isoformat()
        salvar_usuario(alvo, dados_alvo)
        expira = (datetime.now() + timedelta(days=dias_plano(dados_alvo.get("plano", "1mes")))).strftime("%d/%m/%Y")
        enviar(chat_id, T.ADMIN_LIBERADO.format(chat_id=alvo, expira=expira))
        enviar(int(alvo), T.SETUP_LIBERADO, reply_markup=teclado_paises("ori"))
        return

    if texto.startswith("/resetar"):
        partes = texto.split()
        if len(partes) < 2:
            enviar(chat_id, "❌ Use: `/resetar <chat_id>`"); return
        alvo       = partes[1]
        dados_alvo = carregar_usuario(alvo)
        if not dados_alvo:
            enviar(chat_id, T.ADMIN_NAO_ENCONTRADO.format(chat_id=alvo)); return
        dados_alvo["status"]           = "aguardando_pagamento"
        dados_alvo["liberado_em"]      = None
        dados_alvo["plano"]            = None
        dados_alvo["config"]           = {}
        dados_alvo["historico"]        = {}
        dados_alvo["historico_precos"] = {}
        dados_alvo["proxima_busca"]    = None
        dados_alvo["slot_manha"]       = None
        salvar_usuario(alvo, dados_alvo)
        enviar(chat_id, f"🔄 Usuário `{alvo}` resetado para o início.")
        enviar(int(alvo), "🔄 Sua conta foi resetada.")
        return

    if texto.startswith("/bloquear"):
        partes = texto.split()
        if len(partes) < 2:
            enviar(chat_id, T.ADMIN_USO_BLOQUEAR); return
        alvo       = partes[1]
        dados_alvo = carregar_usuario(alvo)
        if dados_alvo:
            dados_alvo["status"] = "bloqueado"
            salvar_usuario(alvo, dados_alvo)
            enviar(chat_id, T.ADMIN_BLOQUEADO.format(chat_id=alvo))
            enviar(int(alvo), T.ACESSO_SUSPENSO)
        else:
            enviar(chat_id, T.ADMIN_NAO_ENCONTRADO.format(chat_id=alvo))
        return

    if texto.startswith("/usuarios"):
        if not todos:
            enviar(chat_id, T.ADMIN_NENHUM_USUARIO); return
        linhas = ["👥 *Usuários:*\n"]
        for uid, u in todos.items():
            cfg   = u.get("config", {})
            rota  = f"{cfg.get('origem','?')}->{cfg.get('destino','?')}" if cfg.get("origem") else "sem rota"
            dias  = dias_restantes_assinatura(u)
            ass   = f" | {dias}d" if dias is not None else ""
            emoji = "🔴" if (dias is not None and dias <= 3) else ("🟡" if (dias is not None and dias <= 7) else "🟢")
            linhas.append(f"{emoji} `{uid}` {u.get('nome','?')} | {u.get('status','?')} | {rota}{ass}")
        enviar(chat_id, "\n".join(linhas))
        return

    if texto.startswith("/leads"):
        leads = listar_leads_internacionais()
        if not leads:
            enviar(chat_id, "Nenhum lead internacional ainda.")
            return
        linhas = [f"🌍 *Leads internacionais ({len(leads)}):*\n"]
        for l in leads:
            data = l['criado_em'][:10] if l.get('criado_em') else '?'
            linhas.append(f"• {l['nome']} (`{l['chat_id']}`) — {l['destino']} — {data}")
        enviar(chat_id, "\n".join(linhas))
        return

    if texto.startswith("/vencendo"):
        vencendo = [
            (dias_restantes_assinatura(u), uid, u.get("nome", "?"))
            for uid, u in todos.items()
            if u.get("status") == "ativo" and
               dias_restantes_assinatura(u) is not None and
               dias_restantes_assinatura(u) <= 7
        ]
        if not vencendo:
            enviar(chat_id, T.ADMIN_NENHUM_VENCENDO); return
        vencendo.sort()
        linhas = ["⏰ *Assinaturas vencendo em até 7 dias:*\n"]
        for dias, uid, nome_u in vencendo:
            emoji = "🔴" if dias <= 1 else ("🟡" if dias <= 3 else "🟠")
            linhas.append(f"{emoji} `{uid}` {nome_u} — {dias} dia{'s' if dias != 1 else ''}")
        enviar(chat_id, "\n".join(linhas))
        return

    if texto.startswith("/forcarbusca"):
        enviar(chat_id, T.ADMIN_BUSCA_INICIADA)
        for uid, u in todos.items():
            if u.get("status") == "ativo":
                threading.Thread(
                    target=executar_ciclo_usuario, args=(uid, "normal"), daemon=True
                ).start()
                time.sleep(30)
        return

    if texto.startswith("/broadcast "):
        msg_texto = texto[len("/broadcast "):].strip()
        if not msg_texto:
            enviar(chat_id, "❌ Use: `/broadcast <mensagem>`"); return
        enviados = 0
        for uid, u in todos.items():
            if u.get("status") == "ativo":
                enviar(int(uid), msg_texto)
                enviados += 1
                time.sleep(0.3)
        enviar(chat_id, f"✅ Mensagem enviada para *{enviados}* usuário(s) ativos.")
        return

    if texto.startswith("/broadcast_pendentes "):
        msg_texto = texto[len("/broadcast_pendentes "):].strip()
        if not msg_texto:
            enviar(chat_id, "❌ Use: `/broadcast_pendentes <mensagem>`"); return
        enviados = 0
        for uid, u in todos.items():
            if u.get("status") == "aguardando_pagamento":
                enviar(int(uid), msg_texto)
                enviados += 1
                time.sleep(0.3)
        enviar(chat_id, f"✅ Mensagem enviada para *{enviados}* usuário(s) pendentes.")
        return

    if texto.startswith("/broadcast_todos "):
        msg_texto = texto[len("/broadcast_todos "):].strip()
        if not msg_texto:
            enviar(chat_id, "❌ Use: `/broadcast_todos <mensagem>`"); return
        enviados = 0
        for uid, u in todos.items():
            enviar(int(uid), msg_texto)
            enviados += 1
            time.sleep(0.3)
        enviar(chat_id, f"✅ Mensagem enviada para *{enviados}* usuário(s) no total.")
        return

    # /campanha — botão "Começar monitoramento" para pendentes
    if texto == "/campanha":
        markup = {"inline_keyboard": [[
            {"text": "🚀 Começar monitoramento", "callback_data": "campanha_iniciar"}
        ]]}
        enviados = 0
        for uid, u in todos.items():
            if u.get("status") == "aguardando_pagamento":
                enviar(int(uid),
                    "✈️ *Ainda não começou a monitorar suas passagens?*\n\n"
                    "Receba alertas de queda de preço e análise completa do melhor momento para comprar.\n\n"
                    "👇 Clique para começar:",
                    reply_markup=markup
                )
                enviados += 1
                time.sleep(0.3)
        enviar(chat_id, f"✅ Campanha enviada para *{enviados}* pendente(s).")
        return

    # /img_broadcast — envia imagem para grupos
    # Uso: encaminhe uma imagem para o bot com legenda: /img_broadcast ativos|pendentes|todos [texto]
    if texto.startswith("/img_broadcast"):
        enviar(chat_id,
            "📸 Para enviar imagem, encaminhe a foto para mim com a legenda:\n\n"
            "`/img ativos Texto opcional`\n"
            "`/img pendentes Texto opcional`\n"
            "`/img todos Texto opcional`\n"
            "`/img_user <id> Texto opcional`"
        )
        return

    if texto.startswith("/msg "):
        partes = texto.split(" ", 2)
        if len(partes) < 3:
            enviar(chat_id, "❌ Use: `/msg <id> <mensagem>`"); return
        alvo, msg_texto = partes[1], partes[2].strip()
        if not msg_texto:
            enviar(chat_id, "❌ Mensagem vazia."); return
        dados_alvo = carregar_usuario(alvo)
        nome_alvo  = (dados_alvo or {}).get("nome", alvo)
        # Prefixo de suporte se estiver em atendimento
        if dados_alvo and dados_alvo.get("status") == "em_suporte":
            enviar(int(alvo), f"💬 *Suporte:* {msg_texto}")
        else:
            enviar(int(alvo), msg_texto)
        enviar(chat_id, f"✅ Mensagem enviada para *{nome_alvo}* (`{alvo}`).")
        return

    # Envio de imagem pelo admin via legenda
    if msg_obj and msg_obj.get("photo") and is_admin(chat_id):
        legenda = (msg_obj.get("caption") or "").strip()
        file_id = msg_obj["photo"][-1]["file_id"]

        def _enviar_foto_grupo(filtro, caption_extra):
            enviados = 0
            for uid, u in todos.items():
                incluir = (
                    (filtro == "ativos"    and u.get("status") == "ativo") or
                    (filtro == "pendentes" and u.get("status") == "aguardando_pagamento") or
                    (filtro == "todos")
                )
                if incluir:
                    from telegram.bot import encaminhar_foto_para_admin
                    url = f"https://api.telegram.org/bot{__import__('config').TELEGRAM_TOKEN}/sendPhoto"
                    import requests as _req
                    _req.post(url, json={
                        "chat_id": uid,
                        "photo":   file_id,
                        "caption": caption_extra or "",
                        "parse_mode": "Markdown",
                    }, timeout=15)
                    enviados += 1
                    time.sleep(0.3)
            return enviados

        if legenda.startswith("/img "):
            partes  = legenda.split(" ", 2)
            filtro  = partes[1].lower() if len(partes) > 1 else ""
            caption = partes[2] if len(partes) > 2 else ""
            if filtro not in ("ativos", "pendentes", "todos"):
                enviar(chat_id, "❌ Use: `/img ativos|pendentes|todos [texto]`"); return
            n = _enviar_foto_grupo(filtro, caption)
            enviar(chat_id, f"✅ Imagem enviada para *{n}* usuário(s) ({filtro}).")
            return

        if legenda.startswith("/img_user "):
            partes  = legenda.split(" ", 2)
            alvo    = partes[1] if len(partes) > 1 else ""
            caption = partes[2] if len(partes) > 2 else ""
            import requests as _req
            _req.post(
                f"https://api.telegram.org/bot{__import__('config').TELEGRAM_TOKEN}/sendPhoto",
                json={"chat_id": alvo, "photo": file_id,
                      "caption": caption, "parse_mode": "Markdown"},
                timeout=15
            )
            nome_alvo = (carregar_usuario(alvo) or {}).get("nome", alvo)
            enviar(chat_id, f"✅ Imagem enviada para *{nome_alvo}* (`{alvo}`).")
            return

    # Callback campanha_iniciar
    if texto in ("/start", "/ajuda", "/help"):
        enviar(chat_id, T.ADMIN_MENU.format(chat_id=chat_id))


def _processar_comprovante(chat_id, msg_obj, dados, nome, status):
    file_id  = None
    is_photo = False
    if msg_obj.get("photo"):
        file_id  = msg_obj["photo"][-1]["file_id"]
        is_photo = True
    elif msg_obj.get("document"):
        file_id = msg_obj["document"]["file_id"]

    if not file_id:
        enviar(chat_id, "❌ Não consegui ver o comprovante.\nEnvie como *foto* ou *PDF*, por favor.")
        return

    enviar(chat_id,
        "✅ *Comprovante recebido!*\n\n"
        "Já encaminhei para verificação. Você receberá a confirmação em instantes. 🙏\n\n"
        "/suporte"
    )

    era_renovacao   = dados.get("liberado_em") is not None
    dados["status"] = "aguardando_liberacao"
    salvar_usuario(chat_id, dados)

    plano    = dados.get("plano", "1mes")
    label    = "1 mês" if plano == "1mes" else "3 meses"
    tipo_msg = "🔄 RENOVAÇÃO" if era_renovacao else "💸 NOVO PAGAMENTO"
    caption  = (
        f"{tipo_msg}\n\n"
        f"👤 *{nome}*\n"
        f"🆔 `{chat_id}`\n"
        f"📅 Plano: *{label}*\n\n"
        "👇 Confira o comprovante e clique em *Liberar* para ativar."
    )
    markup = teclado_liberar_admin(chat_id)
    if is_photo:
        encaminhar_foto_para_admin(ADMIN_CHAT_ID, file_id, caption, reply_markup=markup)
    else:
        encaminhar_documento_para_admin(ADMIN_CHAT_ID, file_id, caption, reply_markup=markup)


def _processar_usuario(chat_id, texto, dados, nome, status, msg_obj=None):
    if texto == "/start":
        if status == "ativo":
            enviar(chat_id, "✅ Você já está ativo! Use /status para ver seu monitoramento.")
        elif status == "aguardando_comprovante":
            enviar(chat_id, "📎 Envie o comprovante como *foto* ou *PDF*.")
        elif status == "aguardando_liberacao":
            enviar(chat_id, "⏳ Comprovante recebido! Aguarde a liberação.")
        else:
            enviar(chat_id, msg_boas_vindas(nome), reply_markup=teclado_planos())
        return

    if texto == "/status":
        cfg  = dados.get("config", {})
        hist = dados.get("historico", {})
        if status != "ativo":
            enviar(chat_id, T.STATUS_AGUARDANDO.format(status=status)); return
        dias   = dias_restantes_assinatura(dados)
        linhas = [
            "📋 *Seu monitoramento:*\n",
            f"• Origem: `{cfg.get('origem','—')}`",
            f"• Destino: `{cfg.get('destino','—')}`",
            f"• Ida: {_iso_para_br(cfg.get('data_ida'))}",
            f"• Volta: {_iso_para_br(cfg.get('data_volta')) if cfg.get('data_volta') else 'sem volta'}",
        ]
        if dias is not None:
            if dias > 7:    linhas.append(f"\n✅ Assinatura: {dias} dias restantes")
            elif dias > 0:  linhas.append(f"\n🟡 Vence em {dias} dia{'s' if dias > 1 else ''}!")
            else:           linhas.append("\n🔴 Assinatura *expirada*")
        if hist.get("ultima_atualizacao"):
            linhas.append(f"\n🕐 Última busca: {hist['ultima_atualizacao']}")
        if hist.get("preco_ida"):
            linhas.append(f"• Último preço ida: R$ {hist['preco_ida']:.0f}")
        if hist.get("preco_volta"):
            linhas.append(f"• Último preço volta: R$ {hist['preco_volta']:.0f}")
        linhas.append(f"\n{COMANDOS_USUARIO}")
        enviar(chat_id, "\n".join(linhas))
        return

    if texto == "/reconfigurar" and status == "ativo":
        dados["status"]           = "setup_origem"
        dados["config"]           = {}
        dados["historico"]        = {}
        dados["historico_precos"] = {}  # zera seq_alta e preco_anterior da rota antiga
        dados["proxima_busca"]    = None
        salvar_usuario(chat_id, dados)
        enviar(chat_id, T.RECONFIGURAR_INICIO, reply_markup=teclado_paises("ori"))
        return

    if texto == "/suporte":
        cfg  = dados.get("config", {})
        hist = dados.get("historico", {})
        origem  = cfg.get("origem", "—")
        destino = cfg.get("destino", "—")
        rota    = f"{origem}→{destino}" if cfg.get("origem") else "sem rota"
        preco   = f"R$ {hist['preco_ida']:.0f}" if hist.get("preco_ida") else "—"
        # Avisa o admin com a ficha do usuário
        enviar(ADMIN_CHAT_ID,
            f"🆘 *Suporte solicitado*\n\n"
            f"👤 *{nome}*\n"
            f"🆔 `{chat_id}`\n"
            f"📋 Status: `{status}`\n"
            f"✈️ Rota: {rota}\n"
            f"💰 Último preço ida: {preco}\n\n"
            f"_A pessoa vai te chamar agora em @suporteflybot_\n"
            f"_Para responder pelo bot: `/msg {chat_id} <texto>`_"
        )
        # Manda o link para o usuário
        enviar(chat_id,
            "💬 *Suporte*\n\n"
            "Fale diretamente comigo clicando abaixo:\n\n"
            "👉 @suporteflybot\n\n"
            "_Ao me chamar, diga seu nome para eu identificar seu pedido._"
        )
        return

    if texto == "/parar":
        dados["status"] = "bloqueado"
        salvar_usuario(chat_id, dados)
        enviar(chat_id, T.MONITORAMENTO_PAUSADO)
        return

    # /suporte e /fechar disponíveis em QUALQUER status
    # Lead internacional — aguarda texto com rota
    if status == "lead_internacional" and texto and not texto.startswith("/"):
        rota = texto.strip()
        # Salva no banco
        salvar_lead_internacional(chat_id, nome, "", rota)
        # Volta para aguardando pagamento
        dados["status"] = "aguardando_pagamento"
        salvar_usuario(chat_id, dados)
        enviar(chat_id,
            "✅ *Anotado!*\n\n"
            f"Rota registrada: *{rota}*\n\n"
            "Você será um dos primeiros avisados quando lançarmos "
            "o monitoramento internacional. 🌍\n\n"
            "Enquanto isso, que tal monitorar voos dentro da América do Sul?"
        )
        enviar(chat_id, msg_boas_vindas(nome), reply_markup=teclado_planos())
        enviar(ADMIN_CHAT_ID,
            f"🌍 *Novo lead internacional*\n"
            f"👤 {nome} (`{chat_id}`)\n"
            f"✈️ Rota: {rota}"
        )
        return

    # Bloqueios de estado
    if status == "aguardando_pagamento":
        enviar(chat_id, msg_boas_vindas(nome), reply_markup=teclado_planos()); return
    if status == "aguardando_comprovante":
        enviar(chat_id, "📎 Envie o comprovante como *foto* ou *PDF*.\n\n❓ Problema? /suporte → @suporteflybot"); return
    if status == "aguardando_liberacao":
        enviar(chat_id, "⏳ Comprovante recebido! Aguarde a liberação.\n\n❓ Problema? /suporte → @suporteflybot"); return
    if status == "bloqueado":
        enviar(chat_id, T.ACESSO_SUSPENSO); return

    # Setup passo a passo via texto (fallback dos botões)
    if status in ("setup_origem", "setup_destino"):
        prefixo = "ori" if status == "setup_origem" else "dst"
        titulo  = "Aeroporto de ORIGEM" if status == "setup_origem" else "Aeroporto de DESTINO"
        passo   = "1/4" if prefixo == "ori" else "2/4"
        enviar(chat_id, f"✈️ *Passo {passo} — {titulo}*\n\nSelecione o país:",
               reply_markup=teclado_paises(prefixo)); return

    if status == "setup_data_ida":
        dt = validar_data_br(texto)
        if not dt:
            enviar(chat_id, "❌ Formato inválido. Use `DD-MM-AAAA`.", reply_markup=teclado_data("ida")); return
        if dt <= date.today():
            enviar(chat_id, "❌ A data precisa ser futura.", reply_markup=teclado_data("ida")); return
        data_iso = _br_para_iso(texto.strip())
        dados["config"]["data_ida"] = data_iso
        dados["status"] = "setup_data_volta"
        salvar_usuario(chat_id, dados)
        enviar(chat_id,
            f"✅ Ida: *{_iso_para_br(data_iso)}*\n\n"
            "📅 *Passo 4/4 — Data de VOLTA*\n\nEscolha o mês ou digite `DD-MM-AAAA`:",
            reply_markup=teclado_data("volta"))
        return

    if status == "setup_data_volta":
        if texto.strip() == "0":
            dados["config"]["data_volta"] = None
        else:
            dt = validar_data_br(texto)
            if not dt:
                enviar(chat_id, "❌ Formato inválido. Use `DD-MM-AAAA` ou clique em *Só ida*.",
                       reply_markup=teclado_data("volta")); return
            dt_ida = datetime.strptime(
                dados["config"].get("data_ida", "2099-01-01"), "%Y-%m-%d"
            ).date()
            if dt <= dt_ida:
                enviar(chat_id, "❌ A volta precisa ser depois da ida.",
                       reply_markup=teclado_data("volta")); return
            dados["config"]["data_volta"] = _br_para_iso(texto.strip())
        dados["status"] = "ativo"
        salvar_usuario(chat_id, dados)
        _finalizar_setup(chat_id, dados, nome)
        return

    if status == "ativo":
        enviar(chat_id, COMANDOS_USUARIO)
