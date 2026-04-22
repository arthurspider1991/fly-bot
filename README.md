# ✈️ Fly Bot v5 — Bot de Monitoramento de Passagens

Bot de passagens aéreas para Telegram com:
- Monitoramento de preços a cada 2h
- Análise de histórico dos últimos 60 dias
- Alertas de alta/queda ≥ 3%
- Sistema SaaS com pagamento via Pix
- Comprovante enviado direto para o admin
- Suporte a Brasil + América do Sul

---

## 📁 Estrutura

```
fly-bot-v5/
├── main.py                  ← ponto de entrada
├── config.py                ← variáveis de ambiente
├── textos.py                ← todas as mensagens editáveis
├── requirements.txt
├── Dockerfile
├── railway.toml
├── .env.example
│
├── db/
│   ├── database.py          ← conexão SQLite + WAL + init
│   ├── usuarios.py          ← CRUD de usuários
│   └── cache.py             ← cache de rotas (SQLite)
│
├── services/
│   ├── scraper.py           ← Playwright + Google Flights
│   ├── analise.py           ← análise de histórico e alertas
│   └── monitor.py           ← ciclos 2h, slots matinais, assinaturas
│
└── telegram/
    ├── bot.py               ← envio e polling
    ├── aeroportos.py        ← dados IATA
    ├── teclados.py          ← inline keyboards
    └── handlers.py          ← processamento de mensagens
```

---

## 🖥️ TESTE LOCAL (VS Code)

### Pré-requisitos
- Python 3.11+
- VS Code com extensão Python

### Passo a passo

**1. Abra a pasta do projeto no VS Code**
```
Arquivo → Abrir Pasta → selecione fly-bot-v5
```

**2. Abra o terminal integrado**
```
Ctrl + ` (acento grave)
```

**3. Crie o ambiente virtual**
```bash
python -m venv venv
```

**4. Ative o ambiente virtual**
```bash
# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```
> Você verá `(venv)` no início da linha do terminal.

**5. Instale as dependências**
```bash
pip install -r requirements.txt
```

**6. Instale o Chromium do Playwright**
```bash
playwright install chromium
playwright install-deps chromium
```
> No Windows o segundo comando pode não ser necessário.

**7. Crie o arquivo .env**

Copie `.env.example` para `.env` e preencha:
```
TELEGRAM_TOKEN=seu_token_aqui
ADMIN_CHAT_ID=seu_chat_id_aqui
PIX_KEY_1MES=sua_chave_pix
PIX_VALOR_1MES=R$ 14,90
PIX_KEY_5MESES=sua_chave_pix
PIX_VALOR_5MESES=R$ 29,90
DB_FILE=bot.db
```

> Para descobrir seu ADMIN_CHAT_ID: mande qualquer mensagem para @userinfobot no Telegram.

**8. Rode o bot**
```bash
python main.py
```

Você verá no terminal:
```
[INFO] Banco SQLite inicializado (WAL mode).
[INFO] Bot v5 iniciado. Admin: 123456789
[INFO] Polling iniciado.
[INFO] Loop de ciclos iniciado.
```

---

## ☁️ DEPLOY NO RAILWAY

### Pré-requisitos
- Conta no [Railway](https://railway.app)
- Conta no [GitHub](https://github.com)
- Git instalado

### Passo 1 — Criar repositório no GitHub

1. Acesse [github.com](https://github.com) e clique em **New repository**
2. Nome: `fly-bot-v5` (ou o que preferir)
3. Visibilidade: **Private** (importante — não deixe público com dados de bot)
4. Clique em **Create repository**

### Passo 2 — Enviar código para o GitHub

No terminal da pasta do projeto:
```bash
git init
git add .
git commit -m "feat: fly-bot v5 — arquitetura modular"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/fly-bot-v5.git
git push -u origin main
```

### Passo 3 — Criar projeto no Railway

1. Acesse [railway.app](https://railway.app) e faça login com GitHub
2. Clique em **New Project**
3. Selecione **Deploy from GitHub repo**
4. Selecione seu repositório `fly-bot-v5`
5. Railway detectará o Dockerfile automaticamente

### Passo 4 — Configurar variáveis de ambiente

No painel do Railway:
1. Clique no seu serviço → aba **Variables**
2. Adicione uma por uma:

| Variável | Valor |
|---|---|
| `TELEGRAM_TOKEN` | seu token do BotFather |
| `ADMIN_CHAT_ID` | seu chat ID |
| `PIX_KEY_1MES` | sua chave Pix |
| `PIX_VALOR_1MES` | R$ 14,90 |
| `PIX_KEY_5MESES` | sua chave Pix |
| `PIX_VALOR_5MESES` | R$ 29,90 |
| `DB_FILE` | /data/bot.db |

### Passo 5 — Criar Volume persistente

**Este passo é obrigatório** para o banco não ser apagado a cada deploy.

1. No painel do Railway, clique em **New** → **Volume**
2. Nome: `bot-data`
3. Mount path: `/data`
4. Clique em **Create**
5. Aguarde o volume ser criado e o serviço reiniciar

> O `bot.db` será salvo em `/data/bot.db` — persiste entre deploys.

### Passo 6 — Verificar deploy

1. Clique na aba **Deployments** para acompanhar o build
2. O build do Playwright leva ~5 minutos na primeira vez
3. Quando aparecer ✅ **Active**, clique em **View Logs**
4. Você deve ver:
```
[INFO] Banco SQLite inicializado (WAL mode).
[INFO] Bot v5 iniciado.
[INFO] Polling iniciado.
```
5. Você também receberá uma mensagem no Telegram confirmando o início

---

## 🔄 Atualizando o bot

Para qualquer atualização futura:
```bash
git add .
git commit -m "descricao da mudança"
git push
```
O Railway detecta o push e faz o deploy automaticamente. O volume `/data` com o banco não é afetado.

---

## 🛠️ Comandos do Admin

| Comando | Descrição |
|---|---|
| `/liberar <id>` | Libera acesso após confirmar pagamento |
| `/bloquear <id>` | Suspende acesso |
| `/usuarios` | Lista todos com status e dias restantes |
| `/vencendo` | Assinaturas vencendo em até 7 dias |
| `/forcarbusca` | Força busca imediata para todos |
| `/broadcast <msg>` | Envia mensagem para todos os ativos |
| `/msg <id> <msg>` | Envia mensagem para um usuário específico |

---

## 📝 Editando mensagens

Todas as mensagens enviadas aos usuários estão em `textos.py`.
Edite à vontade sem mexer na lógica do bot.

---

## ⚠️ Nunca suba para o GitHub

- `.env` — suas credenciais
- `bot.db` — banco de dados com usuários
- `venv/` — ambiente virtual

Todos já estão no `.gitignore`.
