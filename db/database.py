"""
db/database.py — Conexão SQLite, criação de tabelas e migração do JSON legado.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import json
import os
import sqlite3
import threading

from config import DB_FILE, get_logger

log   = get_logger(__name__)
_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # suporte a leituras simultâneas
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Cria tabelas e colunas novas (migração suave)."""
    with _lock:
        conn = get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                chat_id          TEXT PRIMARY KEY,
                nome             TEXT,
                status           TEXT DEFAULT 'aguardando_pagamento',
                config           TEXT DEFAULT '{}',
                historico        TEXT DEFAULT '{}',
                historico_precos TEXT DEFAULT '{}',
                liberado_em      TEXT,
                plano            TEXT DEFAULT '1mes',
                proxima_busca    TEXT,
                slot_manha       TEXT,
                status_temp      TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_rotas (
                chave        TEXT PRIMARY KEY,
                preco        REAL,
                ultima_busca TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS afiliados (
                chat_id       TEXT PRIMARY KEY,
                codigo        TEXT UNIQUE,
                saldo         REAL DEFAULT 0,
                total_ganho   REAL DEFAULT 0,
                total_indicados INTEGER DEFAULT 0,
                total_pagantes  INTEGER DEFAULT 0,
                criado_em     TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indicacoes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                afiliado_id   TEXT,
                indicado_id   TEXT,
                plano         TEXT,
                comissao      REAL DEFAULT 0,
                status        TEXT DEFAULT 'pendente',
                criado_em     TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saques (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     TEXT,
                valor       REAL,
                chave_pix   TEXT,
                status      TEXT DEFAULT 'pendente',
                criado_em   TEXT
            )
        """)
        # Migração suave afiliados
        for col, default in [
            ("afiliado_ref", "NULL"),
            ("preference_id", "NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE usuarios ADD COLUMN {col} TEXT DEFAULT {default}")
            except Exception:
                pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS afiliados (
                chat_id         TEXT PRIMARY KEY,
                codigo          TEXT UNIQUE,
                saldo           REAL DEFAULT 0,
                total_ganho     REAL DEFAULT 0,
                total_indicados INTEGER DEFAULT 0,
                total_pagantes  INTEGER DEFAULT 0,
                criado_em       TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indicacoes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                afiliado_chat_id TEXT,
                indicado_chat_id TEXT,
                plano           TEXT,
                comissao        REAL,
                status          TEXT DEFAULT 'pendente',
                criado_em       TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads_internacionais (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    TEXT,
                nome       TEXT,
                origem     TEXT,
                destino    TEXT,
                criado_em  TEXT
            )
        """)
        # Garante tabelas novas existam (bancos antigos)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS afiliados (
                chat_id         TEXT PRIMARY KEY,
                codigo          TEXT UNIQUE,
                saldo           REAL DEFAULT 0,
                total_ganho     REAL DEFAULT 0,
                total_indicados INTEGER DEFAULT 0,
                total_pagantes  INTEGER DEFAULT 0,
                criado_em       TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indicacoes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                afiliado_chat_id TEXT,
                indicado_chat_id TEXT,
                plano            TEXT,
                comissao         REAL,
                status           TEXT DEFAULT 'pendente',
                criado_em        TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads_internacionais (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   TEXT,
                nome      TEXT,
                origem    TEXT,
                destino   TEXT,
                criado_em TEXT
            )
        """)

        # Migração suave: adiciona colunas caso venha de versão anterior
        for col, default in [
            ("historico_precos", "'{}'"),
            ("plano",            "'60dias'"),
            ("proxima_busca",    "NULL"),
            ("slot_manha",       "NULL"),
            ("ref_afiliado",     "NULL"),
            ("status_temp",      "NULL"),
            ("payment_id",       "NULL"),
            ("preference_id",    "NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE usuarios ADD COLUMN {col} TEXT DEFAULT {default}")
            except Exception:
                pass
        conn.commit()
        conn.close()
    log.info("Banco SQLite inicializado (WAL mode).")


def migrar_json_para_sqlite() -> None:
    """Importa usuarios.json legado para o SQLite, se existir."""
    from db.usuarios import salvar_usuario

    if not os.path.exists("usuarios.json"):
        return
    try:
        with open("usuarios.json", "r", encoding="utf-8") as f:
            dados = json.load(f)
        for chat_id, u in dados.items():
            salvar_usuario(chat_id, u)
        os.rename("usuarios.json", "usuarios.json.bak")
        log.info(f"Migrados {len(dados)} usuários de JSON para SQLite.")
    except Exception as e:
        log.error(f"Erro na migração JSON→SQLite: {e}")
