"""
telegram/handlers.py — Processamento de mensagens e callbacks.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import time
import threading
from datetime import datetime, date, timedelta

import textos as T
from config import ADMIN_CHAT_ID, PLANOS, COMISSAO_MINIMO_SAQUE, MP_ACCESS_TOKEN, get_logger
from db.parceiros import get_ou_criar_parceiro, buscar_parceiro, buscar_parceiro_por_codigo, registrar_acesso, confirmar_venda, solicitar_saque, pagar_saque, listar_saques_pendentes, parceiros_com_saldo, historico_parceiro
from db.financeiro import (relatorio_geral, extrato_recente, afiliados_com_saldo_detalhado,
                           receita_por_plano, confirmar_saque_mov, registrar_saque_mov)
from db.usuarios import (
    carregar_usuario, salvar_usuario, carregar_todos_usuarios,
    salvar_lead_internacional, listar_leads_internacionais,
)
from telegram.bot import (
    enviar, enviar_sem_markdown, encaminhar_foto_para_admin, encaminhar_documento_para_admin,
    editar_mensagem_markup, is_admin,
)
from telegram.teclados import (
    teclado_planos, teclado_paguei, teclado_liberar_admin,
    teclado_paises, teclado_estados, teclado_aeroportos_estado,
    teclado_aeroportos_pais, teclado_data, teclado_dias,
)
from telegram.aeroportos import BRASIL_ESTADOS, OUTROS_PAISES, AEROPORTOS
from services.monitor import (
    executar_ciclo_usuario, atribuir_slot_manha,
    dias_restantes_assinatura, dias_plano,
)
from services.pagamento import gerar_pix

log = get_logger(__name__)

TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "seubot")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _iso_para_br(data_iso) -> str:
    if not data_iso: return "—"
    a, m, d = data_iso.split("-")
    return f"{d}/{m}/{a}"

def _br_para_iso(data_br: str) -> str:
    d, m, a = data_br.strip().split("-")
    return f"{a}-{m}-{d}"

def validar_data_br(texto: str):
    try:
        d, m, a = texto.strip().split("-")
        if len(d)!=2 or len(m)!=2 or len(a)!=4: return None
        return datetime.strptime(f"{a}-{m}-{d}", "%Y-%m-%d").date()
    except: return None

def pix_info(plano: str):
    p = PLANOS.get(plano, PLANOS["60dias"])
    return p["valor"], p["label"]

# ── Mensagens ─────────────────────────────────────────────────────────────────

COMANDOS_USUARIO = (
    "/status · /indicar · /carteira · /suporte · /reconfigurar · /parar"
)

def msg_boas_vindas(nome: str) -> str:
    return (
        f"👋 Olá, *{nome}*!\n\n"
        "🤖 Monitoro preços de passagens e aviso quando vale comprar.\n\n"
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
    from config import PLANOS as P
    p = P.get(plano, P["60dias"])
    # Tenta gerar Pix via Asaas se configurado
    return (
        f"✅ *Plano {p['label']} selecionado!*\n\n"
        f"💰 Valor: *R$ {p['valor']:.2f}*\n\n"
        "Após o pagamento, clique em *Paguei* e envie o comprovante:"
    )

def _finalizar_setup(chat_id, dados: dict, nome: str) -> None:
    cfg  = dados.get("config", {})
    slot = atribuir_slot_manha()
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
        "🔍 Buscando preços e analisando histórico...\n"
        "_Em breve você receberá o primeiro relatório._"
    )
    enviar(ADMIN_CHAT_ID,
        f"🆕 *Usuário ativo:* {nome}\nID: `{chat_id}`\n"
        f"Rota: {origem}->{destino}\nDatas: {data_ida}/{data_volta}\n"
        f"Plano: {dados.get('plano','?')} | Slot: {slot}"
    )
    def busca_inicial():
        time.sleep(2)
        executar_ciclo_usuario(chat_id, modo="completo")
    threading.Thread(target=busca_inicial, daemon=True).start()


# ── Indique e Ganhe ───────────────────────────────────────────────────────────

def _enviar_indique(chat_id: str):
    """Manda a mensagem de parceiro com link exclusivo."""
    parceiro = get_ou_criar_parceiro(chat_id)
    codigo   = parceiro.get("codigo", "")
    bot_user = os.getenv("TELEGRAM_BOT_USERNAME", "seubot").strip()
    log.info(f"BOT_USERNAME lido: '{bot_user}' | codigo: {codigo}")
    link     = f"https://t.me/{bot_user}?start={codigo}"

    comissoes = ""
    for k, p in PLANOS.items():
        com = p.get("comissao", 0)
        if com > 0:
            comissoes += f"• {p['label']} — R$ {com:.2f}\n"


    enviar_sem_markdown(int(chat_id),
        "🚀Que tal faturar uma grana extra com a gente?\n\n"
        "E simples: compartilhe seu link com amigos e ganhe comissão "
        "toda vez que alguem assinar um plano!\n\n"
        f"💰Tabela de comissões:\n{comissoes}\n"
        "Sua comissão é creditada automaticamente assim que a assinatura for confirmada.\n\n"
        f"🔗 Seu link exclusivo (copie e compartilhe):\n{link}"
    )

# ── Handler principal ─────────────────────────────────────────────────────────

def processar_mensagem(chat_id, texto: str, nome: str, msg_obj=None, callback_data=None) -> None:
    nome = nome or 'Usuário'
    chat_id = str(chat_id)
    dados   = carregar_usuario(chat_id)

    # Detecta link de afiliado no /start
    ref_afiliado = None
    if texto and texto.startswith("/start "):
        param = texto.split(" ", 1)[1].strip()
        if param.startswith("REF-"):
            ref_afiliado = param

    if not dados:
        dados = {
            "nome": nome, "status": "aguardando_pagamento",
            "config": {}, "historico": {}, "historico_precos": {},
            "liberado_em": None, "plano": None,
            "proxima_busca": None, "slot_manha": None,
            "ref_afiliado": ref_afiliado,
        }
        salvar_usuario(chat_id, dados)
        if not is_admin(chat_id):
            enviar(ADMIN_CHAT_ID, T.ADMIN_NOVO_USUARIO.format(nome=nome, chat_id=chat_id))
            # Registra rastreamento no novo sistema de parceiros
            if ref_afiliado:
                registrou = registrar_acesso(ref_afiliado, chat_id)
                if registrou:
                    parceiro = buscar_parceiro_por_codigo(ref_afiliado)
                    if parceiro:
                        enviar(ADMIN_CHAT_ID,
                            f"Link de parceiro\n"
                            f"Parceiro: {parceiro.get('nome','')} ({parceiro['chat_id']})\n"
                            f"Indicado: {nome} ({chat_id})"
                        )

    # Registra rastreamento mesmo se usuário já existe
    if ref_afiliado:
        if not dados.get("ref_afiliado"):
            dados["ref_afiliado"] = ref_afiliado
            salvar_usuario(chat_id, dados)
        # Tenta registrar acesso (ignora se já foi registrado)
        registrou = registrar_acesso(ref_afiliado, chat_id)
        if registrou:
            parceiro = buscar_parceiro_por_codigo(ref_afiliado)
            if parceiro and not is_admin(chat_id):
                enviar(ADMIN_CHAT_ID,
                    f"Link de parceiro\n"
                    f"Parceiro: {parceiro.get('nome','')} ({parceiro['chat_id']})\n"
                    f"Indicado: {nome} ({chat_id})"
                )

    status = dados["status"]

    # ── Callbacks ─────────────────────────────────────────────────────────────
    if callback_data:

        if callback_data.startswith("admin_liberar:") and is_admin(chat_id):
            alvo       = callback_data.split(":", 1)[1]
            dados_alvo = carregar_usuario(alvo) or {
                "nome":"Usuário","status":"aguardando_pagamento",
                "config":{},"historico":{},"historico_precos":{},
                "liberado_em":None,"plano":"60dias","proxima_busca":None,"slot_manha":None,
            }
            dados_alvo["status"]      = "setup_origem"
            dados_alvo["liberado_em"] = datetime.now().isoformat()
            salvar_usuario(alvo, dados_alvo)
            expira = (datetime.now() + timedelta(days=dias_plano(dados_alvo.get("plano","60dias")))).strftime("%d/%m/%Y")
            enviar(chat_id, T.ADMIN_LIBERADO.format(chat_id=alvo, expira=expira))
            enviar(int(alvo), T.SETUP_LIBERADO, reply_markup=teclado_paises("ori"))
            if msg_obj and msg_obj.get("message_id"):
                editar_mensagem_markup(chat_id, msg_obj["message_id"])
            return

        if callback_data.startswith("confirmar_saque:") and is_admin(chat_id):
            partes   = callback_data.split(":")
            saque_id = int(partes[1])
            alvo     = partes[2]

            resultado = pagar_saque(saque_id)
            if resultado:
                valor = resultado["valor"]
                chave = resultado["chave_pix"]
                # Remove botão da mensagem
                if msg_obj and msg_obj.get("message_id"):
                    editar_mensagem_markup(chat_id, msg_obj["message_id"])
                enviar(chat_id,
                    f"Pagamento #{saque_id} confirmado!\n"
                    f"Valor: R$ {valor:.2f}\n"
                    f"Parceiro: {alvo}"
                )
                enviar(int(alvo),
                    f"Transferencia recebida!\n\n"
                    f"R$ {valor:.2f} transferido para sua chave Pix ({chave}).\n\n"
                    "Obrigado! Continue indicando e ganhando!"
                )
                # Registra na tabela financeiro
                registrar_saque_mov(alvo, nome, valor, saque_id)
                confirmar_saque_mov(saque_id)
            else:
                enviar(chat_id, f"Saque #{saque_id} nao encontrado.")
                if msg_obj and msg_obj.get("message_id"):
                    editar_mensagem_markup(chat_id, msg_obj["message_id"])
            return

        if callback_data == "configurar_rota":
            enviar(chat_id, T.SETUP_LIBERADO, reply_markup=teclado_paises("ori"))
            return

        if callback_data.startswith("copiar_link:"):
            uid  = callback_data.split(":")[1]
            parc = get_ou_criar_parceiro(uid)
            bot_user = os.getenv("TELEGRAM_BOT_USERNAME", "seubot").strip()
            link = f"https://t.me/{bot_user}?start={parc.get('codigo','')}"
            enviar_sem_markdown(chat_id, f"Seu link:\n{link}")
            return

        if callback_data == "ver_indique":
            _enviar_indique(chat_id)
            return

        if callback_data == "internacional":
            dados["status"] = "lead_internacional"
            salvar_usuario(chat_id, dados)
            enviar(chat_id,
                "🌍 *Voos internacionais*\n\n"
                "Este bot é especializado em voos dentro da América do Sul.\n\n"
                "Mas estamos expandindo! Me conta sua rota e você será um dos "
                "primeiros avisados quando lançarmos:\n\n"
                "✏️ Digite no formato:\n`São Paulo → Lisboa`"
            )
            return

        if callback_data == "campanha_iniciar":
            dados["plano"] = None
            salvar_usuario(chat_id, dados)
            enviar(chat_id, "Escolha seu plano:", reply_markup=teclado_planos())
            return

        if callback_data == "paguei":
            if status in ("aguardando_pagamento", "bloqueado"):
                dados["status"] = "aguardando_comprovante"
                salvar_usuario(chat_id, dados)
                enviar(chat_id,
                    "📎 *Quase lá!*\n\nEnvie o *comprovante* (foto ou PDF) para confirmarmos. 👇\n\n"
                    "❓ Problema? /suporte"
                )
            else:
                dias = dias_restantes_assinatura(dados)
                info = f" ({dias} dias restantes)" if dias is not None else ""
                enviar(chat_id, T.JA_TEM_ACESSO.format(info=info))
            return

        if callback_data.startswith("plano:"):
            plano          = callback_data.split(":")[1]
            dados["plano"] = plano
            salvar_usuario(chat_id, dados)
            p = PLANOS.get(plano, PLANOS["60dias"])

            log.info(f"Plano selecionado: {plano} | MP configurado: {bool(MP_ACCESS_TOKEN)}")

            if MP_ACCESS_TOKEN:
                # Mensagem 1: explica como pagar
                enviar(chat_id,
                    f"✅ *Plano {p['label']} selecionado!*\n\n"
                    f"💰 Valor: *R$ {p['valor']:.2f}*\n\n"
                    "📱 *Como pagar:*\n"
                    "1️⃣ Copie o código Pix abaixo\n"
                    "2️⃣ Abra o app do seu banco\n"
                    "3️⃣ Vá em *Pix → Pix Copia e Cola*\n"
                    "4️⃣ Cole o código e confirme o pagamento\n\n"
                    "⚡ _A liberação é automática após a confirmação!_"
                )
                # Gera o Pix
                enviar(chat_id, "⏳ Gerando seu código Pix...")
                pix = gerar_pix(chat_id, nome, plano)
                if pix:
                    # Mensagem 2: só o código para copiar fácil
                    enviar(chat_id, f"`{pix['pix_code']}`")
                    dados["payment_id"] = pix["payment_id"]
                    dados["status"]     = "aguardando_pagamento_mp"
                    salvar_usuario(chat_id, dados)
                    return
                else:
                    log.warning(f"MP falhou ao gerar Pix para {chat_id}, usando fluxo manual")

            # Fallback: fluxo manual com comprovante
            enviar(chat_id, msg_pix(plano), reply_markup=teclado_paguei())
            return

        if ":" in callback_data:
            _processar_navegacao(chat_id, callback_data, dados, nome, status)
            return

    # ── Admin ──────────────────────────────────────────────────────────────────
    if is_admin(chat_id):
        # Processa comandos admin - se retornar True, o comando foi tratado
        # Se retornar False/None, continua para processar como usuário também
        if _processar_admin(chat_id, texto, nome, dados, msg_obj):
            return

    # ── Comprovante ────────────────────────────────────────────────────────────
    if status in ("aguardando_comprovante", "aguardando_liberacao") and msg_obj:
        if msg_obj.get("photo") or msg_obj.get("document"):
            _processar_comprovante(chat_id, msg_obj, dados, nome, status)
            return

    # ── /suporte global ────────────────────────────────────────────────────────
    if texto == "/suporte":
        cfg  = dados.get("config", {})
        hist = dados.get("historico", {})
        rota = f"{cfg.get('origem','—')}->{cfg.get('destino','—')}" if cfg.get("origem") else "sem rota"
        preco = f"R$ {hist['preco_ida']:.0f}" if hist.get("preco_ida") else "—"
        enviar(ADMIN_CHAT_ID,
            f"🆘 *Pedido de ajuda*\n👤 *{nome}*\n🆔 `{chat_id}`\n"
            f"📋 Status: `{status}`\n✈️ Rota: {rota}\n💰 Último preço: {preco}\n\n"
            f"_Para responder: `/msg {chat_id} <texto>`_"
        )
        enviar(chat_id,
            "💬 *Suporte*\n\nJá recebi seu pedido e respondo em breve.\n\n"
            "Se preferir falar diretamente: @suporteflybot"
        )
        return

    # ── Lead internacional ─────────────────────────────────────────────────────
    if status == "lead_internacional" and texto and not texto.startswith("/"):
        salvar_lead_internacional(chat_id, nome, "", texto.strip())
        dados["status"] = "aguardando_pagamento"
        salvar_usuario(chat_id, dados)
        enviar(chat_id,
            f"✅ *Anotado!* Rota: *{texto.strip()}*\n\n"
            "Você será avisado quando lançarmos. 🌍\n\n"
            "Enquanto isso, que tal monitorar voos na América do Sul?"
        )
        enviar(chat_id, msg_boas_vindas(nome), reply_markup=teclado_planos())
        enviar(ADMIN_CHAT_ID, f"🌍 *Lead internacional*\n👤 {nome} (`{chat_id}`)\n✈️ {texto.strip()}")
        return

    # ── Bloqueios ──────────────────────────────────────────────────────────────
    if texto == "/suporte": return  # já tratado acima
    if status == "aguardando_pagamento":
        enviar(chat_id, msg_boas_vindas(nome), reply_markup=teclado_planos()); return
    if status == "aguardando_pagamento_mp":
        enviar(chat_id,
            "⏳ *Aguardando confirmação do pagamento.*\n\n"
            "Assim que o Pix for confirmado seu acesso é liberado automaticamente. ⚡\n\n"
            "❓ Problema? /suporte"
        ); return
    if status == "aguardando_comprovante":
        enviar(chat_id, "📎 Envie o comprovante como *foto* ou *PDF*.\n\n❓ Problema? /suporte"); return
    if status == "aguardando_liberacao":
        enviar(chat_id, "⏳ Comprovante recebido! Aguarde a liberação.\n\n❓ Problema? /suporte"); return
    if status == "bloqueado":
        enviar(chat_id, T.ACESSO_SUSPENSO); return

    # ── Setup aeroportos ───────────────────────────────────────────────────────
    if status in ("setup_origem", "setup_destino"):
        prefixo = "ori" if status == "setup_origem" else "dst"
        titulo  = "Aeroporto de ORIGEM" if status == "setup_origem" else "Aeroporto de DESTINO"
        passo   = "1/4" if prefixo == "ori" else "2/4"
        enviar(chat_id, f"✈️ *Passo {passo} — {titulo}*\n\nSelecione o país:",
               reply_markup=teclado_paises(prefixo)); return

    # ── Setup datas ────────────────────────────────────────────────────────────
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
            f"✅ Ida: *{_iso_para_br(data_iso)}*\n\n📅 *Passo 4/4 — Data de VOLTA*\n\nEscolha o mês:",
            reply_markup=teclado_data("volta"))
        return

    if status == "setup_data_volta":
        if texto.strip() == "0":
            dados["config"]["data_volta"] = None
        else:
            dt = validar_data_br(texto)
            if not dt:
                enviar(chat_id, "❌ Formato inválido.", reply_markup=teclado_data("volta")); return
            dt_ida = datetime.strptime(
                dados["config"].get("data_ida", "2099-01-01"), "%Y-%m-%d"
            ).date()
            if dt <= dt_ida:
                enviar(chat_id, "❌ A volta precisa ser depois da ida.", reply_markup=teclado_data("volta")); return
            dados["config"]["data_volta"] = _br_para_iso(texto.strip())
        dados["status"] = "ativo"
        dados["historico"] = {}
        dados["historico_precos"] = {}
        dados["proxima_busca"] = None
        salvar_usuario(chat_id, dados)
        _finalizar_setup(chat_id, dados, nome)
        return

    # ── Comandos usuário ativo ─────────────────────────────────────────────────
    _processar_usuario(chat_id, texto, dados, nome, status, msg_obj)


# ── Sub-handlers ──────────────────────────────────────────────────────────────

def _processar_navegacao(chat_id, callback_data, dados, nome, status):
    partes  = callback_data.split(":", 2)
    prefixo = partes[0]
    acao    = partes[1]
    valor   = partes[2] if len(partes) > 2 else ""

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
                f"✈️ *Passo {passo} — {titulo}*\n\nEstado: *{BRASIL_ESTADOS.get(valor,valor)}*\nSelecione o aeroporto:",
                reply_markup=teclado_aeroportos_estado(prefixo, valor)); return
        if acao == "iata":
            iata    = valor.upper()
            nome_ae = AEROPORTOS.get(iata, iata)
            if prefixo == "ori":
                dados["config"]["origem"] = iata
                dados["status"] = "setup_destino"
                salvar_usuario(chat_id, dados)
                enviar(chat_id, f"✅ *Origem:* {iata} — {nome_ae}")
                enviar(chat_id, "✈️ *Passo 2/4 — Aeroporto de DESTINO*\n\nSelecione o país:",
                       reply_markup=teclado_paises("dst"))
            else:
                if iata == dados["config"].get("origem"):
                    enviar(chat_id, T.DESTINO_IGUAL_ORIGEM, reply_markup=teclado_paises("dst")); return
                dados["config"]["destino"] = iata
                dados["status"] = "setup_data_ida"
                salvar_usuario(chat_id, dados)
                enviar(chat_id, f"✅ *Destino:* {iata} — {nome_ae}")
                enviar(chat_id, "📅 *Passo 3/4 — Data de IDA*\n\nEscolha o mês:",
                       reply_markup=teclado_data("ida"))
            return

    if prefixo in ("ida", "volta"):
        if acao == "manual":
            enviar(chat_id, T.SETUP_DATA_MANUAL_IDA if prefixo == "ida" else T.SETUP_DATA_MANUAL_VOLTA); return
        if acao == "semvolta":
            dados["config"]["data_volta"] = None
            dados["status"] = "ativo"
            dados["historico"] = {}
            dados["historico_precos"] = {}
            dados["proxima_busca"] = None
            salvar_usuario(chat_id, dados)
            _finalizar_setup(chat_id, dados, nome); return
        if acao == "mes":
            dados["config"][f"_mes_{prefixo}"] = valor
            salvar_usuario(chat_id, dados)
            enviar(chat_id, "📅 Escolha o dia:", reply_markup=teclado_dias(prefixo, valor)); return
        if acao == "voltames":
            titulo_p = "IDA" if prefixo == "ida" else "VOLTA"
            enviar(chat_id, f"📅 *Data de {titulo_p}* — Escolha o mês:", reply_markup=teclado_data(prefixo)); return
        if acao == "dia":
            dt = datetime.strptime(valor, "%Y-%m-%d").date()
            if prefixo == "ida":
                if dt <= date.today():
                    enviar(chat_id, "❌ Data no passado.", reply_markup=teclado_data("ida")); return
                dados["config"]["data_ida"] = valor
                dados["status"] = "setup_data_volta"
                salvar_usuario(chat_id, dados)
                enviar(chat_id,
                    f"✅ *Ida:* {_iso_para_br(valor)}\n\n📅 *Passo 4/4 — Data de VOLTA*\n\nEscolha o mês:",
                    reply_markup=teclado_data("volta"))
            else:
                dt_ida = datetime.strptime(
                    dados["config"].get("data_ida", "2099-01-01"), "%Y-%m-%d"
                ).date()
                if dt <= dt_ida:
                    enviar(chat_id, "❌ Volta deve ser depois da ida.", reply_markup=teclado_data("volta")); return
                dados["config"]["data_volta"] = valor
                dados["status"] = "ativo"
                dados["historico"] = {}
                dados["historico_precos"] = {}
                dados["proxima_busca"] = None
                salvar_usuario(chat_id, dados)
                _finalizar_setup(chat_id, dados, nome)
            return


def _processar_admin(chat_id, texto, nome, dados, msg_obj=None):
    todos = carregar_todos_usuarios()

    if texto.startswith("/resetar"):
        partes = texto.split()
        if len(partes) < 2:
            enviar(chat_id, "❌ Use: `/resetar <chat_id>`"); return
        alvo = partes[1]
        dados_alvo = carregar_usuario(alvo)
        if not dados_alvo:
            enviar(chat_id, T.ADMIN_NAO_ENCONTRADO.format(chat_id=alvo)); return
        dados_alvo.update({"status":"aguardando_pagamento","liberado_em":None,"plano":None,
            "config":{},"historico":{},"historico_precos":{},"proxima_busca":None,"slot_manha":None})
        salvar_usuario(alvo, dados_alvo)
        enviar(chat_id, f"🔄 Usuário `{alvo}` resetado.")
        enviar(int(alvo), "🔄 Sua conta foi resetada.")
        return True

    if texto.startswith("/liberar"):
        partes = texto.split()
        if len(partes) < 2:
            enviar(chat_id, T.ADMIN_USO_LIBERAR); return
        alvo       = partes[1]
        dados_alvo = carregar_usuario(alvo) or {
            "nome":"Usuário","status":"aguardando_pagamento",
            "config":{},"historico":{},"historico_precos":{},
            "liberado_em":None,"plano":"60dias","proxima_busca":None,"slot_manha":None,
        }
        dados_alvo["status"]      = "setup_origem"
        dados_alvo["liberado_em"] = datetime.now().isoformat()
        salvar_usuario(alvo, dados_alvo)
        expira = (datetime.now() + timedelta(days=dias_plano(dados_alvo.get("plano","60dias")))).strftime("%d/%m/%Y")
        enviar(chat_id, T.ADMIN_LIBERADO.format(chat_id=alvo, expira=expira))
        enviar(int(alvo), T.SETUP_LIBERADO, reply_markup=teclado_paises("ori"))
        # Confirma comissão
        from db.usuarios import confirmar_comissao
        resultado = confirmar_comissao(alvo)
        if resultado:
            af_id = resultado["afiliado_id"]
            comissao = resultado["comissao"]
            af_info = buscar_parceiro(af_id) or {}
            enviar(int(af_id),
                f"🎉 *Comissão recebida!*\nR$ {comissao:.2f} na sua carteira!\n"
                f"Saldo: R$ {af_info.get('saldo',comissao):.2f}\n\nUse /indique e ganhe"
            )
        return True

    if texto == "/financeiro":
        r = relatorio_geral()
        por_plano = receita_por_plano()
        linhas_plano = ""
        for p in por_plano:
            linhas_plano += f"  {p['plano']}: {p['qtd']}x  R$ {p['total']:.2f}\n"
        msg = (
            f"Resumo Financeiro\n"
            f"{'='*20}\n\n"
            f"Receita total: R$ {r['receita_total']:.2f}\n"
            f"Assinaturas: {r['total_assinaturas']}\n\n"
            f"Comissoes a pagar: R$ {r['comissoes_pendentes']:.2f}\n"
            f"Comissoes pagas: R$ {r['comissoes_pagas']:.2f}\n"
            f"Saques pendentes: R$ {r['saques_pendentes_valor']:.2f}\n\n"
            f"Lucro liquido: R$ {r['lucro_liquido']:.2f}\n\n"
            f"Parceiros com saldo: {r['afiliados_com_saldo']}\n\n"
            f"Por plano:\n{linhas_plano}\n"
            "/extrato   /afiliados saldo   /pagar saque"
        )
        enviar(chat_id, msg)
        return True

    if texto == "/extrato":
        movs = extrato_recente(30)
        if not movs:
            enviar(chat_id, "Nenhuma movimentacao ainda."); return
        EMOJI  = {"receita": "+", "comissao": "-", "saque": "-"}
        linhas = ["Ultimas 30 movimentacoes:\n"]
        for m in movs:
            dt    = m["criado_em"][:10]
            sinal = EMOJI.get(m["tipo"], "")
            linhas.append(f"{dt} | {m['tipo']} | {sinal}R$ {m['valor']:.2f} | {m['status']}\n{m['descricao']}")
        enviar(chat_id, "\n\n".join(linhas))
        return True

    if texto == "/afiliados_saldo":
        lista = afiliados_com_saldo_detalhado()
        if not lista:
            enviar(chat_id, "Nenhum afiliado com saldo pendente."); return
        total_devido = sum(a["saldo"] for a in lista)
        linhas = [f"Afiliados com saldo a pagar\nTotal: R$ {total_devido:.2f}\n"]
        for a in lista:
            nome_af = a.get("nome") or a["chat_id"]
            pix     = a.get("chave_pix") or "sem saque solicitado"
            linhas.append(
                f"• {nome_af} ({a['chat_id']})\n"
                f"  Saldo: R$ {a['saldo']:.2f} | Confirmados: {a['total_pagantes']}\n"
                f"  Pix: {pix}"
            )
        enviar(chat_id, "\n".join(linhas))
        return True

    if texto.startswith("/pagar_saque"):
        partes = texto.split()
        if len(partes) < 2:
            enviar(chat_id, "Use: /pagar_saque <saque_id>"); return
        try:
            saque_id = int(partes[1])
            confirmar_saque_mov(saque_id)
            from db.usuarios import confirmar_saque
            confirmar_saque(saque_id)
            enviar(chat_id, f"Saque #{saque_id} marcado como pago.")
        except Exception as e:
            enviar(chat_id, f"Erro: {e}")
        return True

    if texto.startswith("/bloquear"):
        partes = texto.split()
        if len(partes) < 2:
            enviar(chat_id, T.ADMIN_USO_BLOQUEAR); return
        alvo = partes[1]
        dados_alvo = carregar_usuario(alvo)
        if dados_alvo:
            dados_alvo["status"] = "bloqueado"
            salvar_usuario(alvo, dados_alvo)
            enviar(chat_id, T.ADMIN_BLOQUEADO.format(chat_id=alvo))
            enviar(int(alvo), T.ACESSO_SUSPENSO)
        else:
            enviar(chat_id, T.ADMIN_NAO_ENCONTRADO.format(chat_id=alvo))
        return True

    if texto.startswith("/usuarios"):
        if not todos:
            enviar(chat_id, T.ADMIN_NENHUM_USUARIO); return
        from services.monitor import dias_restantes_assinatura as dra
        ativos    = 0
        pendentes = 0
        linhas    = ["Usuarios:\n"]
        for uid, u in todos.items():
            cfg    = u.get("config", {})
            rota   = f"{cfg.get('origem','?')}->{cfg.get('destino','?')}" if cfg.get("origem") else "sem rota"
            dias   = dra(u)
            ass    = f" {dias}d" if dias is not None else ""
            status = u.get("status","?")
            emoji  = "🔴" if (dias is not None and dias<=3) else ("🟡" if (dias is not None and dias<=7) else "🟢")
            if status == "ativo": ativos += 1
            else: pendentes += 1
            nome_u = (u.get("nome") or "?").replace("*","").replace("`","").replace("_","")
            linhas.append(f"{emoji} {uid} {nome_u} {status} {rota}{ass}")
        linhas.insert(1, f"Ativos: {ativos} | Pendentes: {pendentes}\n")
        # Envia em blocos de 30 para não ultrapassar limite do Telegram
        bloco = []
        for i, linha in enumerate(linhas):
            bloco.append(linha)
            if len(bloco) >= 30:
                enviar(chat_id, "\n".join(bloco))
                bloco = []
        if bloco:
            enviar(chat_id, "\n".join(bloco))
        return True

    if texto.startswith("/vencendo"):
        from services.monitor import dias_restantes_assinatura as dra
        vencendo = [(dra(u), uid, u.get("nome","?")) for uid,u in todos.items()
                    if u.get("status")=="ativo" and dra(u) is not None and dra(u)<=7]
        if not vencendo:
            enviar(chat_id, T.ADMIN_NENHUM_VENCENDO); return
        vencendo.sort()
        linhas = ["⏰ *Vencendo em até 7 dias:*\n"]
        for dias, uid, nome_u in vencendo:
            emoji = "🔴" if dias<=1 else ("🟡" if dias<=3 else "🟠")
            linhas.append(f"{emoji} `{uid}` {nome_u} — {dias}d")
        enviar(chat_id, "\n".join(linhas))
        return True

    if texto.startswith("/afiliados"):
        lista = parceiros_com_saldo()
        if not lista:
            enviar(chat_id, "Nenhum parceiro com saldo ainda."); return
        linhas = ["Parceiros com saldo:\n"]
        for a in lista:
            linhas.append(
                f"• {a.get('nome','?')} ({a['chat_id']})\n"
                f"  Codigo: {a['codigo']} | Vendas: {a['total_vendas']} | Saldo: R$ {a['saldo']:.2f}"
            )
        enviar(chat_id, "\n".join(linhas))
        return True

    if texto.startswith("/leads"):
        leads = listar_leads_internacionais()
        if not leads:
            enviar(chat_id, "Nenhum lead internacional ainda."); return
        linhas = [f"🌍 *Leads internacionais ({len(leads)}):*\n"]
        for l in leads:
            data = l['criado_em'][:10] if l.get('criado_em') else '?'
            linhas.append(f"• {l['nome']} (`{l['chat_id']}`) — {l['destino']} — {data}")
        enviar(chat_id, "\n".join(linhas))
        return True

    if texto.startswith("/forcarbusca"):
        enviar(chat_id, T.ADMIN_BUSCA_INICIADA)
        for uid, u in todos.items():
            if u.get("status") == "ativo":
                threading.Thread(target=executar_ciclo_usuario, args=(uid,"normal"), daemon=True).start()
                time.sleep(30)
        return True

    if texto.startswith("/broadcast "):
        msg_texto = texto[len("/broadcast "):].strip()
        if not msg_texto:
            enviar(chat_id, "❌ Use: `/broadcast <mensagem>`"); return
        enviados = sum(1 for uid,u in todos.items() if u.get("status")=="ativo" and not enviar(int(uid), msg_texto) is None and not time.sleep(0.3))
        enviar(chat_id, f"✅ Enviado para *{sum(1 for u in todos.values() if u.get('status')=='ativo')}* ativos.")
        return True

    if texto.startswith("/broadcast_pendentes "):
        msg_texto = texto[len("/broadcast_pendentes "):].strip()
        enviados = 0
        for uid, u in todos.items():
            if u.get("status") == "aguardando_pagamento":
                enviar(int(uid), msg_texto); enviados += 1; time.sleep(0.3)
        enviar(chat_id, f"✅ Enviado para *{enviados}* pendentes.")
        return True

    if texto.startswith("/broadcast_todos "):
        msg_texto = texto[len("/broadcast_todos "):].strip()
        enviados = 0
        for uid in todos:
            enviar(int(uid), msg_texto); enviados += 1; time.sleep(0.3)
        enviar(chat_id, f"✅ Enviado para *{enviados}* usuários.")
        return True

    if texto.startswith("/campanha"):
        markup = {"inline_keyboard": [[{"text": "🚀 Começar monitoramento", "callback_data": "campanha_iniciar"}]]}
        enviados = 0
        for uid, u in todos.items():
            if u.get("status") == "aguardando_pagamento":
                enviar(int(uid),
                    "✈️ *Ainda não começou a monitorar suas passagens?*\n\n"
                    "Receba alertas de queda e análise do melhor momento para comprar.\n\n"
                    "👇 Clique para começar:",
                    reply_markup=markup); enviados += 1; time.sleep(0.3)
        enviar(chat_id, f"✅ Campanha enviada para *{enviados}* pendentes.")
        return True

    if texto.startswith("/msg "):
        partes = texto.split(" ", 2)
        if len(partes) < 3:
            enviar(chat_id, "❌ Use: `/msg <id> <mensagem>`"); return
        alvo, msg_texto = partes[1], partes[2].strip()
        dados_alvo = carregar_usuario(alvo)
        nome_alvo  = (dados_alvo or {}).get("nome", alvo)
        enviar(int(alvo), msg_texto)
        enviar(chat_id, f"✅ Mensagem enviada para *{nome_alvo}* (`{alvo}`).")
        return True

    if msg_obj and msg_obj.get("photo") and is_admin(chat_id):
        legenda = (msg_obj.get("caption") or "").strip()
        file_id = msg_obj["photo"][-1]["file_id"]
        def _enviar_foto_grupo(filtro, caption_extra):
            enviados = 0
            for uid, u in todos.items():
                incluir = (
                    (filtro=="ativos"    and u.get("status")=="ativo") or
                    (filtro=="pendentes" and u.get("status")=="aguardando_pagamento") or
                    filtro=="todos"
                )
                if incluir:
                    import requests as _req
                    _req.post(
                        f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN','')}/sendPhoto",
                        json={"chat_id":uid,"photo":file_id,"caption":caption_extra or "","parse_mode":"Markdown"},
                        timeout=15
                    ); enviados += 1; time.sleep(0.3)
            return enviados
        if legenda.startswith("/img "):
            partes = legenda.split(" ", 2)
            filtro  = partes[1].lower() if len(partes)>1 else ""
            caption = partes[2] if len(partes)>2 else ""
            if filtro not in ("ativos","pendentes","todos"):
                enviar(chat_id, "❌ Use: `/img ativos|pendentes|todos [texto]`"); return
            n = _enviar_foto_grupo(filtro, caption)
            enviar(chat_id, f"✅ Imagem enviada para *{n}* usuários ({filtro}).")
            return True
        if legenda.startswith("/img_user "):
            partes  = legenda.split(" ", 2)
            alvo    = partes[1] if len(partes)>1 else ""
            caption = partes[2] if len(partes)>2 else ""
            import requests as _req
            _req.post(
                f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN','')}/sendPhoto",
                json={"chat_id":alvo,"photo":file_id,"caption":caption,"parse_mode":"Markdown"},
                timeout=15
            )
            nome_alvo = (carregar_usuario(alvo) or {}).get("nome", alvo)
            enviar(chat_id, f"✅ Imagem enviada para *{nome_alvo}* (`{alvo}`).")
            return True

    if texto in ("/start", "/ajuda", "/help"):
        enviar(chat_id,
            "🛠️ *Admin — Comandos:*\n\n"
            "`/liberar <id>` — ativa/renova\n"
            "`/bloquear <id>` — suspende\n"
            "`/resetar <id>` — volta ao início\n"
            "`/usuarios` — lista todos\n"
            "`/vencendo` — assinaturas vencendo\n"
            "`/afiliados` — saldos a pagar\n"
            "`/leads` — leads internacionais\n"
            "`/forcarbusca` — busca imediata\n"
            "`/broadcast <msg>` — ativos\n"
            "`/broadcast_pendentes <msg>` — pendentes\n"
            "`/broadcast_todos <msg>` — todos\n"
            "`/campanha` — botão para pendentes\n"
            "`/msg <id> <msg>` — mensagem individual\n"
            "`/img ativos|pendentes|todos [txt]` — foto em massa\n"
            "`/img_user <id> [txt]` — foto individual\n\n"
            f"Seu ID: `{chat_id}`"
        )
        return True  # comando admin tratado

    return False  # não era comando admin, continua como usuário


def _processar_comprovante(chat_id, msg_obj, dados, nome, status):
    file_id  = None
    is_photo = False
    if msg_obj.get("photo"):
        file_id = msg_obj["photo"][-1]["file_id"]; is_photo = True
    elif msg_obj.get("document"):
        file_id = msg_obj["document"]["file_id"]
    if not file_id:
        enviar(chat_id, "❌ Envie como *foto* ou *PDF*."); return
    enviar(chat_id,
        "✅ *Comprovante recebido!*\n\n"
        "Já encaminhei para verificação. Você receberá a confirmação em instantes. 🙏\n\n"
        "/suporte"
    )
    era_renovacao   = dados.get("liberado_em") is not None
    dados["status"] = "aguardando_liberacao"
    salvar_usuario(chat_id, dados)
    plano   = dados.get("plano", "60dias")
    p       = PLANOS.get(plano, PLANOS["60dias"])
    tipo    = "🔄 RENOVAÇÃO" if era_renovacao else "💸 NOVO PAGAMENTO"
    caption = (
        f"{tipo}\n\n👤 *{nome}*\n🆔 `{chat_id}`\n📅 Plano: *{p['label']}*\n\n"
        "👇 Confirme e clique em *Liberar*:"
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
        elif status in ("aguardando_comprovante",):
            enviar(chat_id, "📎 Envie o comprovante como *foto* ou *PDF*.")
        elif status == "aguardando_liberacao":
            enviar(chat_id, "⏳ Aguarde a liberação.")
        else:
            enviar(chat_id, msg_boas_vindas(nome), reply_markup=teclado_planos())
        return

    if texto == "/status":
        cfg  = dados.get("config", {})
        hist = dados.get("historico", {})
        if status != "ativo":
            enviar(chat_id, T.STATUS_AGUARDANDO.format(status=status)); return
        from services.monitor import dias_restantes_assinatura as dra
        dias   = dra(dados)
        linhas = [
            "📋 *Seu monitoramento:*\n",
            f"• Origem: `{cfg.get('origem','—')}`",
            f"• Destino: `{cfg.get('destino','—')}`",
            f"• Ida: {_iso_para_br(cfg.get('data_ida'))}",
            f"• Volta: {_iso_para_br(cfg.get('data_volta')) if cfg.get('data_volta') else 'sem volta'}",
        ]
        if dias is not None:
            if dias > 7:   linhas.append(f"\n✅ Assinatura: {dias} dias restantes")
            elif dias > 0: linhas.append(f"\n🟡 Vence em {dias} dia{'s' if dias>1 else ''}!")
            else:          linhas.append("\n🔴 Assinatura *expirada*")
        if hist.get("ultima_atualizacao"):
            linhas.append(f"\n🕐 Última busca: {hist['ultima_atualizacao']}")
        if hist.get("preco_ida"):
            linhas.append(f"• Último preço ida: R$ {hist['preco_ida']:.0f}")
        if hist.get("preco_volta"):
            linhas.append(f"• Último preço volta: R$ {hist['preco_volta']:.0f}")
        linhas.append(f"\n{COMANDOS_USUARIO}")
        enviar(chat_id, "\n".join(linhas))
        return

    if texto in ("/indique e ganhe", "/indique", "/indicar"):
        _enviar_indique(chat_id)
        return

    if texto == "/carteira":
        hist = historico_parceiro(chat_id)
        if not hist:
            get_ou_criar_parceiro(chat_id, nome)
            hist = historico_parceiro(chat_id)
        saldo    = hist.get("saldo", 0.0)
        total    = hist.get("total_ganho", 0.0)
        vendas   = hist.get("total_vendas", 0)
        acessos  = hist.get("total_acessos", 0)
        enviar(chat_id,
            f"💳 Sua carteira\n\n"
            f"• Acessos via link: {acessos}\n"
            f"• Vendas confirmadas: {vendas}\n"
            f"• Total ganho: R$ {total:.2f}\n"
            f"• Saldo disponivel: R$ {saldo:.2f}\n\n"
            + (f"Use /sacar para transferir seu saldo."
               if saldo >= COMISSAO_MINIMO_SAQUE
               else f"Minimo para saque: R$ {COMISSAO_MINIMO_SAQUE:.2f}\n\n"
                    f"Continue indicando! Use /indicar para pegar seu link.")
        )
        return

    if texto == "/sacar":
        parceiro = buscar_parceiro(chat_id)
        saldo_disp = parceiro.get("saldo", 0) if parceiro else 0
        if saldo_disp < COMISSAO_MINIMO_SAQUE:
            enviar(chat_id,
                f"Saldo insuficiente para saque.\n"
                f"Minimo: R$ {COMISSAO_MINIMO_SAQUE:.2f}\n"
                f"Seu saldo: R$ {saldo_disp:.2f}\n\n"
                "Use /indicar para pegar seu link e ganhar comissoes."
            ); return
        dados["status_temp"] = "aguardando_chave_pix"
        salvar_usuario(chat_id, dados)
        enviar(chat_id,
            f"Saque — R$ {saldo_disp:.2f}\n\n"
            "Digite sua chave Pix para receber:"
        )
        return

    if dados.get("status_temp") == "aguardando_chave_pix" and texto and not texto.startswith("/"):
        chave_pix = texto.strip()
        dados.pop("status_temp", None)
        salvar_usuario(chat_id, dados)

        # Registra saque e zera saldo no banco
        resultado_saque = solicitar_saque(chat_id, chave_pix)

        if not resultado_saque:
            enviar(chat_id,
                f"Saldo insuficiente para saque.\n"
                f"Minimo: R$ {COMISSAO_MINIMO_SAQUE:.2f}"
            ); return

        saque_id = resultado_saque["id"]
        valor    = resultado_saque["valor"]

        # Confirma para o parceiro
        enviar(chat_id,
            f"Solicitacao de saque enviada!\n\n"
            f"Valor: R$ {valor:.2f}\n"
            f"Chave Pix: {chave_pix}\n\n"
            "Voce recebera a transferencia em breve."
        )

        # Notifica admin com botão de confirmar
        markup = {"inline_keyboard": [[
            {"text": "✅ Confirmar pagamento", "callback_data": f"confirmar_saque:{saque_id}:{chat_id}"}
        ]]}
        enviar(ADMIN_CHAT_ID,
            f"SAQUE SOLICITADO\n\n"
            f"Parceiro: {nome}\n"
            f"ID: {chat_id}\n"
            f"Valor: R$ {valor:.2f}\n"
            f"Chave Pix: {chave_pix}\n\n"
            f"Saque ID: #{saque_id}",
            reply_markup=markup
        )
        return

    if texto == "/reconfigurar" and status == "ativo":
        dados["status"] = "setup_origem"
        dados["config"] = {}
        dados["historico"] = {}
        dados["historico_precos"] = {}
        dados["proxima_busca"] = None
        salvar_usuario(chat_id, dados)
        enviar(chat_id, T.RECONFIGURAR_INICIO, reply_markup=teclado_paises("ori"))
        return

    if texto == "/parar":
        dados["status"] = "bloqueado"
        salvar_usuario(chat_id, dados)
        enviar(chat_id, T.MONITORAMENTO_PAUSADO)
        return

    if status == "ativo":
        enviar(chat_id, COMANDOS_USUARIO)
