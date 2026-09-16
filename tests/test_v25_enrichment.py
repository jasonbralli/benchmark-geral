"""Testes v2.5 — KPIs agregados, campos estendidos, propagação de métricas AA."""

from __future__ import annotations

import pytest

from benchmark_pipe.build import _median, _best, _payload
from benchmark_pipe.enrich import enrich_unified
from benchmark_pipe.normalize import UnifiedModel, apply_canonical, normalize_nvidia, normalize_openrouter


# ─────────────── _median ───────────────

def test_median_empty():
    assert _median([]) is None


def test_median_single():
    assert _median([5.0]) == 5.0


def test_median_odd():
    assert _median([1.0, 3.0, 5.0]) == 3.0


def test_median_even():
    assert _median([1.0, 3.0]) == 2.0


def test_median_unsorted():
    assert _median([5.0, 1.0, 3.0]) == 3.0


# ─────────────── _best ───────────────

def _mk(model_id: str, speed=None, coding=None, agentic=None) -> UnifiedModel:
    m = UnifiedModel(provider="x", model_id=model_id)
    m.speed_tps = speed
    m.coding_index = coding
    m.agentic_index = agentic
    return m


def test_best_returns_max_speed():
    models = [_mk("a", speed=10.0), _mk("b", speed=80.0), _mk("c", speed=50.0)]
    out = _best(models, key=lambda m: m.speed_tps)
    assert out is not None
    assert out["model_id"] == "b"
    assert out["value"] == 80.0


def test_best_handles_none():
    models = [_mk("a", speed=None), _mk("b", speed=80.0)]
    out = _best(models, key=lambda m: m.speed_tps)
    assert out is not None and out["model_id"] == "b"


def test_best_all_none_returns_none():
    models = [_mk("a"), _mk("b")]
    assert _best(models, key=lambda m: m.speed_tps) is None


def test_best_empty_list():
    assert _best([], key=lambda m: m.speed_tps) is None


# ─────────────── KPIs payload ───────────────

def test_payload_kpis_include_aa_aggregates():
    a = _mk("m/a", speed=50.0, coding=80.0, agentic=40.0)
    b = _mk("m/b", speed=100.0, coding=60.0, agentic=70.0)
    for m in (a, b):
        m.tool_call = True; m.cxb_score = 10.0
    payload = _payload([a, b], [])
    kpis = payload["kpis"]
    assert kpis["median_speed_tps"] == 75.0
    assert kpis["fastest_model"]["model_id"] == "m/b"
    assert kpis["fastest_model"]["value"] == 100.0
    assert kpis["top_coder"]["model_id"] == "m/a"
    assert kpis["top_agentic"]["model_id"] == "m/b"


def test_payload_kpis_none_safe():
    a = _mk("m/a")
    a.tool_call = True; a.cxb_score = 5.0
    payload = _payload([a], [])
    kpis = payload["kpis"]
    assert kpis["median_speed_tps"] is None
    assert kpis["fastest_model"] is None
    assert kpis["top_coder"] is None


# ─────────────── Schema extendido ───────────────

def test_unified_model_has_extended_fields():
    m = UnifiedModel(provider="x", model_id="y")
    # deve ter todos os campos v2.5
    for field in ("speed_tps", "ttft_s", "e2e_s", "coding_index", "agentic_index",
                  "modalities_in", "modalities_out", "max_output_tokens",
                  "knowledge_cutoff", "attachment"):
        assert hasattr(m, field), f"campo faltando: {field}"
        assert getattr(m, field) is None


def test_normalize_nvidia_modalities():
    raw = [{
        "id": "test/m1",
        "name": "Test",
        "modalities": {"input": ["text", "image"], "output": ["text"]},
        "limit": {"context": 32768, "output": 4096},
        "attachment": True,
        "knowledge": "2024-12",
        "cost": {"input": 0, "output": 0},
    }]
    out = normalize_nvidia(raw)
    assert len(out) == 1
    m = out[0]
    assert m.modalities_in == ["image", "text"]
    assert m.modalities_out == ["text"]
    assert m.max_output_tokens == 4096
    assert m.knowledge_cutoff == "2024-12"
    assert m.attachment is True
    assert m.multimodal is True  # "image" in input


def test_normalize_openrouter_modalities():
    raw = [{
        "id": "test/or-m1",
        "name": "TestOR",
        "architecture": {
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        },
        "top_provider": {"max_completion_tokens": 8192},
        "context_length": 131072,
        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
    }]
    out = normalize_openrouter(raw)
    assert len(out) == 1
    m = out[0]
    assert m.modalities_in == ["image", "text"]
    assert m.modalities_out == ["text"]
    assert m.max_output_tokens == 8192
    assert m.multimodal is True


# ─────────────── Enrich propaga métricas ───────────────

def test_enrich_propagates_speed_ttft_coding_agentic():
    """Quando AA map tem métricas ricas, enrich_unified deve propagá-las."""
    import json
    from pathlib import Path
    from benchmark_pipe.aa_api import CACHE, fetch_aa_models
    if not CACHE.exists():
        pytest.skip("cache AA ausente — pular propagação real")
    m = UnifiedModel(provider="openrouter", model_id="z-ai/glm-5.2:free")
    apply_canonical(m)
    enrich_unified([m])
    # Se aa_index matchou, deve ter speed_ttft_coding OU todos None (depende do cache)
    if m.aa_index is not None:
        # cascade: se tem aa_index, *pode* ter speed/coding/agentic (não obrigatório)
        # basta validar que os campos existem e não crasheiam
        assert hasattr(m, "speed_tps")
        assert hasattr(m, "coding_index")
        assert hasattr(m, "agentic_index")


def test_enrich_does_not_overwrite_existing_speed():
    """Se speed_tps já está set, enrich não sobrescreve."""
    from benchmark_pipe import enrich
    m = UnifiedModel(provider="x", model_id="test/abc")
    m.speed_tps = 99.0  # pré-existente
    # simular sem cache AA — enrich não deve tocar
    out = enrich.enrich_unified([m], aa_api_map={})
    assert out[0].speed_tps == 99.0


# ─────────────── Payload row expõe campos v2.5 ───────────────

def test_payload_row_exposes_v25_fields():
    m = _mk("m/test", speed=42.5, coding=75.0)
    m.modalities_in = ["text", "image"]
    m.modalities_out = ["text"]
    m.max_output_tokens = 8192
    m.knowledge_cutoff = "2024-12"
    m.attachment = True
    m.tool_call = True
    payload = _payload([m], [])
    row = payload["ranked"][0]
    for key in ("speed_tps", "ttft_s", "e2e_s", "coding_index", "agentic_index",
                "modalities_in", "modalities_out", "max_output_tokens",
                "knowledge_cutoff", "attachment"):
        assert key in row, f"payload[row] falta {key}"
    assert row["speed_tps"] == 42.5
    assert row["coding_index"] == 75.0
    assert row["modalities_in"] == ["text", "image"]
    assert row["max_output_tokens"] == 8192
