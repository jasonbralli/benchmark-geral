"""Tests for benchmark_pipe.enrich"""
from __future__ import annotations

from benchmark_pipe.enrich import enrich_unified
from benchmark_pipe.normalize import UnifiedModel


def test_enrich_known_model():
    m = UnifiedModel(provider="nvidia", model_id="moonshotai/kimi-k3")
    enrich_unified([m])
    assert m.aa_index == 57


def test_enrich_unknown_model_yields_none():
    m = UnifiedModel(provider="nvidia", model_id="vendor/unknown-xyz")
    enrich_unified([m])
    assert m.aa_index is None


def test_enrich_is_case_insensitive():
    m = UnifiedModel(provider="nvidia", model_id="MOONSHOTAI/KIMI-K3")
    enrich_unified([m])
    assert m.aa_index == 57


def test_enrich_display_name_mapping():
    """deepseek-v4-flash sem sufixo deve herdar aa_index=50 + display_name."""
    m = UnifiedModel(provider="nvidia", model_id="deepseek-ai/deepseek-v4-flash")
    enrich_unified([m])
    assert m.aa_index == 50
    assert m.display_name == "deepseek-ai/deepseek-v4-flash-0731"


def test_enrich_does_not_crash_on_prefix_match():
    """Chaves com backticks no dicionário são normalizadas."""
    m = UnifiedModel(provider="nvidia", model_id="`moonshotai/kimi-k3`")
    enrich_unified([m])
    assert m.aa_index == 57
