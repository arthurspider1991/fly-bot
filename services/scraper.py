"""
services/scraper.py — Preço via Kayak + Histórico via Google Flights.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import base64
import re
from datetime import date, timedelta
from typing import Optional, Tuple

from config import get_logger

log = get_logger(__name__)


# ── URLs ──────────────────────────────────────────────────────────────────────

def url_kayak(origem: str, destino: str, data_iso: str) -> str:
    return f"https://www.kayak.com.br/flights/{origem}-{destino}/{data_iso}?sort=price_a"

def _gerar_tfs(origem: str, destino: str, data_iso: str) -> str:
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

def url_google(origem: str, destino: str, data_iso: str) -> str:
    tfs = _gerar_tfs(origem, destino, data_iso)
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&hl=pt-BR&gl=BR&curr=BRL"

def link_flights(origem: str, destino: str, data_iso: str) -> str:
    return f"[🔍 Ver passagens disponíveis]({url_kayak(origem, destino, data_iso)})"


# ── Parser BRL ────────────────────────────────────────────────────────────────

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


# ── Browser ───────────────────────────────────────────────────────────────────

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


# ── Preço via Kayak ───────────────────────────────────────────────────────────

def _buscar_preco_kayak(page, origem: str, destino: str, data_iso: str):
    url = url_kayak(origem, destino, data_iso)
    log.info(f"  Kayak: {origem}->{destino} {data_iso}")
    page.goto(url, timeout=50000)

    for sel in ["button:has-text('Aceitar')", "button:has-text('Accept')", "#onetrust-accept-btn-handler"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(1000)
                break
        except Exception:
            pass

    preco_ant = None
    estavel   = 0
    for t in range(40):
        page.wait_for_timeout(1000)
        try:
            precos_raw = page.evaluate("""
                () => {
                    const result = [];
                    const els = document.querySelectorAll('div.e2GB-price-text');
                    for (const el of els) {
                        const txt = (el.innerText || '').trim();
                        if (!txt.startsWith('R$') || txt.length > 15) continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        result.push(txt);
                    }
                    return result;
                }
            """)
            precos = [v for s in precos_raw for v in [_parse_brl(s)] if v]
            menor  = min(precos) if precos else None
        except Exception:
            menor = None

        if menor:
            log.info(f"  [{t+1}s] Kayak: R$ {menor:.0f}")
            if menor == preco_ant:
                estavel += 1
                if estavel >= 4:
                    log.info(f"  Kayak estável: R$ {menor:.0f}")
                    break
            else:
                estavel   = 0
                preco_ant = menor

    # Captura aeroporto alternativo (card rVsP)
    alternativo = None
    try:
        alt = page.evaluate("""
            () => {
                const card = document.querySelector('div.rVsP-price-display, span.rVsP-price-display');
                if (!card) return null;
                const preco = (card.innerText || '').trim();
                // Pega o texto descritivo do card (aeroporto e distância)
                const container = card.closest('[class*="rVsP"]') || card.parentElement;
                const desc = container ? (container.innerText || '').replace(preco, '').trim() : '';
                return {preco: preco, desc: desc.substring(0, 100)};
            }
        """)
        if alt and alt.get('preco'):
            v = _parse_brl(alt['preco'])
            if v:
                alternativo = {'preco': v, 'desc': alt.get('desc', '')}
                log.info(f"  Alternativo: R$ {v:.0f} — {alt.get('desc','')[:50]}")
    except Exception as e:
        log.warning(f"  Alternativo: {e}")

    return preco_ant, alternativo


# ── Histórico via Google Flights ──────────────────────────────────────────────

def _buscar_historico_google(page, origem: str, destino: str, data_iso: str) -> list:
    url = url_google(origem, destino, data_iso)
    log.info(f"  Google histórico: {origem}->{destino} {data_iso}")
    try:
        page.goto(url, timeout=50000)
        try:
            page.wait_for_selector("ul.Rk10dc", timeout=20000)
        except Exception:
            page.wait_for_timeout(20000)

        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            pass

        # Aguarda mais um pouco para garantir que os botões carregaram
        page.wait_for_timeout(3000)

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
                    break
            except Exception:
                continue

        if not btn_el:
            log.warning("  Histórico: botão não encontrado")
            return []

        btn_el.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        btn_el.click()
        log.info("  Histórico: clicado, aguardando SVG...")
        page.wait_for_timeout(10000)

        hoje = date.today()
        temp = []
        for el in page.query_selector_all("[aria-label]"):
            try:
                label = (
                    (el.get_attribute("aria-label") or "")
                    .replace("\xa0", " ").replace("\u202f", " ")
                    .replace("\u00a0", " ").strip()
                )
                m = re.match(r"H[aá] (\d+) dias? - R\$ ([\d.]+)", label)
                if m:
                    dias_atras = int(m.group(1))
                    preco      = int(m.group(2).replace(".", ""))
                    temp.append({
                        "dias_atras": dias_atras,
                        "preco":      preco,
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

        log.info(f"  Histórico: {len(temp)} pontos")
        if len(temp) >= 10:
            return sorted(temp, key=lambda x: x["dias_atras"], reverse=True)

    except Exception as e:
        log.warning(f"  Histórico indisponível: {e}")

    return []


# ── Funções públicas ──────────────────────────────────────────────────────────

def buscar_preco_e_historico(
    origem: str, destino: str, data_iso: str
) -> Tuple[Optional[float], list]:
    """Preço via Kayak + histórico via Google Flights."""
    from playwright.sync_api import sync_playwright

    preco = None
    hist  = []
    try:
        with sync_playwright() as p:
            browser, context = _novo_browser_context(p)
            page = context.new_page()
            resultado = _buscar_preco_kayak(page, origem, destino, data_iso)
            preco, alt = resultado if isinstance(resultado, tuple) else (resultado, None)
            hist  = _buscar_historico_google(page, origem, destino, data_iso)
            browser.close()
    except Exception as e:
        log.error(f"  Playwright erro: {e}")

    return preco, hist, alt if 'alt' in dir() else None


def buscar_preco_apenas(origem: str, destino: str, data_iso: str) -> Optional[float]:
    """Versão rápida com cache — ciclo de 2h, só Kayak."""
    from db.cache import chave_rota, get_cache, set_cache

    chave  = chave_rota(origem, destino, data_iso)
    cached = get_cache(chave)
    if cached is not None:
        return cached

    from playwright.sync_api import sync_playwright
    preco = None
    try:
        with sync_playwright() as p:
            browser, context = _novo_browser_context(p)
            page = context.new_page()
            resultado = _buscar_preco_kayak(page, origem, destino, data_iso)
            preco, _ = resultado if isinstance(resultado, tuple) else (resultado, None)
            browser.close()
    except Exception as e:
        log.error(f"  Playwright erro: {e}")

    set_cache(chave, preco)
    return preco

def buscar_historico_apenas(origem: str, destino: str, data_iso: str) -> list:
    """Busca só o histórico de 60 dias via Google Flights, sem preço."""
    from playwright.sync_api import sync_playwright
    hist = []
    try:
        with sync_playwright() as p:
            browser, context = _novo_browser_context(p)
            page = context.new_page()
            hist = _buscar_historico_google(page, origem, destino, data_iso)
            browser.close()
    except Exception as e:
        log.error(f"  Playwright erro histórico: {e}")
    return hist
