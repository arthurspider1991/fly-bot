"""
diagnostico_airhint.py — Testa extração de dados do AirHint.
Simula preenchimento do formulário e extrai preço, recomendação e probabilidade.

Uso: python diagnostico_airhint.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
from playwright.sync_api import sync_playwright

ORIGEM  = "Marabá (MAB)"
DESTINO = "São Paulo Congonhas (CGH)"
DATA    = "2026-10-25"

print(f"Testando AirHint: {ORIGEM} → {DESTINO} | {DATA}\n")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,  # visível para acompanhar
        args=["--no-sandbox", "--disable-setuid-sandbox"]
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="pt-BR",
    )
    page = context.new_page()

    print("1. Abrindo AirHint...")
    page.goto("https://www.airhint.com/pt", timeout=30000)
    page.wait_for_timeout(3000)

    # ── Tenta preencher origem ────────────────────────────────────────────────
    # ── Aceita cookies ───────────────────────────────────────────────────────
    print("1b. Aceitando cookies...")
    page.wait_for_timeout(3000)
    for sel in [
        "button:has-text('CONCORDO')",
        "button:has-text('Concordo')",
        "button:has-text('Aceitar')",
        "button:has-text('Accept')",
        "button:has-text('OK')",
        "[id*='cookie'] button",
        "[class*='cookie'] button",
        "[id*='consent'] button",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                print(f"  ✅ Cookies aceitos via: {sel}")
                page.wait_for_timeout(2000)
                break
        except:
            pass

    # Aguarda qualquer overlay/modal fechar
    page.wait_for_timeout(2000)

    # Tira print da tela para ver o estado atual
    page.screenshot(path="debug_airhint_inicio.png")
    print("  Screenshot salvo: debug_airhint_inicio.png")

    print("2. Preenchendo origem...")
    origem_preenchido = False
    for sel in [
        "input[placeholder*='rigens']",
        "input[placeholder*='artida']",
        "input[placeholder*='origen']",
        "input[name*='origin']",
        "input[name*='from']",
        "input[id*='origin']",
        "input[id*='from']",
        "input:first-of-type",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                el.fill("")
                el.type("MAB", delay=100)
                page.wait_for_timeout(2000)
                # Tenta clicar na sugestão
                for sugestao_sel in [
                    f"[data-value*='MAB']",
                    f"li:has-text('MAB')",
                    f"div:has-text('Marabá')",
                    f"option:has-text('MAB')",
                    ".autocomplete-item:first-child",
                    "ul li:first-child",
                    "[role='option']:first-child",
                ]:
                    try:
                        s = page.query_selector(sugestao_sel)
                        if s and s.is_visible():
                            s.click()
                            print(f"  ✅ Origem preenchida via: {sel} → {sugestao_sel}")
                            origem_preenchido = True
                            page.wait_for_timeout(1000)
                            break
                    except:
                        pass
                if not origem_preenchido:
                    # Tenta Enter
                    try:
                        page.keyboard.press("ArrowDown")
                        page.wait_for_timeout(500)
                        page.keyboard.press("Enter")
                        print(f"  ✅ Origem via Enter: {sel}")
                        origem_preenchido = True
                    except:
                        pass
                if origem_preenchido:
                    break
        except Exception as e:
            pass

    if not origem_preenchido:
        print("  ❌ Não conseguiu preencher origem")

    page.wait_for_timeout(1000)

    # ── Tenta preencher destino ───────────────────────────────────────────────
    print("3. Preenchendo destino...")
    destino_preenchido = False
    for sel in [
        "input[placeholder*='estino']",
        "input[placeholder*='chegada']",
        "input[name*='destination']",
        "input[name*='to']",
        "input[id*='destination']",
        "input[id*='to']",
        "input:nth-of-type(2)",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                el.fill("")
                el.type("CGH", delay=100)
                page.wait_for_timeout(2000)
                for sugestao_sel in [
                    f"[data-value*='CGH']",
                    f"li:has-text('CGH')",
                    f"div:has-text('Congonhas')",
                    ".autocomplete-item:first-child",
                    "ul li:first-child",
                    "[role='option']:first-child",
                ]:
                    try:
                        s = page.query_selector(sugestao_sel)
                        if s and s.is_visible():
                            s.click()
                            print(f"  ✅ Destino preenchido via: {sel} → {sugestao_sel}")
                            destino_preenchido = True
                            page.wait_for_timeout(1000)
                            break
                    except:
                        pass
                if not destino_preenchido:
                    try:
                        page.keyboard.press("ArrowDown")
                        page.wait_for_timeout(500)
                        page.keyboard.press("Enter")
                        print(f"  ✅ Destino via Enter: {sel}")
                        destino_preenchido = True
                    except:
                        pass
                if destino_preenchido:
                    break
        except:
            pass

    if not destino_preenchido:
        print("  ❌ Não conseguiu preencher destino")

    page.wait_for_timeout(1000)

    # ── Tenta preencher data ──────────────────────────────────────────────────
    print("4. Preenchendo data...")
    data_preenchida = False
    for sel in [
        "input[type='date']",
        "input[placeholder*='ata']",
        "input[name*='date']",
        "input[id*='date']",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(DATA)
                print(f"  ✅ Data preenchida via: {sel}")
                data_preenchida = True
                break
        except:
            pass

    if not data_preenchida:
        print("  ❌ Não conseguiu preencher data")

    page.wait_for_timeout(1000)

    # ── Salva HTML antes de buscar ────────────────────────────────────────────
    try:
        html_antes = page.content()
        with open("debug_airhint_antes.html", "w", encoding="utf-8") as f:
            f.write(html_antes)
        print("  HTML salvo: debug_airhint_antes.html")
    except Exception as e:
        print(f"  Erro ao salvar HTML: {e}")

    # Lista todos os inputs visíveis
    print("\n5. Inputs visíveis na página:")
    inputs = page.evaluate("""
        () => Array.from(document.querySelectorAll('input, select')).map(el => ({
            tag:         el.tagName,
            type:        el.type || '',
            name:        el.name || '',
            id:          el.id || '',
            placeholder: el.placeholder || '',
            value:       el.value || '',
            visible:     el.offsetParent !== null,
        }))
    """)
    for inp in inputs:
        if inp['visible']:
            print(f"  {inp['tag']:6} type={inp['type']:8} name={inp['name']:20} id={inp['id']:20} placeholder={inp['placeholder']:30} value={inp['value']}")

    # ── Tenta clicar em Procurar/Buscar ──────────────────────────────────────
    print("\n6. Clicando em Procurar...")
    buscou = False
    for sel in [
        "button:has-text('Procurar')",
        "button:has-text('Buscar')",
        "button:has-text('Search')",
        "button[type='submit']",
        "input[type='submit']",
        "button.search",
        ".btn-search",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                print(f"  ✅ Clicou em: {sel}")
                buscou = True
                break
        except:
            pass

    if not buscou:
        print("  ❌ Não encontrou botão de busca")

    # ── Aguarda resultado ─────────────────────────────────────────────────────
    print("\n7. Aguardando resultado (30s)...")
    for i in range(30):
        page.wait_for_timeout(1000)
        body = page.evaluate("() => document.body.innerText")
        tem_preco  = "R$" in body
        tem_prob   = "%" in body and ("probabilidade" in body.lower() or "descida" in body.lower() or "subida" in body.lower())
        tem_rec    = any(x in body.lower() for x in ["espere", "compre", "agora", "comprar"])
        print(f"  [{i+1}s] preço={'✅' if tem_preco else '❌'} prob={'✅' if tem_prob else '❌'} rec={'✅' if tem_rec else '❌'}")
        if tem_preco and (tem_prob or tem_rec):
            print("  ✅ Resultado carregado!")
            break

    # ── Extrai informações ────────────────────────────────────────────────────
    print("\n8. Extraindo dados...")
    body = page.evaluate("() => document.body.innerText")

    # Preço
    precos = re.findall(r"R\$\s*[\d.,]+", body)
    print(f"  Preços encontrados: {precos[:5]}")

    # Recomendação
    for rec in ["Espere", "Compre agora", "Comprar agora", "Reserve agora"]:
        if rec.lower() in body.lower():
            print(f"  Recomendação: {rec}")
            break

    # Probabilidade
    prob = re.findall(r"(\d+)%", body)
    if prob:
        print(f"  Probabilidades: {prob[:5]}")

    # Melhor oferta
    melhor = re.findall(r"(?:melhor|oferta|históric)[^\n]*?(\d+)\s*BRL", body, re.IGNORECASE)
    if melhor:
        print(f"  Melhor oferta: {melhor}")

    # Salva HTML final
    html_depois = page.content()
    with open("debug_airhint_depois.html", "w", encoding="utf-8") as f:
        f.write(html_depois)
    print(f"\n  HTML salvo: debug_airhint_depois.html ({len(html_depois)//1024}KB)")
    print(f"  Body (primeiros 1000 chars):\n{body[:1000]}")

    # Lista todos elementos com R$ ou %
    print("\n9. Elementos com dados relevantes:")
    elementos = page.evaluate("""
        () => {
            const result = [];
            for (const el of document.querySelectorAll('*')) {
                if (el.children.length > 0) continue;
                const t = (el.innerText || '').trim();
                if ((t.includes('R$') || t.includes('%') || 
                     t.toLowerCase().includes('espere') ||
                     t.toLowerCase().includes('compre') ||
                     t.toLowerCase().includes('probabilidade')) && t.length < 100) {
                    result.push({
                        tag:    el.tagName,
                        texto:  t,
                        classe: el.className.substring(0, 60),
                        id:     el.id || '',
                    });
                }
            }
            return result;
        }
    """)
    for el in elementos[:20]:
        print(f"  {el['tag']:6} | {el['texto']:40} | classe: {el['classe'][:40]}")

    input("\nPressione ENTER para fechar o navegador...")
    browser.close()

print("\nDiagnóstico concluído!")
