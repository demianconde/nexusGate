"""Endpoint de proxy de LLM (plano de dados, auth por x-api-key).

Resolve a credencial BYOK do tenant, chama o provedor real (qualquer LLM/local),
faz streaming SSE e grava o uso em usage_logs.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import get_api_tenant
from app.crypto import decrypt_secret
from app.db.models import ProviderKey, Tenant
from app.db.session import get_db
from app.providers.service import (
    ProviderError,
    ProviderService,
    Usage,
    now_ms,
    openai_error_chunk,
)
from app.routing.pricing import cost_usd, infer_provider
from app.usage import record_usage

from .schemas import ChatCompletionRequest

router = APIRouter(prefix="/v1", tags=["proxy"])


async def _resolve_provider_key(
    db: AsyncSession, tenant_id: uuid.UUID, provider: str
) -> ProviderKey:
    result = await db.execute(
        select(ProviderKey)
        .where(ProviderKey.tenant_id == tenant_id, ProviderKey.provider == provider)
        .order_by(ProviderKey.created_at.desc())
    )
    record = result.scalars().first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nenhuma credencial cadastrada para o provedor '{provider}'. "
            f"Cadastre uma em /v1/admin/provider-keys.",
        )
    return record


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    tenant: Tenant = Depends(get_api_tenant),
    db: AsyncSession = Depends(get_db),
):
    if body.model == "nexus-auto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Roteamento automático (nexus-auto) chega na Fase 3. Especifique um modelo.",
        )

    provider = body.provider or infer_provider(body.model)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível inferir o provedor pelo modelo. Envie o campo 'provider'.",
        )

    record = await _resolve_provider_key(db, tenant.id, provider)
    api_key = decrypt_secret(record.ciphertext, record.nonce, record.dek_wrapped)
    service = ProviderService(record.base_url, api_key, record.format)

    upstream: dict = {"model": body.model, "messages": [m.model_dump() for m in body.messages]}
    if body.max_tokens is not None:
        upstream["max_tokens"] = body.max_tokens
    if body.temperature is not None:
        upstream["temperature"] = body.temperature

    request_id = uuid.uuid4().hex
    tenant_id = tenant.id

    if body.stream:
        usage = Usage()

        async def event_stream():
            started = now_ms()
            try:
                async for chunk in service.stream(upstream, usage):
                    yield chunk
            except ProviderError as exc:
                yield openai_error_chunk(f"[{exc.status_code}] {exc.message[:300]}")
            finally:
                model_used = usage.model or body.model
                await record_usage(
                    tenant_id=tenant_id,
                    request_id=request_id,
                    provider=provider,
                    model_requested=body.model,
                    model_used=model_used,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cost_usd=cost_usd(model_used, usage.prompt_tokens, usage.completion_tokens),
                    latency_ms=now_ms() - started,
                )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"x-nexus-request-id": request_id, "cache-control": "no-cache"},
        )

    # Resposta única
    started = now_ms()
    try:
        result = await service.complete(upstream)
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro do provedor [{exc.status_code}]: {exc.message[:300]}",
        ) from exc

    await record_usage(
        tenant_id=tenant_id,
        request_id=request_id,
        provider=provider,
        model_requested=body.model,
        model_used=result.usage.model or body.model,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
        cost_usd=cost_usd(
            result.usage.model or body.model,
            result.usage.prompt_tokens,
            result.usage.completion_tokens,
        ),
        latency_ms=now_ms() - started,
    )

    payload = result.raw or {
        "id": request_id,
        "object": "chat.completion",
        "model": result.model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": result.content},
             "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
        },
    }
    return JSONResponse(payload, headers={"x-nexus-request-id": request_id})
