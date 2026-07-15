"""Type definitions for AegisFlow SDK (OpenAI-compatible)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class Choice:
    index: int
    message: ChatMessage | None = None
    delta: ChatMessage | None = None
    finish_reason: str | None = None


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatCompletion:
    id: str
    object: str = "chat.completion"
    model: str = ""
    choices: list[Choice] = field(default_factory=list)
    usage: Usage | None = None
    # AegisFlow-specific headers
    aegis_request_id: str | None = None
    aegis_model: str | None = None
    aegis_provider: str | None = None
    aegis_cache: str | None = None
    aegis_degraded: bool = False
    aegis_complexity: str | None = None
    aegis_routed: str | None = None
    aegis_local: bool = False


@dataclass
class ChatCompletionChunk:
    id: str | None = None
    object: str = "chat.completion.chunk"
    model: str = ""
    choices: list[Choice] = field(default_factory=list)
    # AegisFlow-specific headers (only on first chunk)
    aegis_request_id: str | None = None
    aegis_model: str | None = None
    aegis_provider: str | None = None
    aegis_cache: str | None = None
    aegis_degraded: bool = False
    aegis_complexity: str | None = None
    aegis_routed: str | None = None
    aegis_local: bool = False


def parse_chat_completion(data: dict, headers: dict) -> ChatCompletion:
    """Parse OpenAI-compatible response into ChatCompletion."""
    choices = []
    for c in data.get("choices", []):
        msg_data = c.get("message") or c.get("delta") or {}
        choices.append(Choice(
            index=c.get("index", 0),
            message=ChatMessage(
                role=msg_data.get("role", "assistant"),
                content=msg_data.get("content", ""),
            ) if "message" in c else None,
            delta=ChatMessage(
                role=msg_data.get("role", "assistant"),
                content=msg_data.get("content", ""),
            ) if "delta" in c else None,
            finish_reason=c.get("finish_reason"),
        ))

    usage_data = data.get("usage") or {}
    usage = Usage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
    ) if usage_data else None

    return ChatCompletion(
        id=data.get("id", ""),
        model=data.get("model", ""),
        choices=choices,
        usage=usage,
        aegis_request_id=headers.get("x-aegis-request-id"),
        aegis_model=headers.get("x-aegis-model"),
        aegis_provider=headers.get("x-aegis-provider"),
        aegis_cache=headers.get("x-aegis-cache"),
        aegis_degraded=headers.get("x-aegis-degraded") == "true",
        aegis_complexity=headers.get("x-aegis-complexity"),
        aegis_routed=headers.get("x-aegis-routed"),
        aegis_local=headers.get("x-aegis-local") == "true",
    )


def parse_chunk(data: dict, headers: dict) -> ChatCompletionChunk:
    """Parse SSE chunk into ChatCompletionChunk."""
    choices = []
    for c in data.get("choices", []):
        delta_data = c.get("delta") or {}
        choices.append(Choice(
            index=c.get("index", 0),
            delta=ChatMessage(
                role=delta_data.get("role", "assistant"),
                content=delta_data.get("content", ""),
            ),
            finish_reason=c.get("finish_reason"),
        ))

    return ChatCompletionChunk(
        id=data.get("id"),
        model=data.get("model", ""),
        choices=choices,
        aegis_request_id=headers.get("x-aegis-request-id"),
        aegis_model=headers.get("x-aegis-model"),
        aegis_provider=headers.get("x-aegis-provider"),
        aegis_cache=headers.get("x-aegis-cache"),
        aegis_degraded=headers.get("x-aegis-degraded") == "true",
        aegis_complexity=headers.get("x-aegis-complexity"),
        aegis_routed=headers.get("x-aegis-routed"),
        aegis_local=headers.get("x-aegis-local") == "true",
    )