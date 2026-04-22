"""
services/analise.py — Análise inteligente de histórico de preços e alertas especiais.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import time
from datetime import date
from typing import Optional

from config import get_logger

log = get_logger(__name__)


def analisar_historico(
    historico_60d: list,
    preco_atual: float,
    data_voo_iso: str,
) -> Optional[str]:
    """
    Recebe lista de dicts {dias_atras, preco} e retorna string de análise
    pronta para enviar ao usuário, ou None se dados insuficientes.
    """
    if not historico_60d or preco_atual is None:
        return None

    precos = [h["preco"] for h in historico_60d]
    if not precos:
        return None

    hoje     = date.today()
    data_voo = date.fromisoformat(data_voo_iso)
    dias_voo = (data_voo - hoje).days

    media    = sum(precos) / len(precos)
    media_30 = [h["preco"] for h in historico_60d if h["dias_atras"] <= 30]
    media_30 = sum(media_30) / max(1, len(media_30))
    minimo   = min(precos)
    maximo   = max(precos)

    dias_mais_barato = sum(1 for p in precos if p < preco_atual)
    total_dias       = len(precos)

    # Tendência 14 dias (regressão linear simples)
    ult14 = [h["preco"] for h in historico_60d if h["dias_atras"] <= 14]
    slope = 0.0
    if len(ult14) >= 3:
        n   = len(ult14)
        xs  = list(range(n))
        xm  = sum(xs) / n
        ym  = sum(ult14) / n
        num = sum((xs[i] - xm) * (ult14[i] - ym) for i in range(n))
        den = sum((xs[i] - xm) ** 2 for i in range(n))
        slope = num / den if den else 0.0

    # Sequências de alta/baixa
    seq_alta = seq_baixa = 0
    ultimos = [h["preco"] for h in sorted(historico_60d, key=lambda x: x["dias_atras"])[:14]]
    for i in range(1, len(ultimos)):
        if ultimos[i] > ultimos[i - 1]:
            seq_alta += 1; seq_baixa = 0
        elif ultimos[i] < ultimos[i - 1]:
            seq_baixa += 1; seq_alta = 0
        else:
            seq_alta = seq_baixa = 0

    pct_vs_media = (preco_atual - media_30) / media_30 * 100

    # Zona de tempo
    if dias_voo > 100:   zona = "longe"
    elif dias_voo > 60:  zona = "zona1"
    elif dias_voo > 20:  zona = "zona2"
    else:                zona = "perigo"

    # Tendência
    if slope > 5:        tendencia = "subindo"
    elif slope < -5:     tendencia = "caindo"
    else:                tendencia = "estavel"

    def _fmt_pct(pct):
        return "na média" if abs(pct) < 2 else f"{pct:+.0f}%"

    linhas = []

    # Preço vs média
    if pct_vs_media < -10:
        linhas += [f"✅ *Preço abaixo da média* dos últimos 30 dias",
                   f"   R$ {preco_atual:.0f} vs média R$ {media_30:.0f} ({_fmt_pct(pct_vs_media)})"]
    elif pct_vs_media < 5:
        linhas += [f"🟡 *Preço próximo da média* dos últimos 30 dias",
                   f"   R$ {preco_atual:.0f} vs média R$ {media_30:.0f} ({_fmt_pct(pct_vs_media)})"]
    else:
        linhas += [f"🔴 *Preço acima da média* dos últimos 30 dias",
                   f"   R$ {preco_atual:.0f} vs média R$ {media_30:.0f} ({_fmt_pct(pct_vs_media)})"]

    linhas.append("")

    # Contexto de zona
    if zona == "longe":
        linhas.append(f"📅 Faltam *{dias_voo} dias* — ainda bem cedo.")
        if tendencia == "caindo":
            linhas.append("   Preço em queda, sem pressa para decidir.")
        elif tendencia == "subindo" and pct_vs_media < 0:
            linhas.append("   Estava abaixo da média mas subindo. Vale monitorar.")
        else:
            linhas.append("   Monitorando e avisando qualquer variação relevante.")

    elif zona == "zona1":
        if pct_vs_media < -5 and tendencia != "subindo":
            linhas += [f"👀 Faltam *{dias_voo} dias* — período que pode ter surpresas boas.",
                       "   Preço abaixo da média. Às vezes surgem as melhores oportunidades aqui.",
                       "   _Não é urgente, mas vale avaliar._"]
        elif pct_vs_media < -5 and tendencia == "subindo":
            linhas += [f"👀 Faltam *{dias_voo} dias* — período de possíveis oportunidades.",
                       "   Preço estava bom mas está subindo. Fique atento."]
        else:
            linhas += [f"👀 Faltam *{dias_voo} dias* — pode ter bons preços nesse período.",
                       "   Continue monitorando."]

    elif zona == "zona2":
        if pct_vs_media <= 5 and tendencia != "subindo":
            linhas += [f"⏳ Faltam *{dias_voo} dias* — você está na *última janela* antes da alta final.",
                       "   Preço dentro do esperado para esse período.",
                       "   _A partir das 3 últimas semanas os preços tendem a subir bastante._",
                       "   _Não há garantias, mas o contexto é favorável para comprar._"]
        elif pct_vs_media <= 5 and tendencia == "subindo":
            linhas += [f"⚠️ Faltam *{dias_voo} dias* — dentro da janela, mas subindo.",
                       "   Se continuar assim por mais 2-3 dias, pode ser que o piso já passou.",
                       "   _Vale decidir em breve._"]
        else:
            linhas += [f"⚠️ Faltam *{dias_voo} dias* — dentro da janela mas preço acima da média.",
                       "   Ainda tem tempo, mas a janela está se fechando."]

    elif zona == "perigo":
        if tendencia == "subindo":
            linhas += [f"🚨 Faltam *{dias_voo} dias* — fase de alta.",
                       "   Preço subindo. Esperar tende a sair mais caro.",
                       "   _Se o voo for essencial, o risco de aguardar é alto._"]
        elif tendencia == "caindo":
            linhas += [f"🚨 Faltam *{dias_voo} dias* — fase de alta, mas preço caindo.",
                       "   Queda nesse período é rara. Pode ser oportunidade pontual."]
        else:
            linhas += [f"🚨 Faltam *{dias_voo} dias* — fase de alta.",
                       "   Historicamente os preços ficam altos agora.",
                       "   _Se precisar do voo, evite esperar muito._"]

    linhas.append("")

    # Tendência recente
    if seq_alta >= 5:
        linhas.append(f"📈 Subindo há *{seq_alta} dias seguidos*")
    elif seq_baixa >= 5:
        linhas.append(f"📉 Caindo há *{seq_baixa} dias seguidos*")
    elif tendencia == "subindo":
        linhas.append("📈 Tendência de alta nos últimos 14 dias")
    elif tendencia == "caindo":
        linhas.append("📉 Tendência de queda nos últimos 14 dias")
    else:
        linhas.append("➡️ Preço estável nos últimos 14 dias")

    linhas.append("")

    # Referência histórica
    linhas.append("\U0001F4CA *Histórico 60 dias:*")
    linhas.append(f"   Mínimo: R$ {minimo:.0f}  |  Máximo: R$ {maximo:.0f}  |  Média: R$ {media:.0f}")
    if dias_mais_barato > 0:
        linhas.append(f"   Nos últimos {total_dias} dias, esteve mais barato em *{dias_mais_barato} deles*")
    else:
        linhas.append(f"   Este é o *menor preço* dos últimos {total_dias} dias 🎯")

    # Destaque: mínimo histórico
    if preco_atual <= minimo:
        linhas.insert(0, "🎯 *Mínimo histórico dos últimos 60 dias!*\n")

    return "\n".join(linhas)


def checar_alertas_especiais(
    chat_id,
    dados: dict,
    preco_atual: float,
    historico_60d: list,
    enviar_fn,
) -> bool:
    """
    Verifica mínimo histórico, alta sustentada e variação brusca.
    Usa enviar_fn(chat_id, texto) para desacoplar do módulo telegram.
    Retorna True se enviou algum alerta.
    """
    if not historico_60d or preco_atual is None:
        return False

    hist_salvo = dados.get("historico_precos", {})
    precos     = [h["preco"] for h in historico_60d]
    minimo     = min(precos)
    alertas    = []

    # Mínimo histórico
    if preco_atual <= minimo:
        alertas.append(
            "🎯 *Mínimo histórico atingido!*\n"
            f"R$ {preco_atual:.0f} — menor preço dos últimos 60 dias."
        )

    # Alta sustentada >= 7 dias
    seq_alta = hist_salvo.get("seq_alta", 0)
    ant      = hist_salvo.get("preco_anterior")
    if ant:
        seq_alta = seq_alta + 1 if preco_atual > ant else 0
    hist_salvo["seq_alta"]       = seq_alta
    hist_salvo["preco_anterior"] = preco_atual
    dados["historico_precos"]    = hist_salvo

    if seq_alta == 7:
        alertas.append(
            f"📈 *Alta por 7 dias seguidos*\n"
            f"Preço subiu de R$ {ant:.0f} para R$ {preco_atual:.0f}.\n"
            "Pode não voltar ao preço anterior."
        )

    # Variação brusca (>15% num dia)
    if ant and abs(preco_atual - ant) / ant * 100 >= 15:
        sinal = "subiu" if preco_atual > ant else "caiu"
        pct   = abs(preco_atual - ant) / ant * 100
        alertas.append(
            f"⚡ *Variação brusca detectada*\n"
            f"Preço {sinal} {pct:.0f}% em 1 dia.\n"
            f"R$ {ant:.0f} → R$ {preco_atual:.0f}"
        )

    for alerta in alertas:
        enviar_fn(chat_id, alerta)
        time.sleep(0.3)

    return bool(alertas)
