# Migração do Fly Bot v5 — Railway → Oracle Cloud (Always Free)

Objetivo: rodar o bot 24/7 de graça, para sempre, numa VM ARM do Oracle Cloud
(camada **Always Free**), com Docker. O banco (`bot.db`) fica num diretório do
host e sobrevive a reboots e atualizações.

Resumo do que muda:

| Antes (Railway) | Agora (Oracle) |
|---|---|
| Deploy automático via `git push` | `git pull` + `docker compose up -d --build` na VM |
| Volume `/data` do Railway | pasta `~/fly-bot/data` na VM (bind mount) |
| URL HTTPS pública automática | **nenhuma** (o bot só faz conexão de saída) |
| Fuso UTC | `America/Sao_Paulo` (ver seção 9) |

> **Mercado Pago está desativado** hoje (não há `MP_ACCESS_TOKEN` no `.env`).
> O fluxo é o manual: usuário manda comprovante, admin dá `/liberar`.
> Por isso **não precisamos abrir nenhuma porta** na VM. Se um dia reativar o
> MP, veja o Apêndice A.

---

## 1. Criar a conta Always Free

1. Acesse <https://www.oracle.com/cloud/free/> → **Start for free**.
2. Vai pedir cartão de crédito **para verificação** — não há cobrança na camada
   Always Free (a conta fica em modo "Free Tier"; ela não vira paga sozinha).
3. **Escolha a Home Region com cuidado — não dá para trocar depois.**
   Recomendado: **Brazil East (São Paulo)** ou **Brazil Southeast (Vinhedo)**.
   Se der falta de capacidade ARM nessas, `US East (Ashburn)` costuma ter mais.

---

## 2. Criar a VM (instância de Compute)

No console: **Menu ☰ → Compute → Instances → Create instance**.

- **Name:** `fly-bot`
- **Image:** *Canonical Ubuntu **22.04*** (marque a opção "Always Free eligible").
  Use 22.04, não 24.04 — o Dockerfile já está calibrado para as libs do 22.04.
- **Shape:** clique em **Change shape → Ampere (Arm)** → `VM.Standard.A1.Flex`
  - **OCPUs:** `2`
  - **Memória:** `12 GB`
  - (a cota Always Free é 4 OCPU + 24 GB no total de ARM; usar 2/12 deixa
    margem para uma segunda VM depois se quiser)
- **Networking:** deixe criar uma **VCN nova**, subnet **pública**, e marque
  **Assign a public IPv4 address**.
- **SSH keys:**
  - No seu PC (Windows PowerShell / Git Bash):
    ```bash
    ssh-keygen -t ed25519 -f "$HOME/.ssh/oracle_flybot" -C flybot
    ```
  - Cole o conteúdo de `~/.ssh/oracle_flybot.pub` no campo **Paste public keys**.
- **Create.** Anote o **IP público** quando a instância ficar *Running*.

### Se aparecer "Out of host capacity"

É comum com ARM. Alternativas, em ordem:
1. Tente outro **Availability Domain** (AD-1, AD-2, AD-3) no mesmo passo.
2. Reduza para **1 OCPU / 6 GB** (ainda folgado para este bot).
3. Tente de novo em algumas horas, ou num script de retry.
4. Último recurso: shape **VM.Standard.E2.1.Micro** (AMD, 1 GB) — funciona, mas
   aí rode **1 navegador por vez** (ver Apêndice B).

---

## 3. Conectar via SSH

```bash
ssh -i ~/.ssh/oracle_flybot ubuntu@SEU_IP_PUBLICO
```

(usuário é `ubuntu` nas imagens Ubuntu do Oracle)

---

## 4. Bootstrap da VM

Dentro da VM:

```bash
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/arthurspider1991/fly-bot.git ~/fly-bot
cd ~/fly-bot
bash deploy/setup-oracle.sh
newgrp docker        # ativa o grupo docker sem precisar deslogar
```

O `setup-oracle.sh` instala Docker, cria **4 GB de swap** (rede de segurança
contra OOM do Chromium), cria a pasta `data/` e um `.env` a partir do exemplo.

---

## 5. Configurar os segredos

```bash
nano ~/fly-bot/.env
```

Preencha:

```
TELEGRAM_TOKEN=...          # o mesmo token do BotFather que já usa
ADMIN_CHAT_ID=...           # seu chat id (ex.: 5035568457)
TELEGRAM_BOT_USERNAME=...   # username do bot, sem @
```

Deixe `MP_ACCESS_TOKEN` / `MP_PUBLIC_KEY` / `MP_WEBHOOK_URL` **em branco**.
Não mexa em `DB_FILE` — o `docker-compose.yml` já força `/data/bot.db`.

Salvar no nano: `Ctrl+O`, `Enter`, `Ctrl+X`.

---

## 6. (Opcional) Levar o banco atual do Railway

Se quiser preservar usuários/assinaturas já cadastrados:

1. Baixe o `bot.db` do volume do Railway (aba do serviço → *Volumes* →
   download, ou via `railway run` / `railway ssh` se ainda tiver acesso).
2. Do seu PC, envie para a VM **antes do primeiro start**:
   ```bash
   scp -i ~/.ssh/oracle_flybot bot.db ubuntu@SEU_IP:~/fly-bot/data/bot.db
   ```

Se não tiver o arquivo, tudo bem — o bot cria um banco limpo no primeiro start
e o `init_db()` monta as tabelas.

---

## 7. Subir o bot

```bash
cd ~/fly-bot
docker compose up -d --build
docker compose logs -f
```

A **primeira build leva ~5–10 min** (baixa Python, Chromium e libs no ARM).
Quando estiver no ar você verá nos logs:

```
[INFO] Banco SQLite inicializado (WAL mode).
[INFO] Bot v5 iniciado. Admin: ...
[INFO] Polling iniciado.
[INFO] Loop de ciclos iniciado.
```

e receberá a mensagem "🤖 Bot v5 iniciado!" no Telegram.

**Agora desligue o serviço no Railway** para não haver dois bots no mesmo token
fazendo polling ao mesmo tempo (isso causa updates perdidos / erros 409).

---

## 8. Operação do dia a dia

| Ação | Comando (dentro de `~/fly-bot`) |
|---|---|
| Ver logs | `docker compose logs -f --tail=100` |
| Reiniciar | `docker compose restart` |
| Parar | `docker compose down` |
| Subir de novo | `docker compose up -d` |
| Atualizar (após novo commit) | `bash deploy/update.sh` |
| Status / uso de RAM | `docker stats flybot` |

**Reboot da VM:** o container volta sozinho (`restart: unless-stopped` +
Docker habilitado no boot). Nada a fazer.

### Backup do banco

```bash
mkdir -p ~/backups
cp ~/fly-bot/data/bot.db ~/backups/bot-$(date +%F).db
```

Automatizar com cron (todo dia às 04:10, mantém 14 dias):

```bash
( crontab -l 2>/dev/null; echo '10 4 * * * cp ~/fly-bot/data/bot.db ~/backups/bot-$(date +\%F).db && find ~/backups -name "bot-*.db" -mtime +14 -delete' ) | crontab -
```

Para trazer um backup para o seu PC:

```bash
scp -i ~/.ssh/oracle_flybot ubuntu@SEU_IP:~/backups/bot-2026-08-30.db .
```

---

## 9. Fuso horário — confira o comportamento

Na Railway o container provavelmente rodava em **UTC**. Agora ele roda em
**America/Sao_Paulo** (`TZ` no Dockerfile + `docker-compose.yml`).

Impacto: os **slots matinais `05:00`–`08:00`** ([`config.py`](../config.py))
e o **job diário das `09:00`** ([`main.py`](../main.py)) passam a disparar no
**horário de Brasília**, que é o que os textos do bot dão a entender.

Se por algum motivo você preferir manter UTC, troque no `docker-compose.yml`:

```yaml
    environment:
      TZ: UTC
```

e rode `docker compose up -d --build`.

---

## 10. A instância não vai ser "recuperada" pelo Oracle?

O Oracle só recupera instâncias **Always Free** que ficam **ociosas** por 7 dias
seguidos (CPU < 20% no percentil 95, além de rede e memória baixas). Este bot
faz polling contínuo + ciclos de scraping, então fica bem acima do limiar.
Ainda assim, o backup em `~/backups` te protege.

---

## Apêndice A — Reativar o Mercado Pago (webhook HTTPS)

Só se você voltar a usar Pix automático. Aí o `webhook.py` precisa ser
alcançável pela internet via HTTPS. Caminho mais simples:

1. **Abrir a porta 443** em dois lugares:
   - Console Oracle: VCN → Security List da subnet → *Add Ingress Rule*:
     Source `0.0.0.0/0`, TCP, porta `443`.
   - Na VM: `sudo iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT` e
     `sudo netfilter-persistent save` (as imagens Oracle têm iptables restrito).
2. **Domínio grátis**: crie um em <https://www.duckdns.org> (ex.:
   `flybot.duckdns.org`) apontando para o IP público da VM.
3. **Caddy** como reverse proxy com HTTPS automático. Adicione ao
   `docker-compose.yml` um serviço `caddy` que faz proxy de `:443` →
   `flybot:8080`, e publique a porta `8080` do serviço `flybot` só na rede
   interna do compose.
4. No `.env`: `MP_ACCESS_TOKEN=...` e
   `MP_WEBHOOK_URL=https://flybot.duckdns.org/`.
5. Cadastre essa URL no painel do Mercado Pago (Notificações / Webhooks).

Peça ajuda quando chegar nessa etapa — dá para eu gerar o `docker-compose.yml`
com o Caddy pronto.

## Apêndice B — Rodar só 1 navegador por vez (VMs pequenas)

Se acabar numa VM de 1 GB, o pico dos **3 navegadores sequenciais** em
[`services/scraper.py`](../services/scraper.py) (`buscar_preco_e_historico`)
pode faltar RAM mesmo com swap. A mitigação é reduzir para Kayak apenas (ou
Kayak + Google), removendo o bloco do AirHint. É uma mudança de código —
me avise que eu faço.
