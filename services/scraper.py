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
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&hl=pt-BR"

def link_flights(origem: str, destino: str, data_iso: str) -> str:
    return url_google(origem, destino, data_iso)


# ── AUXILIARES ────────────────────────────────────────────────────────────────

def _parse_brl(texto: str) -> Optional[float]:
    if not texto: return None
    limpo = re.sub(r'[^\d,]', '', texto)
    if not limpo: return None
    limpo = limpo.replace(',', '.')
    try:
        return float(limpo)
    except:
        return None

def _novo_browser_context(playwright):
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled"
        ]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo"
    )
    return browser, context


# ── PRIVATE SCRAPERS ──────────────────────────────────────────────────────────

def _buscar_preco_kayak(page, origem: str, destino: str, data_iso: str):
    url = url_kayak(origem, destino, data_iso)
    log.info(f"  Kayak: {origem}->{destino} {data_iso}")
    page.goto(url, timeout=50000)

    # 1. Aceita os cookies se o aviso aparecer
    for sel in ["button:has-text('Aceitar')", "button:has-text('Accept')", "#onetrust-accept-btn-handler"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(1000)
                break
        except Exception:
            pass

    # ── 🔍 AGUARDAR A BARRA LARANJA SUMIR ──────────────────────────
    log.info("  Aguardando o Kayak finalizar a busca (barra laranja)...")
    try:
        seletor_loading = 'div[role="progressbar"], .skp2, .skp2-bar'
        
        try:
            page.wait_for_selector(seletor_loading, state="visible", timeout=4000)
            log.info("  Barra de progresso detectada. Aguardando conclusão...")
        except Exception:
            log.info("  A barra de progresso não apareceu a tempo ou já sumiu.")

        page.wait_for_selector(seletor_loading, state="hidden", timeout=35000)
        log.info("  Carregamento do Kayak 100% concluído!")
        page.wait_for_timeout(2000)
        
    except Exception as e:
        log.warning(f"  Aviso no carregamento: {e}. Coletando dados atuais da tela.")
    # ──────────────────────────────────────────────────────────────────────────

    # 2. Coleta dos preços
    menor = None
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
    except Exception as e:
        log.error(f"  Erro ao ler preços do HTML: {e}")

    if menor:
        log.info(f"  Kayak finalizado com sucesso! Menor preço real: R$ {menor:.0f}")
    else:
        log.warning("  Nenhum preço foi encontrado na página do Kayak.")

    # 3. Captura o aeroporto alternativo
    alternativo = None
    try:
        alt = page.evaluate("""
            () => {
                const card = document.querySelector('div.rVsP-price-display, span.rVsP-price-display');
                if (!card) return null;
                const preco = (card.innerText || '').trim();
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

    return menor, alternativo


def _buscar_historico_flights(page, url_flights: str) -> list:
    log.info("  Google Flights Histórico...")
    historico = []
    try:
        page.goto(url_flights, timeout=50000)
        page.wait_for_timeout(2000)

        btn = page.query_selector("button:has-text('Ver histórico de preços'), button:has-text('histórico de preços')")
        if btn:
            btn.click()
            page.wait_for_timeout(2000)

        elementos = page.query_selector_all("[aria-label*='Preço baixo'], [aria-label*='Preço típico'], [aria-label*='Preço alto'], [aria-label*='as de ']")
        log.info(f"  Aria-labels encontrados no gráfico: {len(elementos)}")

        for el in elementos:
            lbl = el.get_attribute("aria-label") or ""
            match_dias = re.search(r'(\d+)\s+dias?\s+atrás', lbl, re.IGNORECASE)
            match_rs   = re.search(r'R\$\s*([\d\.]+)', lbl)
            
            if match_dias and match_rs:
                dias_atras = int(match_dias.group(1))
                valor      = float(match_rs.group(1).replace('.', ''))
                dt = (date.today() - timedelta(days=dias_atras)).isoformat()
                historico.append({"data": dt, "preco": valor})

        historico.sort(key=lambda x: x['data'])
    except Exception as e:
        log.error(f"  Falha no histórico do Google Flights: {e}")
    return historico


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def buscar_preco_e_historico(origem: str, destino: str, data_iso: str) -> Tuple[Optional[float], list, Optional[dict]]:
    """Função mestre para ciclos pesados."""
    from playwright.sync_api import sync_playwright
    preco, hist, alt = None, [], None
    try:
        with sync_playwright() as p:
            browser, context = _novo_browser_context(p)
            page = context.new_page()

            # 1. Preço atual Kayak
            preco, alt = _buscar_preco_kayak(page, origem, destino, data_iso)

            # 2. Histórico Google Flights
            url_g = url_google(origem, destino, data_iso)
            hist = _buscar_historico_flights(page, url_g)

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
            url_g = url_google(origem, destino, data_iso)
            hist = _buscar_historico_flights(page, url_g)
            browser.close()
    except Exception as e:
        log.error(f"  Playwright erro: {e}")
    return hist