"""Testes unitários para nim_pipeline.enrich — enriquecimento com AA Index."""

import pytest

from nim_pipeline.enrich import (
    AA_INTELLIGENCE_INDEX,
    aa_count,
    aa_to_stars,
    aa_url_for,
    enrich_models_with_aa,
)


def test_aa_to_stars_boundaries():
    """Calibração AA → estrelas respeita limites documentados."""
    assert aa_to_stars(50) == 5
    assert aa_to_stars(51) == 5
    assert aa_to_stars(49) == 4
    assert aa_to_stars(35) == 4
    assert aa_to_stars(34) == 3
    assert aa_to_stars(20) == 3
    assert aa_to_stars(19) == 2
    assert aa_to_stars(10) == 2
    assert aa_to_stars(9) == 1
    assert aa_to_stars(0) == 1
    assert aa_to_stars(None) is None


def test_aa_to_stars_negative_guard():
    """Input negativo cai no padrão 1★ (não quebra)."""
    assert aa_to_stars(-5) == 1


def test_aa_to_stars_float():
    """Scores float devem ser aceitos."""
    assert aa_to_stars(50.0) == 5
    assert aa_to_stars(44.5) == 4


def test_aa_count_counts_only_scored():
    """aa_count conta apenas modelos com index não-None."""
    models = [
        {"id": "a", "aa_index": 51, "aa_stars": 5},
        {"id": "b", "aa_index": None, "aa_stars": None},
        {"id": "c", "aa_index": 24, "aa_stars": 3},
    ]
    assert aa_count(models) == 2


def test_enrich_known_model():
    """Modelo conhecido no dicionário recebe AA Index interpretado."""
    models = [{"id": "z-ai/glm-5.2"}]
    out = enrich_models_with_aa(models)
    assert out[0]["aa_index"] == 51
    assert out[0]["aa_stars"] == 5
    assert out[0]["aa_url"].startswith("https://artificialanalysis.ai/")


def test_enrich_unknown_model():
    """Modelo desconhecido recebe index None + URL heurística."""
    models = [{"id": "nova-fabricante/model-x"}]
    out = enrich_models_with_aa(models)
    assert out[0]["aa_index"] is None
    assert out[0]["aa_stars"] is None
    # URL heurística: vendor/model → vendor-model
    assert "nova-fabricante-model-x" in out[0]["aa_url"]


def test_enrich_preserves_other_fields():
    """Enrich não sobrescreve campos pré-existentes não relacionados."""
    models = [{"id": "openai/gpt-oss-120b", "context": "128K", "reasoning": True}]
    out = enrich_models_with_aa(models)
    assert out[0]["context"] == "128K"
    assert out[0]["reasoning"] is True
    assert out[0]["aa_index"] == 24


def test_aa_intelligence_index_has_no_empty_keys():
    """Dicionário curado não contém chaves vazias."""
    for k, v in AA_INTELLIGENCE_INDEX.items():
        assert k
        assert "index" in v


def test_aa_url_for_known_returns_explicit():
    """Modelos com URL explícita no dicionário a usam."""
    assert (
        aa_url_for("z-ai/glm-5.2")
        == "https://artificialanalysis.ai/models/glm-5-2"
    )


def test_aa_url_for_unknown_uses_slug():
    """Modelo não mapeado usa slug kebab-case (vendor + nome)."""
    url = aa_url_for("abacusai/dracarys-llama-3.1-70b-instruct")
    assert url == "https://artificialanalysis.ai/models/abacusai-dracarys-llama-3.1-70b-instruct"


def test_aa_url_for_known_model_from_dict():
    """Modelo com URL explícita no dicionário a usa (sem slug heuristic)."""
    url = aa_url_for("thinkingmachines/inkling")
    # inkling está no dict com URL explícita
    assert url == "https://artificialanalysis.ai/models/inkling"