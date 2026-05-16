"""
telegram/teclados.py — Todos os inline keyboards do bot.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import calendar
from datetime import datetime, date, timedelta

from telegram.aeroportos import BRASIL_ESTADOS, BRASIL_AEROPORTOS, OUTROS_PAISES


def teclado_planos() -> dict:
    from config import PLANOS
    return {"inline_keyboard": [
        [{"text": f"📅 {PLANOS['60dias']['label']} — R$ {PLANOS['60dias']['valor']:.2f}",
          "callback_data": "plano:60dias"}],
        [{"text": f"📅 {PLANOS['5meses']['label']} — R$ {PLANOS['5meses']['valor']:.2f}",
          "callback_data": "plano:5meses"}],
        [{"text": f"📅 {PLANOS['1ano']['label']} — R$ {PLANOS['1ano']['valor']:.2f}",
          "callback_data": "plano:1ano"}],
        [{"text": "✈️ Voos internacionais", "callback_data": "internacional"}],
    ]}


def teclado_paguei() -> dict:
    return {"inline_keyboard": [[{"text": "✅ Paguei!", "callback_data": "paguei"}]]}



def teclado_liberar_admin(chat_id_usuario) -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ Liberar acesso", "callback_data": f"admin_liberar:{chat_id_usuario}"}
    ]]}


def teclado_paises(prefixo: str) -> dict:
    botoes = [[{"text": "🇧🇷 Brasil", "callback_data": f"{prefixo}:pais:BR"}]]
    row = []
    for p in OUTROS_PAISES:
        row.append({"text": p, "callback_data": f"{prefixo}:pais:{p}"})
        if len(row) == 2:
            botoes.append(row)
            row = []
    if row:
        botoes.append(row)
    return {"inline_keyboard": botoes}


def teclado_estados(prefixo: str) -> dict:
    botoes = []
    row    = []
    for uf, nome in sorted(BRASIL_ESTADOS.items()):
        row.append({"text": nome, "callback_data": f"{prefixo}:uf:{uf}"})
        if len(row) == 2:
            botoes.append(row)
            row = []
    if row:
        botoes.append(row)
    botoes.append([{"text": "⬅️ Voltar", "callback_data": f"{prefixo}:voltar:paises"}])
    return {"inline_keyboard": botoes}


def teclado_aeroportos_estado(prefixo: str, uf: str) -> dict:
    botoes = [
        [{"text": f"{iata} — {nome}", "callback_data": f"{prefixo}:iata:{iata}"}]
        for iata, nome in BRASIL_AEROPORTOS.get(uf, [])
    ]
    botoes.append([{"text": "⬅️ Voltar", "callback_data": f"{prefixo}:voltar:estados"}])
    return {"inline_keyboard": botoes}


def teclado_aeroportos_pais(prefixo: str, pais: str) -> dict:
    botoes = [
        [{"text": f"{iata} — {nome}", "callback_data": f"{prefixo}:iata:{iata}"}]
        for iata, nome in OUTROS_PAISES.get(pais, [])
    ]
    botoes.append([{"text": "⬅️ Voltar", "callback_data": f"{prefixo}:voltar:paises"}])
    return {"inline_keyboard": botoes}


MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",    6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro",10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

def teclado_data(prefixo: str) -> dict:
    hoje   = datetime.now()
    botoes = []
    row    = []
    # Gera os próximos 12 meses em ordem correta
    ano_atual = hoje.year
    mes_atual = hoje.month
    for i in range(1, 13):
        mes_num = (mes_atual - 1 + i) % 12 + 1
        ano_num = ano_atual + (mes_atual - 1 + i) // 12
        label   = f"{MESES_PT[mes_num]}/{str(ano_num)[2:]}"
        data_iso = f"{ano_num}-{mes_num:02d}-01"
        row.append({
            "text":          label,
            "callback_data": f"{prefixo}:mes:{data_iso}",
        })
        if len(row) == 2:
            botoes.append(row)
            row = []
    if row:
        botoes.append(row)
    if prefixo == "volta":
        botoes.append([{"text": "✈️ Só ida (sem volta)", "callback_data": "volta:semvolta:0"}])
    botoes.append([{"text": "📝 Digitar data manual", "callback_data": f"{prefixo}:manual:0"}])
    return {"inline_keyboard": botoes}


def teclado_dias(prefixo: str, mes_iso: str) -> dict:
    ano, mes, _ = mes_iso.split("-")
    ano, mes    = int(ano), int(mes)
    _, total    = calendar.monthrange(ano, mes)
    hoje        = date.today()
    botoes      = []
    row         = []
    for d in range(1, total + 1):
        if date(ano, mes, d) <= hoje:
            continue
        row.append({
            "text":          f"{d:02d}",
            "callback_data": f"{prefixo}:dia:{ano}-{mes:02d}-{d:02d}",
        })
        if len(row) == 7:
            botoes.append(row)
            row = []
    if row:
        botoes.append(row)
    botoes.append([{"text": "⬅️ Voltar", "callback_data": f"{prefixo}:voltames:0"}])
    return {"inline_keyboard": botoes}
