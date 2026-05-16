"""
telegram/handlers.py — Processamento de mensagens e callbacks.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import time
import threading
from datetime import datetime, date, timedelta

import textos as T
from config import ADMIN_CHAT_ID, PLANOS, COMISSAO_MINIMO_SAQUE, ASAAS_API_KEY, get_logger
from db.usuarios import (
    carregar_usuario, salvar_usuario, carregar_todos_usuarios,
    salvar_lead_internacional, listar_leads_internacionais,
    criar_afiliado, buscar_afiliado, buscar_afiliado_por_codigo,
    registrar_indicacao, registrar_novo_indicado, zerar_saldo_afiliado,
    listar_afiliados_com_saldo,
)
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
    "/status · /indique e ganhe · /suporte · /reconfigurar · /parar"
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
            # Registra indicação pendente
            if ref_afiliado:
                af = buscar_afiliado_por_codigo(ref_afiliado)
                if af:
                    registrar_novo_indicado(af["chat_id"])
                    enviar(ADMIN_CHAT_ID,
                        f"🔗 *Novo indicado via afiliado*\n"
                        f"Afiliado: `{af['chat_id']}` ({ref_afiliado})\n"
                        f"Indicado: {nome} (`{chat_id}`)"
                    )

    # Atualiza ref_afiliado se veio via link
    if ref_afiliado and not dados.get("ref_afiliado"):
        dados["ref_afiliado"] = ref_afiliado
        salvar_usuario(chat_id, dados)

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
            # Confirma comissão do afiliado
            from db.usuarios import confirmar_comissao
            resultado = confirmar_comissao(alvo)
            if resultado:
                af_id    = resultado["afiliado_id"]
                comissao = resultado["comissao"]
                af_dados = carregar_usuario(af_id) or {}
                af_nome  = af_dados.get("nome", af_id)
                af_info  = buscar_afiliado(af_id)
                enviar(int(af_id),
                    f"🎉 *Você ganhou uma comissão!*\n\n"
                    f"Seu indicado acabou de assinar.\n"
                    f"💰 *R$ {comissao:.2f}* adicionados à sua carteira!\n\n"
                    f"Saldo atual: R$ {af_info.get('saldo', comissao):.2f}\n\n"
                    "Use /indique e ganhe para ver sua carteira."
                )
                enviar(ADMIN_CHAT_ID,
                    f"💰 *Comissão gerada*\nAfiliado: {af_nome} (`{af_id}`)\n"
                    f"Valor: R$ {comissao:.2f}"
                )
            if msg_obj and msg_obj.get("message_id"):
                editar_mensagem_markup(chat_id, msg_obj["message_id"])
            return

        if callback_data.startswith("admin_pago:") and is_admin(chat_id):
            alvo = callback_data.split(":", 1)[1]
            af   = buscar_afiliado(alvo)
            if af:
                saldo = af.get("saldo", 0)
                zerar_saldo_afiliado(alvo)
                enviar(chat_id, f"✅ Saldo de R$ {saldo:.2f} zerado para `{alvo}`.")
                enviar(int(alvo),
                    f"✅ *Transferência recebida!*\n\n"
                    f"R$ {saldo:.2f} foi transferido para sua chave Pix.\n"
                    "Obrigado! Continue indicando 🚀"
                )
                if msg_obj and msg_obj.get("message_id"):
                    editar_mensagem_markup(chat_id, msg_obj["message_id"])
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

        if ":" in callback_data:
            _processar_navegacao(chat_id, callback_data, dados, nome, status)
            return

        if callback_data.startswith("plano:"):
            plano          = callback_data.split(":")[1]
            dados["plano"] = plano
            salvar_usuario(chat_id, dados)
            # Tenta gerar Pix via Asaas
            log.info(f"Plano selecionado: {plano} | Asaas configurado: {bool(ASAAS_API_KEY)}")
            if ASAAS_API_KEY:
                enviar(chat_id, "⏳ Gerando seu Pix...")
                pix = gerar_pix(chat_id, nome, plano)
                if pix:
                    p = PLANOS[plano]
                    enviar(chat_id,
                        f"✅ *Plano {p['label']} — R$ {p['valor']:.2f}*\n\n"
                        f"📋 *Código Pix (copia e cola):*\n`{pix['pix_code']}`\n\n"
                        f"⏰ Válido por {pix['expira_em']}\n\n"
                        "_Após o pagamento, a liberação é automática!_ ⚡\n\n"
                        "❓ Problema? /suporte",
                    )
                    dados["payment_id"] = pix["payment_id"]
                    salvar_usuario(chat_id, dados)
                    return
            enviar(chat_id, msg_pix(plano), reply_markup=teclado_paguei())
            return

    # ── Admin ──────────────────────────────────────────────────────────────────
    if is_admin(chat_id):
        _processar_admin(chat_id, texto, nome, dados, msg_obj)
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
        return

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
            af_info = buscar_afiliado(af_id)
            enviar(int(af_id),
                f"🎉 *Comissão recebida!*\nR$ {comissao:.2f} na sua carteira!\n"
                f"Saldo: R$ {af_info.get('saldo',comissao):.2f}\n\nUse /indique e ganhe"
            )
        return

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
        return

    if texto.startswith("/usuarios"):
        if not todos:
            enviar(chat_id, T.ADMIN_NENHUM_USUARIO); return
        from services.monitor import dias_restantes_assinatura as dra
        linhas = ["👥 *Usuários:*\n"]
        for uid, u in todos.items():
            cfg   = u.get("config", {})
            rota  = f"{cfg.get('origem','?')}->{cfg.get('destino','?')}" if cfg.get("origem") else "sem rota"
            dias  = dra(u)
            ass   = f" | {dias}d" if dias is not None else ""
            emoji = "🔴" if (dias is not None and dias<=3) else ("🟡" if (dias is not None and dias<=7) else "🟢")
            linhas.append(f"{emoji} `{uid}` {u.get('nome','?')} | {u.get('status','?')} | {rota}{ass}")
        enviar(chat_id, "\n".join(linhas))
        return

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
        return

    if texto.startswith("/afiliados"):
        lista = listar_afiliados_com_saldo()
        if not lista:
            enviar(chat_id, "Nenhum afiliado com saldo ainda."); return
        linhas = ["💰 *Afiliados:*\n"]
        for a in lista:
            linhas.append(
                f"• `{a['chat_id']}` {a.get('nome','?')} | "
                f"Código: {a['codigo']} | "
                f"Indicados: {a['total_indicados']} | "
                f"Pagantes: {a['total_pagantes']} | "
                f"Saldo: R$ {a['saldo']:.2f}"
            )
        enviar(chat_id, "\n".join(linhas))
        return

    if texto.startswith("/leads"):
        leads = listar_leads_internacionais()
        if not leads:
            enviar(chat_id, "Nenhum lead internacional ainda."); return
        linhas = [f"🌍 *Leads internacionais ({len(leads)}):*\n"]
        for l in leads:
            data = l['criado_em'][:10] if l.get('criado_em') else '?'
            linhas.append(f"• {l['nome']} (`{l['chat_id']}`) — {l['destino']} — {data}")
        enviar(chat_id, "\n".join(linhas))
        return

    if texto.startswith("/forcarbusca"):
        enviar(chat_id, T.ADMIN_BUSCA_INICIADA)
        for uid, u in todos.items():
            if u.get("status") == "ativo":
                threading.Thread(target=executar_ciclo_usuario, args=(uid,"normal"), daemon=True).start()
                time.sleep(30)
        return

    if texto.startswith("/broadcast "):
        msg_texto = texto[len("/broadcast "):].strip()
        if not msg_texto:
            enviar(chat_id, "❌ Use: `/broadcast <mensagem>`"); return
        enviados = sum(1 for uid,u in todos.items() if u.get("status")=="ativo" and not enviar(int(uid), msg_texto) is None and not time.sleep(0.3))
        enviar(chat_id, f"✅ Enviado para *{sum(1 for u in todos.values() if u.get('status')=='ativo')}* ativos.")
        return

    if texto.startswith("/broadcast_pendentes "):
        msg_texto = texto[len("/broadcast_pendentes "):].strip()
        enviados = 0
        for uid, u in todos.items():
            if u.get("status") == "aguardando_pagamento":
                enviar(int(uid), msg_texto); enviados += 1; time.sleep(0.3)
        enviar(chat_id, f"✅ Enviado para *{enviados}* pendentes.")
        return

    if texto.startswith("/broadcast_todos "):
        msg_texto = texto[len("/broadcast_todos "):].strip()
        enviados = 0
        for uid in todos:
            enviar(int(uid), msg_texto); enviados += 1; time.sleep(0.3)
        enviar(chat_id, f"✅ Enviado para *{enviados}* usuários.")
        return

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
        return

    if texto.startswith("/msg "):
        partes = texto.split(" ", 2)
        if len(partes) < 3:
            enviar(chat_id, "❌ Use: `/msg <id> <mensagem>`"); return
        alvo, msg_texto = partes[1], partes[2].strip()
        dados_alvo = carregar_usuario(alvo)
        nome_alvo  = (dados_alvo or {}).get("nome", alvo)
        enviar(int(alvo), msg_texto)
        enviar(chat_id, f"✅ Mensagem enviada para *{nome_alvo}* (`{alvo}`).")
        return

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
            return
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
            return

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

    if texto in ("/indique e ganhe", "/indique"):
        # Cria afiliado se não existir
        af = buscar_afiliado(chat_id)
        if not af:
            af = criar_afiliado(chat_id)
        codigo  = af.get("codigo", "")
        saldo   = af.get("saldo", 0.0)
        total   = af.get("total_ganho", 0.0)
        pagantes = af.get("total_pagantes", 0)
        indicados = af.get("total_indicados", 0)
        bot_user = os.getenv("TELEGRAM_BOT_USERNAME", "seubot")
        link    = f"https://t.me/{bot_user}?start={codigo}"
        enviar(chat_id,
            f"🎉 *Que bom ter você por aqui!*\n\n"
            f"Indique amigos e ganhe comissão em cada assinatura confirmada:\n\n"
            f"💰 *Comissões por plano:*\n"
            f"• 60 dias — R$ 5,00\n"
            f"• 5 meses — R$ 10,00\n"
            f"• 1 ano — R$ 20,00\n\n"
            f"🔗 *Seu link de indicação:*\n`{link}`\n\n"
            f"📊 *Seu histórico:*\n"
            f"• Indicados: {indicados}\n"
            f"• Assinantes: {pagantes}\n"
            f"• Total ganho: R$ {total:.2f}\n\n"
            f"💳 *Sua carteira:*\n"
            f"Saldo disponível: *R$ {saldo:.2f}*\n\n"
            + (f"Para sacar, use /sacar" if saldo >= COMISSAO_MINIMO_SAQUE
               else f"_Saldo mínimo para saque: R$ {COMISSAO_MINIMO_SAQUE:.2f}_")
        )
        return

    if texto == "/sacar":
        af = buscar_afiliado(chat_id)
        if not af or af.get("saldo", 0) < COMISSAO_MINIMO_SAQUE:
            enviar(chat_id,
                f"❌ Saldo insuficiente para saque.\n"
                f"Mínimo: R$ {COMISSAO_MINIMO_SAQUE:.2f}\n"
                f"Seu saldo: R$ {af.get('saldo',0):.2f}" if af else
                f"❌ Você ainda não tem carteira. Use /indique e ganhe primeiro."
            ); return
        dados["status_temp"] = "aguardando_chave_pix"
        salvar_usuario(chat_id, dados)
        enviar(chat_id,
            f"💳 *Saque — R$ {af['saldo']:.2f}*\n\n"
            "Digite sua *chave Pix* para receber:"
        )
        return

    if dados.get("status_temp") == "aguardando_chave_pix" and texto and not texto.startswith("/"):
        chave_pix = texto.strip()
        af        = buscar_afiliado(chat_id)
        saldo     = af.get("saldo", 0) if af else 0
        dados.pop("status_temp", None)
        salvar_usuario(chat_id, dados)
        enviar(chat_id,
            f"✅ Solicitação de saque enviada!\n\n"
            f"💰 Valor: R$ {saldo:.2f}\n"
            f"🔑 Chave Pix: `{chave_pix}`\n\n"
            "_Você receberá a transferência em breve._"
        )
        markup = {"inline_keyboard": [[
            {"text": "✅ Transferência concluída", "callback_data": f"admin_pago:{chat_id}"}
        ]]}
        enviar(ADMIN_CHAT_ID,
            f"💸 *Solicitação de saque*\n\n"
            f"👤 {nome} (`{chat_id}`)\n"
            f"💰 Valor: *R$ {saldo:.2f}*\n"
            f"🔑 Chave Pix: `{chave_pix}`",
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
