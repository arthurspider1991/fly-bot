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
    keys = row.keys()
    def g(k, default=None):
        return row[k] if k in keys else default
    return {
        "nome":             g("nome", "Usuário"),
        "status":           g("status", "aguardando_pagamento"),
        "config":           json.loads(g("config")           or "{}"),
        "historico":        json.loads(g("historico")        or "{}"),
        "historico_precos": json.loads(g("historico_precos") or "{}"),
        "liberado_em":      g("liberado_em"),
        "plano":            g("plano") or "60dias",
        "proxima_busca":    g("proxima_busca"),
        "slot_manha":       g("slot_manha"),
        "ref_afiliado":     g("ref_afiliado"),
        "status_temp":      g("status_temp"),
        "payment_id":       g("payment_id"),
        "preference_id":    g("preference_id"),
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
        # Migração suave: adiciona status_temp se não existir
        try:
            conn.execute("ALTER TABLE usuarios ADD COLUMN status_temp TEXT")
            conn.commit()
        except:
            pass

        conn.execute("""
            INSERT INTO usuarios
                (chat_id, nome, status, config, historico, historico_precos,
                 liberado_em, plano, proxima_busca, slot_manha, status_temp)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(chat_id) DO UPDATE SET
                nome             = excluded.nome,
                status           = excluded.status,
                config           = excluded.config,
                historico        = excluded.historico,
                historico_precos = excluded.historico_precos,
                liberado_em      = excluded.liberado_em,
                plano            = excluded.plano,
                proxima_busca    = excluded.proxima_busca,
                slot_manha       = excluded.slot_manha,
                status_temp      = excluded.status_temp
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
            dados.get("status_temp"),
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


# ── Afiliados ──────────────────────────────────────────────────────────────────

import random, string

def _gerar_codigo():
    return "REF-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_ou_criar_afiliado(chat_id, nome=""):
    chat_id = str(chat_id)
    with _lock:
        conn = get_conn()
        row  = conn.execute("SELECT * FROM afiliados WHERE chat_id=?", (chat_id,)).fetchone()
        if row:
            conn.close()
            return dict(row)
        from datetime import datetime
        codigo = _gerar_codigo()
        # Garante código único
        while conn.execute("SELECT 1 FROM afiliados WHERE codigo=?", (codigo,)).fetchone():
            codigo = _gerar_codigo()
        conn.execute("""
            INSERT INTO afiliados (chat_id, codigo, saldo, total_ganho,
                total_indicados, total_pagantes, criado_em)
            VALUES (?,?,0,0,0,0,?)
        """, (chat_id, codigo, datetime.now().isoformat()))
        conn.commit()
        row = conn.execute("SELECT * FROM afiliados WHERE chat_id=?", (chat_id,)).fetchone()
        conn.close()
        return dict(row)

def registrar_indicacao(afiliado_id, indicado_id):
    """Registra que indicado_id veio do afiliado_id."""
    from datetime import datetime
    afiliado_id = str(afiliado_id)
    indicado_id = str(indicado_id)
    with _lock:
        conn = get_conn()
        # Evita duplicata
        existe = conn.execute(
            "SELECT 1 FROM indicacoes WHERE indicado_id=?", (indicado_id,)
        ).fetchone()
        if not existe:
            conn.execute("""
                INSERT INTO indicacoes (afiliado_id, indicado_id, status, criado_em)
                VALUES (?,?,'acessou',?)
            """, (afiliado_id, indicado_id, datetime.now().isoformat()))
            conn.execute(
                "UPDATE afiliados SET total_indicados=total_indicados+1 WHERE chat_id=?",
                (afiliado_id,)
            )
            conn.commit()
        conn.close()

def confirmar_comissao(indicado_id, plano):
    """Confirma comissão quando indicado paga. Retorna (afiliado_id, comissao)."""
    from datetime import datetime
    from config import PLANOS
    indicado_id = str(indicado_id)
    comissao = PLANOS.get(plano, {}).get("comissao", 0)
    with _lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT afiliado_id FROM indicacoes WHERE indicado_id=? AND status!='pago'",
            (indicado_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None, 0
        afiliado_id = row["afiliado_id"]
        conn.execute("""
            UPDATE indicacoes SET status='pago', plano=?, comissao=?
            WHERE indicado_id=?
        """, (plano, comissao, indicado_id))
        conn.execute("""
            UPDATE afiliados
            SET saldo=saldo+?, total_ganho=total_ganho+?, total_pagantes=total_pagantes+1
            WHERE chat_id=?
        """, (comissao, comissao, afiliado_id))
        conn.commit()
        conn.close()
    return afiliado_id, comissao

def get_afiliado_por_codigo(codigo):
    with _lock:
        conn = get_conn()
        row  = conn.execute("SELECT * FROM afiliados WHERE codigo=?", (codigo,)).fetchone()
        conn.close()
        return dict(row) if row else None

def listar_afiliados():
    with _lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM afiliados ORDER BY total_ganho DESC"
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]

def registrar_saque(chat_id, valor, chave_pix):
    from datetime import datetime
    chat_id = str(chat_id)
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO saques (chat_id, valor, chave_pix, status, criado_em)
            VALUES (?,?,?,'pendente',?)
        """, (chat_id, valor, chave_pix, datetime.now().isoformat()))
        conn.execute(
            "UPDATE afiliados SET saldo=saldo-? WHERE chat_id=?",
            (valor, chat_id)
        )
        conn.commit()
        saque_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
    return saque_id

def confirmar_saque(saque_id):
    with _lock:
        conn = get_conn()
        conn.execute("UPDATE saques SET status='pago' WHERE id=?", (saque_id,))
        conn.commit()
        conn.close()

def listar_saques_pendentes():
    with _lock:
        conn = get_conn()
        rows = conn.execute("""
            SELECT s.*, a.chat_id as aff_chat
            FROM saques s JOIN afiliados a ON s.chat_id=a.chat_id
            WHERE s.status='pendente'
            ORDER BY s.criado_em
        """).fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ── Afiliados ──────────────────────────────────────────────────────────────────

import random, string

def gerar_codigo_afiliado() -> str:
    return "REF-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def criar_afiliado(chat_id) -> dict:
    chat_id = str(chat_id)
    from datetime import datetime
    codigo = gerar_codigo_afiliado()
    with _lock:
        conn = get_conn()
        # Garante código único
        while conn.execute("SELECT 1 FROM afiliados WHERE codigo=?", (codigo,)).fetchone():
            codigo = gerar_codigo_afiliado()
        conn.execute("""
            INSERT OR IGNORE INTO afiliados (chat_id, codigo, saldo, total_ganho,
                total_indicados, total_pagantes, criado_em)
            VALUES (?,?,0,0,0,0,?)
        """, (chat_id, codigo, datetime.now().isoformat()))
        conn.commit()
        row = conn.execute("SELECT * FROM afiliados WHERE chat_id=?", (chat_id,)).fetchone()
        conn.close()
    return dict(row) if row else {}


def buscar_afiliado(chat_id) -> dict:
    chat_id = str(chat_id)
    with _lock:
        conn = get_conn()
        row  = conn.execute("SELECT * FROM afiliados WHERE chat_id=?", (chat_id,)).fetchone()
        conn.close()
    return dict(row) if row else {}


def buscar_afiliado_por_codigo(codigo: str) -> dict:
    with _lock:
        conn = get_conn()
        row  = conn.execute("SELECT * FROM afiliados WHERE codigo=?", (codigo,)).fetchone()
        conn.close()
    return dict(row) if row else {}


def registrar_indicacao(afiliado_chat_id, indicado_chat_id, plano: str, comissao: float):
    from datetime import datetime
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT OR IGNORE INTO indicacoes
                (afiliado_chat_id, indicado_chat_id, plano, comissao, status, criado_em)
            VALUES (?,?,?,?,'pendente',?)
        """, (str(afiliado_chat_id), str(indicado_chat_id), plano, comissao, datetime.now().isoformat()))
        conn.commit()
        conn.close()


# confirmar_comissao: usar a versao na linha 185 que recebe plano


def registrar_novo_indicado(afiliado_chat_id):
    """Incrementa contador de indicados quando novo usuário acessa via link."""
    with _lock:
        conn = get_conn()
        conn.execute(
            "UPDATE afiliados SET total_indicados = total_indicados + 1 WHERE chat_id=?",
            (str(afiliado_chat_id),)
        )
        conn.commit()
        conn.close()


def zerar_saldo_afiliado(chat_id):
    with _lock:
        conn = get_conn()
        conn.execute("UPDATE afiliados SET saldo=0 WHERE chat_id=?", (str(chat_id),))
        conn.commit()
        conn.close()


def listar_afiliados_com_saldo() -> list:
    with _lock:
        conn = get_conn()
        rows = conn.execute("""
            SELECT a.chat_id, a.codigo, a.saldo, a.total_ganho,
                   a.total_indicados, a.total_pagantes, u.nome
            FROM afiliados a
            LEFT JOIN usuarios u ON u.chat_id = a.chat_id
            WHERE a.saldo > 0 OR a.total_pagantes > 0
            ORDER BY a.saldo DESC
        """).fetchall()
        conn.close()
    return [dict(r) for r in rows]
