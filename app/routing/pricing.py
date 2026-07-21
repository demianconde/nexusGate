"""Catálogo de preços de LLMs + inferência de provedor.

Preços em **USD por 1 milhão de tokens** (input, output). Valores de referência —
mudam com frequência e devem ser revisados. O match é por **prefixo mais longo**,
então nomes datados (ex.: "gpt-4o-2024-08-06") caem no preço do modelo base.

Este catálogo é a fonte de verdade do custo: o resumo de uso recomputa o custo a
partir dos tokens, então expandir/ajustar o catálogo corrige valores retroativamente.
"""

from __future__ import annotations

# model (minúsculo) -> (usd_input_por_mtok, usd_output_por_mtok)
MODEL_PRICES: dict[str, tuple[float, float]] = {
    # ---------- OpenAI ----------
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1-mini": (1.10, 4.40),
    "o1": (15.00, 60.00),
    "o3-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    # gpt-5.x — preços de REFERÊNCIA (estimados); revisar com o pricing real do provedor.
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),  # base p/ gpt-5, gpt-5.1, gpt-5.2-pro… (match por prefixo)
    # ---------- Anthropic ----------
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-sonnet": (3.00, 15.00),
    "claude-haiku-4": (1.00, 5.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    # ---------- Google Gemini ----------
    "gemini-1.5-flash-8b": (0.0375, 0.15),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-3.1-flash-lite": (0.10, 0.40),
    "gemini-3-flash": (0.30, 2.50),
    "gemini-flash-lite": (0.10, 0.40),
    "gemini-flash": (0.30, 2.50),
    # ---------- Qwen (Alibaba) ----------
    "qwen-turbo": (0.05, 0.20),
    "qwen-plus": (0.40, 1.20),
    "qwen-max": (1.60, 6.40),
    "qwen2.5-coder-32b-instruct": (0.20, 0.60),
    "qwen2.5-72b-instruct": (0.35, 0.40),
    "qwen2.5-7b-instruct": (0.05, 0.10),
    # ---------- DeepSeek ----------
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    # ---------- Mistral ----------
    "mistral-large": (2.00, 6.00),
    "mistral-small": (0.20, 0.60),
    "mistral-nemo": (0.15, 0.15),
    "ministral-8b": (0.10, 0.10),
    "ministral-3b": (0.04, 0.04),
    "codestral": (0.30, 0.90),
    "pixtral-large": (2.00, 6.00),
    # ---------- Meta Llama (preços típicos Groq/Together) ----------
    "llama-3.3-70b": (0.59, 0.79),
    "llama-3.1-405b": (3.50, 3.50),
    "llama-3.1-70b": (0.59, 0.79),
    "llama-3.1-8b": (0.05, 0.08),
    "llama-3-70b": (0.59, 0.79),
    "llama-3-8b": (0.05, 0.08),
    # ---------- xAI Grok ----------
    "grok-2": (2.00, 10.00),
    "grok-beta": (5.00, 15.00),
    # ---------- Cohere ----------
    "command-r-plus": (2.50, 10.00),
    "command-r": (0.15, 0.60),
    # ---------- Groq (modelos abertos hospedados) ----------
    "mixtral-8x7b": (0.24, 0.24),
    "gemma2-9b": (0.20, 0.20),
}


def _match_price(model: str) -> tuple[float, float]:
    m = model.lower().split("/")[-1]  # tolera "models/gemini-..."
    if m in MODEL_PRICES:
        return MODEL_PRICES[m]
    best: tuple[float, float] | None = None
    best_len = -1
    for key, price in MODEL_PRICES.items():
        if m.startswith(key) and len(key) > best_len:
            best, best_len = price, len(key)
    return best if best is not None else (0.0, 0.0)


def price_of(model: str) -> tuple[float, float]:
    """Preço (input, output) por 1M tokens para um modelo (0,0 se desconhecido)."""
    return _match_price(model)


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = _match_price(model)
    return round((prompt_tokens * inp + completion_tokens * out) / 1_000_000, 6)


def catalog() -> list[dict]:
    """Catálogo para o frontend (ordenado por nome)."""
    return [
        {"model": name, "input_per_mtok": inp, "output_per_mtok": out}
        for name, (inp, out) in sorted(MODEL_PRICES.items())
    ]


def infer_provider(model: str) -> str | None:
    """Inferência simples de provedor a partir do nome do modelo."""
    m = model.lower()
    if m.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")):
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("qwen"):
        return "qwen"
    if m.startswith("deepseek"):
        return "deepseek"
    if m.startswith(("mistral", "mixtral", "ministral", "codestral", "pixtral")):
        return "mistral"
    if m.startswith("gemini"):
        return "google"
    if m.startswith(("grok",)):
        return "grok"
    if m.startswith("command"):
        return "cohere"
    return None
