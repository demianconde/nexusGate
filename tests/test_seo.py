"""Testes de SEO/GEO: robots com crawlers de IA, sitemap e llms.txt."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_robots_allows_ai_crawlers():
    body = client.get("/robots.txt").text
    for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert f"User-agent: {bot}" in body
    assert "Sitemap: https://aegisflow.tech/sitemap.xml" in body
    assert "/llms.txt" in body


def test_sitemap_has_lastmod():
    body = client.get("/sitemap.xml").text
    assert "<lastmod>" in body
    assert "/artigos/tokenizacao-e-uso-otimizado-de-ia-para-empresas" in body


def test_llms_txt_served():
    resp = client.get("/llms.txt")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "# AegisFlow" in resp.text
    assert "BYOK" in resp.text
