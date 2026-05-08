"""
db/usuarios.py — CRUD de usuários no SQLite.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import json
import threading
from typing import Optional

from db.database import get_conn
from config import get_logger

log   = get_logger(__name__)
_lock = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    return {
        "nome":             row["nome"],
        "status":           row["status"],
        "config":           json.loads(row["config"]           or "{}"),
        "historico":        json.loads(row["historico"]        or "{}"),
        "historico_precos": json.loads(row["historico_precos"] or "{}"),
        "liberado_em":      row["liberado_em"],
        "plano":            row["plano"] or "1mes",
        "proxima_busca":    row["proxima_busca"],
        "slot_manha":       row["slot_manha"],
    }

# ── Operações ─────────────────────────────────────────────────────────────────

def carregar_usuario(chat_id) -> Optional[dict]:
    chat_id = str(chat_id)
    with _lock:
        conn = get_conn()
        row  = conn.execute(
            "SELECT * FROM usuarios WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        conn.close()
    return _row_to_dict(row) if row else None


def salvar_usuario(chat_id, dados: dict) -> None:
    chat_id = str(chat_id)
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO usuarios
                (chat_id, nome, status, config, historico, historico_precos,
                 liberado_em, plano, proxima_busca, slot_manha)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(chat_id) DO UPDATE SET
                nome             = excluded.nome,
                status           = excluded.status,
                config           = excluded.config,
                historico        = excluded.historico,
                historico_precos = excluded.historico_precos,
                liberado_em      = excluded.liberado_em,
                plano            = excluded.plano,
                proxima_busca    = excluded.proxima_busca,
                slot_manha       = excluded.slot_manha
        """, (
            chat_id,
            dados.get("nome", ""),
            dados.get("status", "aguardando_pagamento"),
            json.dumps(dados.get("config",           {}), ensure_ascii=False),
            json.dumps(dados.get("historico",        {}), ensure_ascii=False),
            json.dumps(dados.get("historico_precos", {}), ensure_ascii=False),
            dados.get("liberado_em"),
            dados.get("plano", "1mes"),
            dados.get("proxima_busca"),
            dados.get("slot_manha"),
        ))
        conn.commit()
        conn.close()


def carregar_todos_usuarios() -> dict:
    with _lock:
        conn = get_conn()
        rows = conn.execute("SELECT * FROM usuarios").fetchall()
        conn.close()
    return {row["chat_id"]: _row_to_dict(row) for row in rows}


def deletar_usuario(chat_id) -> None:
    chat_id = str(chat_id)
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM usuarios WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()


# ── Leads internacionais ───────────────────────────────────────────────────────

def salvar_lead_internacional(chat_id, nome, origem, destino):
    from datetime import datetime
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO leads_internacionais (chat_id, nome, origem, destino, criado_em)
            VALUES (?, ?, ?, ?, ?)
        """, (str(chat_id), nome, origem, destino, datetime.now().isoformat()))
        conn.commit()
        conn.close()


def listar_leads_internacionais():
    with _lock:
        conn = get_conn()
        rows = conn.execute("""
            SELECT chat_id, nome, origem, destino, criado_em
            FROM leads_internacionais
            ORDER BY criado_em DESC
        """).fetchall()
        conn.close()
    return [dict(r) for r in rows]
