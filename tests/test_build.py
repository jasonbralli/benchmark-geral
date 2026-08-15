"""Testes para build_dashboard.py — parsing de MD e montagem do payload."""

import json
import re
import sys
from pathlib import Path

import pytest

# Garante que o projeto raiz está no path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# Importa funções do build (evita execução do main)
import build_dashboard as bd

# Amostra real do MD (Scorecard — Top 10 por AA Index)
SCORECARD_MD = """
## 📊 Scorecard — Top 10 por AA Index

Ranking ordenado pelo **Artificial Analysis Intelligence Index v4.1**.

| AA Rank | Modelo | AA Index | AA ★ | Tier |
|--------:|--------|---------:|:----:|:----:|
| 1 | `z-ai/glm-5.2` | 51 | ★★★★★ | S |
| 2 | `deepseek-ai/deepseek-v4-flash-0731` | 50 | ★★★★★ | S |
| 3 | `minimaxai/minimax-m3` | 44 | ★★★★☆ | S |
| N/D | `poolside/laguna-xs-2.1` | N/D | N/D | S |
"""


def test_split_row():
    cells = bd.split_row("| a | b | c |")
    assert cells == ["a", "b", "c"]


def test_split_row_no_pipes():
    assert bd.split_row("x | y | z") == ["x", "y", "z"]


def test_is_separator():
    assert bd.is_separator("|------|--------|")
    assert bd.is_separator("|:------|--------:|")
    assert bd.is_separator("---|-----")
    assert not bd.is_separator("| a | b |")
    assert not bd.is_separator("hello")


def test_normalize_model_key_strips_backticks():
    assert bd.normalize_model_key("`z-ai/glm-5.2`") == "z-ai/glm-5.2"


def test_normalize_model_key_strips_alias():
    """Remove backticks e parênteses de alias no formato real do MD."""
    assert bd.normalize_model_key("`deepseek-v4-pro` *(alias: flash)*") == "deepseek-v4-pro"


def test_parse_scorecard_numeric_fields():
    rows = bd.parse_scorecard(SCORECARD_MD)
    assert len(rows) == 4
    # GLM-5.2
    assert rows[0]["modelo"] == "`z-ai/glm-5.2`"
    assert rows[0]["aa_index"] == 51
    assert rows[0]["aa_stars"] == 5
    assert rows[0]["aa_rank"] is None  # preenchido depois pelo compute
    assert rows[0]["tier"] == "S"
    # Poolside N/D
    third = next(r for r in rows if "poolside" in r["modelo"])
    assert third["aa_index"] is None
    assert third["aa_stars"] is None


def test_parse_scorecard_stops_at_next_section():
    md = SCORECARD_MD + "\n## 📝 Metodologia\nSome text"
    rows = bd.parse_scorecard(md)
    assert len(rows) == 4  # não captura conteúdo da Metodologia


def test_format_context():
    assert bd.format_context(1_000_000) == "1M"
    assert bd.format_context(976_000) == "953K"
    assert bd.format_context(262144) == "256K"
    assert bd.format_context(131072) == "128K"
    assert bd.format_context(4096) == "4K"


def test_compute_aa_ranks_sets_rank_and_tier():
    tiers = {
        "S": [
            {"modelo": "`z-ai/glm-5.2`", "aa_index": 51, "aa_stars": 5},
            {"modelo": "`thinkingmachines/inkling`", "aa_index": 41, "aa_stars": 4},
        ],
        "A": [
            {"modelo": "`google/gemma-4-31b-it`", "aa_index": 30, "aa_stars": 3},
        ],
    }
    scorecard = [
        {"modelo": "`z-ai/glm-5.2`", "aa_index": 51, "aa_stars": 5, "aa_rank": None, "tier": ""},
        {"modelo": "`google/gemma-4-31b-it`", "aa_index": 30, "aa_stars": 3, "aa_rank": None, "tier": ""},
        {"modelo": "`unknown/model`", "aa_index": None, "aa_stars": None, "aa_rank": None, "tier": ""},
    ]
    bd.compute_aa_ranks(tiers, scorecard)

    # GLM é rank #1 (maior AA)
    assert scorecard[0]["aa_rank"] == 1
    assert scorecard[0]["tier"] == "S"
    # Gemma é rank #3 (menor)
    assert scorecard[1]["aa_rank"] == 3
    assert scorecard[1]["tier"] == "A"
    # Unknown sem aa_index não tem rank
    assert scorecard[2]["aa_rank"] is None


def test_tier_tables_from_pipeline_uses_display_name():
    from nim_pipeline.fetch import fetch_nvidia_models
    from nim_pipeline.filter import filter_frontier_models
    from nim_pipeline.enrich import enrich_models_with_aa

    # Inventário real do cache (se existir)
    cache = bd.BASE / "data" / "nvidia_models_raw.json"
    if not cache.exists():
        pytest.skip("cache ausente — teste de integração requer dados")
    raw = fetch_nvidia_models(use_cache=True)
    frontier = filter_frontier_models(raw)
    frontier = enrich_models_with_aa(frontier)
    tiers = bd.tier_tables_from_pipeline(frontier)

    assert set(tiers.keys()) == {"S", "A"}
    total = sum(len(v) for v in tiers.values())
    assert total == len(frontier)
    assert total > 0

    # DeepSeek deve exibir nome com sufixo 0731 (display_name)
    ds = next(m for m in tiers["S"] if "deepseek-v4-flash" in m["modelo"])
    assert "deepseek-v4-flash-0731" in ds["modelo"]


def test_assemble_payload_structure():
    tiers = {
        "S": [{"modelo": "`z-ai/glm-5.2`"}],
        "A": [{"modelo": "`google/gemma-4-31b-it`"}],
    }
    scorecard = [{"modelo": "`z-ai/glm-5.2`", "aa_rank": 1}]
    # frontier p/ aa_count
    frontier = [{"id": "z-ai/glm-5.2", "aa_index": 51}, {"id": "x/y", "aa_index": None}]
    payload = bd.assemble_payload("", frontier, tiers, scorecard)

    assert payload["meta"]["total_ranked"] == 2
    assert payload["meta"]["aa_count"] == 1
    assert "pipeline" in payload["meta"]
    assert set(payload["tiers"].keys()) == {"S", "A"}
    assert payload["scorecard"] == scorecard
    assert "aa_calibration" in payload["meta"]