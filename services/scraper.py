"""
services/scraper.py — Preço via Kayak + Histórico via Google Flights + Previsão via AirHint.
Versão com Timeouts Blindados — Previne travamentos infinitos no Railway.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import base64
import re
from datetime import date, timedelta, datetime
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

def _novo_browser_context(p, headless=True):
    browser = p.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox", 
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            # ── 🧠 ARGUMENTOS PARA ECONOMIA DE MEMÓRIA RAM (Anti-Crash Railway) ──
            "--disable-gpu",                  # Desativa aceleração de hardware (reduz muita RAM)
            "--disable-software-rasterizer",   # Evita renderizações 3D pesadas em CPU
            "--disable-extensions",            # Desativa extensões internas
            "--no-first-run",                  # Pula setups iniciais do browser
            "--no-zygote",                     # Evita processos filhos redundantes
            "--single-process",                # Força o Chromium a rodar tudo em uma única thread
        ],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1280, "height": 720}, # Reduzido ligeiramente para exigir menos buffer gráfico
    )
    return browser, context


# ── Preço via Kayak ───────────────────────────────────────────────────────────

def _buscar_preco_kayak(page, origem: str, destino: str, data_iso: str):
    page.set_default_timeout(30000) # Timeout padrão de segurança para o Kayak
    url = url_kayak(origem, destino, data_iso)
    log.info(f"  Kayak: {origem}->{destino} {data_iso}")
    page.goto(url, timeout=40000)

    for sel in ["button:has-text('Aceitar')", "button:has-text('Accept')", "#onetrust-accept-btn-handler"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=3000)
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

    # Captura aeroporto alternativo
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

    return preco_ant, alternativo


# ── Histórico via Google Flights ──────────────────────────────────────────────

def _buscar_historico_google(page, origem: str, destino: str, data_iso: str) -> list:
    page.set_default_timeout(30000) # Timeout padrão de segurança para o Google
    url = url_google(origem, destino, data_iso)
    log.info(f"  Google histórico: {origem}->{destino} {data_iso}")
    try:
        page.goto(url, timeout=40000)
        try:
            page.wait_for_selector("ul.Rk10dc", timeout=15000)
        except Exception:
            page.wait_for_timeout(5000)

        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            pass

        page.wait_for_timeout(2000)

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
        btn_el.click(timeout=5000)
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


# ── Previsão via AirHint ──────────────────────────────────────────────────────

MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
}

def _data_iso_para_airhint(data_iso: str) -> tuple:
    dt = datetime.strptime(data_iso, "%Y-%m-%d")
    return str(dt.day), f"{MESES_PT[dt.month]} {dt.year}"

def _navegar_calendario(page, selector_input: str, mes_ano_alvo: str, dia_alvo: str) -> bool:
    meses_map = {
        "janeiro":1,"fevereiro":2,"março":3,"abril":4,"maio":5,"junho":6,
        "julho":7,"agosto":8,"setembro":9,"outubro":10,"novembro":11,"dezembro":12
    }
    alvo_partes  = mes_ano_alvo.lower().strip().split()
    mes_alvo_num = meses_map.get(alvo_partes[0], 1)
    ano_alvo_num = int(alvo_partes[1])

    page.click("body", position={"x": 0, "y": 0}, force=True, timeout=5000)
    page.wait_for_timeout(500)
    page.click(selector_input, force=True, timeout=5000)
    page.wait_for_selector(".datepicker-dropdown", state="attached", timeout=10000)

    for i in range(12):
        switch_mes = page.locator(".datepicker-dropdown:visible .datepicker-switch").first
        texto_atual = switch_mes.inner_text().strip().lower()

        if mes_ano_alvo.lower() in texto_atual:
            dia_el = page.locator(
                ".datepicker-dropdown:visible td.day:not(.old):not(.new)",
                has_text=str(int(dia_alvo))
            ).first
            dia_el.click(force=True, timeout=5000)
            page.wait_for_timeout(1000)
            return True

        atual_partes  = texto_atual.split()
        mes_atual_num = meses_map.get(atual_partes[0], 1)
        ano_atual_num = int(atual_partes[1])

        if (ano_alvo_num < ano_atual_num) or (ano_alvo_num == ano_atual_num and mes_alvo_num < mes_atual_num):
            page.locator(".datepicker-dropdown:visible .prev").first.click(force=True, timeout=5000)
        else:
            page.locator(".datepicker-dropdown:visible .next").first.click(force=True, timeout=5000)
        page.wait_for_timeout(800)

    return False

def _buscar_previsao_airhint(
    page, origem: str, destino: str,
    data_ida_iso: str, data_volta_iso: Optional[str] = None
) -> Optional[dict]:
    log.info(f"  AirHint: {origem}->{destino} ida={data_ida_iso} volta={data_volta_iso}")
    apenas_ida = data_volta_iso is None

    try:
        # Trava rígida de proteção: se qualquer ação demorar mais de 25s, o script desiste
        page.set_default_timeout(25000)

        try:
            page.goto("https://www.airhint.com/pt", timeout=35000, wait_until="commit")
        except Exception as e_nav:
            log.warning(f"  AirHint navegação interceptada/lenta: {e_nav}")

        time.sleep(2.0)

        # Cookies — Varredura ultra rápida (limite individual de 1.5s por tentativa)
        seletores_cookies = [
            "button.css-1jqk1n3", "button:has-text('CONCORDO')",
            "button:has-text('Aceitar')", "button:has-text('Accept')",
            ".fc-cta-consent", "button.fc-button"
        ]
        for sel in seletores_cookies:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    el.click(force=True, timeout=2000)
                    log.info(f"  AirHint: cookies aceitos via '{sel}'")
                    time.sleep(1.0)
                    break
            except Exception:
                pass

        # Limpeza física via JS de modais que bloqueiam cliques
        try:
            page.evaluate("""
                () => {
                    const overlays = document.querySelectorAll(
                        '.fc-consent-root, .cc-window, #onetrust-banner-sdk, .cookie-consent'
                    );
                    overlays.forEach(el => el.remove());
                    document.body.style.overflow = 'auto';
                }
            """)
        except Exception:
            pass

        # ── 🔄 ALTERAÇÃO ULTRA-RESILIENTE DE MODALIDADE ─────────────────────
        # Se for Ida e Volta, garantimos o clique no botão visual caso o rádio falhe.
        # Se for Apenas Ida, deixamos o site alternar sozinho ao ignorar o calendário de volta.
        if not apenas_ida:
            try:
                # Tenta pelo rádio tradicional primeiro
                page.check("input[name='trip_type'][value='roundtrip']", force=True, timeout=3000)
            except Exception:
                try:
                    # Se falhar (oculto no mobile/headless), clica no texto visual que ativa o modo
                    page.locator("label:has-text('Ida e volta'), label:has-text('Round trip')").first.click(force=True, timeout=3000)
                except Exception:
                    pass
            time.sleep(1.0)

        # ── 🛫 Preenchimento de Origem ────────────────────────────────────────
        for _ in range(4):
            try:
                # Clica no container principal do Select2 usando seletor de ID ou Classe genérica
                page.locator("#select2-origin-container, .select2-selection--single").first.click(force=True, timeout=4000)
                inp = page.locator(".select2-search--dropdown input.select2-search__field, input.select2-search__field").first
                inp.wait_for(state="attached", timeout=2500)
                inp.fill(origem.lower())
                time.sleep(0.5)
                page.locator("li.select2-results__option", has_text=origem.upper()).first.click(force=True, timeout=4000)
                time.sleep(1.5)
                break
            except Exception:
                time.sleep(1.0)

        # ── 🛬 Preenchimento de Destino ───────────────────────────────────────
        for _ in range(4):
            try:
                page.locator("#select2-destination-container").click(force=True, timeout=4000)
                inp = page.locator(".select2-search--dropdown input.select2-search__field, input.select2-search__field").first
                inp.wait_for(state="attached", timeout=2500)
                inp.fill(destino.lower())
                time.sleep(0.5)
                page.locator("li.select2-results__option", has_text=destino.upper()).first.click(force=True, timeout=4000)
                time.sleep(2.0)
                break
            except Exception:
                time.sleep(1.0)

        # ── 📅 Calendários ────────────────────────────────────────────────────
        dia_ida, mes_ano_ida = _data_iso_para_airhint(data_ida_iso)
        if not _navegar_calendario(page, "#departure", mes_ano_ida, dia_ida):
            log.warning("  AirHint: falha data ida")
            return None

        if not apenas_ida:
            dia_volta, mes_ano_volta = _data_iso_para_airhint(data_volta_iso)
            if not _navegar_calendario(page, "#return_date", mes_ano_volta, dia_volta):
                log.warning("  AirHint: falha data volta")
                return None

        # Desmarca extras e dispara busca
        page.click("body", position={"x": 5, "y": 5}, force=True, timeout=4000)
        time.sleep(1.0)
        try:
            if page.locator("#directOnly").is_checked(timeout=2000):
                page.uncheck("#directOnly", force=True, timeout=2000)
            if page.locator("#findAccomodation").is_checked(timeout=2000):
                page.uncheck("#findAccomodation", force=True, timeout=2000)
        except Exception:
            pass

        time.sleep(1.0)
        page.click("#find_btn", force=True, timeout=5000)

        # Aguarda predição
        page.wait_for_selector("#suggestion", state="visible", timeout=60000)
        time.sleep(4.0)

        dados = page.evaluate(r"""
            () => {
                const elSug = document.querySelector('#suggestion');
                const sugestao = elSug ? elSug.innerText.trim() : "";
                const elTooltip = document.querySelector('#prediction_tooltip');
                let motivo = "";
                if (elTooltip) {
                    motivo = elTooltip.getAttribute('data-original-title') ||
                             elTooltip.title || "";
                }
                let porcentagem = "";
                const svgTexts = Array.from(document.querySelectorAll('svg text tspan, svg text'));
                for (let el of svgTexts) {
                    const txt = (el.textContent || '').trim();
                    if (/^\d+%$/.test(txt)) { porcentagem = txt; break; }
                }
                return {sugestao, motivo, porcentagem};
            }
        """)

        sugestao    = dados.get("sugestao", "")
        motivo      = dados.get("motivo", "")
        porcentagem = dados.get("porcentagem", "")

        sug_lower = sugestao.lower()
        if "espere" in sug_lower or "aguarde" in sug_lower or "wait" in sug_lower:
            acao = "esperar"
        elif "reservar" in sug_lower or "comprar" in sug_lower or "book" in sug_lower:
            acao = "comprar"
        else:
            acao = "neutro"

        log.info(f"  AirHint sucesso: {sugestao} | {porcentagem} | acao={acao}")
        return {"sugestao": sugestao, "motivo": motivo, "probabilidade": porcentagem, "acao": acao}

    except Exception as e:
        log.warning(f"  AirHint indisponível ou estourou timeout de segurança: {e}")
        return None

# ── Funções públicas ──────────────────────────────────────────────────────────

# ── Funções públicas (Versão Otimizada para RAM no Railway) ───────────────────

def buscar_preco_e_historico(
    origem: str, destino: str, data_iso: str,
    data_volta_iso: Optional[str] = None
) -> Tuple[Optional[float], list, Optional[dict], Optional[dict]]:
    from playwright.sync_api import sync_playwright
    import time

    preco     = None
    hist      = []
    alt       = None
    airhint   = None

    try:
        with sync_playwright() as p:
            # Criamos APENAS UM processo do navegador para economizar memória RAM
            browser, context = _novo_browser_context(p)
            
            # ── Sessão 1: Kayak + Google Flights ──────────────────────────────
            page1 = context.new_page()
            try:
                preco, alt = _buscar_preco_kayak(page1, origem, destino, data_iso)
                hist = _buscar_historico_google(page1, origem, destino, data_iso)
            finally:
                page1.close() # Fecha a aba liberando a memória interna dela
                log.info("  Aba 1 fechada (Kayak+Google)")

            # Pequena pausa para o Garbage Collector coletar resíduos da aba anterior
            time.sleep(2)

            # ── Sessão 2: AirHint (Reutilizando o MESMO Browser) ──────────────
            try:
                page2 = context.new_page() # Abre uma nova aba isolada dentro do mesmo browser
                airhint = _buscar_previsao_airhint(page2, origem, destino, data_iso, data_volta_iso)
                page2.close()
                log.info("  Aba 2 fechada (AirHint)")
            except Exception as e2:
                log.warning(f"  AirHint sessão falhou: {e2}")
                airhint = None

            # Agora sim, encerramos o processo global do Chromium
            browser.close()
            log.info("  Processo global do Browser finalizado com sucesso.")

    except Exception as e:
        log.error(f"  Playwright erro geral no scraper: {e}")

    return preco, hist, alt, airhint


def buscar_preco_apenas(origem: str, destino: str, data_iso: str) -> Optional[float]:
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