"""
diagnostico_kayak.py — Testa extração de preços do Kayak.
Uso: python diagnostico_kayak.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re
from playwright.sync_api import sync_playwright

URL_IDA   = "https://www.kayak.com.br/flights/MAB-CGH/2026-10-25?sort=price_a"
URL_VOLTA = "https://www.kayak.com.br/flights/CGH-MAB/2026-10-31?sort=price_a"

def _parse_brl(txt):
    try:
        limpo = txt.replace("R$","").replace(".","").replace(",",".").replace("\xa0","").replace(" ","").strip()
        v = float(limpo)
        return v if 100 < v < 30000 else None
    except:
        return None

def testar_url(page, url, label):
    print(f"\n{'='*50}")
    print(f"Testando: {label}")
    print(f"URL: {url}")
    print('='*50)

    page.goto(url, timeout=50000)

    # Aceita cookies
    for sel in ["button:has-text('Aceitar')", "button:has-text('Accept all')",
                "button:has-text('Aceito')", "#onetrust-accept-btn-handler"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                print(f"✅ Cookies aceitos: {sel}")
                page.wait_for_timeout(1000)
                break
        except:
            pass

    # Aguarda preços estabilizarem
    print("\nAguardando preços...")
    preco_ant = None
    estavel   = 0
    for t in range(40):
        page.wait_for_timeout(1000)

        # Pega preços de div.e2GB-price-text (preços reais dos voos)
        # Ignora: rVsP-price-display (aeroporto alternativo)
        #         NEl9-price (calendário de datas)
        #         hYzH-price (filtros laterais)
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

        menor = min(precos) if precos else None
        print(f"  [{t+1}s] menor={menor} | visíveis={sorted(set(precos))[:5] if precos else []}")

        if menor:
            if menor == preco_ant:
                estavel += 1
                if estavel >= 4:
                    print(f"  ✅ Estável: R$ {menor:.0f}")
                    break
            else:
                estavel   = 0
                preco_ant = menor

    # Screenshot
    page.screenshot(path=f"debug_kayak_{label}.png")
    print(f"Screenshot salvo: debug_kayak_{label}.png")

    # Lista TODOS os elementos com R$ (visíveis e invisíveis) com detalhes
    print(f"\n=== Todos elementos com R$ ({label}) ===")
    todos = page.evaluate("""
        () => {
            const result = [];
            const els = document.querySelectorAll('*');
            for (const el of els) {
                if (el.children.length > 0) continue;
                const txt = (el.innerText || '').trim();
                if (!txt.includes('R$') || txt.length > 20) continue;
                const rect = el.getBoundingClientRect();
                const visivel = rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top <= window.innerHeight;
                result.push({
                    texto:   txt,
                    tag:     el.tagName,
                    classe:  (el.className || '').substring(0, 50),
                    visivel: visivel,
                    top:     Math.round(rect.top),
                });
            }
            return result;
        }
    """)
    seen = set()
    for el in todos:
        k = f"{el['texto']}|{el['classe']}"
        if k in seen: continue
        seen.add(k)
        vis = "✅ visível" if el['visivel'] else "❌ oculto "
        print(f"  {vis} | {el['texto']:15} | {el['tag']:6} | top={el['top']:4} | {el['classe']}")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"]
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="pt-BR",
        viewport={"width": 1440, "height": 900},
    )
    page = ctx.new_page()

    testar_url(page, URL_IDA, "ida")
    input("\nENTER para fechar...")
    browser.close()

print("Concluído!")
