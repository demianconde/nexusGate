# AegisFlow — Arquitetura, Banco e Deploy

Referência única de infraestrutura, dados e como publicar. Atualizado em jul/2026.

> **O que é:** LLM Gateway BYOK para empresas brasileiras — roteia cada requisição
> para o modelo mais barato que resolve, cacheia respostas repetidas e usa a chave
> do próprio cliente (BYOK), com dados no Brasil e conformidade LGPD.

---

## 1. Visão geral da arquitetura

```
                      Internet (HTTPS)
                            │
              aegisflow.tech  (GoDaddy DNS → Fly)
                            │  TLS (Let's Encrypt via Fly)
                            ▼
        ┌─────────────────────────────────────────┐
        │  Fly.io — app "aegisflow" (região gru/SP)  │
        │  FastAPI + uvicorn (Docker)               │
        │  2× shared-cpu-1x 512MB                    │
        └───────┬───────────────┬───────────────────┘
                │               │
      (rede privada)      (internet/TLS)
                │               │
                ▼               ▼
   ┌───────────────────┐   ┌──────────────────────────┐
   │ Redis (Upstash/Fly)│   │ Supabase (Postgres, SP)   │
   │ rate-limit + cache │   │ sa-east-1 — dados no BR    │
   └───────────────────┘   │ + Auth (login do painel)   │
                            └──────────────────────────┘
   Externos: provedores LLM (OpenAI/Anthropic/… via BYOK),
             SMTP GoDaddy (notificação de leads), Stripe (billing, futuro)
```

- **Compute:** Fly.io. App `aegisflow`, região **`gru` (São Paulo)**. Hostname interno `aegisflow.fly.dev`; domínio público `aegisflow.tech`.
- **Dados:** Supabase Postgres, região **`sa-east-1` (São Paulo)** — cumpre "dados no Brasil".
- **Motivo do split (Supabase em vez de Postgres no Fly):** o Fly `gru` ficou sem capacidade de CPU para provisionar o Postgres; o Supabase SP não tem esse problema. O que garante a residência é onde o **dado** mora.

## 2. Stack

| Camada | Tecnologia |
|---|---|
| API | FastAPI + Uvicorn (Python 3.11 no Docker; 3.12 no venv local) |
| ORM / migrations | SQLAlchemy (async) + Alembic |
| Banco | Supabase Postgres 16 (driver `asyncpg`) |
| Cache / rate-limit | Redis (Upstash gerenciado via Fly) |
| Auth do painel | Supabase Auth (e-mail/senha, magic link, Google OAuth) |
| Auth da API (gateway) | Chave própria `agf_…` no header `x-api-key` |
| Cripto BYOK | AES-256-GCM (envelope encryption); KEK = `AEGIS_MASTER_KEY` |
| E-mail | SMTP GoDaddy (`smtpout.secureserver.net:465`) — notificação de leads |
| Front | HTML/CSS/JS estáticos servidos pelo FastAPI (`app/public/`) |
| Deploy | Fly.io (Docker), CI de deploy manual via `fly deploy` |
| Repo | github.com/demianconde/aegisflow |

## 3. Banco de dados

- **Conexão (produção):** Supabase **Session pooler** — host `aws-1-sa-east-1.pooler.supabase.com`, porta `5432`, user `postgres.<project_ref>`, db `postgres`, `sslmode=require`. Project ref: `cztjqjzkshxcjibifuxf`.
- **`DATABASE_URL`:** o app normaliza automaticamente (`app/config.py`): converte `postgres://`/`postgresql://` → `postgresql+asyncpg://` e `sslmode=<x>` → `ssl=<x>` (asyncpg não aceita `sslmode`). Pode-se colar a URL nativa do provedor.
- **Migrations:** Alembic em `alembic/versions/` (`0001`→`0007`). Rodam **automaticamente no deploy** via `release_command = "alembic upgrade head"` (fly.toml). Nova migração: `alembic revision -m "descricao"` (ou escrever à mão seguindo o padrão).
- **Tabelas principais:** `tenants` (empresa; inclui `guardrail_pii`, `routing_mode`), `users` (vinculado ao Supabase user), `aegis_api_keys` (chaves `agf_` com orçamento/rpm/allowlist), `provider_keys` (BYOK cifrado), `usage_logs`, `subscriptions`, `leads`.
- **Modelo mental:** Empresa (**tenant**) → **chaves da API** (escopo/orçamento por chave) → **chaves BYOK** dos provedores. *Não há entidade "projeto"* — as chaves virtuais cumprem esse papel.

## 4. Roteamento (aegis-auto)

- **Complexidade em 3 níveis** (`app/routing/router.py`): sistema de pontos (sinais de alta +4 / média +2 + tamanho de contexto) → `low` / `medium` / `high`. 100% de acurácia no dataset rotulado (`scripts/eval_router.py`).
- **Tiers por provedor:** `cheap` / `mid` / `premium` (mapeados de low/medium/high). Política **local-first** com escalonamento para hospedado.
- **Modo configurável por tenant** (`routing_mode`): `heuristic` (sem IA, padrão) ou `classifier` (IA leve, endpoint compatível OpenAI via `AEGIS_CLASSIFIER_*`, com fallback para a heurística). Ajustável no painel.

## 5. Segredos e variáveis de ambiente

**Secrets no Fly** (`fly secrets set … -a aegisflow`) — nunca no git:

| Secret | Descrição |
|---|---|
| `DATABASE_URL` | Postgres do Supabase (Session pooler, com `?sslmode=require`) |
| `REDIS_URL` | Redis Upstash (`redis://…@fly-aegisflow-redis.upstash.io:6379`) |
| `AEGIS_MASTER_KEY` | KEK base64 de 32 bytes (cripto BYOK). **Perder = perder as chaves cifradas.** |
| `SUPABASE_URL` | `https://cztjqjzkshxcjibifuxf.supabase.co` |
| `SUPABASE_ANON_KEY` | chave publishable (pública) |
| `AEGIS_OWNER_EMAILS` | e-mails com acesso ao console do dono (`/gestaoaegis`) |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | SMTP GoDaddy p/ notificação de leads |
| `LEADS_NOTIFY_EMAIL` | destino das notificações (`contato@aegisflow.tech`) |

**Não sensíveis** (em `fly.toml [env]`): `AEGIS_ENV=production`, `AEGIS_LOG_JSON=true`, `AEGIS_CORS_ORIGINS=https://aegisflow.tech,https://www.aegisflow.tech`.

**Opcionais** (classificador IA): `AEGIS_ROUTING_MODE`, `AEGIS_CLASSIFIER_URL`, `AEGIS_CLASSIFIER_MODEL`, `AEGIS_CLASSIFIER_API_KEY`. Billing (futuro): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.

## 6. Deploy — runbook

**Pré-requisitos:** `flyctl` instalado e `fly auth login`; acesso de push ao repo.

```bash
export PATH="$PATH:$HOME/.fly/bin"           # (Windows: C:/Users/<user>/.fly/bin)
cd "<repo>/AegisFlow"

# 1. subir código
git add -A && git commit -m "..." && git push

# 2. deploy (build Docker + migrations no boot + rollout)
fly deploy -a aegisflow --regions gru

# util
fly logs -a aegisflow                # logs
fly status -a aegisflow              # máquinas/checks
fly secrets list -a aegisflow        # secrets (nomes/digests)
fly releases -a aegisflow            # histórico p/ rollback
```

- O deploy roda o **`release_command` (`alembic upgrade head`)** numa VM temporária antes do rollout; se a migração falhar, o deploy aborta.
- **Rollback:** `fly releases -a aegisflow` → `fly deploy -a aegisflow --image <imagem_anterior>`.
- **Healthcheck:** `GET /health` (liveness). Também `GET /health/ready` (checa o banco) e `GET /metrics` (Prometheus, protegido por token em prod).

## 7. Domínio e TLS (GoDaddy → Fly)

Certificados já emitidos (`fly certs`). Registros DNS na GoDaddy:

| Tipo | Nome | Valor |
|---|---|---|
| A | `@` | `66.241.124.177` (IPv4 compartilhado do Fly) |
| AAAA | `@` | `2a09:8280:1::14c:66e7:0` (IPv6 dedicado) |
| A / AAAA | `www` | mesmos valores (ou CNAME `www` → `aegisflow.fly.dev`) |

TLS/HTTPS é emitido automaticamente pelo Fly após a propagação. Verificar: `fly certs check aegisflow.tech`.

## 8. Configuração externa necessária (checklist de publicação do free)

O cadastro grátis self-service já está no código (login Supabase → tenant plano `free`,
sem cartão) com anti-abuso (blocklist de e-mail descartável + limite de contas por IP/dia).
Para liberar ao público, falta **configuração externa** (não é código):

- [ ] **Supabase Auth → e-mail verificado (escolha do produto: B):** manter "Confirm email"
      LIGADO **e configurar SMTP próprio** (Authentication → Providers → Email) — senão o
      e-mail de confirmação não é enviado e o cadastro não completa. *(bloqueador do free)*
- [ ] **Supabase Auth → URL Configuration:** Site URL `https://aegisflow.tech` + Redirect
      `https://aegisflow.tech/**` (confirmação de e-mail / magic link / Google).
- [ ] **Fly billing:** cartão cadastrado (evita suspensão do app / habilita add-ons).
- [ ] **GoDaddy DNS:** registros da seção 7 (feito).
- [ ] **Segurança:** `AEGIS_MASTER_KEY` guardada com segurança; rotacionar a senha do banco se exposta.
- [ ] **Termos/Privacidade:** preencher razão social/CNPJ (placeholders em `termos.html`/`privacidade.html`).
- [ ] **Retenção de custo (recomendado):** agendar `scripts/prune_usage_logs.py` (cron diário)
      para limitar o crescimento de `usage_logs` — principal custo variável do free em escala.
      Opcional: ajustar `AEGIS_SIGNUP_IP_DAILY_LIMIT` / `AEGIS_DISPOSABLE_EMAIL_DOMAINS`.

## 9. URLs úteis

- Site: `https://aegisflow.tech` · Painel: `/dashboard` · Login: `/login`
- Docs API: `/documentacao` · Blog: `/artigos` · Console do dono: `/gestaoaegis` (restrito)
- API do gateway: `https://aegisflow.tech/v1/chat/completions` (header `x-api-key: agf_…`, `model: "aegis-auto"`)
- Fly dashboard: fly.io/apps/aegisflow · Supabase: supabase.com/dashboard (projeto AegisFlow)
