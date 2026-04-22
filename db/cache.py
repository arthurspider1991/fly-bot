"""
db/cache.py — Cache de preços de rotas no SQLite.
Substitui o cache_rotas.json — persiste entre reinicializações do container.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import threading
from datetime import datetime
from typing import Optional

from db.database import get_conn
from config import get_logger

log   = get_logger(__name__)
_lock = threading.Lock()

CACHE_TTL_MINUTOS = 110  # reutiliza se buscado há menos de 1h50min


def chave_rota(origem: str, destino: str, data_iso: str) -> str:
    return f"{origem}-{destino}-{data_iso}"


def get_cache(chave: str) -> Optional[float]:
    """Retorna preço em cache se ainda válido, ou None."""
    with _lock:
        conn = get_conn()
        row  = conn.execute(
            "SELECT preco, ultima_busca FROM cache_rotas WHERE chave = ?", (chave,)
        ).fetchone()
        conn.close()

    if not row or row["preco"] is None:
        return None

    ultima = row["ultima_busca"]
    if ultima:
        delta = (datetime.now() - datetime.fromisoformat(ultima)).total_seconds() / 60
        if delta < CACHE_TTL_MINUTOS:
            log.info(f"  Cache hit: {chave} ({delta:.0f}min)")
            return row["preco"]

    return None


def set_cache(chave: str, preco: Optional[float]) -> None:
    """Grava ou atualiza um preço no cache."""
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO cache_rotas (chave, preco, ultima_busca)
            VALUES (?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET
                preco        = excluded.preco,
                ultima_busca = excluded.ultima_busca
        """, (chave, preco, datetime.now().isoformat()))
        conn.commit()
        conn.close()


def limpar_cache_antigo() -> None:
    """Remove entradas com mais de 24h (manutenção opcional)."""
    from datetime import timedelta
    limite = (datetime.now() - timedelta(hours=24)).isoformat()
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM cache_rotas WHERE ultima_busca < ?", (limite,))
        conn.commit()
        conn.close()
    log.info("Cache antigo limpo.")
