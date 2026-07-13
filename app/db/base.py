"""Base declarativa compartilhada por todos os modelos ORM."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe base para os modelos SQLAlchemy."""
