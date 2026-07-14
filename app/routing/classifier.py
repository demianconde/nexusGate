"""Classificação de complexidade da tarefa para o roteamento (aegis-auto).

Dois modos, controlados por ``AEGIS_ROUTING_MODE``:
- ``heuristic`` (padrão): usa ``estimate_complexity`` (palavras-chave + tamanho, sem IA).
- ``classifier``: pergunta a um modelo leve (endpoint compatível com OpenAI) se a tarefa
  é ``high`` ou ``low``. Em qualquer falha (não configurado, timeout, erro), cai
  automaticamente na heurística — o roteamento nunca quebra por causa disso.

O endpoint do classificador é plugável (``AEGIS_CLASSIFIER_URL``/``_MODEL``/``_API_KEY``),
então dá para começar com um provedor barato e depois migrar para um modelo pequeno
self-hosted na nuvem, sem tocar no código.
"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.logging_config import get_logger
from app.routing.router import estimate_complexity

_log = get_logger("classifier")

_SYSTEM_PROMPT = (
    "Você classifica a COMPLEXIDADE de uma tarefa enviada a um modelo de código/IA. "
    "Responda APENAS com uma palavra: 'high', 'medium' ou 'low'. "
    "'high' = arquitetura, design de sistema, raciocínio complexo, matemática, "
    "migração ampla, decisões de infraestrutura. "
    "'medium' = implementar uma função/componente, corrigir um bug não trivial, "
    "integrar algo, refatorar um trecho. "
    "'low' = tarefas simples e rotineiras (regex, formatação, testes triviais, "
    "pequenos ajustes, perguntas diretas)."
)


async def _classify_with_llm(messages: list[dict]) -> str | None:
    """Chama o classificador leve. Retorna 'high'/'low' ou None se não deu para decidir."""
    s = get_settings()
    if not (s.classifier_url and s.classifier_model):
        return None

    text = " ".join(str(m.get("content", "")) for m in messages)[:4000]
    payload = {
        "model": s.classifier_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": 4,
    }
    headers = {"Content-Type": "application/json"}
    if s.classifier_api_key:
        headers["Authorization"] = f"Bearer {s.classifier_api_key}"

    url = f"{s.classifier_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            out = resp.json()["choices"][0]["message"]["content"].strip().lower()
    except Exception as exc:  # noqa: BLE001
        _log.warning("classifier_unavailable", error=str(exc))
        return None

    if "high" in out:
        return "high"
    if "medium" in out or "médi" in out:
        return "medium"
    if "low" in out:
        return "low"
    _log.warning("classifier_unexpected_output", output=out[:40])
    return None


async def classify_complexity(messages: list[dict]) -> str:
    """Retorna 'high' ou 'low'. Usa o classificador de IA se habilitado; senão heurística."""
    s = get_settings()
    if s.routing_mode == "classifier":
        result = await _classify_with_llm(messages)
        if result is not None:
            return result
        # fallback silencioso para a heurística
    return estimate_complexity(messages)
