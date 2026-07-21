"""Testes do roteador aegis-auto (local-first + escalonamento)."""

from __future__ import annotations

from dataclasses import dataclass

from app.routing.router import choose_route, estimate_complexity


@dataclass
class FakeKey:
    provider: str
    base_url: str | None = None
    default_model: str | None = None


def test_estimate_complexity():
    # 3 níveis por pontuação: baixa / média / alta.
    assert estimate_complexity([{"content": "some um mais um"}]) == "low"
    assert (
        estimate_complexity([{"content": "Projete a arquitetura de um sistema distribuído"}])
        == "high"
    )
    # médio: feature com framework (React + Hooks), sem sinal de alta complexidade.
    assert (
        estimate_complexity([{"content": "Crie um componente em React usando Hooks"}]) == "medium"
    )


def test_simple_prefers_local():
    keys = [
        FakeKey("openai"),
        FakeKey("ollama", "http://localhost:11434/v1", "qwen3.5:4b"),
    ]
    route = choose_route("low", keys)
    assert route.is_local
    assert route.model == "qwen3.5:4b"
    # escala para o hospedado mais barato (cheap tier)
    assert route.escalation is not None
    assert route.escalation.model == "gpt-4o-mini"


def test_complex_still_prefers_local_then_escalates_to_premium():
    keys = [
        FakeKey("openai"),
        FakeKey("ollama", "http://localhost:11434/v1", "qwen3.5:9b"),
    ]
    route = choose_route("high", keys)
    assert route.is_local  # local primeiro mesmo na tarefa complexa
    assert route.model == "qwen3.5:9b"
    assert route.escalation.model == "gpt-4o"  # escala p/ premium hospedado


def test_no_local_uses_cheapest_hosted_for_simple():
    keys = [FakeKey("openai"), FakeKey("google")]
    route = choose_route("low", keys)
    assert not route.is_local
    # gemini-3.1-flash-lite (0.10/0.40=0.5) é mais barato que gpt-4o-mini (0.15/0.60=0.75)
    assert route.model == "gemini-3.1-flash-lite"
    assert route.escalation is None


def test_no_local_uses_premium_for_complex():
    keys = [FakeKey("google")]
    route = choose_route("high", keys)
    assert route.model == "gemini-2.5-pro"


def test_none_when_no_eligible():
    # local sem default_model e nenhum hospedado
    route = choose_route("low", [FakeKey("ollama", "http://localhost:11434/v1", None)])
    assert route is None


def test_openrouter_routes_by_tier():
    # OpenRouter mapeado em PROVIDER_TIERS: roteia por tier (custo→qualidade).
    keys = [FakeKey("openrouter", "https://openrouter.ai/api/v1", "openai/gpt-5-mini")]
    assert choose_route("low", keys).model == "openai/gpt-5-nano"
    assert choose_route("medium", keys).model == "openai/gpt-5-mini"
    assert choose_route("high", keys).model == "anthropic/claude-opus-4.7"
