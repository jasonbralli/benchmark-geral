"""benchmark_pipe.build
======================

Gera dashboard.html consolidado multi-provider via template_consolidado.html
(marker //CONSOLIDATED_DATA//). Idempotente: lê template, injeta, escreve OUT.

Output = `dashboard.html` (canónico) — decisão 22/08/2026: substitui o
dashboard NVIDIA antigo.
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
OUTPUT = ROOT / "dashboard.html"
MARKER = "//CONSOLIDATED_DATA//"


def _payload(models_ranked: list[UnifiedModel], models_nd: list[UnifiedModel]) -> dict:
    def row(m: UnifiedModel, rank: int | None) -> dict:
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
            "canonical_id": m.canonical_id,
            "variant": m.variant,
            "aliases": m.aliases,
            "divergences": m.divergences,
        }

    return {
        "ranked": [row(m, i + 1) for i, m in enumerate(models_ranked)],
        "non_ranked": [row(m, None) for m in models_nd],
        "kpis": {
            "total_ranked": len(models_ranked),
            "total_inventory": len(models_ranked) + len(models_nd),
            "free_ranked": sum(1 for m in models_ranked if m.is_free),
            "top_cxb": models_ranked[0].cxb_score if models_ranked else 0,
            "top_model": (models_ranked[0].display_name or models_ranked[0].model_id)
            if models_ranked
            else "-",
        },
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
    Path(output_path).write_text(injected, encoding="utf-8")
    logger.info(
        "Dashboard consolidado escrito: %s (ranked=%d, N/D=%d)",
        output_path,
        len(models_ranked),
        len(models_nd),
    )
    return Path(output_path)
