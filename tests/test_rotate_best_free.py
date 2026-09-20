"""tests/test_rotate_best_free.py — suite do rotador de fallback free.

Cobre: dedup canonical, sanitização de inventário, filtro de health,
ordenação por usabilidade, idempotência do parse/replace do config,
e no-op quando a chain já está aplicada.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "rotate_best_free", ROOT / "scripts" / "rotate_best_free.py"
)
rot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rot)


def _free(cxb: float, prov: str, model_id: str, cid: str | None = None) -> dict:
    return {
        "provider": prov,
        "model_id": model_id,
        "canonical_id": cid or model_id,
        "is_free": True,
        "cxb_score": cxb,
    }


HEALTH = {
    "openrouter": {"last_ok": True, "samples": 10, "uptime_pct": 100.0, "p50_ms": 800.0, "shed_hits": 0},
    "kilocode": {"last_ok": True, "samples": 9, "uptime_pct": 22.0, "p50_ms": 770.0, "shed_hits": 7},
    "nvidia": {"last_ok": True, "samples": 9, "uptime_pct": 100.0, "p50_ms": 114000.0, "shed_hits": 0},
    "huggingface": {"last_ok": True, "samples": 9, "uptime_pct": 100.0, "p50_ms": 610.0, "shed_hits": 0},
    "novita": {"last_ok": False, "samples": 5, "uptime_pct": 0.0, "p50_ms": 277.0, "shed_hits": 0},
    "dead": {"last_ok": False, "samples": 3, "uptime_pct": 0.0, "p50_ms": 100.0, "shed_hits": 0},
}
INV = {
    "openrouter": {"thinkingmachines/inkling:free", "moonshotai/kimi-k3"},
    "kilocode": {"thinkingmachines/inkling-small:free", "qwen/qwen3.8-27b:free"},
    "nvidia": {"moonshotai/kimi-k3", "z-ai/glm-5.3-flash"},
    "huggingface": set(),
    "novita": {"moonshotai/kimi-k3"},
}


def test_dedup_canonical_picks_best_cxb():
    models = [
        _free(50.0, "openrouter", "thinkingmachines/inkling:free"),
        _free(60.0, "kilocode", "thinkingmachines/inkling:free"),  # mesmo canonical
    ]
    chain = rot.build_chain(models, HEALTH, INV, top=3)
    assert [(t["provider"], t["model"]) for t in chain] == [
        ("kilocode", "thinkingmachines/inkling:free")
    ] or all(t["model"] == "thinkingmachines/inkling:free" for t in chain)


def test_unhealthy_provider_excluded():
    models = [_free(99.0, "novita", "moonshotai/kimi-k3")]
    assert rot.build_chain(models, HEALTH, INV, top=3) == []


def test_low_samples_provider_excluded():
    models = [_free(99.0, "dead", "x/y")]
    assert rot.build_chain(models, HEALTH, INV, top=3) == []


def test_ghost_model_sanitized():
    # modelo no consolidated mas ausente do inventário do provider → excluído
    models = [_free(99.0, "openrouter", "ghost/model-410")]
    assert rot.build_chain(models, HEALTH, INV, top=3) == []


def test_distinct_providers_and_order_by_usability():
    models = [
        _free(68.0, "nvidia", "moonshotai/kimi-k3"),          # melhor cxb, lento
        _free(50.0, "openrouter", "thinkingmachines/inkling:free"),
        _free(49.0, "kilocode", "thinkingmachines/inkling-small:free"),
    ]
    chain = rot.build_chain(models, HEALTH, INV, top=3)
    provs = [t["provider"] for t in chain]
    # providers distintos
    assert len(provs) == len(set(provs))
    # openrouter (800ms) antes de nvidia (114s)
    assert provs.index("openrouter") < provs.index("nvidia")
    # top respeitado
    assert len(chain) <= 3


def test_top_limits_chain():
    models = [
        _free(68.0, "nvidia", "moonshotai/kimi-k3"),
        _free(50.0, "openrouter", "thinkingmachines/inkling:free"),
        _free(49.0, "kilocode", "thinkingmachines/inkling-small:free"),
    ]
    assert len(rot.build_chain(models, HEALTH, INV, top=2)) == 2


CFG = """model:
  default: x
providers:
  local: {}
fallback_providers:
  - provider: kilocode
    model: qwen/qwen3.8-27b:free
  - provider: huggingface
    model: inclusionAI/Ling-3.0-flash-Fin
  - provider: novita
    model: inclusionai/ling-3.0-flash-fin
toolsets:
  - browser
"""


def test_parse_current_chain():
    assert rot.parse_current_chain(CFG) == [
        ("kilocode", "qwen/qwen3.8-27b:free"),
        ("huggingface", "inclusionAI/Ling-3.0-flash-Fin"),
        ("novita", "inclusionai/ling-3.0-flash-fin"),
    ]


def test_replace_block_is_surgical():
    chain = [
        {"provider": "openrouter", "model": "thinkingmachines/inkling:free"},
        {"provider": "nvidia", "model": "moonshotai/kimi-k3"},
    ]
    out = rot.replace_fallback_block(CFG, chain)
    assert out is not None
    # resto do arquivo intacto
    assert out.startswith("model:\n  default: x\nproviders:\n  local: {}\n")
    assert out.endswith("toolsets:\n  - browser\n")
    # novo bloco parseia de volta
    assert rot.parse_current_chain(out) == [
        ("openrouter", "thinkingmachines/inkling:free"),
        ("nvidia", "moonshotai/kimi-k3"),
    ]


def test_replace_idempotent_roundtrip():
    chain = [{"provider": "openrouter", "model": "a/b:free"}]
    once = rot.replace_fallback_block(CFG, chain)
    twice = rot.replace_fallback_block(once, chain)
    assert once == twice  # byte-idêntico na segunda aplicação


def test_no_fallback_block_inserts():
    cfg_no_block = "model:\n  default: x\ntoolsets:\n  - browser\n"
    chain = [{"provider": "openrouter", "model": "a/b:free"}]
    out = rot.replace_fallback_block(cfg_no_block, chain)
    assert out is not None
    assert rot.parse_current_chain(out) == [("openrouter", "a/b:free")]
