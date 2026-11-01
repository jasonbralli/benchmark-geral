"""Tests for benchmark_pipe.reconcile — guarda de paridade catálogo live vs dashboard."""
from __future__ import annotations

from types import SimpleNamespace

from benchmark_pipe.reconcile import reconcile, format_report


def _m(provider: str, model_id: str, is_free: bool = False, ctx: int | None = None):
    m = SimpleNamespace()
    m.provider = provider
    m.model_id = model_id
    m.is_free = is_free
    m.context_k = ctx
    return m


def test_reconcile_missing_model_flagged():
    """Modelo que o Kilo lista ao vivo mas o dashboard não exibiu -> missing."""
    models = [_m("kilocode", "anthropic/claude-5", is_free=False)]
    live = {"kilocode": [
        {"id": "anthropic/claude-5", "pricing": {"prompt": "1", "completion": "2"}},
        {"id": "reflection/beam-free", "pricing": {"prompt": "0", "completion": "0"}},
    ]}
    rep = reconcile(models, live)
    assert rep["missing"] == 1
    assert "reflection/beam" in rep["by_provider"]["kilocode"]["missing"]


def test_reconcile_free_mismatch_flagged():
    """Preço 0 ao vivo mas dashboard não marcou FREE -> free_mismatch."""
    models = [_m("kilocode", "reflection/beam-free", is_free=False)]
    live = {"kilocode": [
        {"id": "reflection/beam-free", "pricing": {"prompt": "0", "completion": "0"}},
    ]}
    rep = reconcile(models, live)
    assert rep["free_mismatch"] == 1
    assert "reflection/beam" in rep["by_provider"]["kilocode"]["free_mismatch"]


def test_reconcile_free_ok_not_flagged():
    """Preço 0 ao vivo e dashboard marcou FREE -> sem free_mismatch."""
    models = [_m("kilocode", "reflection/beam-free", is_free=True)]
    live = {"kilocode": [
        {"id": "reflection/beam-free", "pricing": {"prompt": "0", "completion": "0"}},
    ]}
    rep = reconcile(models, live)
    assert rep["free_mismatch"] == 0
    assert rep["missing"] == 0


def test_reconcile_extra_model_flagged():
    """Dashboard exibe modelo que o provider removeu -> extra."""
    models = [_m("kilocode", "google/gemini-3-pro-image", is_free=False)]
    live = {"kilocode": []}
    rep = reconcile(models, live)
    assert rep["extra"] == 1
    assert "google/gemini-3-pro-image" in rep["by_provider"]["kilocode"]["extra"]


def test_reconcile_nvidia_resolved_not_missing():
    """Modelo NVIDIA resolvido por família e exibido no dashboard -> não é missing."""
    models = [
        _m("nvidia", "mistralai/mistral-large-4-0", is_free=True),
        _m("nvidia", "mistralai/mistral-large-4-1t-a52b", is_free=True, ctx=512),
    ]
    live = {"nvidia-nim": [{"id": "mistralai/mistral-large-4-1t-a52b"}]}
    rep = reconcile(models, live)
    assert rep["missing"] == 0


def test_reconcile_empty_live_no_crash():
    rep = reconcile([], {})
    assert rep["missing"] == 0
    assert rep["free_mismatch"] == 0
    assert rep["extra"] == 0


def test_format_report_lines():
    rep = {
        "missing": 2, "free_mismatch": 1, "extra": 1,
        "by_provider": {
            "kilocode": {
                "missing": ["reflection/beam", "inclusionai/ling-3.1-flash-1019"],
                "free_mismatch": ["reflection/beam"],
                "extra": ["google/gemini-3-pro-image"],
                "live_total": 384, "shown_total": 377,
                "live_free_total": 17, "shown_free_total": 10,
            }
        },
    }
    lines = format_report(rep)
    joined = "\n".join(lines)
    assert "kilocode" in joined
    assert "reflection/beam" in joined
    assert "2 do provider sem display" in joined or "1 com preço 0 fora" in joined

def test_reconcile_inventory_filter_ignores_live_only_models():
    """Modelos só no catálogo live (não no inventário Hermes) não contam como missing."""
    models = [_m("nous", "ornith/ornith-1.5-122b", is_free=True)]
    live = {"nous": [{"id": "ornith/ornith-1.5-122b", "pricing": {"prompt": "1", "completion": "2"}}] + [{"id": f"aion-labs/aion-{i}.0", "pricing": {"prompt": "1", "completion": "2"}} for i in range(5)]}
    # inventário Hermes só tem ornith
    inv = {"nous": {"ornith/ornith-1.5-122b"}}
    rep = reconcile(models, live, hermes_inventory=inv)
    assert rep["missing"] == 0
    assert rep["by_provider"]["nous"]["missing"] == []


def test_reconcile_nous_free_stripped_match():
    """Dashboard usa ID bare 'ornith/ornith-1.5-122b'; live usa ':free' -> não é free_mismatch."""
    models = [_m("nous", "ornith/ornith-1.5-122b", is_free=True)]
    live = {"nous": [{"id": "ornith/ornith-1.5-122b:free", "pricing": {"prompt": "0", "completion": "0"}}]}
    rep = reconcile(models, live, hermes_inventory={"nous": {"ornith/ornith-1.5-122b"}})
    assert rep["free_mismatch"] == 0
    assert rep["missing"] == 0

