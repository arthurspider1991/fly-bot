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

    # ── 🔍 OPÇÃO 2: AGUARDAR A BARRA LARANJA SUMIR ──────────────────────────
    log.info("  Aguardando o Kayak finalizar a busca (barra laranja)...")
    try:
        # Combinamos vários seletores comuns que o Kayak usa para indicar progresso:
        # - div[role="progressbar"] é o padrão de acessibilidade para barras de progresso
        # - [class*="progress"] pega qualquer classe que tenha "progress" no nome
        seletor_loading = 'div[role="progressbar"], .skp2, .skp2-bar'
        
        # Primeiro, damos até 4 segundos para a barra aparecer na tela (caso demore a iniciar)
        try:
            page.wait_for_selector(seletor_loading, state="visible", timeout=4000)
            log.info("  Barra de progresso detectada. Aguardando conclusão...")
        except Exception:
            log.info("  A barra de progresso não apareceu a tempo ou já sumiu.")

        # Agora, travamos o código ATÉ que a barra fique oculta/sumir (state="hidden")
        # Damos um limite (timeout) de até 35 segundos para o Kayak terminar tudo
        page.wait_for_selector(seletor_loading, state="hidden", timeout=35000)
        log.info("  Carregamento do Kayak 100% concluído!")
        
        # Uma pequena pausa de 2 segundos para o JavaScript renderizar os menores preços na tela
        page.wait_for_timeout(2000)
        
    except Exception as e:
        log.warning(f"  Aviso no carregamento: {e}. Coletando dados atuais da tela.")
    # ──────────────────────────────────────────────────────────────────────────

    # 2. Agora fazemos a coleta definitiva dos preços (sem loops desnecessários)
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

    # 3. Captura o aeroporto alternativo (card rVsP)
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