# NexusGate

**LLM Gateway & Multi-Agent Proxy BYOK** — SaaS gerenciado que fica entre as aplicações dos clientes e os provedores de IA (OpenAI, Anthropic, Qwen), agregando: proxy BYOK, roteamento por custo, cache semântico e billing multi-tenant.

> Reescrita do protótipo `nexusGate` como produto real. Stack oficial: **Python 3.11 + FastAPI**. Entrega: **SaaS gerenciado**. Auth do painel: **Supabase**.

## Arquitetura (resumo)

```
[App do cliente] --(x-api-key)--> [NexusGate API / FastAPI]
   Supabase (auth do painel)          | resolve tenant + descriptografa chave BYOK
   [Router de custo] -> [Cache semântico (Redis)] -> [Provider] -> OpenAI/Anthropic/Qwen (streaming)
   [Postgres: tenants, api_keys, provider_keys, usage_logs, subscriptions]   [Stripe]   [Dashboard]
```

Dois planos de autenticação distintos:
- **Painel**: usuários logam via Supabase.
- **Proxy de dados**: apps clientes autenticam com uma `x-api-key` do NexusGate (prefixo + hash).

## Requisitos
- Docker + Docker Compose (recomendado), ou
- Python 3.11, Postgres 16 e Redis Stack locais.

## Como rodar (Docker)

```bash
cp .env.example .env    # ajuste as variáveis
make up                 # sobe postgres + redis-stack + api (aplica migrations)
make logs               # acompanha a API
curl http://localhost:8000/health
```

## Como rodar (local, sem Docker)

```bash
make install
# suba Postgres e Redis (ex.: via docker compose up -d postgres redis)
make migrate            # alembic upgrade head
make dev                # uvicorn com reload
```

## Comandos úteis (Makefile)
- `make migrate` — aplica migrations
- `make revision m="mensagem"` — gera nova migration (autogenerate)
- `make lint` / `make test` — ruff / pytest

## API

**Painel (auth Supabase — `Authorization: Bearer <jwt>`):**
- `GET /v1/admin/me` — perfil do usuário + tenant
- `GET /v1/admin/keys` — lista as chaves de API do tenant
- `POST /v1/admin/keys` `{ "name": "..." }` — cria chave (retorna o valor em claro **só aqui**)
- `DELETE /v1/admin/keys/{id}` — revoga a chave

**Proxy / plano de dados (auth `x-api-key: nxg_....`):**
- `GET /v1/whoami` — resolve o tenant a partir da chave (após rate limit). O `/v1/chat/completions` real chega na Fase 2.

Rate limiting por tenant (janela de 1 min): free=60, pro=600, enterprise=6000 req/min.

## Estrutura
```
app/
  config.py            # settings (pydantic-settings)
  logging_config.py    # logging estruturado (sem PII/segredos)
  main.py              # app factory FastAPI + middleware de request_id
  redis_client.py      # conexão Redis compartilhada
  ratelimit.py         # rate limiting por tenant
  auth/                # supabase (painel) + api_key (proxy) + parsing de token
  db/                  # engine async, sessão e modelos ORM
  api/                 # rotas: health, admin (painel), proxy (dados)
alembic/               # migrations
tests/                 # pytest
```

## Roadmap (fases)
- **F0 Fundação** ✅ scaffold, DB async + Alembic, /health, Docker, CI
- **F1 Multi-tenant + Auth** ✅ Supabase real, provisionamento de tenants/users, CRUD de x-api-key, rate-limiting por tenant
- **F2 Proxy BYOK real** — envelope encryption, chamadas reais com streaming
- **F3 Roteamento + Economia** — router de custo, dashboard de economia
- **F4 Cache semântico real** — embeddings (fastembed) + Redis vetorial
- **F5 Billing** — Stripe metered, planos, webhooks
- **F6 Hardening / GA** — observabilidade, retries, security review

## Segurança
- Nunca comitar `.env` nem segredos. Chaves BYOK são criptografadas at-rest (envelope encryption, Fase 2).
- Logs não registram prompts, segredos ou PII.
