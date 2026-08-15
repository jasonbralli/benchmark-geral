"""nim_pipeline: pipeline automatizado para inventário + ranking de modelos NVIDIA NIM."""

from .fetch import fetch_nvidia_models
from .filter import filter_frontier_models, filter_by_tier, is_excluded
from .enrich import enrich_models_with_aa, aa_count, AA_INTELLIGENCE_INDEX

__all__ = [
    "fetch_nvidia_models",
    "filter_frontier_models",
    "filter_by_tier",
    "is_excluded",
    "enrich_models_with_aa",
    "aa_count",
    "AA_INTELLIGENCE_INDEX",
]
