"""
db/financeiro.py
Registra e consulta todas as movimentações financeiras do bot.

Tabela: movimentacoes
  tipo: 'receita' | 'comissao' | 'saque'
  status: 'confirmado' | 'pendente' | 'pago'

Comandos do admin:
  /financeiro        — resumo geral (receita, comissões, lucro)
  /extrato           — últimas 30 movimentações
  /afiliados_saldo   — afiliados com saldo a pagar
  /confirmar_saque N — marca saque como pago
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from datetime import datetime
from db.database import get_conn, get_logger

log = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

def init_financeiro():
    """Cria tabela de movimentações se não existir."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo        TEXT NOT NULL,
            descricao   TEXT,
            valor       REAL NOT NULL,
            chat_id     TEXT,
            nome        TEXT,
            plano       TEXT,
            ref_id      TEXT,
            status      TEXT DEFAULT 'confirmado',
            criado_em   TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    log.info("Tabela movimentacoes OK")


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRO DE MOVIMENTAÇÕES
# ══════════════════════════════════════════════════════════════════════════════

def registrar_receita(chat_id: str, nome: str, plano: str, valor: float, payment_id: str):
    """Registra entrada de receita quando pagamento é confirmado."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO movimentacoes (tipo, descricao, valor, chat_id, nome, plano, ref_id, status, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmado', ?)
    """, (
        "receita",
        f"Assinatura {plano} — {nome}",
        valor,
        chat_id,
        nome,
        plano,
        payment_id,
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()
    log.info(f"Receita registrada: R$ {valor:.2f} | {nome} | {plano} | payment={payment_id}")


def registrar_comissao(afiliado_id: str, afiliado_nome: str, indicado_nome: str,
                       plano: str, valor: float, indicacao_id: str):
    """Registra comissão gerada para afiliado."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO movimentacoes (tipo, descricao, valor, chat_id, nome, plano, ref_id, status, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pendente', ?)
    """, (
        "comissao",
        f"Comissão de {afiliado_nome} por indicar {indicado_nome}",
        valor,
        afiliado_id,
        afiliado_nome,
        plano,
        str(indicacao_id),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()
    log.info(f"Comissão registrada: R$ {valor:.2f} | afiliado={afiliado_id} | plano={plano}")


def registrar_saque_mov(chat_id: str, nome: str, valor: float, saque_id: int):
    """Registra saque solicitado por afiliado."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO movimentacoes (tipo, descricao, valor, chat_id, nome, ref_id, status, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?)
    """, (
        "saque",
        f"Saque solicitado por {nome}",
        valor,
        chat_id,
        nome,
        str(saque_id),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


def confirmar_saque_mov(saque_id: int):
    """Marca saque como pago."""
    conn = get_conn()
    conn.execute("""
        UPDATE movimentacoes SET status = 'pago'
        WHERE tipo = 'saque' AND ref_id = ?
    """, (str(saque_id),))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# RELATÓRIOS
# ══════════════════════════════════════════════════════════════════════════════

def relatorio_geral() -> dict:
    """
    Retorna resumo financeiro completo:
    - receita_total: tudo que entrou
    - comissoes_pendentes: a pagar para afiliados
    - comissoes_pagas: já sacadas
    - lucro_liquido: receita - comissões pendentes - comissões pagas
    - total_assinaturas: quantidade de pagamentos
    - total_afiliados_com_saldo: quantos têm saldo a receber
    """
    conn = get_conn()

    receita_total = conn.execute(
        "SELECT COALESCE(SUM(valor), 0) FROM movimentacoes WHERE tipo = 'receita' AND status = 'confirmado'"
    ).fetchone()[0]

    comissoes_pendentes = conn.execute(
        "SELECT COALESCE(SUM(valor), 0) FROM movimentacoes WHERE tipo = 'comissao' AND status = 'pendente'"
    ).fetchone()[0]

    comissoes_pagas = conn.execute(
        "SELECT COALESCE(SUM(valor), 0) FROM movimentacoes WHERE tipo = 'saque' AND status = 'pago'"
    ).fetchone()[0]

    total_assinaturas = conn.execute(
        "SELECT COUNT(*) FROM movimentacoes WHERE tipo = 'receita' AND status = 'confirmado'"
    ).fetchone()[0]

    afiliados_com_saldo = conn.execute(
        "SELECT COUNT(*) FROM afiliados WHERE saldo > 0"
    ).fetchone()[0]

    saques_pendentes_valor = conn.execute(
        "SELECT COALESCE(SUM(valor), 0) FROM movimentacoes WHERE tipo = 'saque' AND status = 'pendente'"
    ).fetchone()[0]

    conn.close()

    lucro_liquido = receita_total - comissoes_pendentes - comissoes_pagas

    return {
        "receita_total":          receita_total,
        "comissoes_pendentes":    comissoes_pendentes,
        "comissoes_pagas":        comissoes_pagas,
        "saques_pendentes_valor": saques_pendentes_valor,
        "lucro_liquido":          lucro_liquido,
        "total_assinaturas":      total_assinaturas,
        "afiliados_com_saldo":    afiliados_com_saldo,
    }


def extrato_recente(limite: int = 30) -> list:
    """Retorna as últimas N movimentações."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT tipo, descricao, valor, status, criado_em
        FROM movimentacoes
        ORDER BY id DESC
        LIMIT ?
    """, (limite,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def afiliados_com_saldo_detalhado() -> list:
    """Lista afiliados com saldo pendente para pagamento."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.chat_id, a.saldo, a.total_ganho, a.total_pagantes,
               u.nome,
               s.chave_pix
        FROM afiliados a
        LEFT JOIN usuarios u ON u.chat_id = a.chat_id
        LEFT JOIN saques s ON s.chat_id = a.chat_id AND s.status = 'pendente'
        WHERE a.saldo > 0
        ORDER BY a.saldo DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def receita_por_plano() -> list:
    """Receita agrupada por plano."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT plano,
               COUNT(*) as qtd,
               SUM(valor) as total
        FROM movimentacoes
        WHERE tipo = 'receita' AND status = 'confirmado'
        GROUP BY plano
        ORDER BY total DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
