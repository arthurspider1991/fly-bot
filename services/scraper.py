"""
services/scraper.py — Busca de preços via Playwright + Google Flights.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



import base64
import re
from datetime import date, timedelta
from typing import Optional, Tuple

from config import get_logger

log = get_logger(__name__)


# ── URL builder ───────────────────────────────────────────────────────────────

def _gerar_tfs(origem: str, destino: str, data_iso: str) -> str:
    """Gera o parâmetro tfs (protobuf base64) para URL do Google Flights one-way."""
    ori   = origem.encode()
    dst   = destino.encode()
    dat   = data_iso.encode()
    inner = (
        b'\x12\x0a' + dat +
        b'\x6a\x07\x08\x01\x12\x03' + ori +
        b'\x72\x07\x08\x01\x12\x03' + dst
    )
    wrapper = b'\x08\x1c\x10\x02\x1a' + bytes([len(inner)]) + inner
    return base64.urlsafe_b64encode(wrapper).decode().rstrip("=")


def url_flights(origem: str, destino: str, data_iso: str) -> str:
    tfs = _gerar_tfs(origem, destino, data_iso)
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&hl=pt-BR&gl=BR&curr=BRL"


def link_flights(origem: str, destino: str, data_iso: str) -> str:
    return f"[🔍 Ver passagens disponíveis]({url_flights(origem, destino, data_iso)})"


# ── Parser de preço BRL ───────────────────────────────────────────────────────

def _parse_brl(txt: str) -> Optional[float]:
    try:
        limpo = (
            txt.replace("R$", "").replace("\xa0", "").replace("\u202f", "")
               .replace(" ", "").replace(".", "").replace(",", ".").strip()
        )
        v = float(limpo)
        return v if 150 < v < 25000 else None
    except Exception:
        return None


# ── Browser context ───────────────────────────────────────────────────────────

def _novo_browser_context(p):
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1440, "height": 900},
    )
    return browser, context


# ── Busca principal ───────────────────────────────────────────────────────────

def buscar_preco_e_historico(
    origem: str, destino: str, data_iso: str
) -> Tuple[Optional[float], list]:
    """
    Abre o Google Flights UMA vez e retorna:
      preco    : float ou None  (menor preço atual)
      historico: list de dicts {dias_atras, preco, data} ou []
    """
    from playwright.sync_api import sync_playwright

    url   = url_flights(origem, destino, data_iso)
    preco = None
    hist  = []

    try:
        with sync_playwright() as p:
            browser, context = _novo_browser_context(p)
            page = context.new_page()
            log.info(f"  Flights: {origem}->{destino} {data_iso}")
            page.goto(url, timeout=50000)
            page.wait_for_timeout(12000)
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(800)
            except Exception:
                pass

            # ── Preço atual ──────────────────────────────────────────────────
            prices = []
            for el in page.query_selector_all("span"):
                try:
                    txt = el.inner_text().strip()
                    if "R$" in txt:
                        v = _parse_brl(txt)
                        if v:
                            prices.append(v)
                except Exception:
                    pass
            if not prices:
                for el in page.query_selector_all("div[class*='price'],div[class*='Price']"):
                    try:
                        v = _parse_brl(el.inner_text().strip())
                        if v:
                            prices.append(v)
                    except Exception:
                        pass
            if prices:
                preco = sorted(set(prices))[0]
                log.info(f"  Preco: R$ {preco:.2f}")

            # ── Histórico 60 dias ────────────────────────────────────────────
            try:
                btn_el = None
                for frame in [page] + list(page.frames):
                    try:
                        handle = frame.evaluate_handle("""
                            () => {
                                const botoes = document.querySelectorAll('button[aria-label]');
                                for (const b of botoes) {
                                    const l = (b.getAttribute('aria-label') || '').toLowerCase();
                                    if ((l.includes('hist') && l.includes('pre')) ||
                                        l.includes('price history') ||
                                        l === 'ver histórico de preços') {
                                        return b;
                                    }
                                }
                                return null;
                            }
                        """)
                        el = handle.as_element() if handle else None
                        if el:
                            btn_el = el
                            log.info(f"  Historico: botão no frame {frame.url[:50]}")
                            break
                    except Exception:
                        continue

                if btn_el:
                    btn_el.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
                    btn_el.click()
                    log.info("  Historico: clicado, aguardando SVG...")
                    page.wait_for_timeout(5000)

                    hoje = date.today()
                    temp = []
                    aria_els = page.query_selector_all("[aria-label]")
                    for el in aria_els:
                        try:
                            label = (
                                (el.get_attribute("aria-label") or "")
                                .replace("\xa0", " ").replace("\u202f", " ")
                                .replace("\u00a0", " ").strip()
                            )
                            m = re.match(r"H[aá] (\d+) dias? - R\$ ([\d.]+)", label)
                            if m:
                                dias_atras = int(m.group(1))
                                p          = int(m.group(2).replace(".", ""))
                                temp.append({
                                    "dias_atras": dias_atras,
                                    "preco":      p,
                                    "data":       (hoje - timedelta(days=dias_atras)).isoformat(),
                                })
                            elif label.startswith("Hoje") and "R$" in label:
                                m2 = re.search(r"R\$ ([\d.]+)", label)
                                if m2:
                                    temp.append({
                                        "dias_atras": 0,
                                        "preco":      int(m2.group(1).replace(".", "")),
                                        "data":       hoje.isoformat(),
                                    })
                        except Exception:
                            continue

                    log.info(f"  Historico: {len(temp)} pontos")
                    if len(temp) >= 10:
                        hist = sorted(temp, key=lambda x: x["dias_atras"], reverse=True)
                else:
                    log.warning("  Historico: botão não encontrado")
            except Exception as e:
                log.warning(f"  Historico indisponível: {e}")

            browser.close()
    except Exception as e:
        log.error(f"  Playwright erro: {e}")

    return preco, hist


def buscar_preco_apenas(origem: str, destino: str, data_iso: str) -> Optional[float]:
    """
    Versão rápida com cache — usada no ciclo de 2h.
    Não busca histórico para economizar tempo.
    """
    from db.cache import chave_rota, get_cache, set_cache

    chave  = chave_rota(origem, destino, data_iso)
    cached = get_cache(chave)
    if cached is not None:
        return cached

    preco, _ = buscar_preco_e_historico(origem, destino, data_iso)
    set_cache(chave, preco)
    return preco
