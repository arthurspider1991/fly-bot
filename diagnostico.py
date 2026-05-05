"""
diagnostico.py — Roda separado para ver exatamente o que o Playwright captura.
Salva o HTML e lista todos os preços encontrados com seus seletores.

Uso: python diagnostico.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base64
import re
from playwright.sync_api import sync_playwright

ORIGEM  = "MAB"
DESTINO = "CGH"
DATA    = "2026-10-25"

def _gerar_tfs(origem, destino, data_iso):
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

url = f"https://www.google.com/travel/flights/search?tfs={_gerar_tfs(ORIGEM, DESTINO, DATA)}&hl=pt-BR&gl=BR&curr=BRL"
print(f"URL: {url}\n")

def _parse_brl(txt):
    try:
        limpo = (
            txt.replace("R$","").replace("\xa0","").replace("\u202f","")
               .replace(" ","").replace(".","").replace(",",".").strip()
        )
        v = float(limpo)
        return v if 150 < v < 25000 else None
    except:
        return None

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"]
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
    )
    page = context.new_page()
    page.goto(url, timeout=50000)

    print("Aguardando página carregar...")

    # Tenta esperar aba "Melhor opção"
    try:
        page.wait_for_selector("div[jsname='IWWDBc']", timeout=15000)
        print("✅ div[jsname='IWWDBc'] encontrado")
    except:
        print("❌ div[jsname='IWWDBc'] não encontrado")

    try:
        page.wait_for_selector("li[data-id]", timeout=10000)
        print("✅ li[data-id] encontrado")
    except:
        print("❌ li[data-id] não encontrado")

    try:
        page.wait_for_selector("ul.Rk10dc", timeout=5000)
        print("✅ ul.Rk10dc encontrado")
    except:
        print("❌ ul.Rk10dc não encontrado")

    page.wait_for_timeout(3000)

    # Aguarda preço estabilizar (sem clicar em nada)
    print("\nAguardando preço estabilizar...")
    preco_ant = None
    estavel = 0
    for i in range(30):
        page.wait_for_timeout(1000)
        # Lê spans de preço e texto da página separadamente
        spans_txt = page.evaluate(
            "() => Array.from(document.querySelectorAll('span.hXU5Ud, span.YMlIz'))"
            ".map(e => e.innerText.trim()).filter(t => t.includes('R$'))"
        )
        body_txt = page.evaluate("() => document.body.innerText")
        import re as _re
        m = _re.search(r"a partir de R\$[  ]?([\d.,]+)", body_txt, _re.IGNORECASE)
        atual = spans_txt[0] if spans_txt else (f"R$ {m.group(1)}" if m else None)
        print(f"  [{i+1}s] {atual}")
        if atual == preco_ant:
            estavel += 1
            if estavel >= 4:
                print(f"  ✅ Estável por 4s: {atual}")
                break
        else:
            estavel = 0
            preco_ant = atual

    # Salva HTML para análise
    html = page.content()
    with open("debug_flights.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML salvo: debug_flights.html ({len(html)//1024}KB)")

    # Testa camada 1: "a partir de R$ X"
    print("\n=== Camada 1: 'a partir de R$' ===")
    txt_pagina = page.evaluate("() => document.body.innerText")
    matches = re.findall(
        r"(?:a partir de|partir de|from)\s*R\$\s?([\d.,]+)",
        txt_pagina, re.IGNORECASE
    )
    for m in matches:
        v = _parse_brl("R$ " + m)
        print(f"  Encontrado: R$ {v:.0f}" if v else f"  Inválido: {m}")

    # Testa camada 2: ul.Rk10dc
    print("\n=== Camada 2: ul.Rk10dc spans ===")
    for el in page.query_selector_all("ul.Rk10dc span")[:20]:
        txt = el.inner_text().strip()
        if "R$" in txt and len(txt) < 20:
            print(f"  {txt}")

    # Testa camada 3: span.hXU5Ud
    print("\n=== Camada 3: span.hXU5Ud ===")
    for el in page.query_selector_all("span.hXU5Ud")[:10]:
        print(f"  {el.inner_text().strip()}")

    # Texto completo da página (primeiros 3000 chars com R$)
    print("\n=== Contexto 'a partir de' na página ===")
    idx = txt_pagina.find("a partir")
    if idx >= 0:
        print(repr(txt_pagina[max(0,idx-20):idx+60]))

    # Lista todos elementos com R$ curtos
    print("\n=== Todos spans curtos com R$ ===")
    resultados = page.evaluate("""
        () => {
            const result = [];
            const els = document.querySelectorAll('span');
            for (const el of els) {
                const txt = (el.innerText || '').trim();
                if (txt.includes('R$') && txt.length < 25 && !el.children.length) {
                    result.push({
                        texto:  txt,
                        classe: el.className.substring(0, 50),
                    });
                }
            }
            return result;
        }
    """)
    seen = set()
    for r in resultados:
        k = f"{r['texto']}|{r['classe']}"
        if k not in seen:
            seen.add(k)
            print(f"  {r['texto']:20} | {r['classe']}")

    browser.close()

print("\nDiagnóstico concluído! Abra debug_flights.html no navegador para inspecionar.")
