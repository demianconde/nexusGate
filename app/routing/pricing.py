"""Catálogo de preços (parcial) e inferência de provedor.

Preços em USD por 1 milhão de tokens (input, output). Serve para estimar o custo
gravado em `usage_logs`. É um catálogo aberto: modelos desconhecidos custam 0 e o
cálculo de economia real será refinado na Fase 3 (roteamento por custo).
"""

from __future__ import annotations

# model -> (usd_input_per_mtok, usd_output_per_mtok)
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "o3-mini": (1.1, 4.4),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.8, 4.0),
    "claude-3-opus": (15.0, 75.0),
    "qwen-max": (1.6, 6.4),
    "qwen-plus": (0.4, 1.2),
    "qwen2.5-coder-32b-instruct": (0.2, 0.6),
    "deepseek-chat": (0.27, 1.1),
    "mistral-large-latest": (2.0, 6.0),
}


def _match_price(model: str) -> tuple[float, float]:
    if model in MODEL_PRICES:
        return MODEL_PRICES[model]
    # match por prefixo (ex.: "gpt-4o-2024-..." → "gpt-4o")
    for key, price in MODEL_PRICES.items():
        if model.startswith(key):
            return price
    return (0.0, 0.0)


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = _match_price(model)
    return round((prompt_tokens * inp + completion_tokens * out) / 1_000_000, 6)


def infer_provider(model: str) -> str | None:
    """Inferência simples de provedor a partir do nome do modelo."""
    m = model.lower()
    if m.startswith(("gpt-", "o1", "o3", "chatgpt")):
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("qwen"):
        return "qwen"
    if m.startswith("deepseek"):
        return "deepseek"
    if m.startswith("mistral") or m.startswith("mixtral"):
        return "mistral"
    if m.startswith("gemini"):
        return "google"
    return None
