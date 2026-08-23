"""Tests for benchmark_pipe.enrich"""
from __future__ import annotations

from benchmark_pipe.enrich import enrich_unified
from benchmark_pipe.normalize import UnifiedModel


def test_enrich_known_model():
    m = UnifiedModel(provider="nvidia", model_id="moonshotai/kimi-k3")
    enrich_unified([m])
    # API v4.1 (ago/26): 59.7; curado fallback: 57
    assert m.aa_index in (57, 59.7)


def test_enrich_unknown_model_yields_none():
    m = UnifiedModel(provider="nvidia", model_id="vendor/unknown-xyz")
    enrich_unified([m])
    assert m.aa_index is None


def test_enrich_is_case_insensitive():
    m = UnifiedModel(provider="nvidia", model_id="MOONSHOTAI/KIMI-K3")
    enrich_unified([m])
    assert m.aa_index in (57, 59.7)


def test_enrich_display_name_mapping():
    """deepseek-v4-flash sem sufixo deve herdar aa_index=50 + display_name."""
    m = UnifiedModel(provider="nvidia", model_id="deepseek-ai/deepseek-v4-flash")
    enrich_unified([m])
    assert m.aa_index in (50, 51.8)
    # display_name mapping is curated-only; API path keeps original model_id
    assert m.display_name in (None, "deepseek-ai/deepseek-v4-flash-0731", "deepseek-ai/deepseek-v4-flash")


def test_enrich_does_not_crash_on_prefix_match():
    """Chaves com backticks no dicionário são normalizadas."""
    m = UnifiedModel(provider="nvidia", model_id="`moonshotai/kimi-k3`")
    enrich_unified([m])
    assert m.aa_index in (57, 59.7)


def test_enrich_free_variant_inherits_aa():
    """z-ai/glm-5.2:free deve herdar AA=51 do canónico."""
    from benchmark_pipe.normalize import apply_canonical
    m = UnifiedModel(provider="openrouter", model_id="z-ai/glm-5.2:free")
    apply_canonical(m)
    enrich_unified([m])
    assert m.aa_index in (51, 52.6)


def test_enrich_tilde_alias_inherits_aa():
    """deepseek alias com vendor diferente também herda via canonical."""
    from benchmark_pipe.normalize import apply_canonical
    m = UnifiedModel(provider="openrouter", model_id="deepseek/deepseek-v4-flash:free")
    apply_canonical(m)
    enrich_unified([m])
    # canónico é deepseek-ai/deepseek-v4-flash-0731 -> curado 50, API 51.8
    assert m.aa_index in (50, 51.8)
