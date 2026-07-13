"""Registry de provedores conhecidos + resolução de endpoint.

O gateway é agnóstico: qualquer LLM que fale o protocolo OpenAI (`format=openai`)
ou Anthropic (`format=anthropic`) funciona. Este registry só dá atalhos de
`base_url`/`format` para provedores populares; provedores "custom" e locais
(Ollama, LM Studio, vLLM, LocalAI, ...) usam a `base_url` informada pelo usuário.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    format: str  # "openai" | "anthropic"
    default_base_url: str | None
    requires_key: bool = True
    local: bool = False


# Endpoints OpenAI-compatíveis cobrem a maioria dos provedores e servidores locais.
KNOWN_PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec("openai", "OpenAI", "openai", "https://api.openai.com/v1"),
    "anthropic": ProviderSpec("anthropic", "Anthropic (Claude)", "anthropic", "https://api.anthropic.com"),
    "qwen": ProviderSpec(
        "qwen", "Qwen (DashScope)", "openai",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    ),
    "groq": ProviderSpec("groq", "Groq", "openai", "https://api.groq.com/openai/v1"),
    "mistral": ProviderSpec("mistral", "Mistral", "openai", "https://api.mistral.ai/v1"),
    "deepseek": ProviderSpec("deepseek", "DeepSeek", "openai", "https://api.deepseek.com/v1"),
    "together": ProviderSpec("together", "Together AI", "openai", "https://api.together.xyz/v1"),
    "openrouter": ProviderSpec("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1"),
    "google": ProviderSpec(
        "google", "Google Gemini (OpenAI-compat)", "openai",
        "https://generativelanguage.googleapis.com/v1beta/openai",
    ),
    # Locais — sem chave por padrão; base_url pode ser sobrescrita.
    "ollama": ProviderSpec(
        "ollama", "Ollama (local)", "ollama",
        "http://localhost:11434/v1", requires_key=False, local=True,
    ),
    "lmstudio": ProviderSpec(
        "lmstudio", "LM Studio (local)", "openai",
        "http://localhost:1234/v1", requires_key=False, local=True,
    ),
    "vllm": ProviderSpec(
        "vllm", "vLLM (local)", "openai",
        "http://localhost:8000/v1", requires_key=False, local=True,
    ),
    "localai": ProviderSpec(
        "localai", "LocalAI (local)", "openai",
        "http://localhost:8080/v1", requires_key=False, local=True,
    ),
    # Curinga: usuário fornece base_url e format.
    "custom": ProviderSpec(
        "custom", "Custom / outro endpoint", "openai", None, requires_key=False,
    ),
}


def is_local_url(url: str | None) -> bool:
    """Detecta se um endpoint aponta para a máquina local / rede privada."""
    if not url:
        return False
    u = url.lower()
    markers = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal", ".local")
    if any(m in u for m in markers):
        return True
    # faixas privadas comuns
    return any(seg in u for seg in ("//192.168.", "//10.", "//172."))


def resolve_endpoint(
    provider: str, format_override: str | None, base_url_override: str | None
) -> tuple[str, str]:
    """Retorna (format, base_url) resolvidos para um provider cadastrado.

    Levanta ValueError se não houver base_url (nem default nem override).
    """
    spec = KNOWN_PROVIDERS.get(provider)
    fmt = format_override or (spec.format if spec else "openai")
    base_url = base_url_override or (spec.default_base_url if spec else None)
    if not base_url:
        raise ValueError(
            f"Sem base_url para o provedor '{provider}'. Informe base_url ao cadastrar a chave."
        )
    return fmt, base_url.rstrip("/")
