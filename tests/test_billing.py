"""Testes dos planos de billing."""

from __future__ import annotations

from app.billing.plans import PLANS, get_plan


def test_plans_exist():
    assert set(PLANS) == {"free", "pro", "enterprise"}


def test_get_plan_default_and_fallback():
    assert get_plan(None).key == "free"
    assert get_plan("inexistente").key == "free"
    assert get_plan("pro").price_brl == 249.0


def test_limits_increase_with_tier():
    assert PLANS["free"].rpm < PLANS["pro"].rpm < PLANS["enterprise"].rpm
    assert PLANS["free"].monthly_quota < PLANS["enterprise"].monthly_quota
