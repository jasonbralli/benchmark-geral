"""benchmark_pipe.enrich
=======================

Reusa AA_INTELLIGENCE_INDEX curado + AA Data API v2 (bulk) por chave normalizada.
Modelos sem mapeamento -> aa_index=None (N/D). Nao quebra.

Prioridade de lookup:
  1) mapa AA API (bulk free, cache 24h) via canonical_id/model_id -> slug
  2) dicionario curado AA_INTELLIGENCE_INDEX (fallback estatico)

Normalizacao canonica: lookup tenta model_id, display_name e
canonical_id (strip :free/:batch + vendor alias). Assim
z-ai/glm-5.2:free herda AA de z-ai/glm-5.2.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from nim_pipeline.enrich import AA_INTELLIGENCE_INDEX, aa_to_stars  # noqa: E402

from .normalize import UnifiedModel, canonicalize  # noqa: E402

logger = logging.getLogger(__name__)


def _norm_key(model_id: str) -> str:
    """Normaliza chave p/ lookup AA curado: lowercase, sem backticks/~."""
    return model_id.lower().replace("`", "").lstrip("~").strip()


def _load_aa_api_map() -> dict[str, float] | None:
    """Tenta carregar mapa slug->index do cache AA API (se existir)."""
    try:
        from .aa_api import CACHE as AA_CACHE, build_aa_index_map
        if AA_CACHE.exists():
            raw = json.loads(AA_CACHE.read_text(encoding="utf-8"))
            m = build_aa_index_map(raw)
            if m:
                return m
    except Exception as e:  # noqa: BLE001
        logger.debug("AA API cache nao carregado: %s", e)
    return None


def enrich_unified(models: list[UnifiedModel], aa_api_map: dict[str, float] | None = None) -> list[UnifiedModel]:
    """Aplica AA Index a cada UnifiedModel in-place.

    Args:
        models: lista de UnifiedModel (mutada in-place).
        aa_api_map: opcional {slug_norm: index} vindo de aa_api.build_aa_index_map.
            Se None, tenta carregar do cache em disco automaticamente.
    """
    if aa_api_map is None:
        aa_api_map = _load_aa_api_map()

    aa_lower = {k.lower(): v for k, v in AA_INTELLIGENCE_INDEX.items()}

    lookup_fn = None
    if aa_api_map:
        try:
            from .aa_api import lookup_aa_index as _lookup
            lookup_fn = _lookup
        except Exception:
            lookup_fn = None

    for m in models:
        if lookup_fn is not None and aa_api_map is not None:
            idx = lookup_fn(m.model_id, m.canonical_id, aa_api_map)
            if idx is None and m.display_name:
                try:
                    from .aa_api import _norm_slug
                    dn_norm = _norm_slug(m.display_name.split("/")[-1])
                    idx = aa_api_map.get(dn_norm)
                except Exception:
                    idx = None
            if idx is not None:
                m.aa_index = float(idx)
                continue

        entry = None
        entry = aa_lower.get(_norm_key(m.model_id))
        if entry is None and m.display_name:
            entry = aa_lower.get(_norm_key(m.display_name))
        if entry is None and m.canonical_id:
            entry = aa_lower.get(_norm_key(m.canonical_id))
        if entry is None:
            canon, _ = canonicalize(m.model_id)
            entry = aa_lower.get(_norm_key(canon))
        if entry:
            m.aa_index = entry.get("index")
            if entry.get("display_name"):
                m.display_name = entry["display_name"]
        else:
            m.aa_index = None
    return models


__all__ = ["enrich_unified", "aa_to_stars"]
