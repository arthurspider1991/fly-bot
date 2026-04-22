"""
telegram/teclados.py — Todos os inline keyboards do bot.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import calendar
from datetime import datetime, date, timedelta

from config import PIX_VALOR_1MES, PIX_VALOR_5MESES
from telegram.aeroportos import BRASIL_ESTADOS, BRASIL_AEROPORTOS, OUTROS_PAISES


def teclado_planos() -> dict:
    return {"inline_keyboard": [[
        {"text": f"📅 1 mês — {PIX_VALOR_1MES}",     "callback_data": "plano:1mes"},
        {"text": f"📅 5 meses — {PIX_VALOR_5MESES}", "callback_data": "plano:5meses"},
    ]]}


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


def teclado_data(prefixo: str) -> dict:
    hoje   = datetime.now()
    botoes = []
    row    = []
    for i in range(1, 13):
        mes = hoje + timedelta(days=30 * i)
        row.append({
            "text":          mes.strftime("%b/%y").capitalize(),
            "callback_data": f"{prefixo}:mes:{mes.strftime('%Y-%m-01')}",
        })
        if len(row) == 3:
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
