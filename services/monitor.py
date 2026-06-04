"""
services/monitor.py — Ciclos de monitoramento individual e gestão de assinaturas.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import time
import threading
from datetime import datetime, date, timedelta
from typing import Optional

from config import ALERTA_PERCENT, SLOTS_MANHA, ADMIN_CHAT_ID, get_logger
from db.usuarios import carregar_usuario, salvar_usuario, carregar_todos_usuarios
from services.scraper import buscar_preco_e_historico, buscar_preco_apenas, link_flights, buscar_historico_apenas
from services.analise import analisar_historico, checar_alertas_especiais

log = get_logger(__name__)

# Importado lazy para evitar import circular com telegram
def _enviar(chat_id, texto, reply_markup=None):
    from telegram.bot import enviar
    return enviar(chat_id, texto, reply_markup)

# ── Helpers de data ───────────────────────────────────────────────────────────

def _iso_para_br(data_iso: Optional[str]) -> str:
    if not data_iso:
        return "—"
    a, m, d = data_iso.split("-")
    return f"{d}/{m}/{a}"

# ── Assinatura ────────────────────────────────────────────────────────────────

def dias_plano(plano: str) -> int:
    return 90 if plano == "5meses" else 30

def dias_restantes_assinatura(dados: dict) -> Optional[int]:
    liberado_em = dados.get("liberado_em")
    if not liberado_em:
        return None
    expira = datetime.fromisoformat(liberado_em) + timedelta(days=dias_plano(dados.get("plano", "1mes")))
    return (expira - datetime.now()).days

# ── Slot matinal ──────────────────────────────────────────────────────────────

def atribuir_slot_manha() -> str:
    """Retorna o slot com menos usuários atribuídos."""
    usuarios  = carregar_todos_usuarios()
    contagem  = {s: 0 for s in SLOTS_MANHA}
    for u in usuarios.values():
        s = u.get("slot_manha")
        if s in contagem:
            contagem[s] += 1
    return min(contagem, key=contagem.get)

# ── Execução do ciclo por usuário ─────────────────────────────────────────────

COMANDOS_USUARIO = (
    "ℹ️ *Comandos:*\n"
    "/status — ver monitoramento\n"
    "/reconfigurar — mudar rota ou datas\n"
    "/parar — pausar alertas"
)

def executar_ciclo_usuario(chat_id, modo: str = "normal") -> None:
    """
    modo='completo' → primeira vez: preço + histórico + análise + link + comandos
    modo='normal'   → ciclo 2h: preço + alertas de variação + link
    modo='manha'    → slot matinal: preço + histórico + análise completa + link + comandos
    """
    dados = carregar_usuario(chat_id)
    if not dados or dados.get("status") != "ativo":
        return

    cfg        = dados.get("config", {})
    hist_dados = dados.get("historico", {})
    origem     = cfg.get("origem")
    destino    = cfg.get("destino")
    data_ida   = cfg.get("data_ida")
    data_volta = cfg.get("data_volta")

    if not origem or not destino or not data_ida:
        return

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── Busca de preço ────────────────────────────────────────────────────────
    alt_ida   = None
    alt_volta = None

    airhint_ida   = None
    airhint_volta = None

    if modo in ("completo", "manha"):
        # Passa data_volta para AirHint poder fazer análise ida+volta
        preco_ida, hist60_ida, alt_ida, airhint_ida = buscar_preco_e_historico(
            origem, destino, data_ida, data_volta_iso=data_volta
        )
    else:
        preco_ida  = buscar_preco_apenas(origem, destino, data_ida)
        hist60_ida = []

    preco_volta  = None
    hist60_volta = []
    if data_volta:
        if modo in ("completo", "manha"):
            preco_volta, hist60_volta, alt_volta, airhint_volta = buscar_preco_e_historico(
                destino, origem, data_volta
            )
        else:
            preco_volta = buscar_preco_apenas(destino, origem, data_volta)

    # ── Alertas de variação (modo normal) ────────────────────────────────────
    if modo == "normal":
        for trecho, preco_novo, chave_hist, data_ref in [
            (f"{origem}->{destino}", preco_ida,   "preco_ida",   data_ida),
            (f"{destino}->{origem}", preco_volta, "preco_volta", data_volta),
        ]:
            if preco_novo is None:
                continue
            ant = hist_dados.get(chave_hist)
            if ant:
                pct = abs(preco_novo - ant) / ant * 100
                if pct >= ALERTA_PERCENT:
                    sinal = "📉 QUEDA" if preco_novo < ant else "📈 ALTA"
                    _enviar(chat_id,
                        f"{sinal}\n{trecho} | {_iso_para_br(data_ref)}\n"
                        f"R$ {ant:.0f} → *R$ {preco_novo:.0f}* ({pct:.1f}%)"
                    )
                    time.sleep(0.3)

    # ── Atualiza histórico ────────────────────────────────────────────────────
    if preco_ida   is not None: hist_dados["preco_ida"]   = preco_ida
    if preco_volta is not None: hist_dados["preco_volta"] = preco_volta
    hist_dados["ultima_atualizacao"] = now_str
    dados["historico"] = hist_dados

    # ── Alertas especiais ─────────────────────────────────────────────────────
    if hist60_ida and preco_ida:
        checar_alertas_especiais(chat_id, dados, preco_ida, hist60_ida, _enviar)

    # ── Análise rápida de preço ───────────────────────────────────────────────
    def _tag_rapida(preco, hist_salvo_chave):
        """Retorna tag curta de análise para o ciclo normal."""
        ant = hist_dados.get(hist_salvo_chave)
        precos_hist = [h["preco"] for h in hist60_ida] if hist60_ida else []
        tags = []
        # Tendência vs anterior
        if ant:
            pct = (preco - ant) / ant * 100
            if pct >= 2:   tags.append("📈 subindo")
            elif pct <= -2: tags.append("📉 caindo")
            else:           tags.append("➡️ estável")
        # Vs média 30 dias
        if precos_hist:
            media30 = sum(precos_hist[:30]) / min(30, len(precos_hist))
            pct_m   = (preco - media30) / media30 * 100
            if pct_m <= -10:  tags.append("✅ preço bom")
            elif pct_m <= 5:  tags.append("🟡 na média")
            else:             tags.append("🔴 acima da média")
        return " · ".join(tags) if tags else ""

    # ── Monta mensagem principal ──────────────────────────────────────────────
    linhas = [f"✈️ *{origem} → {destino}* | {_iso_para_br(data_ida)}\n"]

    # Ida
    if preco_ida is not None:
        tag_ida = f" — {_tag_rapida(preco_ida, 'preco_ida')}" if modo == "normal" else ""
        linhas.append(f"💰 Ida:   *R$ {preco_ida:.0f}*{tag_ida}")
    else:
        ant = hist_dados.get("preco_ida")
        linhas.append(f"💰 Ida:   R$ {ant:.0f} _(último conhecido)_" if ant else "💰 Ida:   ⚠️ sem dados")

    # Volta
    if data_volta:
        if preco_volta is not None:
            tag_volta = f" — {_tag_rapida(preco_volta, 'preco_volta')}" if modo == "normal" else ""
            linhas.append(f"↩️ Volta: *R$ {preco_volta:.0f}*{tag_volta}")
            if preco_ida:
                linhas.append(f"💳 Total: *R$ {(preco_ida + preco_volta):.0f}*")
        else:
            ant = hist_dados.get("preco_volta")
            linhas.append(f"↩️ Volta: R$ {ant:.0f} _(último conhecido)_" if ant else "↩️ Volta: ⚠️ sem dados")

    # Aeroporto alternativo ida
    if alt_ida and alt_ida.get('preco') and preco_ida:
        economia = preco_ida - alt_ida['preco']
        if economia > 0:
            desc = alt_ida.get('desc', '')
            # Extrai nome do aeroporto alternativo da descrição
            import re as _re
            aeroporto_alt = _re.search(r'([A-Z]{3})', desc)
            aeroporto_alt = aeroporto_alt.group(1) if aeroporto_alt else "aeroporto alternativo"
            linhas.append(f"🔀 *Opção mais barata pelo {aeroporto_alt}:* R$ {alt_ida['preco']:.0f} _(economia de R$ {economia:.0f})_")

    # Aeroporto alternativo volta
    if alt_volta and alt_volta.get('preco') and preco_volta:
        economia = preco_volta - alt_volta['preco']
        if economia > 0:
            desc = alt_volta.get('desc', '')
            import re as _re
            aeroporto_alt = _re.search(r'([A-Z]{3})', desc)
            aeroporto_alt = aeroporto_alt.group(1) if aeroporto_alt else "aeroporto alternativo"
            linhas.append(f"🔀 *Opção mais barata volta pelo {aeroporto_alt}:* R$ {alt_volta['preco']:.0f} _(economia de R$ {economia:.0f})_")

    linhas.append("")
    linhas.append(f"💡 Se acha que esse valor é ideal, compre agora:")
    linhas.append(link_flights(origem, destino, data_ida))
    linhas.append("")

    # Análise inteligente
    dias_voo = (date.fromisoformat(data_ida) - date.today()).days

    def _bloco_airhint(airhint: dict, orig: str, dest: str) -> list:
        """Monta bloco com previsão do AirHint para incluir na mensagem."""
        if not airhint:
            return []

        acao         = airhint.get("acao", "neutro")
        sugestao     = airhint.get("sugestao", "")
        motivo       = airhint.get("motivo", "")
        probabilidade = airhint.get("probabilidade", "")

        if acao == "esperar":
            emoji = "⏳"
        elif acao == "comprar":
            emoji = "✅"
        else:
            emoji = "🤖"

        bloco = ["─────────────────────",
                 f"🤖 *Previsão IA — {orig} → {dest}*", ""]

        if sugestao:
            bloco.append(f"{emoji} *{sugestao}*")
        if probabilidade:
            bloco.append(f"   Probabilidade: *{probabilidade}*")
        if motivo:
            # Trunca motivo longo
            motivo_curto = motivo[:200] + "..." if len(motivo) > 200 else motivo
            bloco.append(f"   _{motivo_curto}_")

        bloco.append("")
        bloco.append("_Previsão gerada pelo AirHint com base em IA_")
        bloco.append("")
        return bloco

    def _bloco_analise(hist60, preco, data_ref, label):
        """Monta bloco de análise para uma rota (ida ou volta)."""
        bloco = [f"─────────────────────", f"📊 *Análise — {label}*"]
        if hist60 and preco:
            analise = analisar_historico(hist60, preco, data_ref)
            if analise:
                bloco.append(analise)
        else:
            dias_ref = (date.fromisoformat(data_ref) - date.today()).days
            if dias_ref > 100:
                bloco += [f"📅 Faltam *{dias_ref} dias*.",
                          "   Monitorando e avisando qualquer variação."]
            elif dias_ref > 60:
                bloco += [f"👀 Faltam *{dias_ref} dias* — pode ter boas surpresas.",
                          "   Fique atento às atualizações."]
            elif dias_ref > 20:
                bloco += [f"⏳ Faltam *{dias_ref} dias* — janela antes da alta final.",
                          "   _Preços tendem a subir bastante nas 3 últimas semanas._"]
            else:
                bloco += [f"🚨 Faltam *{dias_ref} dias* — fase de alta.",
                          "   _Se o voo for essencial, o risco de esperar é alto._"]
            bloco.append("_Histórico indisponível para essa rota no momento._")
        bloco.append("")
        return bloco

    if modo in ("completo", "manha"):
        # Análise da ida
        linhas += _bloco_analise(hist60_ida, preco_ida, data_ida,
                                 f"{origem} → {destino}")
        # Análise da volta (se houver)
        if data_volta and preco_volta:
            linhas += _bloco_analise(hist60_volta, preco_volta, data_volta,
                                     f"{destino} → {origem}")

        # Previsão IA do AirHint
        if airhint_ida:
            linhas += _bloco_airhint(airhint_ida, origem, destino)

    elif modo == "normal" and preco_ida:
        if dias_voo <= 20:
            linhas.append("🚨 _Menos de 20 dias para o voo — fase de alta de preços._")
        elif dias_voo <= 50:
            linhas.append("⏳ _Você está na janela antes da alta final. Fique atento._")

    # Próxima atualização
    proxima = datetime.now() + timedelta(hours=2)
    dados["proxima_busca"] = proxima.isoformat()

    if modo in ("completo", "manha"):
        linhas.append("")
        linhas.append("─────────────────────")
        linhas.append(COMANDOS_USUARIO)
        linhas.append("\n/suporte")

    linhas.append("\n_Você receberá novas atualizações em 2 horas_")

    salvar_usuario(chat_id, dados)
    _enviar(chat_id, "\n".join(linhas))

# ── Loop principal de ciclos (roda a cada 60s) ────────────────────────────────

def loop_ciclos() -> None:
    """
    Verifica a cada 60s quem tem proxima_busca <= agora.
    Também dispara slots matinais no horário correto.
    """
    log.info("Loop de ciclos iniciado.")
    while True:
        try:
            agora     = datetime.now()
            hora_hhmm = agora.strftime("%H:%M")
            usuarios  = carregar_todos_usuarios()

            for chat_id, dados in usuarios.items():
                if dados.get("status") != "ativo":
                    continue

                # Ciclo de 2h individual
                proxima = dados.get("proxima_busca")
                if proxima:
                    try:
                        if agora >= datetime.fromisoformat(proxima):
                            log.info(f"Ciclo 2h: {chat_id}")
                            threading.Thread(
                                target=executar_ciclo_usuario,
                                args=(chat_id, "normal"),
                                daemon=True,
                            ).start()
                            dados["proxima_busca"] = (agora + timedelta(hours=2)).isoformat()
                            salvar_usuario(chat_id, dados)
                            time.sleep(30)
                    except Exception as e:
                        log.error(f"Erro ciclo {chat_id}: {e}")

                # Slot matinal
                slot = dados.get("slot_manha")
                if slot and hora_hhmm == slot:
                    log.info(f"Slot matinal {slot}: {chat_id}")
                    threading.Thread(
                        target=executar_ciclo_usuario,
                        args=(chat_id, "manha"),
                        daemon=True,
                    ).start()
                    time.sleep(30)

        except Exception as e:
            log.error(f"Erro loop_ciclos: {e}")

        time.sleep(60)

# ── Ciclo diário de assinaturas ───────────────────────────────────────────────

def ciclo_assinaturas() -> None:
    from config import PIX_KEY_1MES, PIX_KEY_5MESES, PIX_VALOR_1MES, PIX_VALOR_5MESES
    from telegram.teclados import teclado_paguei

    log.info("=== Checando assinaturas ===")
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    for chat_id, dados in carregar_todos_usuarios().items():
        if dados.get("status") != "ativo":
            continue
        dias = dias_restantes_assinatura(dados)
        if dias is None:
            continue

        nome  = dados.get("nome", "usuário")
        plano = dados.get("plano", "1mes")
        pix_key   = PIX_KEY_5MESES if plano == "5meses" else PIX_KEY_1MES
        pix_valor = PIX_VALOR_5MESES if plano == "5meses" else PIX_VALOR_1MES

        if dias <= 0:
            dados["status"] = "aguardando_pagamento"
            salvar_usuario(chat_id, dados)
            _enviar(int(chat_id),
                f"⏰ *Sua assinatura expirou!*\n\nO monitoramento foi pausado.\n"
                f"Renove agora:\n\n🔑 Chave Pix: `{pix_key}`\n💰 Valor: {pix_valor}",
                reply_markup=teclado_paguei()
            )
            _enviar(ADMIN_CHAT_ID,
                f"🔴 *Assinatura expirada*\nNome: {nome}\nID: `{chat_id}`\nData: {now_str}"
            )

        elif 1 <= dias <= 7:
            emoji  = "🟡" if dias > 3 else ("🟠" if dias > 1 else "🔴")
            sufixo = "s" if dias > 1 else ""
            _enviar(int(chat_id),
                f"{emoji} *Sua assinatura vence em {dias} dia{sufixo}!*\n\n"
                f"Renove agora:\n\n🔑 Chave Pix: `{pix_key}`\n💰 Valor: {pix_valor}\n\n"
                "_Após o pagamento, clique em Paguei:_",
                reply_markup=teclado_paguei()
            )
            _enviar(ADMIN_CHAT_ID,
                f"{emoji} *Vencendo em {dias} dia{sufixo}*\nNome: {nome}\nID: `{chat_id}`"
            )

    log.info("=== Assinaturas concluídas ===")
