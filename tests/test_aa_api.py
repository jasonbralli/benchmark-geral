"""Tests for benchmark_pipe.aa_api — AA Data API v2 bulk fetch + mapping."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from benchmark_pipe.aa_api import (
    AA_FREE_URL,
    _norm_slug,
    build_aa_index_map,
    fetch_aa_models,
    lookup_aa_index,
)


# ---------------------------------------------------------------------------
# _norm_slug
# ---------------------------------------------------------------------------

def test_norm_slug():
    assert _norm_slug("Kimi-K3") == "kimi-k3"
    assert _norm_slug("glm_5.2") == "glm-5-2"
    assert _norm_slug("a--b") == "a-b"
    assert _norm_slug("~deepseek/v4") == "deepseek/v4"


# ---------------------------------------------------------------------------
# build_aa_index_map
# ---------------------------------------------------------------------------

def test_build_aa_index_map_basic():
    raw = {
        "intelligence_index_version": "4.1",
        "data": [
            {"slug": "kimi-k3", "evaluations": {"artificial_analysis_intelligence_index": 59.7}},
            {"slug": "glm-5-2", "evaluations": {"artificial_analysis_intelligence_index": 52.6}},
            {"slug": "null-model", "evaluations": {"artificial_analysis_intelligence_index": None}},
        ],
    }
    m = build_aa_index_map(raw)
    assert m["kimi-k3"] == 59.7
    assert m["glm-5-2"] == 52.6
    assert "null-model" not in m


def test_build_aa_index_map_list_input():
    raw = [
        {"slug": "a", "evaluations": {"artificial_analysis_intelligence_index": 10}},
    ]
    m = build_aa_index_map(raw)  # type: ignore[arg-type]
    assert m["a"] == 10


def test_build_aa_index_map_keeps_max_on_dup():
    raw = {
        "data": [
            {"slug": "dup", "evaluations": {"artificial_analysis_intelligence_index": 10}},
            {"slug": "dup", "evaluations": {"artificial_analysis_intelligence_index": 20}},
        ]
    }
    m = build_aa_index_map(raw)
    assert m["dup"] == 20


# ---------------------------------------------------------------------------
# lookup_aa_index
# ---------------------------------------------------------------------------

def test_lookup_exact():
    aa_map = {"kimi-k3": 59.7, "glm-5-2": 52.6}
    assert lookup_aa_index("moonshotai/kimi-k3", "moonshotai/kimi-k3", aa_map) == 59.7


def test_lookup_free_variant():
    aa_map = {"glm-5-2": 52.6}
    # :free stripped via canonical, but lookup also handles raw model_id
    assert lookup_aa_index("z-ai/glm-5.2:free", "z-ai/glm-5.2", aa_map) == 52.6


def test_lookup_vendor_prefix_tolerant():
    # AA slug often omits vendor — nvidia/nemotron-3-super -> slug nvidia-nemotron-3-super-120b-a12b
    aa_map = {"nvidia-nemotron-3-super-120b-a12b": 25.7}
    assert lookup_aa_index("nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-super-120b-a12b", aa_map) == 25.7


def test_lookup_missing_returns_none():
    aa_map = {"kimi-k3": 59.7}
    assert lookup_aa_index("unknown/model", "unknown/model", aa_map) is None
    assert lookup_aa_index("a/b", "a/b", {}) is None


def test_lookup_prefix_fallback():
    # deepseek-v4-flash-0731 canonical vs slug deepseek-v4-flash
    aa_map = {"deepseek-v4-flash": 51.8}
    assert lookup_aa_index("deepseek-ai/deepseek-v4-flash-0731", "deepseek-ai/deepseek-v4-flash-0731", aa_map) == 51.8


# ---------------------------------------------------------------------------
# fetch_aa_models — mocked network
# ---------------------------------------------------------------------------

def _mock_resp(payload, remaining="99"):
    m = MagicMock()
    m.read.return_value = json.dumps(payload).encode()
    m.headers = {"X-Ratelimit-Remaining": remaining}
    m.__enter__ = lambda s: s
    m.__exit__ = lambda s, *a: False
    return m


def test_fetch_mocked_pagination(tmp_path: Path):
    cache = tmp_path / "aa.json"
    page1 = {
        "intelligence_index_version": "4.1",
        "pagination": {"has_more": True},
        "data": [{"slug": "m1", "evaluations": {"artificial_analysis_intelligence_index": 10}}],
    }
    page2 = {
        "intelligence_index_version": "4.1",
        "pagination": {"has_more": False},
        "data": [{"slug": "m2", "evaluations": {"artificial_analysis_intelligence_index": 20}}],
    }
    with patch("benchmark_pipe.aa_api.urlopen", side_effect=[_mock_resp(page1), _mock_resp(page2)]):
        out = fetch_aa_models(api_key="fake-key", use_cache=False, cache_path=cache)
    assert out is not None
    assert out["total"] == 2
    assert cache.exists()
    m = build_aa_index_map(out)
    assert m["m1"] == 10 and m["m2"] == 20


def test_fetch_uses_cache_when_fresh(tmp_path: Path):
    cache = tmp_path / "aa.json"
    cache.write_text(json.dumps({"intelligence_index_version": "4.1", "total": 1, "data": [{"slug": "x", "evaluations": {"artificial_analysis_intelligence_index": 1}}]}), encoding="utf-8")
    # should not call urlopen
    with patch("benchmark_pipe.aa_api.urlopen", side_effect=AssertionError("should not fetch")):
        out = fetch_aa_models(api_key="fake", use_cache=True, ttl_hours=24, cache_path=cache)
    assert out["data"][0]["slug"] == "x"


def test_fetch_no_key_returns_none(tmp_path: Path):
    cache = tmp_path / "aa.json"
    with patch("benchmark_pipe.aa_api._get_api_key", return_value=None):
        out = fetch_aa_models(api_key=None, use_cache=False, cache_path=cache)
    assert out is None


def test_fetch_401_fallback_to_stale(tmp_path: Path):
    from urllib.error import HTTPError
    cache = tmp_path / "aa.json"
    cache.write_text(json.dumps({"intelligence_index_version": "4.1", "total": 1, "data": [{"slug": "stale", "evaluations": {"artificial_analysis_intelligence_index": 9}}]}), encoding="utf-8")
    err = HTTPError(AA_FREE_URL, 401, "Unauthorized", {}, None)  # type: ignore[arg-type]
    with patch("benchmark_pipe.aa_api.urlopen", side_effect=err):
        out = fetch_aa_models(api_key="bad", use_cache=False, cache_path=cache)
    assert out is not None and out["data"][0]["slug"] == "stale"
