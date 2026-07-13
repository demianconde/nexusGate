"""Testes da proteção anti-SSRF (validação de endpoint)."""

from __future__ import annotations

import pytest

from app.security.net import _is_blocked_ip, is_public_endpoint, validate_endpoint


def test_blocked_ips():
    assert _is_blocked_ip("127.0.0.1")
    assert _is_blocked_ip("169.254.169.254")  # metadata cloud
    assert _is_blocked_ip("10.0.0.5")
    assert _is_blocked_ip("192.168.1.10")
    assert not _is_blocked_ip("8.8.8.8")


def test_is_public_endpoint_localhost_blocked():
    assert not is_public_endpoint("http://localhost:11434/v1")
    assert not is_public_endpoint("http://127.0.0.1:8000")
    assert not is_public_endpoint("http://169.254.169.254/latest/meta-data")


def test_validate_endpoint_allow_private_bypass():
    # allow_private=True não levanta, mesmo em rede privada
    validate_endpoint("http://localhost:11434/v1", allow_private=True)


def test_validate_endpoint_blocks_private():
    with pytest.raises(ValueError):
        validate_endpoint("http://192.168.0.1/v1", allow_private=False)
