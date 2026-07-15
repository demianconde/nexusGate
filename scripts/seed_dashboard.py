"""Script para popular o dashboard do staging com dados de uso simulados.

Faz requisicoes ao endpoint /v1/chat/completions no modo dev (bypass de login),
gerando dados de uso variados no SQLite para visualizacao no painel.

Uso:
    python scripts/seed_dashboard.py [--requests N] [--days D]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import UTC, datetime, timedelta

import httpx

BASE = os.getenv("AEGIS_BASE_URL", "https://aegisflow-staging.fly.dev")
TOKEN = "dev-local-access"  # bypass dev mode

# ----- Prompts realistas para simular trafego variado -----

SIMPLE_PROMPTS: list[tuple[str, str]] = [
    ("gpt-4o-mini", "Ola, como vai?"),
    ("gpt-4o-mini", "O que e Python? Explique em 2 frases."),
    ("gpt-4o-mini", "Qual a capital do Brasil?"),
    ("gpt-4o-mini", "Traduza 'hello world' para portugues."),
    ("gpt-4o-mini", "Me de 5 dicas de produtividade."),
    ("gpt-4o-mini", "O que e Git?"),
    ("gpt-4o-mini", "Como fazer um bolo de chocolate?"),
    ("gpt-4o-mini", "Qual a diferenca entre HTTP e HTTPS?"),
    ("gpt-4o-mini", "Liste 3 frameworks Python para web."),
    ("gpt-4o-mini", "O que e uma API REST?"),
    ("gpt-4o-mini", "Explique o que e JSON."),
    ("gpt-4o-mini", "Como funciona a internet?"),
    ("gpt-4o-mini", "Defina inteligencia artificial."),
    ("gpt-4o-mini", "Qual a velocidade da luz?"),
    ("gpt-4o-mini", "O que e open source?"),
    ("gpt-4o-mini", "Me explique o que e Docker."),
    ("gpt-4o-mini", "Como instalar o Python?"),
    ("gpt-4o-mini", "O que e um banco de dados?"),
    ("gpt-4o-mini", "Qual o sentido da vida?"),
    ("gpt-4o-mini", "Conte uma piada."),
]

MEDIUM_PROMPTS: list[tuple[str, str]] = [
    ("claude-3-5-sonnet", "Crie um componente React com useState e useEffect para buscar dados de uma API."),
    ("claude-3-5-sonnet", "Escreva uma query SQL com JOIN entre 3 tabelas para relatorio de vendas."),
    ("gpt-4o", "Implemente um middleware de autenticacao JWT em Express.js."),
    ("gpt-4o", "Configure um docker-compose com Postgres, Redis e uma API Python."),
    ("gpt-4o", "Explique como funciona o padrao de design Observer com exemplo em TypeScript."),
    ("claude-3-5-sonnet", "Crie um pipeline CI/CD no GitHub Actions para deploy."),
    ("gpt-4o", "Implemente um rate limiter com sliding window em Python."),
    ("claude-3-5-sonnet", "Escreva testes e2e com Cypress para um formulario de login."),
    ("gpt-4o", "Como fazer web scraping com BeautifulSoup respeitando robots.txt?"),
    ("gpt-4o", "Explique o conceito de programacao assincrona com async/await."),
]

COMPLEX_PROMPTS: list[tuple[str, str]] = [
    ("gpt-4o", "Projete uma arquitetura de microservicos para um e-commerce com "
     "separacao de catalogo, carrinho, pagamento e notificacao. Considere "
     "consistencia eventual, saga pattern para transacoes distribuidas e "
     "event sourcing para auditoria."),
    ("gpt-4o", "Implemente um algoritmo de consenso Raft em Python com eleicao de "
     "lider, replicacao de log e tolerancia a falhas."),
    ("claude-3-5-sonnet", "Otimize uma query SQL com window functions, indices compostos e "
     "particionamento para uma tabela de 500 milhoes de registros."),
    ("gpt-4o", "Projete um sistema de cache distribuido com consistencia eventual, "
     "invalidacao baseada em TTL e eventos, e estrategia de CRDT."),
    ("claude-3-5-sonnet", "Explique como implementar um sistema de recomendacao com "
     "collaborative filtering e similaridade de cosseno em larga escala."),
]


async def create_api_key(client: httpx.AsyncClient) -> str:
    """Cria uma chave de API no tenant dev e retorna o valor."""
    resp = await client.post(
        f"{BASE}/v1/admin/keys",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json={"name": "simulacao-carga"},
    )
    if resp.status_code != 200:
        print(f"Erro ao criar chave: {resp.status_code} {resp.text}")
        sys.exit(1)
    data = resp.json()
    print(f"Chave criada: {data['key_prefix']}...")
    return data["api_key"]


async def send_request(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    prompt: str,
    stream: bool = False,
) -> dict | None:
    """Envia uma requisicao ao endpoint de chat."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
        "max_tokens": 150,
    }
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    try:
        resp = await client.post(
            f"{BASE}/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=120.0,
        )
        if resp.status_code != 200:
            print(f"  Erro HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        tokens = data.get("usage", {})
        return {
            "model": data.get("model", model),
            "provider": resp.headers.get("x-aegis-provider", "unknown"),
            "cache": resp.headers.get("x-aegis-cache", "miss"),
            "prompt_tokens": tokens.get("prompt_tokens", 0),
            "completion_tokens": tokens.get("completion_tokens", 0),
        }
    except httpx.TimeoutException:
        print("  Timeout")
        return None
    except Exception as exc:
        print(f"  Erro: {exc}")
        return None


async def seed_historical(
    client: httpx.AsyncClient,
    api_key: str,
    days: int,
    requests_per_day: int,
) -> None:
    """Simula dados historicos fazendo requisicoes com diferentes prompts."""
    print(f"\nSimulando {days} dias de historico, ~{requests_per_day} req/dia...")
    
    all_prompts = (
        [(p, 0.6) for p in SIMPLE_PROMPTS]
        + [(p, 0.3) for p in MEDIUM_PROMPTS]
        + [(p, 0.1) for p in COMPLEX_PROMPTS]
    )

    total = 0
    # Distribui as requisicoes pelos dias (do mais antigo para hoje)
    for day_offset in range(days - 1, -1, -1):
        n = requests_per_day + random.randint(-5, 5)  # variacao diaria
        n = max(1, n)
        print(f"  Dia {-day_offset} ({n} requisicoes)...")
        
        for _ in range(n):
            # Escolhe prompt com probabilidade ponderada
            r = random.random()
            cumulative = 0.0
            chosen = SIMPLE_PROMPTS[0]  # default
            for (prompt, weight) in all_prompts:
                cumulative += weight / len(all_prompts) * 3  # normaliza
                if r < cumulative:
                    chosen = prompt
                    break
            else:
                chosen = all_prompts[-1][0]

            model, text = chosen
            result = await send_request(client, api_key, model, text)
            total += 1
            
            if total % 10 == 0:
                print(f"    {total} requisicoes enviadas...")
            
            # Pequena pausa para nao sobrecarregar
            await asyncio.sleep(0.1)

    print(f"\nTotal: {total} requisicoes enviadas no historico.")


async def seed_duplicates(client: httpx.AsyncClient, api_key: str, count: int = 30) -> None:
    """Envia o mesmo prompt repetido para gerar cache hits no dashboard."""
    print(f"\nGerando {count} requisicoes repetidas para cache hits...")
    dup_model, dup_prompt = SIMPLE_PROMPTS[1]  # "O que e Python?..."
    
    for i in range(count):
        result = await send_request(client, api_key, dup_model, dup_prompt)
        if result and result.get("cache") == "hit":
            print(f"  Cache HIT #{i+1}")
        await asyncio.sleep(0.05)
    
    print(f"  Concluido.")


async def main():
    parser = argparse.ArgumentParser(description="Popular dashboard do staging com dados simulados")
    parser.add_argument("--requests", type=int, default=200, help="Total de requisicoes (default: 200)")
    parser.add_argument("--days", type=int, default=14, help="Dias de historico (default: 14)")
    parser.add_argument("--duplicates", type=int, default=30, help="Requisicoes duplicadas para cache (default: 30)")
    args = parser.parse_args()

    print(f"AegisFlow Dashboard Seed")
    print(f"Base URL: {BASE}")
    print(f"Modo: dev (bypass)")
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Verifica se o staging esta no ar
        resp = await client.get(f"{BASE}/health")
        if resp.status_code != 200:
            print(f"ERRO: Staging nao esta respondendo. Status: {resp.status_code}")
            sys.exit(1)
        print(f"Staging OK: {resp.json()}")

        # Cria chave de API
        api_key = await create_api_key(client)

        # Calcula requisicoes por dia
        req_per_day = max(1, (args.requests - args.duplicates) // args.days)
        
        # Simula historico
        await seed_historical(client, api_key, args.days, req_per_day)
        
        # Gera cache hits
        await seed_duplicates(client, api_key, args.duplicates)

    print(f"\n✅ Dashboard populado!")
    print(f"   Acesse: {BASE}/dashboard")
    print(f"   Login: clique em 'Entrar sem login (dev)'")


if __name__ == "__main__":
    asyncio.run(main())