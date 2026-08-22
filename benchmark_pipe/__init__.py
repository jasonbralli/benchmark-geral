"""benchmark_pipe: pipeline consolidado multi-provider (extract -> map -> normalize -> enrich -> score -> build)."""

from .extract import extract_provider_models
from .normalize import UnifiedModel, derive_is_free, is_rankable
from .map_source import fetch_openrouter, build_metadata_index
from .enrich import enrich_unified
from .score import benefit, cxb_score, score_models

__all__ = [
    "extract_provider_models",
    "UnifiedModel",
    "derive_is_free",
    "is_rankable",
    "fetch_openrouter",
    "build_metadata_index",
    "enrich_unified",
    "benefit",
    "cxb_score",
    "score_models",
]
