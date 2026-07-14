"""Roteador de custo (aegis-auto) — local-first com escalonamento.

Política:
- **Local é o primeiro recurso**, para tarefas simples E complexas (é gratuito).
- Só quando o local **não dá conta** (falha/erro na chamada) é que escala para um
  modelo pago hospedado — o **premium** no caso de tarefa complexa, ou o hospedado
  mais barato no caso de tarefa simples.
- Sem provedor local, escolhe direto o hospedado adequado ao tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.providers.registry import KNOWN_PROVIDERS, is_local_url
from app.routing.pricing import price_of

# Pontuação de complexidade (PT + EN — devs escrevem prompts nos dois idiomas).
# Cada categoria soma seus pontos UMA vez (se casar). Mais pontos → tarefa mais
# complexa → modelo mais capaz. Ajuste os pesos/limiares para calibrar o roteamento.
# Sinais de ALTA complexidade (+4): arquitetura, algoritmos, sistemas distribuídos,
# otimização/performance, segurança ofensiva, baixo nível, IA/ML, infra avançada.
_HIGH_SIGNALS = re.compile(
    r"arquitetura|architecture|design de sistema|system design|microservi|"
    r"distribu[íi]|distributed|sharding|parti[çc][ãa]o de dados|"
    r"compilador|compiler|\blexer\b|\bparser\b|"
    r"race condition|condi[çc][ãa]o de corrida|"
    r"sql injection|\bxss\b|cross-site|vulnerabilidad|malware|engenharia reversa|"
    r"ofusca|timing attack|reentrancy|"
    r"\balgoritmo\b|\balgorithm|heur[íi]stic|\ba\*|"
    r"machine learning|pytorch|tensorflow|rede neural|neural network|\bgpu|"
    r"collaborative filtering|similaridade do cosseno|cosine similarity|motor de recomenda|"
    r"smart contract|solidity|\bdefi\b|blockchain|staking|"
    r"kubernetes|garbage collector|memory limit|out of memory|\boom\b|core dump|"
    r"cache distribu|distributed cache|\blru\b|"
    r"serverless|\blambda\b|dynamodb|dead letter|"
    r"alocador de mem[óo]ria|\bmalloc\b|embedded|sistema embutido|fragmenta[çc]|"
    r"clean architecture|domain-driven|\bddd\b|"
    r"service mesh|\bistio\b|\bmtls\b|\bcanary\b|"
    r"\bcrdt|conflict-free|colaborativo em tempo real|editor de texto colaborativo|"
    r"consenso|\bpaxos\b|\braft\b|leader election|elei[çc][ãa]o de l[íi]der|"
    r"memory leak|fuga de mem[óo]ria|"
    r"terraform|multi-cloud|\bfailover\b|infrastructure as code|"
    r"\baes-256\b|criptogr[áa]f|cryptograph|encripta|"
    r"\brag\b|retrieval-augmented|langchain|re-ranking|chunking|"
    r"big o|complexidade de (tempo|espa[çc]o)|prove matem|mathematical proof|o\(n|"
    r"\bassembly\b|x86|call stack|"
    r"engine f[íi]sica|separating axis|detec[çc][ãa]o de colis|"
    r"zero downtime|sem interrup[çc][ãa]o de servi[çc]o|"
    r"\babac\b|attribute-based|"
    r"otimiz|optimiz|\bfps\b|perda de frames",
    re.IGNORECASE,
)

# Sinais de MÉDIA complexidade (+2): frameworks/libs, integração e features reais.
_MEDIUM_SIGNALS = re.compile(
    r"\breact\b|\bexpress\b|\bvue\b|angular|next\.?js|nextauth|svelte|"
    r"mongoose|mongodb|prisma|\borm\b|sqlalchemy|sqlite|"
    r"\bjest\b|cypress|\be2e\b|teste unit[áa]rio|teste de integra|"
    r"dockerfile|docker-compose|docker compose|"
    r"graphql|middleware|\bjwt\b|oauth|"
    r"stripe|sendgrid|"
    r"\bhook\b|usefetch|usestate|useeffect|composition api|"
    r"web scraping|beautifulsoup|"
    r"github actions|\bpipeline\b|ci/cd|"
    r"rate limiter|debounce|drag and drop|"
    r"\bcron\b|reverse proxy|nginx|"
    r"design pattern|padr[ãa]o de|strategy|"
    r"goroutines|concorrent|concurrency|concorr[êe]ncia|"
    r"\bjoin\b|\bsql\b|query sql|junte a tabela|batch insert|"
    r"backup|tar\.gz|\bs3\b|"
    r"formul[áa]rio|componente|component|dashboard|sidebar|layout responsivo|"
    r"jogo da velha|tic-tac-toe|spinner|anima[çc][ãa]o|keyframes|"
    r"pagina[çc][ãa]o|migra[çc][ãa]o|migration",
    re.IGNORECASE,
)

_SIGNALS: list[tuple[re.Pattern[str], int]] = [(_HIGH_SIGNALS, 4), (_MEDIUM_SIGNALS, 2)]

# Limiares de pontuação → nível de complexidade (baixa/média/alta).
_MEDIUM_THRESHOLD = 2
_HIGH_THRESHOLD = 4

# Três tiers por provedor: barato (baixa), médio (média) e premium (alta).
PROVIDER_TIERS: dict[str, dict[str, str]] = {
    "openai": {"cheap": "gpt-4o-mini", "mid": "gpt-4o", "premium": "gpt-4o"},
    "anthropic": {
        "cheap": "claude-3-5-haiku",
        "mid": "claude-3-5-sonnet",
        "premium": "claude-3-5-sonnet",
    },
    "google": {
        "cheap": "gemini-3.1-flash-lite",
        "mid": "gemini-2.5-flash",
        "premium": "gemini-2.5-pro",
    },
    "qwen": {"cheap": "qwen-turbo", "mid": "qwen-plus", "premium": "qwen-max"},
    "deepseek": {"cheap": "deepseek-chat", "mid": "deepseek-chat", "premium": "deepseek-reasoner"},
    "mistral": {"cheap": "mistral-small", "mid": "mistral-medium", "premium": "mistral-large"},
    "groq": {"cheap": "llama-3.1-8b", "mid": "llama-3.3-70b", "premium": "llama-3.3-70b"},
    "together": {"cheap": "llama-3.1-8b", "mid": "llama-3.1-70b", "premium": "llama-3.1-70b"},
}


class _KeyLike(Protocol):
    provider: str
    base_url: str | None
    default_model: str | None


@dataclass
class Route:
    provider_key: _KeyLike
    model: str
    baseline_model: str
    complexity: str
    tier: str
    is_local: bool
    escalation: Route | None = None


def complexity_score(messages: list[dict]) -> int:
    """Soma os pontos de complexidade dos sinais de texto + tamanho + código."""
    text = " ".join(str(m.get("content", "")) for m in messages)
    score = 0
    for pattern, points in _SIGNALS:
        if pattern.search(text):
            score += points
    n = len(text)
    if n > 6000:  # ~1500 tokens
        score += 3
    elif n > 2000:
        score += 2
    elif n > 800:
        score += 1
    if "```" in text:  # lida com bloco de código
        score += 1
    return score


def estimate_complexity(messages: list[dict]) -> str:
    """Retorna o nível de complexidade: 'low', 'medium' ou 'high' (por pontuação)."""
    score = complexity_score(messages)
    if score >= _HIGH_THRESHOLD:
        return "high"
    if score >= _MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _is_local(pk: _KeyLike) -> bool:
    spec = KNOWN_PROVIDERS.get(pk.provider)
    return bool(spec and spec.local) or is_local_url(pk.base_url)


def _tier_model(pk: _KeyLike, tier: str) -> str | None:
    if _is_local(pk):
        return pk.default_model
    tiers = PROVIDER_TIERS.get(pk.provider)
    if tiers:
        # mid ausente cai para premium; premium ausente cai para cheap.
        return tiers.get(tier) or tiers.get("premium") or tiers.get("cheap") or pk.default_model
    return pk.default_model


def _best_hosted(keys: list[_KeyLike], tier: str) -> tuple[_KeyLike, str] | None:
    """Provedor hospedado mais barato para o tier."""
    cands: list[tuple[float, _KeyLike, str]] = []
    for pk in keys:
        if _is_local(pk):
            continue
        model = _tier_model(pk, tier)
        if model:
            inp, out = price_of(model)
            cands.append((inp + out, pk, model))
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    return cands[0][1], cands[0][2]


def choose_route(complexity: str, provider_keys: list[_KeyLike]) -> Route | None:
    tier = {"high": "premium", "medium": "mid", "low": "cheap"}.get(complexity, "cheap")

    local_keys = [pk for pk in provider_keys if _is_local(pk) and pk.default_model]
    hosted_tier = _best_hosted(provider_keys, tier)
    hosted_premium = _best_hosted(provider_keys, "premium")
    baseline_model = (hosted_premium or hosted_tier or (None, None))[1]

    if local_keys:
        lpk = local_keys[0]
        escalation = None
        if hosted_tier:
            e_pk, e_model = hosted_tier
            escalation = Route(
                provider_key=e_pk,
                model=e_model,
                baseline_model=e_model,
                complexity=complexity,
                tier=tier,
                is_local=False,
            )
        return Route(
            provider_key=lpk,
            model=lpk.default_model,
            baseline_model=baseline_model or lpk.default_model,
            complexity=complexity,
            tier=tier,
            is_local=True,
            escalation=escalation,
        )

    if hosted_tier:
        h_pk, h_model = hosted_tier
        return Route(
            provider_key=h_pk,
            model=h_model,
            baseline_model=baseline_model or h_model,
            complexity=complexity,
            tier=tier,
            is_local=False,
        )

    return None
