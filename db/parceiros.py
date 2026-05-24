"""
db/parceiros.py
Sistema de parceiros (afiliados) — reescrito do zero.

Fluxo:
  1. Usuário acessa bot via link ?start=REF-xxx
  2. bot.py chama registrar_acesso(parceiro_codigo, indicado_id)
  3. Indicado paga → webhook chama confirmar_venda(indicado_id, plano)
  4. Comissão é creditada automaticamente ao parceiro
  5. Parceiro pede saque → admin confirma → /pagar_saque <id>

Tabelas usadas: parceiros, vendas_parceiros, saques_parceiros
(novas tabelas, sem conflito com o sistema antigo)
"""

import os, sys, uuid, random, string
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from datetime import datetime
from db.database import get_conn, get_logger
from config import PLANOS

log = get_logger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# INIT
# ══════════════════════════════════════════════════════════════════════════════

def init_parceiros():
    conn = get_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS parceiros (
            chat_id         TEXT PRIMARY KEY,
            nome            TEXT,
            codigo          TEXT UNIQUE NOT NULL,
            saldo           REAL DEFAULT 0.0,
            total_ganho     REAL DEFAULT 0.0,
            total_vendas    INTEGER DEFAULT 0,
            chave_pix       TEXT,
            criado_em       TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS vendas_parceiros (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            parceiro_id     TEXT NOT NULL,
            indicado_id     TEXT NOT NULL,
            plano           TEXT NOT NULL,
            comissao        REAL NOT NULL,
            status          TEXT DEFAULT 'pendente',
            criado_em       TEXT NOT NULL,
            pago_em         TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS saques_parceiros (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            parceiro_id     TEXT NOT NULL,
            valor           REAL NOT NULL,
            chave_pix       TEXT NOT NULL,
            status          TEXT DEFAULT 'pendente',
            criado_em       TEXT NOT NULL,
            pago_em         TEXT
        )
    """)

    # Tabela de rastreamento: quem veio pelo link de quem
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rastreamento (
            indicado_id     TEXT PRIMARY KEY,
            parceiro_id     TEXT NOT NULL,
            criado_em       TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    log.info("Tabelas de parceiros OK")


# ══════════════════════════════════════════════════════════════════════════════
# PARCEIRO
# ══════════════════════════════════════════════════════════════════════════════

def _gerar_codigo() -> str:
    chars = string.ascii_uppercase + string.digits
    return "REF-" + "".join(random.choices(chars, k=6))

def get_ou_criar_parceiro(chat_id: str, nome: str = "") -> dict:
    """Retorna parceiro existente ou cria um novo."""
    chat_id = str(chat_id)
    conn    = get_conn()

    row = conn.execute(
        "SELECT * FROM parceiros WHERE chat_id = ?", (chat_id,)
    ).fetchone()

    if row:
        conn.close()
        return dict(row)

    # Gera código único
    codigo = _gerar_codigo()
    while conn.execute("SELECT 1 FROM parceiros WHERE codigo = ?", (codigo,)).fetchone():
        codigo = _gerar_codigo()

    conn.execute("""
        INSERT INTO parceiros (chat_id, nome, codigo, criado_em)
        VALUES (?, ?, ?, ?)
    """, (chat_id, nome or "", codigo, datetime.now().isoformat()))
    conn.commit()

    row = conn.execute(
        "SELECT * FROM parceiros WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    conn.close()

    log.info(f"Novo parceiro: {nome} ({chat_id}) | código: {codigo}")
    return dict(row)


def buscar_parceiro(chat_id: str) -> dict | None:
    chat_id = str(chat_id)
    conn    = get_conn()
    row     = conn.execute(
        "SELECT * FROM parceiros WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def buscar_parceiro_por_codigo(codigo: str) -> dict | None:
    conn = get_conn()
    row  = conn.execute(
        "SELECT * FROM parceiros WHERE codigo = ?", (codigo.upper(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def atualizar_chave_pix(chat_id: str, chave_pix: str):
    conn = get_conn()
    conn.execute(
        "UPDATE parceiros SET chave_pix = ? WHERE chat_id = ?",
        (chave_pix, str(chat_id))
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# RASTREAMENTO — quem veio pelo link de quem
# ══════════════════════════════════════════════════════════════════════════════

def registrar_acesso(codigo: str, indicado_id: str) -> bool:
    """
    Chamado quando usuário entra via link ?start=REF-xxx.
    Retorna True se registrado, False se já existia.
    """
    parceiro = buscar_parceiro_por_codigo(codigo)
    if not parceiro:
        log.warning(f"Código inválido: {codigo}")
        return False

    indicado_id = str(indicado_id)
    parceiro_id = str(parceiro["chat_id"])

    # Não registra se o parceiro indicou ele mesmo
    if parceiro_id == indicado_id:
        return False

    conn = get_conn()
    existe = conn.execute(
        "SELECT 1 FROM rastreamento WHERE indicado_id = ?", (indicado_id,)
    ).fetchone()

    if existe:
        conn.close()
        return False

    conn.execute("""
        INSERT INTO rastreamento (indicado_id, parceiro_id, criado_em)
        VALUES (?, ?, ?)
    """, (indicado_id, parceiro_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    log.info(f"Rastreamento: {indicado_id} veio de {parceiro_id} ({codigo})")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# VENDA — confirma comissão quando pagamento é aprovado
# ══════════════════════════════════════════════════════════════════════════════

def confirmar_venda(indicado_id: str, plano: str) -> dict | None:
    """
    Chamado pelo webhook quando pagamento é aprovado.
    Se o indicado veio pelo link de um parceiro, credita a comissão.
    Retorna {parceiro_id, parceiro_nome, comissao} ou None.
    """
    indicado_id = str(indicado_id)

    conn = get_conn()
    rastr = conn.execute(
        "SELECT parceiro_id FROM rastreamento WHERE indicado_id = ?",
        (indicado_id,)
    ).fetchone()

    if not rastr:
        conn.close()
        return None  # não veio por indicação

    parceiro_id = rastr["parceiro_id"]

    # Verifica se já foi creditado para esse indicado
    ja_pago = conn.execute(
        "SELECT 1 FROM vendas_parceiros WHERE indicado_id = ? AND status = 'confirmado'",
        (indicado_id,)
    ).fetchone()

    if ja_pago:
        conn.close()
        log.info(f"Venda já creditada para indicado {indicado_id}")
        return None

    # Busca comissão do plano no config
    comissao = float(PLANOS.get(plano, {}).get("comissao", 0))
    if comissao <= 0:
        conn.close()
        log.warning(f"Comissão zero para plano {plano}")
        return None

    agora = datetime.now().isoformat()

    # Registra a venda
    conn.execute("""
        INSERT INTO vendas_parceiros (parceiro_id, indicado_id, plano, comissao, status, criado_em, pago_em)
        VALUES (?, ?, ?, ?, 'confirmado', ?, ?)
    """, (parceiro_id, indicado_id, plano, comissao, agora, agora))

    # Credita no saldo do parceiro
    conn.execute("""
        UPDATE parceiros
        SET saldo       = saldo + ?,
            total_ganho = total_ganho + ?,
            total_vendas = total_vendas + 1
        WHERE chat_id = ?
    """, (comissao, comissao, parceiro_id))

    conn.commit()

    parceiro = conn.execute(
        "SELECT nome FROM parceiros WHERE chat_id = ?", (parceiro_id,)
    ).fetchone()
    conn.close()

    nome_parceiro = parceiro["nome"] if parceiro else parceiro_id
    log.info(f"Comissão creditada: R$ {comissao:.2f} para {nome_parceiro} ({parceiro_id}) | plano={plano}")

    return {
        "parceiro_id":   parceiro_id,
        "parceiro_nome": nome_parceiro,
        "comissao":      comissao,
        "plano":         plano,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SAQUE
# ══════════════════════════════════════════════════════════════════════════════

def solicitar_saque(chat_id: str, chave_pix: str) -> dict | None:
    """
    Parceiro solicita saque do saldo disponível.
    Retorna {id, valor} ou None se saldo insuficiente.
    """
    from config import COMISSAO_MINIMO_SAQUE
    chat_id = str(chat_id)
    conn    = get_conn()

    parceiro = conn.execute(
        "SELECT saldo FROM parceiros WHERE chat_id = ?", (chat_id,)
    ).fetchone()

    if not parceiro or parceiro["saldo"] < COMISSAO_MINIMO_SAQUE:
        conn.close()
        return None

    valor = parceiro["saldo"]

    # Salva chave pix e zera saldo
    conn.execute(
        "UPDATE parceiros SET chave_pix = ?, saldo = 0 WHERE chat_id = ?",
        (chave_pix, chat_id)
    )

    conn.execute("""
        INSERT INTO saques_parceiros (parceiro_id, valor, chave_pix, criado_em)
        VALUES (?, ?, ?, ?)
    """, (chat_id, valor, chave_pix, datetime.now().isoformat()))

    saque_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    log.info(f"Saque solicitado: R$ {valor:.2f} | {chat_id} | pix={chave_pix}")
    return {"id": saque_id, "valor": valor}


def pagar_saque(saque_id: int) -> dict | None:
    """Admin marca saque como pago."""
    conn = get_conn()
    row  = conn.execute(
        "SELECT * FROM saques_parceiros WHERE id = ?", (saque_id,)
    ).fetchone()

    if not row:
        conn.close()
        return None

    conn.execute("""
        UPDATE saques_parceiros SET status = 'pago', pago_em = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), saque_id))
    conn.commit()
    conn.close()

    return dict(row)


def listar_saques_pendentes() -> list:
    conn  = get_conn()
    rows  = conn.execute("""
        SELECT s.*, p.nome
        FROM saques_parceiros s
        LEFT JOIN parceiros p ON p.chat_id = s.parceiro_id
        WHERE s.status = 'pendente'
        ORDER BY s.criado_em
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# RELATÓRIOS
# ══════════════════════════════════════════════════════════════════════════════

def listar_todos_parceiros() -> list:
    """Lista todos os parceiros com métricas completas."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            p.chat_id, p.nome, p.codigo, p.saldo, p.total_ganho,
            p.total_vendas, p.criado_em,
            (SELECT COUNT(*) FROM rastreamento r WHERE r.parceiro_id = p.chat_id) as total_acessos
        FROM parceiros p
        ORDER BY p.total_vendas DESC, p.total_ganho DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def parceiros_com_saldo() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.chat_id, p.nome, p.saldo, p.total_ganho, p.total_vendas, p.chave_pix
        FROM parceiros p
        WHERE p.saldo > 0
        ORDER BY p.saldo DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def historico_parceiro(chat_id: str) -> dict:
    """Dados completos de um parceiro para exibir na carteira."""
    chat_id = str(chat_id)
    conn    = get_conn()

    parceiro = conn.execute(
        "SELECT * FROM parceiros WHERE chat_id = ?", (chat_id,)
    ).fetchone()

    if not parceiro:
        conn.close()
        return {}

    # Conta quantas pessoas acessaram via link
    total_acessos = conn.execute(
        "SELECT COUNT(*) FROM rastreamento WHERE parceiro_id = ?", (chat_id,)
    ).fetchone()[0]

    # Últimas 5 vendas
    ultimas = conn.execute("""
        SELECT indicado_id, plano, comissao, criado_em
        FROM vendas_parceiros
        WHERE parceiro_id = ? AND status = 'confirmado'
        ORDER BY criado_em DESC LIMIT 5
    """, (chat_id,)).fetchall()

    conn.close()
    return {
        **dict(parceiro),
        "total_acessos": total_acessos,
        "ultimas_vendas": [dict(r) for r in ultimas],
    }
