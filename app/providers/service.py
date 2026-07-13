"""ProviderService: fala com qualquer LLM (OpenAI-compatível ou Anthropic).

- format="openai": funciona com OpenAI, Qwen, Groq, Together, DeepSeek, OpenRouter,
  Gemini (compat) e servidores locais (Ollama, LM Studio, vLLM, LocalAI, ...).
- format="anthropic": API Messages da Anthropic (Claude).

Expõe `complete()` (resposta única) e `stream()` (Server-Sent Events). A resposta é
sempre normalizada para o formato OpenAI, para o cliente ter uma interface única.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

_TIMEOUT = httpx.Timeout(300.0, connect=10.0)
_ANTHROPIC_VERSION = "2023-06-01"
_OLLAMA_NUM_CTX = 8192  # contexto fixo: modelos com 262k default estouram a memória


class ProviderError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


@dataclass
class Usage:
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ChatResult:
    model: str
    content: str
    usage: Usage
    raw: dict = field(default_factory=dict)


async def _post_retry(
    url: str, headers: dict, json_body: dict, retries: int = 1
) -> httpx.Response:
    """POST com 1 retry em erros transitórios (timeout / 5xx)."""
    delay = 0.6
    resp: httpx.Response | None = None
    for attempt in range(retries + 1):
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(url, headers=headers, json=json_body)
            except httpx.TimeoutException:
                if attempt < retries:
                    await asyncio.sleep(delay)
                    continue
                raise
        if resp.status_code >= 500 and attempt < retries:
            await asyncio.sleep(delay)
            continue
        return resp
    return resp  # type: ignore[return-value]


def _auth_headers(fmt: str, api_key: str) -> dict[str, str]:
    if fmt == "anthropic":
        h = {"anthropic-version": _ANTHROPIC_VERSION, "content-type": "application/json"}
        if api_key:
            h["x-api-key"] = api_key
        return h
    h = {"content-type": "application/json"}
    if api_key:
        h["authorization"] = f"Bearer {api_key}"
    return h


def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Anthropic separa o system do restante das mensagens."""
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    system = "\n".join(system_parts) if system_parts else None
    return system, rest


class ProviderService:
    def __init__(self, base_url: str, api_key: str, fmt: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.fmt = fmt

    # ---------- resposta única ----------
    async def complete(self, req: dict) -> ChatResult:
        if self.fmt == "anthropic":
            return await self._complete_anthropic(req)
        if self.fmt == "ollama":
            return await self._complete_ollama(req)
        return await self._complete_openai(req)

    # ---------- Ollama nativo (/api/chat): desliga thinking e fixa contexto ----------
    def _ollama_url(self) -> str:
        base = self.base_url
        if base.endswith("/v1"):
            base = base[:-3]
        return base.rstrip("/") + "/api/chat"

    def _ollama_body(self, req: dict, stream: bool) -> dict:
        options: dict = {"num_ctx": _OLLAMA_NUM_CTX}
        if req.get("max_tokens") is not None:
            options["num_predict"] = req["max_tokens"]
        if req.get("temperature") is not None:
            options["temperature"] = req["temperature"]
        return {
            "model": req["model"],
            "messages": req.get("messages", []),
            "stream": stream,
            "think": False,  # respostas diretas (sem gastar tokens "pensando")
            "options": options,
        }

    async def _complete_ollama(self, req: dict) -> ChatResult:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        resp = await _post_retry(self._ollama_url(), headers, self._ollama_body(req, False))
        if resp.status_code >= 400:
            raise ProviderError(resp.status_code, resp.text)
        data = resp.json()
        content = (data.get("message") or {}).get("content", "")
        model = data.get("model", req["model"])
        return ChatResult(
            model=model,
            content=content,
            usage=Usage(
                model=model,
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
            ),
            raw=data,
        )

    async def _stream_ollama(self, req: dict, usage_out: Usage) -> AsyncIterator[bytes]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream(
                "POST", self._ollama_url(), headers=headers, json=self._ollama_body(req, True)
            ) as resp:
                if resp.status_code >= 400:
                    text = (await resp.aread()).decode("utf-8", "replace")
                    raise ProviderError(resp.status_code, text)
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    model = obj.get("model", req["model"])
                    content = (obj.get("message") or {}).get("content", "")
                    if content:
                        chunk = {
                            "choices": [
                                {"index": 0, "delta": {"role": "assistant", "content": content}}
                            ],
                            "model": model,
                        }
                        yield f"data: {json.dumps(chunk)}\n\n".encode()
                    if obj.get("done"):
                        usage_out.model = model
                        usage_out.prompt_tokens = obj.get("prompt_eval_count", 0)
                        usage_out.completion_tokens = obj.get("eval_count", 0)
                        done = {
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                            "model": model,
                        }
                        yield f"data: {json.dumps(done)}\n\n".encode()
                        yield b"data: [DONE]\n\n"

    async def _complete_openai(self, req: dict) -> ChatResult:
        body = {**req, "stream": False}
        resp = await _post_retry(
            f"{self.base_url}/chat/completions",
            _auth_headers("openai", self.api_key),
            body,
        )
        if resp.status_code >= 400:
            raise ProviderError(resp.status_code, resp.text)
        data = resp.json()
        usage_raw = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        return ChatResult(
            model=data.get("model", req.get("model", "")),
            content=content,
            usage=Usage(
                model=data.get("model", req.get("model", "")),
                prompt_tokens=usage_raw.get("prompt_tokens", 0),
                completion_tokens=usage_raw.get("completion_tokens", 0),
            ),
            raw=data,
        )

    async def _complete_anthropic(self, req: dict) -> ChatResult:
        system, messages = _split_system(req.get("messages", []))
        body = {
            "model": req["model"],
            "messages": messages,
            "max_tokens": req.get("max_tokens", 1024),
        }
        if system:
            body["system"] = system
        if req.get("temperature") is not None:
            body["temperature"] = req["temperature"]
        resp = await _post_retry(
            f"{self.base_url}/v1/messages",
            _auth_headers("anthropic", self.api_key),
            body,
        )
        if resp.status_code >= 400:
            raise ProviderError(resp.status_code, resp.text)
        data = resp.json()
        content = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        )
        usage_raw = data.get("usage") or {}
        return ChatResult(
            model=data.get("model", req["model"]),
            content=content,
            usage=Usage(
                model=data.get("model", req["model"]),
                prompt_tokens=usage_raw.get("input_tokens", 0),
                completion_tokens=usage_raw.get("output_tokens", 0),
            ),
            raw=data,
        )

    # ---------- streaming (SSE) ----------
    async def stream(self, req: dict, usage_out: Usage) -> AsyncIterator[bytes]:
        """Gera bytes SSE no formato OpenAI. Preenche `usage_out` ao final."""
        if self.fmt == "anthropic":
            async for chunk in self._stream_anthropic(req, usage_out):
                yield chunk
        elif self.fmt == "ollama":
            async for chunk in self._stream_ollama(req, usage_out):
                yield chunk
        else:
            async for chunk in self._stream_openai(req, usage_out):
                yield chunk

    async def _stream_openai(self, req: dict, usage_out: Usage) -> AsyncIterator[bytes]:
        body = {**req, "stream": True, "stream_options": {"include_usage": True}}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=_auth_headers("openai", self.api_key),
                json=body,
            ) as resp:
                if resp.status_code >= 400:
                    text = (await resp.aread()).decode("utf-8", "replace")
                    raise ProviderError(resp.status_code, text)
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        payload = line[6:]
                        if payload.strip() != "[DONE]":
                            _capture_openai_usage(payload, usage_out)
                    yield (line + "\n\n").encode("utf-8")

    async def _stream_anthropic(self, req: dict, usage_out: Usage) -> AsyncIterator[bytes]:
        # Simplificação Fase 2: resolve via complete() e emite como SSE estilo OpenAI.
        result = await self._complete_anthropic(req)
        usage_out.model = result.usage.model
        usage_out.prompt_tokens = result.usage.prompt_tokens
        usage_out.completion_tokens = result.usage.completion_tokens
        first = {
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": result.content}}],
            "model": result.model,
        }
        yield f"data: {json.dumps(first)}\n\n".encode()
        done = {
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "model": result.model,
        }
        yield f"data: {json.dumps(done)}\n\n".encode()
        yield b"data: [DONE]\n\n"


def _capture_openai_usage(payload: str, usage_out: Usage) -> None:
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return
    if obj.get("model"):
        usage_out.model = obj["model"]
    usage = obj.get("usage")
    if usage:
        usage_out.prompt_tokens = usage.get("prompt_tokens", usage_out.prompt_tokens)
        usage_out.completion_tokens = usage.get("completion_tokens", usage_out.completion_tokens)


def openai_error_chunk(message: str) -> bytes:
    payload = {"error": {"message": message, "type": "provider_error"}}
    return f"data: {json.dumps(payload)}\n\n".encode()


def now_ms() -> int:
    return int(time.time() * 1000)
