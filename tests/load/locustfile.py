"""Testes de carga do AegisFlow com Locust.

Simula trafego realista: requisicoes nao-streaming, streaming, cache hit/miss,
fallback, e fail-open. Gera relatorio de performance.

Uso:
    cd tests/load
    locust -f locustfile.py --host=http://localhost:8000

    # Headless (CI):
    locust -f locustfile.py --host=http://localhost:8000 --headless \\
        --users 100 --spawn-rate 10 --run-time 5m \\
        --html=report.html --csv=results

Requisitos:
    pip install locust
"""

from __future__ import annotations

import os
import random
import time

from locust import HttpUser, between, task
from locust.exception import StopUser

# Configuracao via variaveis de ambiente
API_KEY = os.getenv("AEGIS_API_KEY", "agf_test.test_key")
FAIL_OPEN = os.getenv("AEGIS_FAIL_OPEN", "false").lower() == "true"

# Mensagens de exemplo para simular prompts reais
_SIMPLE_PROMPTS = [
    "Ola, como vai?",
    "O que e Python?",
    "Me explique o que e uma API REST.",
    "Qual a capital do Brasil?",
    "Traduza 'hello world' para portugues.",
    "Me de 5 dicas de produtividade.",
    "O que e Git?",
    "Como fazer um bolo de chocolate?",
    "Qual a diferenca entre HTTP e HTTPS?",
    "Liste 3 frameworks Python para web.",
]

_MEDIUM_PROMPTS = [
    "Crie um componente React com useState e useEffect para buscar dados de uma API.",
    "Escreva uma query SQL com JOIN entre 3 tabelas para relatorio de vendas.",
    "Implemente um middleware de autenticacao JWT em Express.js.",
    "Configure um docker-compose com Postgres, Redis e uma API Python.",
    "Explique como funciona o padrao de design Observer com exemplo em TypeScript.",
    "Crie um pipeline CI/CD no GitHub Actions para deploy no Railway.",
    "Implemente um rate limiter com sliding window em Python.",
    "Escreva testes e2e com Cypress para um formulario de login.",
    "Como fazer web scraping com BeautifulSoup respeitando robots.txt?",
    "Explique o conceito de programacao assincrona com async/await.",
]

_COMPLEX_PROMPTS = [
    "Projete uma arquitetura de microservicos para um e-commerce com separacao de "
    "catalogo, carrinho, pagamento e notificacao. Considere consistencia eventual, "
    "saga pattern para transacoes distribuidas e event sourcing para auditoria.",
    "Implemente um algoritmo de consenso Raft em Python com eleicao de lider, "
    "replicacao de log e tolerancia a falhas. Inclua testes de rede particionada.",
    "Otimize uma query SQL com window functions, indices compostos e particionamento "
    "para uma tabela de 500 milhoes de registros. Explique o plano de execucao.",
    "Projete um sistema de cache distribuido com consistencia eventual, invalidation "
    "baseada em TTL e eventos, e estrategia de resolucao de conflitos (CRDT).",
    "Implemente um compilador simples (lexer + parser + gerador de codigo) para uma "
    "linguagem de expressoes matematicas. Use o algoritmo de shunting-yard.",
    "Explique como implementar um sistema de recomendacao com collaborative filtering "
    "e similaridade de cosseno em larga escala (milhoes de usuarios/itens).",
    "Projete a migracao de um monolith para microservicos usando o padrao Strangler "
    "Fig. Considere banco de dados compartilhado, transacoes distribuidas e "
    "observabilidade (distributed tracing, metrica, logging).",
    "Implemente um motor de busca full-text com indice invertido, TF-IDF, e "
    "ranking por relevancia. Suporte a busca por proximidade e fuzzy matching.",
    "Projete um sistema de autenticacao e autorizacao com OAuth 2.0, OpenID Connect, "
    "RBAC e ABAC. Considere single sign-on, MFA e auditoria de acessos.",
    "Explique como implementar um sistema de processamento de eventos em tempo real "
    "com Kafka, processamento de streams e janelas de tempo para agregacoes.",
]

# Modelos para teste
_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "claude-3-5-haiku",
    "claude-3-5-sonnet",
    "aegis-auto",
]


class AegisFlowUser(HttpUser):
    """Usuario simulado do AegisFlow.

    Distribuicao de trafego:
    - 60% prompts simples (cache hit provavel)
    - 30% prompts medios (cache miss, roteamento)
    - 10% prompts complexos (roteamento premium)
    - 20% streaming
    - 5% fail-open
    """

    wait_time = between(0.5, 3.0)  # tempo entre requisicoes (segundos)

    def on_start(self):
        """Verifica se a API esta respondendo antes de comecar."""
        headers = {"x-api-key": API_KEY}
        with self.client.get("/health", headers=headers, catch_response=True) as resp:
            if resp.status_code != 200:
                raise StopUser("API nao esta saudavel")

    @task(6)
    def simple_chat(self):
        """Prompt simples — alta probabilidade de cache hit."""
        prompt = random.choice(_SIMPLE_PROMPTS)
        model = random.choice(["gpt-4o-mini", "aegis-auto"])
        self._chat(model, prompt, stream=False)

    @task(3)
    def medium_chat(self):
        """Prompt medio — roteamento e possivel cache miss."""
        prompt = random.choice(_MEDIUM_PROMPTS)
        model = random.choice(["gpt-4o", "claude-3-5-sonnet", "aegis-auto"])
        self._chat(model, prompt, stream=False)

    @task(1)
    def complex_chat(self):
        """Prompt complexo — roteamento premium."""
        prompt = random.choice(_COMPLEX_PROMPTS)
        model = "aegis-auto"
        self._chat(model, prompt, stream=False)

    @task(2)
    def streaming_chat(self):
        """Chat com streaming — testa SSE."""
        prompt = random.choice(_SIMPLE_PROMPTS + _MEDIUM_PROMPTS)
        model = random.choice(_MODELS)
        self._chat(model, prompt, stream=True)

    @task(1)
    def fail_open_chat(self):
        """Chat com fail-open ativado."""
        prompt = random.choice(_SIMPLE_PROMPTS)
        model = "gpt-4o-mini"
        self._chat(model, prompt, stream=False, fail_open=True)

    @task(1)
    def health_check(self):
        """Health check periodico."""
        headers = {"x-api-key": API_KEY}
        self.client.get("/health", headers=headers, name="/health")

    @task(1)
    def health_status(self):
        """Status detalhado de dependencias."""
        headers = {"x-api-key": API_KEY}
        self.client.get("/health/status", headers=headers, name="/health/status")

    @task(1)
    def whoami(self):
        """Resolucao de tenant."""
        headers = {"x-api-key": API_KEY}
        self.client.get("/v1/whoami", headers=headers, name="/v1/whoami")

    def _chat(
        self,
        model: str,
        prompt: str,
        stream: bool = False,
        fail_open: bool = False,
    ):
        """Faz uma chamada ao endpoint de chat."""
        headers = {
            "x-api-key": API_KEY,
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "max_tokens": 200,
        }
        if fail_open:
            body["fail_open"] = True

        name = f"/v1/chat/completions [{'stream' if stream else 'sync'}]"
        if fail_open:
            name += " [fail-open]"

        start = time.time()

        if stream:
            with self.client.post(
                "/v1/chat/completions",
                headers=headers,
                json=body,
                catch_response=True,
                name=name,
                stream=True,
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    return
                # Consome o stream
                for _ in resp.iter_lines():
                    pass
                resp.success()
        else:
            with self.client.post(
                "/v1/chat/completions",
                headers=headers,
                json=body,
                catch_response=True,
                name=name,
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    return
                data = resp.json()
                # Verifica se a resposta tem conteudo
                choices = data.get("choices", [])
                if not choices:
                    resp.failure("Resposta sem choices")
                    return
                resp.success()

        elapsed = time.time() - start
        # Registra metrica customizada de latencia
        resp.request_meta["latency_ms"] = round(elapsed * 1000, 1)


class AegisFlowCacheUser(HttpUser):
    """Usuario focado em testar cache semantico.

    Envia o mesmo prompt repetidamente para medir cache hit rate.
    """

    wait_time = between(0.1, 0.5)  # alta frequencia

    def on_start(self):
        headers = {"x-api-key": API_KEY}
        with self.client.get("/health", headers=headers, catch_response=True) as resp:
            if resp.status_code != 200:
                raise StopUser("API nao esta saudavel")

    @task
    def cached_prompt(self):
        """Envia o mesmo prompt repetidamente — deve dar cache hit."""
        headers = {
            "x-api-key": API_KEY,
            "content-type": "application/json",
        }
        body = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "O que e Python? Explique em 2 frases."}],
            "max_tokens": 100,
        }
        with self.client.post(
            "/v1/chat/completions",
            headers=headers,
            json=body,
            catch_response=True,
            name="/v1/chat/completions [cache-test]",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            cache_header = resp.headers.get("x-aegis-cache", "miss")
            if cache_header == "hit":
                resp.request_meta["cache"] = "hit"
            else:
                resp.request_meta["cache"] = "miss"
            resp.success()