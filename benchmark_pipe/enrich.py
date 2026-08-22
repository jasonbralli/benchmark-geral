"""benchmark_pipe.enrich
=======================

Reusa nim_pipeline.enrich.AA_INTELLIGENCE_INDEX por chave normalizada.
Modelos sem mapeamento -> aa_index=None (N/D). Não quebra.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from nim_pipeline.enrich import AA_INTELLIGENCE_INDEX, aa_to_stars  # noqa: E402

from .normalize import UnifiedModel  # noqa: E402


def _norm_key(model_id: str) -> str:
    """Normaliza chave p/ lookup AA: lowercase, sem backticks."""
    return model_id.lower().replace("`", "").strip()


def enrich_unified(models: list[UnifiedModel]) -> list[UnifiedModel]:
    """Aplica AA Index a cada UnifiedModel in-place."""
    # Índice lower-cased do AA para lookup tolerante
    aa_lower = {k.lower(): v for k, v in AA_INTELLIGENCE_INDEX.items()}

    for m in models:
        key = _norm_key(m.model_id)
        entry = aa_lower.get(key)
        if entry is None:
            # tenta match pelo display_name (ex.: deepseek-v4-flash-0731)
            if m.display_name:
                entry = aa_lower.get(_norm_key(m.display_name))
        if entry:
            m.aa_index = entry.get("index")
            if entry.get("display_name"):
                m.display_name = entry["display_name"]
        else:
            m.aa_index = None
    return models


__all__ = ["enrich_unified", "aa_to_stars"]
