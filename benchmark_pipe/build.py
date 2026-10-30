"""benchmark_pipe.build
======================

Gera index.html consolidado multi-provider via template_consolidado.html
(marker //CONSOLIDATED_DATA//). Idempotente: lê template, injeta, escreve OUT.

Output = `index.html` (canónico desde v2.6.5) — arquivo único servido pelo
GitHub Pages. Substituiu `dashboard.html` (22/08/2026→18/09/2026).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from nim_pipeline.enrich import aa_to_stars  # noqa: E402

from .normalize import UnifiedModel  # noqa: E402

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
TEMPLATE = ROOT / "template_consolidado.html"
OUTPUT = ROOT / "index.html"
MARKER = "//CONSOLIDATED_DATA//"
# provider_health.json agora vive em benchmark-providers (repo separado).
# Env var PROVIDERS_DATA_DIR permite override; default = pasta irma benchmark_providers/data.
_PROVIDERS_DATA = Path(
    __import__("os").environ.get(
        "PROVIDERS_DATA_DIR",
        str(ROOT.parent / "benchmark-providers" / "data"),
    )
)
HEALTH_FILE = _PROVIDERS_DATA / "provider_health.json"


def _load_provider_health() -> dict | None:
    """Le provider_health.json (gerado por benchmark_providers.probe_health).
    Retorna None se ausente/invalido — NUNCA quebra o build."""
    if not HEALTH_FILE.exists():
        return None
    try:
        return json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_liveness() -> dict[str, str]:
    """Le data/liveness_daily.json e mapeia model_id -> 'ok'|'dead'|None.

    Best-effort: ausente/ilegivel = todos None (dashboard nao quebra).
    So modelos do catálogo NIM testados pelo liveness recebem marca.
    """
    p = ROOT / "data" / "liveness_daily.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for r in d.get("results", []) or []:
        mid = r.get("model_id")
        if not mid:
            continue
        out[mid] = "ok" if r.get("alive") else "dead"
    return out


def _median(xs: list[float]) -> float | None:
    """Mediana de uma lista de floats; None se vazia."""
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def _payload(models_ranked: list[UnifiedModel], models_nd: list[UnifiedModel]) -> dict:
    _LIVENESS = _load_liveness()

    def _LIVENESS_SUMMARY() -> dict:
        ok = [mid for mid, s in _LIVENESS.items() if s == "ok"]
        dead = [mid for mid, s in _LIVENESS.items() if s == "dead"]
        try:
            d = json.loads(
                (ROOT / "data" / "liveness_daily.json").read_text(encoding="utf-8")
            )
            recommended = d.get("recommended")
            total = d.get("total_candidates", len(_LIVENESS))
        except Exception:
            recommended = None
            total = len(_LIVENESS)
        return {
            "alive": ok,
            "dead": dead,
            "alive_count": len(ok),
            "dead_count": len(dead),
            "total": total,
            "recommended": recommended,
        }

    def row(m: UnifiedModel, rank: int | None) -> dict:
        # liveness: tenta model_id completo, depois canonical_id (remove sufixo :free etc.)
        _lv = _LIVENESS.get(m.model_id)
        if _lv is None and getattr(m, "canonical_id", None):
            _lv = _LIVENESS.get(m.canonical_id)
        stars = aa_to_stars(m.aa_index)
        return {
            "rank": rank,
            "provider": m.provider,
            "model_id": m.model_id,
            "display_name": m.display_name or m.model_id,
            "context_k": m.context_k,
            "tool_call": m.tool_call,
            "reasoning": m.reasoning,
            "multimodal": m.multimodal,
            "open_weights": m.open_weights,
            "family": m.family,
            "structured_output": m.structured_output,
            "has_cache_pricing": m.has_cache_pricing,
            "price_in": m.price_in,
            "price_out": m.price_out,
            "is_free": m.is_free,
            "aa_index": m.aa_index,
            "aa_stars": stars,
            "cxb_score": m.cxb_score,
            "source": m.source,
            "release_date": m.release_date,
            # v2.5: métricas AA e capabilities
            "speed_tps": m.speed_tps,
            "ttft_s": m.ttft_s,
            "e2e_s": m.e2e_s,
            "coding_index": m.coding_index,
            "agentic_index": m.agentic_index,
            "modalities_in": m.modalities_in,
            "modalities_out": m.modalities_out,
            "max_output_tokens": m.max_output_tokens,
            "knowledge_cutoff": m.knowledge_cutoff,
            "attachment": m.attachment,
            "canonical_id": m.canonical_id,
            "variant": m.variant,
            "aliases": m.aliases,
            "divergences": m.divergences,
            # liveness diário (prova real de modelo vivo/morto)
            "liveness": _lv,
        }

    return {
        "ranked": [row(m, i + 1) for i, m in enumerate(models_ranked)],
        "non_ranked": [row(m, None) for m in models_nd],
        "liveness_summary": _LIVENESS_SUMMARY(),
        "kpis": {
            "total_ranked": len(models_ranked),
            "total_inventory": len(models_ranked) + len(models_nd),
            "free_ranked": sum(1 for m in models_ranked if m.is_free),
            "top_cxb": models_ranked[0].cxb_score if models_ranked else 0,
            "top_model": (models_ranked[0].display_name or models_ranked[0].model_id)
            if models_ranked
            else "-",
            # v2.5 F3: KPIs agregados das métricas AA
            "median_speed_tps": _median([m.speed_tps for m in models_ranked if m.speed_tps is not None]),
            "median_ttft_s": _median([m.ttft_s for m in models_ranked if m.ttft_s is not None]),
            "fastest_model": _best(models_ranked, key=lambda m: m.speed_tps, reverse=True),
            "top_coder": _best(models_ranked, key=lambda m: m.coding_index, reverse=True),
            "top_agentic": _best(models_ranked, key=lambda m: m.agentic_index, reverse=True),
        },
        "provider_health": _load_provider_health(),
    }


def _best(models: list[UnifiedModel], key, reverse: bool = True) -> dict | None:
    """Retorna {model_id, display_name, value} do modelo com max/min da key (None-safe)."""
    pool = [m for m in models if key(m) is not None]
    if not pool:
        return None
    top = max(pool, key=key) if reverse else min(pool, key=key)
    return {
        "model_id": top.model_id,
        "display_name": top.display_name or top.model_id,
        "value": key(top),
    }


def build_dashboard(
    models_ranked: list[UnifiedModel],
    models_nd: list[UnifiedModel],
    template_path: Path = TEMPLATE,
    output_path: Path = OUTPUT,
) -> Path:
    """Lê TEMPLATE, substitui MARKER pelo payload JSON, escreve OUTPUT.

    Levanta RuntimeError se o marker não existir (template quebrado).
    """
    tpl = Path(template_path).read_text(encoding="utf-8")
    if MARKER not in tpl:
        raise RuntimeError(f"Marker {MARKER!r} não encontrado em {template_path}")

    payload = _payload(models_ranked, models_nd)
    injected = tpl.replace(MARKER, json.dumps(payload, ensure_ascii=False))
    # newline="\n" garante LF — paridade byte-a-byte com o blob gh-pages (autocrlf)
    Path(output_path).write_text(injected, encoding="utf-8", newline="\n")
    logger.info(
        "Dashboard consolidado escrito: %s (ranked=%d, N/D=%d)",
        output_path,
        len(models_ranked),
        len(models_nd),
    )
    return Path(output_path)
