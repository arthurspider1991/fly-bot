"""
services/analise.py — Análise inteligente de histórico de preços e alertas especiais.
Versão "IA de Decisão" — Gatilhos claros, urgência comercial e análise mais segura.
"""
import sys
import os
from datetime import date
from statistics import median
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from config import get_logger

log = get_logger(__name__)


def _formatar_moeda(valor: float) -> str:
    return f"R$ {valor:.0f}"


def _percentil(valores: list[float], p: float) -> float:
    """Percentil simples sem depender de bibliotecas externas."""
    if not valores:
        return 0.0

    valores_ordenados = sorted(valores)
    k = (len(valores_ordenados) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(valores_ordenados) - 1)

    if f == c:
        return valores_ordenados[f]

    return valores_ordenados[f] + (valores_ordenados[c] - valores_ordenados[f]) * (k - f)


def _dias_ate_voo(data_voo_iso: str) -> Optional[int]:
    try:
        data_voo = date.fromisoformat(data_voo_iso)
        return (data_voo - date.today()).days
    except Exception:
        log.warning("Data de voo inválida recebida: %s", data_voo_iso)
        return None


def _extrair_precos_validos(historico_60d: list) -> list[float]:
    precos = []

    for item in historico_60d or []:
        try:
            preco = float(item.get("preco"))
            if preco > 0:
                precos.append(preco)
        except Exception:
            continue

    return precos


def _extrair_precos_passados(historico_60d: list) -> list[float]:
    """
    Extrai apenas preços de dias anteriores.
    Evita comparar o preço atual contra ele mesmo no alerta de mínimo histórico.
    """
    precos = []

    for item in historico_60d or []:
        try:
            dias_atras = int(item.get("dias_atras", 0))
            preco = float(item.get("preco"))
            if dias_atras > 0 and preco > 0:
                precos.append(preco)
        except Exception:
            continue

    return precos


def analisar_historico(
    historico_60d: list,
    preco_atual: float,
    data_voo_iso: str,
) -> Optional[str]:
    """
    Recebe a lista de dicts {dias_atras, preco} e o preço atual.
    Retorna uma análise humanizada e comercial, focada na tomada de decisão do cliente.
    """

    if not historico_60d or preco_atual is None:
        return None

    try:
        preco_atual = float(preco_atual)
    except Exception:
        return None

    if preco_atual <= 0:
        return None

    precos = _extrair_precos_validos(historico_60d)
    if not precos:
        return None

    dias_voo = _dias_ate_voo(data_voo_iso)
    if dias_voo is None:
        return None

    total_pontos = len(precos)
    precos_passados = _extrair_precos_passados(historico_60d) or precos

    minimo_anterior = min(precos_passados)

    precos_30d = []
    for h in historico_60d:
        try:
            dias_atras = int(h.get("dias_atras", 999))
            preco = float(h.get("preco"))
            if 0 < dias_atras <= 30 and preco > 0:
                precos_30d.append(preco)
        except Exception:
            continue

    if not precos_30d:
        precos_30d = precos_passados

    media_30 = sum(precos_30d) / len(precos_30d)
    mediana_30 = median(precos_30d)
    p25_30 = _percentil(precos_30d, 25)
    pct_vs_media = ((preco_atual - media_30) / media_30) * 100 if media_30 else 0

    # ── 1. CLASSIFICAÇÃO DO PREÇO ───────────────────────────────────────────
    if preco_atual <= minimo_anterior:
        preco_status = "MINIMO"
    elif preco_atual <= p25_30 or pct_vs_media <= -8:
        preco_status = "EXCELENTE"
    elif preco_atual <= media_30 * 1.04 or preco_atual <= mediana_30 * 1.06:
        preco_status = "JUSTO"
    else:
        preco_status = "ALTO"

    # ── 2. CLASSIFICAÇÃO DA URGÊNCIA ────────────────────────────────────────
    if dias_voo > 60:
        tempo_status = "LONGE"
    elif 25 <= dias_voo <= 60:
        tempo_status = "MEDIO"
    else:
        tempo_status = "CURTO"

    linhas = []

    # ── 3. MATRIZ DE DECISÃO ────────────────────────────────────────────────
    if preco_status == "MINIMO":
        linhas += [
            "🔥 *OPORTUNIDADE REAL DE COMPRA:*",
            f"   Este é o menor valor registrado no histórico recente monitorado ({total_pontos} pontos).",
            f"   O preço atual está em *{_formatar_moeda(preco_atual)}*.",
            "   Tarifas que chegam ao piso histórico costumam ter pouca duração.",
            "   _👉 Recomendação: Se tem certeza da viagem, este é um excelente momento para emitir._",
        ]

    elif preco_status == "EXCELENTE":
        if tempo_status == "LONGE":
            linhas += [
                "🔥 *ACHADO ANTECIPADO:*",
                f"   O preço caiu para *{_formatar_moeda(preco_atual)}*, abaixo do padrão recente desta rota.",
                f"   Como faltam {dias_voo} dias, ainda pode haver oscilações, mas o valor atual já é muito competitivo.",
                "   _👉 Recomendação: Se a viagem está definida, vale muito considerar a compra agora._",
            ]
        elif tempo_status == "MEDIO":
            linhas += [
                "🎯 *JANELA DE OURO ABERTA:*",
                "   Entramos num período importante de compra e o valor atual está abaixo da média recente.",
                f"   Média dos últimos 30 dias: {_formatar_moeda(media_30)}.",
                "   _👉 Recomendação: COMPRE se a viagem já está decidida. Esperar pode trazer risco de alta._",
            ]
        else:
            linhas += [
                "🚀 *RARIDADE DE ÚLTIMA HORA:*",
                f"   Encontrar uma tarifa boa a apenas {dias_voo} dias do voo é pouco comum.",
                f"   O valor atual está em *{_formatar_moeda(preco_atual)}*.",
                "   _👉 Recomendação: Emita o quanto antes se a viagem for certa._",
            ]

    elif preco_status == "JUSTO":
        if tempo_status == "LONGE":
            linhas += [
                "⏳ *VALE A PENA ACOMPANHAR:*",
                f"   A tarifa atual de *{_formatar_moeda(preco_atual)}* está dentro do padrão esperado.",
                f"   Como faltam {dias_voo} dias, ainda há espaço para oscilações.",
                "   _👉 Recomendação: Pode aguardar. Vamos continuar monitorando para tentar capturar uma queda._",
            ]
        elif tempo_status == "MEDIO":
            linhas += [
                "⚠️ *ALERTA DE SEGURANÇA:*",
                f"   O valor está dentro da faixa normal, em *{_formatar_moeda(preco_atual)}*.",
                "   Porém, a data do voo começa a se aproximar.",
                "   _👉 Recomendação: Se não pode adiar a viagem, comprar agora reduz o risco de pagar mais caro depois._",
            ]
        else:
            linhas += [
                "⏰ *ÚLTIMA CHAMADA:*",
                f"   O preço está regular, mas faltam apenas {dias_voo} dias para o embarque.",
                "   Nesta janela, quedas ainda podem acontecer, mas o risco de alta costuma ser maior.",
                "   _👉 Recomendação: Se a viagem for necessária, compre agora._",
            ]

    else:
        if tempo_status == "LONGE":
            linhas += [
                "🛑 *NÃO PARECE UM BOM MOMENTO:*",
                f"   A passagem está acima da média recente, em *{_formatar_moeda(preco_atual)}*.",
                "   Com bastante antecedência, as companhias podem testar preços mais altos.",
                "   _👉 Recomendação: Aguarde novas oscilações antes de comprar._",
            ]
        elif tempo_status == "MEDIO":
            linhas += [
                "❌ *MOMENTO DESFAVORÁVEL:*",
                f"   O preço atual está acima da média recente de {_formatar_moeda(media_30)}.",
                "   Pode ser apenas um pico temporário, mas já existe algum risco por causa da aproximação da data.",
                "   _👉 Recomendação: Se possível, aguarde alguns dias e continue monitorando._",
            ]
        else:
            linhas += [
                "🚨 *ZONA DE EMERGÊNCIA:*",
                f"   O preço está alto, em *{_formatar_moeda(preco_atual)}*, e o voo está próximo.",
                f"   Faltam apenas {dias_voo} dias para o embarque.",
                "   _👉 Recomendação: Se a viagem for inadiável, compre antes que o valor piore. Se tiver flexibilidade, considere alterar a data._",
            ]

    # ── 4. MEMÓRIA COMPARATIVA ──────────────────────────────────────────────
    ponto_5d = next(
        (
            h for h in historico_60d
            if 4 <= int(h.get("dias_atras", 999)) <= 7 and h.get("preco")
        ),
        None,
    )

    if ponto_5d:
        preco_5d = float(ponto_5d["preco"])
        diferenca = preco_atual - preco_5d

        if diferenca <= -40:
            linhas.append(
                f"📉 *Evolução recente:* O preço recuou *{_formatar_moeda(abs(diferenca))}* em relação a {ponto_5d['dias_atras']} dias atrás."
            )
        elif diferenca >= 40:
            linhas.append(
                f"🔺 *Evolução recente:* O preço subiu *{_formatar_moeda(diferenca)}* em relação a {ponto_5d['dias_atras']} dias atrás."
            )

    linhas.append(
        f"📊 *Referência:* média 30d {_formatar_moeda(media_30)} | menor anterior {_formatar_moeda(minimo_anterior)}."
    )

    return "\n".join(linhas)


def checar_alertas_especiais(
    historico_60d: list,
    preco_atual: float,
    dados: dict,
) -> list:
    """
    Verificações rápidas e gatilhos de push em tempo real.
    Retorna uma lista de mensagens. O envio deve ser feito pelo monitor.py.
    """

    if not historico_60d or preco_atual is None:
        return []

    try:
        preco_atual = float(preco_atual)
    except Exception:
        return []

    if preco_atual <= 0:
        return []

    alertas = []
    hist_salvo = dados.get("historico_precos", {})
    precos = _extrair_precos_validos(historico_60d)

    if not precos:
        return []

    precos_passados = _extrair_precos_passados(historico_60d) or precos
    minimo_anterior = min(precos_passados)

    # ── Alerta 1: mínimo histórico real ─────────────────────────────────────
    if preco_atual <= minimo_anterior:
        alertas.append(
            "🎯 *ALERTA DE MÍNIMO HISTÓRICO!*\n"
            f"O preço atingiu o menor valor do histórico recente: *{_formatar_moeda(preco_atual)}*.\n"
            "🔥 Esta é uma das melhores oportunidades registradas até agora."
        )

    # ── Sequência de altas ─────────────────────────────────────────────────
    seq_alta = int(hist_salvo.get("seq_alta", 0) or 0)
    ant = hist_salvo.get("preco_anterior")

    try:
        ant = float(ant) if ant else None
    except Exception:
        ant = None

    if ant:
        if preco_atual > ant:
            seq_alta += 1
        else:
            seq_alta = 0

    hist_salvo["seq_alta"] = seq_alta
    hist_salvo["preco_anterior"] = preco_atual
    dados["historico_precos"] = hist_salvo

    if seq_alta == 7:
        alertas.append(
            "📈 *Aviso de Tendência: Alta por 7 verificações seguidas*\n"
            f"O preço vem subindo de forma consecutiva e agora está em *{_formatar_moeda(preco_atual)}*.\n"
            "O mercado parece ter estabilizado em alta. Reduza a expectativa de quedas fortes no curto prazo."
        )

    # ── Alerta 2: queda brusca ──────────────────────────────────────────────
    if ant and ant > 0:
        queda_pct = ((ant - preco_atual) / ant) * 100

        if queda_pct >= 12:
            alertas.append(
                "⚡ *QUEDA BRUSCA DETECTADA!*\n"
                f"O preço caiu de {_formatar_moeda(ant)} para *{_formatar_moeda(preco_atual)}* desde a última verificação.\n"
                "Pode ter surgido um lote promocional temporário."
            )

    return alertas
