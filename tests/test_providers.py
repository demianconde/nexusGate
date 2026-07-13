"""Testes de registry/pricing de provedores (sem rede)."""

from __future__ import annotations

import pytest

from app.providers.registry import is_local_url, resolve_endpoint
from app.routing.pricing import cost_usd, infer_provider


def test_resolve_known_provider_default():
    fmt, base = resolve_endpoint("openai", None, None)
    assert fmt == "openai"
    assert base == "https://api.openai.com/v1"


def test_resolve_anthropic_format():
    fmt, base = resolve_endpoint("anthropic", None, None)
    assert fmt == "anthropic"


def test_resolve_custom_requires_base_url():
    with pytest.raises(ValueError):
        resolve_endpoint("custom", None, None)


def test_resolve_local_override():
    fmt, base = resolve_endpoint("ollama", None, "http://localhost:11434/v1/")
    assert base == "http://localhost:11434/v1"  # sem barra final


def test_is_local_url():
    assert is_local_url("http://localhost:11434/v1")
    assert is_local_url("http://192.168.0.10:1234/v1")
    assert not is_local_url("https://api.openai.com/v1")
    assert not is_local_url(None)


def test_infer_provider():
    assert infer_provider("gpt-4o-mini") == "openai"
    assert infer_provider("claude-3-5-sonnet") == "anthropic"
    assert infer_provider("qwen2.5-coder-32b-instruct") == "qwen"
    assert infer_provider("modelo-desconhecido") is None


def test_cost_usd_known_and_unknown():
    # 1M input @ 2.5 + 1M output @ 10 = 12.5
    assert cost_usd("gpt-4o", 1_000_000, 1_000_000) == 12.5
    assert cost_usd("modelo-local-qualquer", 1000, 1000) == 0.0
