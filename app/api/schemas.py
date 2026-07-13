"""Schemas Pydantic de request/response da API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MeResponse(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    plan: str


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key_prefix: str
    name: str
    created_at: datetime
    revoked_at: datetime | None = None


class ApiKeyCreated(ApiKeyInfo):
    # Chave completa em claro — retornada APENAS na criação.
    api_key: str
