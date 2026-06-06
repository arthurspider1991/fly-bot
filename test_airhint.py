"""
test_airhint.py — Script Definitivo e Híbrido para o AirHint.
Suporta viagens de 'Ida e Volta' ou 'Apenas Ida' com navegação inteligente de datas.
"""
import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("AirHintBot")

def navegar_e_clicar_dia(page, selector_input, mes_ano_alvo: str, dia_alvo: str):
    """
    Abre o calendário do input correspondente, calcula se o mês alvo está no
    passado ou no futuro em relação ao mês atual na tela e navega na direção certa.
    """
    log.info(f"📅 Abrindo calendário para o campo: {selector_input}")
    
    # Fecha qualquer dropdown residual clicando no topo e abre o correto
    page.click("body", position={"x": 0, "y": 0})
    page.wait_for_timeout(500)
    page.click(selector_input)
    
    page.wait_for_selector(".datepicker-dropdown", state="visible", timeout=5000)
    
    # Mapeamento dos meses para cálculo de distância temporal
    meses_map = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
        "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
    }
    
    # Extrai o mês e ano alvo
    alvo_partes = mes_ano_alvo.lower().strip().split()
    mes_alvo_num = meses_map.get(alvo_partes[0], 1)
    ano_alvo_num = int(alvo_partes[1])
    
    # Loop de até 12 tentativas para achar o mês correto
    for i in range(12):
        switch_mes = page.locator(".datepicker-dropdown:visible .datepicker-switch").first
        texto_atual = switch_mes.inner_text().strip().lower()
        log.info(f"   [Calendário {selector_input}] Passo {i+1}: Atualmente em '{texto_atual}'")
        
        if mes_ano_alvo.lower() in texto_atual:
            log.info(f"   🎯 Mês correto encontrado! Clicando no dia: {dia_alvo}")
            # Garante o clique no dia do mês ativo (ignora os dias cinzas das pontas)
            dia_elemento = page.locator(".datepicker-dropdown:visible td.day:not(.old):not(.new)", has_text=str(int(dia_alvo))).first
            dia_elemento.click()
            page.wait_for_timeout(1000)
            return True
            
        # Parseia o mês e ano em que o calendário está posicionado na tela agora
        atual_partes = texto_atual.split()
        mes_atual_num = meses_map.get(atual_partes[0], 1)
        ano_atual_num = int(atual_partes[1])
        
        # Decide a direção comparando as datas (Ano e Mês)
        if (ano_alvo_num < ano_atual_num) or (ano_alvo_num == ano_atual_num and mes_alvo_num < mes_atual_num):
            log.info("   ← Clicando na seta ESQUERDA (retroceder)...")
            page.locator(".datepicker-dropdown:visible .prev").first.click()
        else:
            log.info("   → Clicando na seta DIREITA (avançar)...")
            page.locator(".datepicker-dropdown:visible .next").first.click()
            
        page.wait_for_timeout(800)
        
    return False

def testar_scrapper_airhint(origem: str, destino: str, dia_ida: str, dia_volta: str, mes_ano_alvo: str, apenas_ida: bool = False):
    url = "https://www.airhint.com/pt"
    modalidade_txt = "Apenas Ida" if apenas_ida else "Ida e Volta"
    log.info(f"🚀 Iniciando teste adaptativo [{modalidade_txt}]: {origem} ⇄ {destino}")
    
    with sync_playwright() as p:
        log.info("🌐 Abrindo o navegador Chromium (Visível)...")
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        try:
            log.info(f"🔗 Navegando para {url}...")
            try:
                page.goto(url, timeout=30000, wait_until="commit")
            except Exception as e_nav:
                log.warning(f"⚠️ Alerta de carregamento de scripts externos ignorado: {e_nav}")
            
            log.info("⏳ Aguardando renderização do formulário principal...")
            page.wait_for_selector("#select2-origin-container", state="visible", timeout=30000)
            page.wait_for_timeout(2000)

            # ── 🍪 Cookies ────────────────────────────────────────────────────────
            seletores_lista = [
                "button.css-1jqk1n3", "button:has-text('CONCORDO')", 
                "button:has-text('Aceitar')", "button:has-text('AGREE')", "button:has-text('Accept')"
            ]
            botao_cookie = page.locator(", ".join(seletores_lista))
            try:
                botao_cookie.first.wait_for(state="visible", timeout=2000)
                log.info("🍪 Banner de cookies detectado. Aceitando termos...")
                botao_cookie.first.click()
                page.wait_for_timeout(1000)
            except Exception:
                log.info("🍪 Banner de cookies não apareceu ou já estava aceito. Prosseguindo...")

            # ── 🔄 Alterar modalidade dinamicamente ────────────────────────────
            if apenas_ida:
                log.info(f"🔄 Selecionando modalidade: oneway (Apenas Ida)...")
                page.check("input[name='trip_type'][value='oneway']")
            else:
                log.info(f"🔄 Selecionando modalidade: roundtrip (Ida e Volta)...")
                page.check("input[name='trip_type'][value='roundtrip']")
            page.wait_for_timeout(1500)

            # ── 🛫 Preenchimento de Origem ────────────────────────────────────────
            log.info("🛫 Selecionando Origem...")
            input_busca = page.locator(".select2-search--dropdown input.select2-search__field")
            for tentativa in range(4):
                try:
                    page.click("#select2-origin-container")
                    input_busca.wait_for(state="visible", timeout=3000)
                    break
                except Exception:
                    page.wait_for_timeout(1000)
            
            input_busca.fill(origem)
            page.locator("li.select2-results__option", has_text=origem).first.click()
            page.wait_for_timeout(1500)

            # ── 🛬 Preenchimento de Destino ───────────────────────────────────────
            log.info("🛬 Selecionando Destino...")
            input_busca_dest = page.locator(".select2-search--dropdown input.select2-search__field")
            for tentativa in range(4):
                try:
                    page.click("#select2-destination-container")
                    input_busca_dest.wait_for(state="visible", timeout=3000)
                    break
                except Exception:
                    page.wait_for_timeout(1000)
            
            input_busca_dest.fill(destino)
            page.locator("li.select2-results__option", has_text=destino).first.click()
            page.wait_for_timeout(2000)

            # ── 📅 Navegação da Ida (Sempre acontece) ─────────────────────────────
            if not navegar_e_clicar_dia(page, "#departure", mes_ano_alvo, dia_ida):
                raise Exception(f"Falha ao selecionar o dia de ida no mês {mes_ano_alvo}")

            # ── 📅 Navegação da Volta (Condicional) ───────────────────────────────
            if not apenas_ida:
                if not navegar_e_clicar_dia(page, "#return_date", mes_ano_alvo, dia_volta):
                    raise Exception(f"Falha ao selecionar o dia de volta no mês {mes_ano_alvo}")
            else:
                log.info("⏭️ Ignorando seleção de volta (Modo Apenas Ida ativo).")

            # Fecha focos residuais
            page.click("body", position={"x": 5, "y": 5})
            page.wait_for_timeout(1000)

            # ── ⚙️ Desmarcar Caixas Extras ────────────────────────────────────────
            log.info("⚙️ Desmarcando opções extras...")
            if page.locator("#directOnly").is_checked(): 
                page.uncheck("#directOnly")
            if page.locator("#findAccomodation").is_checked(): 
                page.uncheck("#findAccomodation")
            
            page.wait_for_timeout(1000)
            
            # ── 🔍 Disparar Busca ─────────────────────────────────────────────────
            log.info("🔍 Clicando no botão 'Procurar voo'...")
            page.click("#find_btn")

            # ── ⏳ Espera pela Resposta da IA ──────────────────────────────────────
            log.info("⏳ Aguardando a IA carregar e processar a predição na tela...")
            page.wait_for_selector("#suggestion", state="visible", timeout=60000)
            page.wait_for_timeout(5000)

            # ── 🧬 Extração Cirúrgica do Gráfico SVG e Textos ─────────────────────
            dados_finais = page.evaluate(r"""
                () => {
                    const elSuggestion = document.querySelector('#suggestion');
                    const sugestao_texto = elSuggestion ? elSuggestion.innerText.trim() : "Não encontrado";

                    const elPredictionTooltip = document.querySelector('#prediction_tooltip');
                    let porque_texto = "Não encontrado";
                    if (elPredictionTooltip) {
                        porque_texto = elPredictionTooltip.getAttribute('data-original-title') || 
                                       elPredictionTooltip.title || "Não disponível";
                    }

                    let porcentagem_detectada = "N/A";
                    // Alvo Direto no SVG usando textContent (Bypass do innerText)
                    const elementos_svg_text = Array.from(document.querySelectorAll('svg text tspan, svg text'));
                    
                    for (let el of elementos_svg_text) {
                        if (el && el.textContent) {
                            const texto = el.textContent.trim();
                            if (/^\d+%$/.test(texto)) {
                                porcentagem_detectada = texto;
                                break;
                            }
                        }
                    }

                    return {
                        sugestao: sugestao_texto,
                        porque: porque_texto,
                        porcentagens: porcentagem_detectada
                    };
                }
            """)

            log.info("==================================================")
            log.info("🎉 [DADOS EXTRAÍDOS COM SUCESSO]")
            log.info(f"   👉 Modalidade: {modalidade_txt}")
            log.info(f"   👉 Sugestão: {dados_finais['sugestao']}")
            log.info(f"   👉 Motivo: {dados_finais['porque']}")
            log.info(f"   👉 Probabilidade: {dados_finais['porcentagens']}")
            log.info("==================================================")

        except Exception as e:
            log.error(f"💥 Erro Crítico: {e}", exc_info=True)
        finally:
            browser.close()

if __name__ == "__main__":
    
    # EXEMPLO 1: Executando busca de Ida e Volta (MAB -> CGH)
    testar_scrapper_airhint(
        origem="bsb", 
        destino="cgh", 
        dia_ida="02",
        dia_volta="10",
        mes_ano_alvo="outubro 2026",
        apenas_ida=False
    )
    
    print("\n" + "="*60 + "\n")
    
    # EXEMPLO 2: Executando busca de APENAS IDA (GRU -> REC)
    testar_scrapper_airhint(
        origem="bsb", 
        destino="cgh", 
        dia_ida="02",
        dia_volta="", # Pode ir vazio no modo apenas_ida
        mes_ano_alvo="junho 2026",
        apenas_ida=True
    )