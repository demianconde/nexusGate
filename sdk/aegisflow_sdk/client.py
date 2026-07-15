"""AegisFlow SDK client with circuit breaker, retry, and fail-open.

Features:
- OpenAI-compatible interface (drop-in replacement)
- Circuit breaker: stops calling gateway after N consecutive failures
- Automatic retry with exponential backoff
- Fail-open mode: bypasses gateway and calls provider directly if gateway is down
- Streaming support (SSE)
- AegisFlow-specific response headers exposed
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from .types import (
    ChatCompletion,
    ChatCompletionChunk,
    parse_chat_completion,
    parse_chunk,
)

# Default timeout for gateway requests (seconds)
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_CONNECT_TIMEOUT = 10.0

# Circuit breaker defaults
_DEFAULT_FAILURE_THRESHOLD = 5
_DEFAULT_RECOVERY_TIMEOUT = 30.0  # seconds before trying gateway again
_DEFAULT_HALF_OPEN_LIMIT = 1  # requests to test before closing circuit

# Retry defaults
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_BACKOFF_BASE = 0.5  # seconds


@dataclass
class CircuitState:
    failures: int = 0
    last_failure: float = 0.0
    open: bool = False
    half_open_count: int = 0


class CircuitBreaker:
    """Circuit breaker that opens after N consecutive failures.

    States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing) -> CLOSED
    """

    def __init__(
        self,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: float = _DEFAULT_RECOVERY_TIMEOUT,
        half_open_limit: int = _DEFAULT_HALF_OPEN_LIMIT,
    ) -> None:
        self._threshold = failure_threshold
        self._recovery = recovery_timeout
        self._half_open_limit = half_open_limit
        self._state = CircuitState()

    def before_request(self) -> bool:
        """Returns True if request should proceed, False if circuit is open."""
        if not self._state.open:
            return True
        if time.time() - self._state.last_failure >= self._recovery:
            self._state.open = False
            self._state.half_open_count = 0
            return True
        return False

    def on_success(self) -> None:
        self._state.failures = 0
        self._state.open = False
        self._state.half_open_count = 0

    def on_failure(self) -> None:
        self._state.failures += 1
        self._state.last_failure = time.time()
        if self._state.failures >= self._threshold:
            self._state.open = True

    @property
    def is_open(self) -> bool:
        return self._state.open


class ChatCompletions:
    """OpenAI-compatible chat completions interface."""

    def __init__(self, client: AegisFlow) -> None:
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        provider: str | None = None,
        stream: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        fallback: list[str] | None = None,
        fail_open: bool = False,
        timeout: float | None = None,
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]:
        """Create a chat completion.

        Args:
            model: Model name (e.g., "gpt-4o", "aegis-auto").
            messages: List of {"role": "...", "content": "..."} dicts.
            provider: Optional provider override.
            stream: If True, returns an iterator of chunks.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.
            fallback: Fallback chain ["provider:model", ...].
            fail_open: If True, bypasses gateway on failure and calls provider directly.
            timeout: Request timeout in seconds.

        Returns:
            ChatCompletion or Iterator[ChatCompletionChunk] if streaming.
        """
        return self._client._request(
            model=model,
            messages=messages,
            provider=provider,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
            fallback=fallback,
            fail_open=fail_open,
            timeout=timeout,
        )


class AegisFlow:
    """AegisFlow API client with circuit breaker and fail-open support.

    Args:
        api_key: Your AegisFlow API key (agf_...).
        base_url: AegisFlow API base URL.
        timeout: Request timeout in seconds (default 120).
        connect_timeout: Connection timeout in seconds (default 10).
        max_retries: Max retries on transient errors (default 2).
        circuit_failure_threshold: Consecutive failures before opening circuit (default 5).
        circuit_recovery_timeout: Seconds before testing gateway again (default 30).
        direct_provider_url: Fallback provider URL for fail-open mode.
        direct_provider_key: Fallback provider API key for fail-open mode.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.aegisflow.tech",
        timeout: float = _DEFAULT_TIMEOUT,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        circuit_failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        circuit_recovery_timeout: float = _DEFAULT_RECOVERY_TIMEOUT,
        direct_provider_url: str | None = None,
        direct_provider_key: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._connect_timeout = connect_timeout
        self._max_retries = max_retries
        self._direct_provider_url = direct_provider_url
        self._direct_provider_key = direct_provider_key
        self._circuit = CircuitBreaker(
            failure_threshold=circuit_failure_threshold,
            recovery_timeout=circuit_recovery_timeout,
        )
        self.chat = ChatCompletions(self)

    @property
    def circuit_open(self) -> bool:
        """Whether the circuit breaker is currently open."""
        return self._circuit.is_open

    def _request(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        provider: str | None = None,
        stream: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        fallback: list[str] | None = None,
        fail_open: bool = False,
        timeout: float | None = None,
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]:
        """Internal request method with circuit breaker and retry logic."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if provider:
            body["provider"] = provider
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if fallback:
            body["fallback"] = fallback
        if fail_open:
            body["fail_open"] = True

        req_timeout = timeout or self._timeout

        # Check circuit breaker
        if not self._circuit.before_request():
            if fail_open and self._direct_provider_url:
                return self._direct_call(model, messages, stream, req_timeout)
            raise AegisFlowError("Circuit breaker is open. Gateway is unavailable.")

        # Try gateway with retries
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    return self._stream_request(body, req_timeout)
                return self._sync_request(body, req_timeout)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    backoff = _DEFAULT_BACKOFF_BASE * (2 ** attempt)
                    time.sleep(backoff)
                    continue
            except httpx.HTTPStatusError as exc:
                # Don't retry client errors (4xx), only server errors (5xx)
                if exc.response.status_code >= 500 and attempt < self._max_retries:
                    last_error = exc
                    backoff = _DEFAULT_BACKOFF_BASE * (2 ** attempt)
                    time.sleep(backoff)
                    continue
                self._circuit.on_failure()
                raise AegisFlowError(
                    f"Gateway returned {exc.response.status_code}: {exc.response.text[:500]}"
                ) from exc

        # All retries exhausted
        self._circuit.on_failure()
        if fail_open and self._direct_provider_url:
            return self._direct_call(model, messages, stream, req_timeout)
        raise AegisFlowError(
            f"Gateway unavailable after {self._max_retries + 1} attempts"
        ) from last_error

    def _sync_request(self, body: dict, timeout: float) -> ChatCompletion:
        """Non-streaming request to gateway."""
        headers = {
            "x-api-key": self._api_key,
            "content-type": "application/json",
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{self._base_url}/v1/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            self._circuit.on_success()
            return parse_chat_completion(resp.json(), dict(resp.headers))

    def _stream_request(self, body: dict, timeout: float) -> Iterator[ChatCompletionChunk]:
        """Streaming request to gateway. Returns a generator."""
        headers = {
            "x-api-key": self._api_key,
            "content-type": "application/json",
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.send(
                client.build_request(
                    "POST",
                    f"{self._base_url}/v1/chat/completions",
                    headers=headers,
                    json=body,
                ),
                stream=True,
            )
            resp.raise_for_status()
            self._circuit.on_success()
            resp_headers = dict(resp.headers)
            first_chunk = True
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if first_chunk:
                    yield parse_chunk(data, resp_headers)
                    first_chunk = False
                else:
                    yield parse_chunk(data, {})

    def _direct_call(
        self, model: str, messages: list[dict[str, str]], stream: bool, timeout: float
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]:
        """Direct call to provider (fail-open bypass)."""
        if not self._direct_provider_url:
            raise AegisFlowError(
                "Fail-open requires direct_provider_url to be configured."
            )
        headers = {"content-type": "application/json"}
        if self._direct_provider_key:
            headers["authorization"] = f"Bearer {self._direct_provider_key}"

        body = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        if stream:
            return self._direct_stream(
                self._direct_provider_url, headers, body, timeout
            )

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{self._direct_provider_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return parse_chat_completion(data, {"x-aegis-degraded": "true"})

    def _direct_stream(
        self, url: str, headers: dict, body: dict, timeout: float
    ) -> Iterator[ChatCompletionChunk]:
        """Direct streaming call to provider."""
        with httpx.Client(timeout=timeout) as client:
            resp = client.send(
                client.build_request(
                    "POST",
                    f"{url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=body,
                ),
                stream=True,
            )
            resp.raise_for_status()
            degraded_headers = {"x-aegis-degraded": "true"}
            first_chunk = True
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if first_chunk:
                    yield parse_chunk(data, degraded_headers)
                    first_chunk = False
                else:
                    yield parse_chunk(data, {})


class AegisFlowError(Exception):
    """Base exception for AegisFlow SDK errors."""
    pass