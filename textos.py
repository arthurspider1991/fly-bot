"""
textos.py — Todas as mensagens enviadas pelo bot aos usuários.

Edite aqui para mudar qualquer texto sem mexer na lógica do bot.py.

Variáveis disponíveis nas f-strings (são preenchidas automaticamente pelo bot):
  {nome}       — primeiro nome do usuário no Telegram
  {PIX_KEY}    — chave Pix configurada no .env
  {PIX_VALOR}  — valor da assinatura configurado no .env
  {chat_id}    — ID do usuário
  {expira}     — data de expiração da assinatura (DD/MM/AAAA)
  {dias}       — dias restantes da assinatura
  {origem}     — código IATA de origem
  {destino}    — código IATA de destino
  {nome_ae}    — nome do aeroporto
  {data_ida}   — data de ida formatada (DD/MM/AAAA)
  {data_volta} — data de volta formatada (DD/MM/AAAA)
  {now_str}    — data/hora atual
"""

# ══════════════════════════════════════════════════════════════════════════════
# SUPORTE
# ══════════════════════════════════════════════════════════════════════════════

CONTATO_SUPORTE = "@suporteflybot"  # ← altere aqui quando mudar o @

SUPORTE_LINHA = "❓ Dúvidas ou problemas? Fale comigo: @suporteflybot"

# ══════════════════════════════════════════════════════════════════════════════
# BOAS-VINDAS E PAGAMENTO
# ══════════════════════════════════════════════════════════════════════════════

BOAS_VINDAS = (
    "👋 Olá, *{nome}*!\n\n"
    "🤖 Monitoro preços de passagens aéreas e aviso quando cair ou subir 3% ou mais.\n\n"
    "━━━━━━━━━━━━━━━\n"
    "💳 *Como funciona:*\n"
    "1️⃣ Faça o Pix para a chave abaixo\n"
    "2️⃣ Clique em *Paguei*\n"
    "3️⃣ Aguarde a liberação\n"
    "4️⃣ Configure sua rota\n"
    "━━━━━━━━━━━━━━━\n\n"
    "🔑 *Chave Pix:*\n`{PIX_KEY}`\n\n"
    "💰 *Valor:* {PIX_VALOR}"
)

PAGAMENTO_PENDENTE = (
    "⏳ Aguardando confirmação do pagamento.\n\n"
    "Chave Pix: `{PIX_KEY}` — {PIX_VALOR}\n\n"
    "Clique em *Paguei* abaixo após realizar o pagamento:"
)

PAGUEI_CONFIRMADO = (
    "✅ Recebi! Seu pagamento está sendo verificado.\n\n"
    "Aguarde a liberação em instantes.\n\n"
    "❓ Algum problema? Digite /suporte"
)

JA_TEM_ACESSO = "✅ Você já tem acesso ativo{info}!"

ACESSO_SUSPENSO = "🚫 Acesso suspenso. Entre em contato com o administrador."

# ══════════════════════════════════════════════════════════════════════════════
# SETUP — SELEÇÃO DE AEROPORTO
# ══════════════════════════════════════════════════════════════════════════════

SETUP_LIBERADO = (
    "✅ *Acesso liberado! Vamos configurar.*\n\n"
    "✈️ *Passo 1/4 — Aeroporto de ORIGEM*\n\n"
    "Selecione o país:"
)

SETUP_ORIGEM = "✈️ *Passo 1/4 — Aeroporto de ORIGEM*\n\nSelecione o país:"
SETUP_DESTINO = "✈️ *Passo 2/4 — Aeroporto de DESTINO*\n\nSelecione o país:"

SETUP_SELECIONE_ESTADO = (
    "✈️ *Passo {passo} — {titulo}*\n\n"
    "Selecione o estado:"
)

SETUP_SELECIONE_AEROPORTO_ESTADO = (
    "✈️ *Passo {passo} — {titulo}*\n\n"
    "Estado: *{estado}*\n"
    "Selecione o aeroporto:"
)

SETUP_SELECIONE_AEROPORTO_PAIS = (
    "✈️ *Passo {passo} — {titulo}*\n\n"
    "Selecione o aeroporto:"
)

DESTINO_IGUAL_ORIGEM = (
    "❌ Destino igual à origem. Escolha outro aeroporto."
)

ORIGEM_CONFIRMADA = "✅ *Origem:* {iata} — {nome_ae}"
DESTINO_CONFIRMADO = "✅ *Destino:* {iata} — {nome_ae}"

# ══════════════════════════════════════════════════════════════════════════════
# SETUP — DATAS
# ══════════════════════════════════════════════════════════════════════════════

SETUP_DATA_IDA = (
    "📅 *Passo 3/4 — Data de IDA*\n\n"
    "Escolha o mês:"
)

SETUP_DATA_VOLTA = (
    "✅ *Ida:* {data_ida}\n\n"
    "📅 *Passo 4/4 — Data de VOLTA*\n\n"
    "Escolha o mês:"
)

SETUP_DATA_MANUAL_IDA = (
    "📝 Digite a data de ida no formato `DD-MM-AAAA`:\n"
    "Ex: `26-10-2026`"
)

SETUP_DATA_MANUAL_VOLTA = (
    "📝 Digite a data de volta no formato `DD-MM-AAAA`:\n"
    "Ex: `31-10-2026`\n"
    "Ou `0` para só ida."
)

ERRO_DATA_INVALIDA = (
    "❌ Formato inválido. Use `DD-MM-AAAA`. Ex: `26-10-2026`"
)

ERRO_DATA_PASSADO = "❌ A data precisa ser futura."

ERRO_VOLTA_ANTES_IDA = "❌ A volta precisa ser depois da ida."

ESCOLHA_DIA = "📅 Escolha o dia:"

# ══════════════════════════════════════════════════════════════════════════════
# MONITORAMENTO ATIVADO
# ══════════════════════════════════════════════════════════════════════════════

MONITORAMENTO_ATIVADO = (
    "🚀 *Monitoramento ativado!*\n\n"
    "• Rota: *{origem} → {destino}*\n"
    "• Ida: {data_ida}\n"
    "• Volta: {data_volta}\n\n"
    "🔍 Buscando preços agora, aguarde...\n\n"
    "_Você receberá atualizações a cada 2h e alertas quando o preço variar 3% ou mais._"
)

MONITORAMENTO_PAUSADO = (
    "⏹️ Monitoramento pausado. Fale com o administrador para reativar."
)

# ══════════════════════════════════════════════════════════════════════════════
# ALERTAS DE PREÇO
# ══════════════════════════════════════════════════════════════════════════════

ALERTA_QUEDA_IDA = (
    "📉 *QUEDA — IDA!*\n"
    "{origem} → {destino} | {data_ida}\n"
    "R$ {preco_ant:.2f} → *R$ {preco_novo:.2f}* (-{pct:.1f}%)"
)

ALERTA_ALTA_IDA = (
    "📈 *ALTA — IDA*\n"
    "{origem} → {destino} | {data_ida}\n"
    "R$ {preco_ant:.2f} → R$ {preco_novo:.2f} (+{pct:.1f}%)"
)

ALERTA_QUEDA_VOLTA = (
    "📉 *QUEDA — VOLTA!*\n"
    "{destino} → {origem} | {data_volta}\n"
    "R$ {preco_ant:.2f} → *R$ {preco_novo:.2f}* (-{pct:.1f}%)"
)

ALERTA_ALTA_VOLTA = (
    "📈 *ALTA — VOLTA*\n"
    "{destino} → {origem} | {data_volta}\n"
    "R$ {preco_ant:.2f} → R$ {preco_novo:.2f} (+{pct:.1f}%)"
)

RESUMO_PRECOS = (
    "✈️ *Preços — {now_str}*\n\n"
    "{linhas_precos}"
    "\n_Próxima atualização em 2h_"
)

LINHA_PRECO_IDA   = "• Ida {origem}→{destino} ({data}): *R$ {preco:.2f}*"
LINHA_PRECO_VOLTA = "• Volta {destino}→{origem} ({data}): *R$ {preco:.2f}*"
LINHA_PRECO_TOTAL = "\n💰 *Total: R$ {total:.2f}*"
LINHA_SEM_DADOS   = "• {trecho} ({data}): ⚠️ sem dados no momento"
LINHA_ULTIMO_PRECO = "• {trecho} ({data}): R$ {preco:.2f} _(último conhecido)_"

# ══════════════════════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════════════════════

STATUS_AGUARDANDO = "⏳ Status: *{status}*\nAguarde a liberação do acesso."

STATUS_ATIVO = (
    "📋 *Seu monitoramento:*\n\n"
    "• Origem: `{origem}`\n"
    "• Destino: `{destino}`\n"
    "• Ida: {data_ida}\n"
    "• Volta: {data_volta}\n"
    "{assinatura}"
    "{ultima_busca}"
    "{precos}"
    "\n/reconfigurar — mudar rota\n/parar — pausar"
)

ASSINATURA_OK      = "\n✅ Assinatura: {dias} dias restantes"
ASSINATURA_ALERTA  = "\n🟡 Assinatura: vence em {dias} dia{sufixo}!"
ASSINATURA_EXPIRADA = "\n🔴 Assinatura: *expirada*"

COMANDOS_USUARIO = (
    "ℹ️ *Comandos disponíveis:*\n\n"
    "/status — ver monitoramento atual\n"
    "/reconfigurar — mudar rota ou datas\n"
    "/parar — pausar alertas"
)

# ══════════════════════════════════════════════════════════════════════════════
# ASSINATURA — VENCIMENTO E RENOVAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

ASSINATURA_EXPIROU_USUARIO = (
    "⏰ *Sua assinatura expirou!*\n\n"
    "O monitoramento foi pausado.\n"
    "Renove agora para continuar recebendo alertas:\n\n"
    "🔑 Chave Pix: `{PIX_KEY}`\n"
    "💰 Valor: {PIX_VALOR}\n\n"
    "❓ Problemas? Digite /suporte"
)

AVISO_VENCIMENTO_USUARIO = (
    "{emoji} *Sua assinatura vence em {dias} dia{sufixo}!*\n\n"
    "Para continuar monitorando sem interrupção, renove agora:\n\n"
    "🔑 Chave Pix: `{PIX_KEY}`\n"
    "💰 Valor: {PIX_VALOR}\n\n"
    "_Após o pagamento, clique em Paguei abaixo:_"
)

RECONFIGURAR_INICIO = (
    "✈️ *Reconfiguração — Passo 1/4 — ORIGEM*\n\nSelecione o país:"
)

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — NOTIFICAÇÕES
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_BOT_INICIADO = (
    "🤖 *Bot de Passagens — SaaS iniciado!*\n\n"
    "`/liberar <id>` — ativa/renova (30 dias)\n"
    "`/bloquear <id>` — suspende acesso\n"
    "`/usuarios` — lista todos\n"
    "`/vencendo` — assinaturas vencendo\n"
    "`/forcarbusca` — busca imediata\n\n"
    "_Avisos de vencimento: 7d, 3d, 1d antes_\n"
    "_Bloqueio automático ao expirar_"
)

ADMIN_NOVO_USUARIO = (
    "🔔 *Novo usuário!*\n"
    "Nome: {nome}\n"
    "ID: `{chat_id}`"
)

ADMIN_PAGUEI_NOVO = (
    "💸 *NOVO PAGAMENTO* — *{nome}* clicou em PAGUEI!\n"
    "ID: `{chat_id}`\n\n"
    "➡️ Confirme e use:\n"
    "`/liberar {chat_id}`"
)

ADMIN_PAGUEI_RENOVACAO = (
    "🔄 *RENOVAÇÃO* — *{nome}* clicou em PAGUEI!\n"
    "ID: `{chat_id}`\n\n"
    "➡️ Confirme e use:\n"
    "`/liberar {chat_id}`"
)

ADMIN_LIBERADO = "✅ Usuário `{chat_id}` liberado! Assinatura até {expira}."

ADMIN_BLOQUEADO = "🚫 `{chat_id}` bloqueado."

ADMIN_NAO_ENCONTRADO = "❌ Usuário `{chat_id}` não encontrado."

ADMIN_USUARIO_ATIVO = (
    "🆕 *Usuário ativo:* {nome}\n"
    "ID: `{chat_id}`\n"
    "Rota: {origem}→{destino}\n"
    "Datas: {data_ida} / {data_volta}"
)

ADMIN_ASSINATURA_EXPIRADA = (
    "🔴 *Assinatura expirada — bloqueio automático*\n"
    "Nome: {nome}\n"
    "ID: `{chat_id}`\n"
    "Data: {now_str}"
)

ADMIN_AVISO_VENCIMENTO = (
    "{emoji} *Assinatura vencendo em {dias} dia{sufixo}*\n"
    "Nome: {nome}\n"
    "ID: `{chat_id}`"
)

ADMIN_NENHUM_USUARIO = "Nenhum usuário ainda."

ADMIN_NENHUM_VENCENDO = "✅ Nenhuma assinatura vencendo nos próximos 7 dias."

ADMIN_BUSCA_INICIADA = "🔄 Iniciando busca manual..."

ADMIN_MENU = (
    "🛠️ *Admin — Comandos:*\n\n"
    "`/liberar <id>` — ativa/renova usuário\n"
    "`/bloquear <id>` — suspende acesso\n"
    "`/usuarios` — lista todos (com dias restantes)\n"
    "`/vencendo` — assinaturas vencendo em 7 dias\n"
    "`/forcarbusca` — busca imediata\n"
    "`/broadcast <msg>` — envia para todos\n"
    "`/msg <id> <msg>` — mensagem para um usuário\n"
    "\n"
    "Seu ID: `{chat_id}`"
)

ADMIN_USO_LIBERAR  = "❌ Use: `/liberar <chat_id>`"
ADMIN_USO_BLOQUEAR = "❌ Use: `/bloquear <chat_id>`"
