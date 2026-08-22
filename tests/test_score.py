"""Tests for benchmark_pipe.score"""
from __future__ import annotations

from benchmark_pipe.normalize import UnifiedModel
from benchmark_pipe.score import benefit, cxb_score, score_models


# ---------- benefit monotonicidade ----------

def test_benefit_increases_with_ctx():
    base = UnifiedModel(provider="p", model_id="x", context_k=8).to_dict() and UnifiedModel(provider="p", model_id="x", context_k=8)
    big = UnifiedModel(provider="p", model_id="x", context_k=512)
    assert benefit(big) > benefit(base)


def test_benefit_tool_call_adds():
    a = UnifiedModel(provider="p", model_id="x", context_k=128)
    b = UnifiedModel(provider="p", model_id="x", context_k=128, tool_call=True)
    assert benefit(b) == benefit(a) + 15


def test_benefit_reasoning_adds():
    a = UnifiedModel(provider="p", model_id="x", context_k=128)
    b = UnifiedModel(provider="p", model_id="x", context_k=128, reasoning=True)
    assert benefit(b) == benefit(a) + 15


def test_benefit_caps_context_at_40():
    huge = UnifiedModel(provider="p", model_id="x", context_k=1_000_000)
    # ctx=1M em K => saturado em 40
    assert benefit(huge) >= 39.5


# ---------- cxb_score ----------

def test_free_beats_paid_same_capability():
    common = dict(context_k=128, tool_call=True, reasoning=True, multimodal=False, aa_index=40)
    free = UnifiedModel(provider="nvidia", model_id="a", is_free=True, **common)
    paid = UnifiedModel(provider="openrouter", model_id="b", is_free=False, price_in=2.0, **common)
    assert cxb_score(free) > cxb_score(paid)


def test_cheaper_paid_beats_expensive_same_capability():
    common = dict(context_k=128, tool_call=True, reasoning=False, multimodal=False, is_free=False)
    cheap = UnifiedModel(provider="o", model_id="c", price_in=0.5, **common)
    exp = UnifiedModel(provider="o", model_id="e", price_in=10.0, **common)
    assert cxb_score(cheap) > cxb_score(exp)


def test_free_price_zero_handled():
    m = UnifiedModel(provider="nvidia", model_id="x", context_k=256, is_free=True)
    s = cxb_score(m)
    assert s > 0 and s == benefit(m)  # cost=0, eps=1 → equal


# ---------- score_models split ----------

def test_score_models_splits_rankable():
    rankable = UnifiedModel(provider="nvidia", model_id="a", context_k=128)
    non = UnifiedModel(provider="gemini", model_id="b")  # all None
    r, n = score_models([rankable, non])
    assert len(r) == 1 and len(n) == 1
    assert r[0].cxb_score > 0
    assert n[0].cxb_score == 0.0


def test_score_models_orders_by_cxb_desc():
    a = UnifiedModel(provider="nvidia", model_id="low", context_k=8, is_free=True)
    b = UnifiedModel(provider="nvidia", model_id="hi", context_k=1024, tool_call=True, reasoning=True, is_free=True)
    r, _ = score_models([a, b])
    assert r[0].model_id == "hi"
    assert r[1].model_id == "low"
