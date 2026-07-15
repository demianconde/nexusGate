"""Cache semantico por tenant: reaproveita respostas de prompts similares.

Suporta dois backends:
- Redis Stack (RediSearch/HNSW): producao multi-instancia, cache compartilhado.
- In-memory (dict): fallback automatico quando Redis nao esta disponivel.

Interface get()/put() e a mesma independente do backend.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.cache.embedder import embed
from app.config import get_settings
from app.logging_config import get_logger
from app.redis_client import get_redis

_log = get_logger("cache")

# Dimensao do embedding (depende do modelo configurado; 768 e comum para
# modelos como nomic-embed-text). Ajustavel via config se necessario.
_VECTOR_DIM = 768
_INDEX_PREFIX = "aegis:cache:idx"
_DATA_PREFIX = "aegis:cache:data"


@dataclass
class CachedResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _Entry:
    embedding: list[float]
    response: CachedResponse
    ts: float


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)


def _redis_index_name(tenant_id: str) -> str:
    """Nome do indice vetorial no Redis para este tenant."""
    return f"{_INDEX_PREFIX}:{tenant_id}"


def _redis_key(tenant_id: str, entry_id: str) -> str:
    return f"{_DATA_PREFIX}:{tenant_id}:{entry_id}"


class RedisSemanticCache:
    """Cache semantico usando Redis Stack com RediSearch (HNSW)."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def _ensure_index(self, tenant_id: str) -> bool:
        """Cria o indice vetorial HNSW se nao existir."""
        idx_name = _redis_index_name(tenant_id)
        try:
            await self._redis.execute_command("FT.INFO", idx_name)
            return True
        except RedisError:
            pass
        try:
            await self._redis.execute_command(
                "FT.CREATE",
                idx_name,
                "ON", "JSON",
                "PREFIX", "1", f"{_DATA_PREFIX}:{tenant_id}:",
                "SCHEMA",
                "$.embedding", "AS", "embedding", "VECTOR", "FLAT", "6",
                "TYPE", "FLOAT32",
                "DIM", str(_VECTOR_DIM),
                "DISTANCE_METRIC", "COSINE",
                "$.ts", "AS", "ts", "NUMERIC",
                "$.model", "AS", "model", "TAG",
            )
            return True
        except RedisError as exc:
            _log.warning("redis_index_create_failed", tenant=tenant_id, error=str(exc))
            return False

    async def lookup(
        self, tenant_id: str, text: str
    ) -> tuple[CachedResponse | None, list[float] | None]:
        """Busca no Redis Stack por similaridade de cosseno via HNSW."""
        settings = get_settings()
        if not settings.cache_enabled:
            return None, None
        emb = await embed(text)
        if emb is None:
            return None, None

        if not await self._ensure_index(tenant_id):
            return None, emb

        idx_name = _redis_index_name(tenant_id)
        ttl = settings.cache_ttl_seconds
        now = time.time()
        query = (
            f"(@ts:[{now - ttl} inf])=>[KNN 1 @embedding $vec AS score]"
        )
        try:
            results = await self._redis.execute_command(
                "FT.SEARCH",
                idx_name,
                query,
                "PARAMS", "2", "vec", _vector_bytes(emb),
                "SORTBY", "score",
                "LIMIT", "0", "1",
                "RETURN", "2", "score", "$.response",
                "DIALECT", "2",
            )
        except RedisError as exc:
            _log.warning("redis_search_failed", tenant=tenant_id, error=str(exc))
            return None, emb

        if not results or results[0] == 0:
            return None, emb

        # results[0] = count, results[1] = key, results[2..] = fields
        score = 1.0 - float(results[2][1])  # COSINE distance -> similarity
        if score < settings.cache_threshold:
            return None, emb

        try:
            response_data = json.loads(results[3][1])
            cached = CachedResponse(
                content=response_data["content"],
                model=response_data["model"],
                provider=response_data["provider"],
                prompt_tokens=response_data["prompt_tokens"],
                completion_tokens=response_data["completion_tokens"],
            )
            return cached, emb
        except (json.JSONDecodeError, KeyError, IndexError):
            return None, emb

    async def store(
        self, tenant_id: str, embedding: list[float] | None, response: CachedResponse
    ) -> None:
        """Armazena a resposta no Redis Stack."""
        settings = get_settings()
        if embedding is None or not settings.cache_enabled or not response.content:
            return
        if not await self._ensure_index(tenant_id):
            return

        entry_id = f"{int(time.time() * 1000)}"
        key = _redis_key(tenant_id, entry_id)
        doc = {
            "embedding": embedding,
            "ts": time.time(),
            "model": response.model,
            "response": {
                "content": response.content,
                "model": response.model,
                "provider": response.provider,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            },
        }
        try:
            await self._redis.execute_command(
                "JSON.SET", key, "$", json.dumps(doc)
            )
            await self._redis.expire(key, settings.cache_ttl_seconds)
        except RedisError as exc:
            _log.warning("redis_store_failed", tenant=tenant_id, error=str(exc))


class InMemoryCache:
    """Cache em memoria (fallback quando Redis nao esta disponivel)."""

    def __init__(self) -> None:
        self._store: dict[str, list[_Entry]] = {}

    def _prune(self, tenant: str, now: float, ttl: int) -> None:
        items = self._store.get(tenant)
        if items:
            self._store[tenant] = [e for e in items if now - e.ts <= ttl]

    async def lookup(
        self, tenant_id: str, text: str
    ) -> tuple[CachedResponse | None, list[float] | None]:
        settings = get_settings()
        if not settings.cache_enabled:
            return None, None
        emb = await embed(text)
        if emb is None:
            return None, None
        now = time.time()
        self._prune(tenant_id, now, settings.cache_ttl_seconds)
        best: _Entry | None = None
        best_score = 0.0
        for entry in self._store.get(tenant_id, []):
            score = _cosine(emb, entry.embedding)
            if score > best_score:
                best_score, best = score, entry
        if best and best_score >= settings.cache_threshold:
            return best.response, emb
        return None, emb

    async def store(
        self, tenant_id: str, embedding: list[float] | None, response: CachedResponse
    ) -> None:
        settings = get_settings()
        if embedding is None or not settings.cache_enabled or not response.content:
            return
        entries = self._store.setdefault(tenant_id, [])
        entries.append(_Entry(embedding=embedding, response=response, ts=time.time()))
        overflow = len(entries) - settings.cache_max_entries
        if overflow > 0:
            del entries[:overflow]


class SemanticCache:
    """Cache hibrido: tenta Redis Stack primeiro, cai para memoria se indisponivel."""

    def __init__(self) -> None:
        self._redis: RedisSemanticCache | None = None
        self._memory = InMemoryCache()
        self._redis_available: bool | None = None

    async def _get_redis(self) -> RedisSemanticCache | None:
        """Lazy init do cache Redis. Retorna None se Redis nao estiver disponivel."""
        if self._redis_available is False:
            return None
        if self._redis is not None:
            return self._redis
        try:
            r = get_redis()
            await r.ping()
            self._redis = RedisSemanticCache(r)
            self._redis_available = True
            _log.info("cache_backend", backend="redis")
            return self._redis
        except Exception as exc:
            _log.warning("redis_unavailable_falling_back_to_memory", error=str(exc))
            self._redis_available = False
            return None

    async def lookup(
        self, tenant_id: str, text: str
    ) -> tuple[CachedResponse | None, list[float] | None]:
        redis = await self._get_redis()
        if redis is not None:
            return await redis.lookup(tenant_id, text)
        return await self._memory.lookup(tenant_id, text)

    async def store(
        self, tenant_id: str, embedding: list[float] | None, response: CachedResponse
    ) -> None:
        redis = await self._get_redis()
        if redis is not None:
            await redis.store(tenant_id, embedding, response)
        else:
            await self._memory.store(tenant_id, embedding, response)


_cache = SemanticCache()


def get_cache() -> SemanticCache:
    return _cache


def prompt_text(messages: list[dict]) -> str:
    """Texto para embutir: concatena as mensagens (foco na ultima do usuario)."""
    parts = [str(m.get("content", "")) for m in messages]
    return "\n".join(parts).strip()


def _vector_bytes(vec: list[float]) -> bytes:
    """Converte lista de floats para bytes (FLOAT32 little-endian)."""
    import struct
    return b"".join(struct.pack("<f", x) for x in vec)