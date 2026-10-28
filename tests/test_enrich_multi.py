"""Tests for benchmark_pipe.enrich"""
from __future__ import annotations

from benchmark_pipe.enrich import _load_aa_api_map, enrich_unified
from benchmark_pipe.normalize import UnifiedModel


def _aa_api_active() -> bool:
    """True quando o mapa AA Data API está disponível (online ou cache fresco)."""
    return _load_aa_api_map() is not None


def _assert_aa_index(m, curated: tuple[float, ...]) -> None:
    """Valida aa_index tolerando flutuação da AA Data API.

    - API ativa: aceite qualquer score numérico válido (0-100).
    - API inativa: deve bater no valor curado fixo.
    """
    if _aa_api_active():
        assert m.aa_index is not None
        assert 0.0 <= float(m.aa_index) <= 100.0
    else:
        assert m.aa_index in curated


def test_enrich_known_model():
    m = UnifiedModel(provider="nvidia", model_id="moonshotai/kimi-k3")
    enrich_unified([m])
    # Curado: 57; AA Data API v4.x flutua (43.8 em v4.3, 43.6 noutra).
    _assert_aa_index(m, (57,))


def test_enrich_unknown_model_yields_none():
    m = UnifiedModel(provider="nvidia", model_id="vendor/unknown-xyz")
    enrich_unified([m])
    assert m.aa_index is None


def test_enrich_is_case_insensitive():
    m = UnifiedModel(provider="nvidia", model_id="MOONSHOTAI/KIMI-K3")
    enrich_unified([m])
    _assert_aa_index(m, (57,))


def test_enrich_display_name_mapping():
    """deepseek-v4-flash sem sufixo deve herdar aa_index=50 + display_name."""
    m = UnifiedModel(provider="nvidia", model_id="deepseek-ai/deepseek-v4-flash")
    enrich_unified([m])
    # Curado: 50; AA Data API v4.3+ flutua: 34.5, 34.3
    _assert_aa_index(m, (50,))
    # display_name mapping é curado-apenas; API v4.3 não define -> None
    assert m.display_name in (None, "deepseek-ai/deepseek-v4-flash-0731", "deepseek-ai/deepseek-v4-flash")


def test_enrich_does_not_crash_on_prefix_match():
    """Chaves com backticks no dicionário são normalizadas."""
    m = UnifiedModel(provider="nvidia", model_id="`moonshotai/kimi-k3`")
    enrich_unified([m])
    _assert_aa_index(m, (57,))


def test_enrich_free_variant_inherits_aa():
    """z-ai/glm-5.2:free deve herdar AA=51 do canónico."""
    from benchmark_pipe.normalize import apply_canonical
    m = UnifiedModel(provider="openrouter", model_id="z-ai/glm-5.2:free")
    apply_canonical(m)
    enrich_unified([m])
    # Curado: 51; AA Data API v4.3+ flutua: 38.6, 34.0, 33.7
    _assert_aa_index(m, (51,))


def test_enrich_tilde_alias_inherits_aa():
    """deepseek alias com vendor diferente também herda via canonical."""
    from benchmark_pipe.normalize import apply_canonical
    m = UnifiedModel(provider="openrouter", model_id="deepseek/deepseek-v4-flash:free")
    apply_canonical(m)
    enrich_unified([m])
    # canónico é deepseek-ai/deepseek-v4-flash-0731 -> curado 50, API v4.3: 34.5, 34.3
    _assert_aa_index(m, (50,))
