"""Testes unitários para nim_pipeline.filter — critério Opção A."""

import pytest

from nim_pipeline.filter import (
    _context_ok,
    _is_recent_or_reasoning,
    _tool_call_ok,
    filter_by_tier,
    filter_frontier_models,
    is_excluded,
)


# ─────────────── is_excluded ───────────────

def test_is_excluded_embeddings():
    assert is_excluded({"family": "embedding", "id": "x/embed", "name": "Emb", "description": ""})


def test_is_excluded_vision_only():
    """Modelo sem text no output é excluído."""
    m = {
        "id": "nvidia/cosmos-predict1-5b",
        "family": "cosmos",
        "name": "Cosmos",
        "description": "video generation",
        "modalities": {"input": ["text", "video"], "output": ["video"]},
    }
    assert is_excluded(m)


def test_is_excluded_safety():
    assert is_excluded({"family": "nemotron-3-content-safety", "id": "nvidia/safety", "name": "Safety", "description": ""})


def test_is_not_excluded_llm():
    """LLM de chat genérico NÃO é excluído."""
    m = {
        "id": "z-ai/glm-5.2",
        "family": "glm",
        "name": "GLM-5.2",
        "description": "Open flagship GLM for coding agents",
        "modalities": {"input": ["text"], "output": ["text"]},
    }
    assert not is_excluded(m)


def test_is_not_excluded_multimodal_attachment():
    """Modelo multimodal com text no output NÃO é excluído."""
    m = {
        "id": "minimaxai/minimax-m3",
        "family": "minimax",
        "name": "MiniMax M3",
        "description": "multimodal agentic",
        "modalities": {"input": ["text", "image"], "output": ["text"]},
    }
    assert not is_excluded(m)


# ─────────────── _helpers ───────────────

def test_tool_call_ok():
    assert _tool_call_ok({"tool_call": True})
    assert not _tool_call_ok({"tool_call": False})
    assert not _tool_call_ok({})


def test_is_recent_or_reasoning():
    # reasoning=True passa mesmo se antigo
    assert _is_recent_or_reasoning({"reasoning": True, "release_date": "2023-01-01"})
    # recente sem reasoning passa
    assert _is_recent_or_reasoning({"reasoning": False, "release_date": "2026-06-01"})
    # antigo sem reasoning não passa
    assert not _is_recent_or_reasoning({"reasoning": False, "release_date": "2024-01-01"})


def test_context_ok():
    assert _context_ok({"limit": {"context": 131072}})
    assert _context_ok({"limit": {"context": 1000000}})
    assert not _context_ok({"limit": {"context": 8000}})
    assert not _context_ok({})


# ─────────────── filter_frontier_models ───────────────

def _llm(model_id, ctx=524288, reasoning=True, tool=True, release="2026-06-01", family="", modalities=None, desc=""):
    return {
        "id": model_id,
        "family": family or model_id.split("/")[-1],
        "name": model_id.split("/")[-1],
        "description": desc or "chat model",
        "modalities": modalities or {"input": ["text"], "output": ["text"]},
        "reasoning": reasoning,
        "tool_call": tool,
        "release_date": release,
        "limit": {"context": ctx},
    }


def test_filter_frontier_models_keeps_qualified():
    models = [
        _llm("z-ai/glm-5.2"),
        _llm("deepseek-ai/deepseek-v4-flash"),
        _llm("minimaxai/minimax-m3"),
    ]
    out = filter_frontier_models(models)
    assert len(out) == 3
    assert all(m.get("tier_heuristic") in ("S", "A") for m in out)


def test_filter_frontier_models_drops_old_small():
    models = [
        _llm("z-ai/glm-5.2"),
        _llm("old/model-2023", ctx=4096, reasoning=False, release="2023-01-01"),  # descartado (ctx + antigo)
        _llm("no-tool/model", tool=False),  # descartado (sem tool_call)
        _llm("embed/emb", family="embedding", modalities={"input": ["text"], "output": ["text"]}),  # family
    ]
    out = filter_frontier_models(models)
    assert len(out) == 1
    assert out[0]["id"] == "z-ai/glm-5.2"


def test_tier_heuristic_present():
    out = filter_frontier_models([_llm("z-ai/glm-5.2")])
    assert "tier_heuristic" in out[0]
    assert out[0]["tier_heuristic"] in ("S", "A")


def test_filter_by_tier():
    models = [
        _llm("z-ai/glm-5.2", ctx=1000000, reasoning=True, release="2026-06-13"),
        _llm("google/gemma-4-31b-it", ctx=250000, reasoning=True, release="2026-04-02"),
    ]
    model_list = filter_frontier_models(models)
    s = filter_by_tier(model_list, "S")
    a = filter_by_tier(model_list, "A")
    assert all(m.get("tier_heuristic") == "S" for m in s)
    assert all(m.get("tier_heuristic") == "A" for m in a)
    # glm-5.2 (1M ctx + recente) deve ser S; gemma-4 (menor) A
    assert any(m["id"] == "z-ai/glm-5.2" for m in s)
    assert any(m["id"] == "google/gemma-4-31b-it" for m in a)


def test_sorting_puts_S_first():
    models = [
        _llm("google/gemma-4-31b-it", ctx=250000),
        _llm("z-ai/glm-5.2", ctx=1000000),
        _llm("openai/gpt-oss-120b", ctx=131072),
    ]
    out = filter_frontier_models(models)
    # S(glm) deve vir antes de A(gemma, gpt-oss)
    assert out[0]["id"] == "z-ai/glm-5.2"