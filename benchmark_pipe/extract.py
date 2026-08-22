"""benchmark_pipe.extract
========================

Lê o cache de providers do Hermes (provider_models_cache.json) e retorna
{provider: set(model_ids)}. Cache Hermes = single source of IDs (1 leitura,
não N chamadas de API de listagem).

Formato do cache:
    {"nvidia": {"fp": "...", "at": 123, "models": ["a/b", ...]}, ...}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

HERMES_CACHE = Path(
    r"C:\Users\Jason\AppData\Local\hermes\provider_models_cache.json"
)


def extract_provider_models(
    cache_path: Path = HERMES_CACHE,
) -> dict[str, set[str]]:
    """Retorna {provider: set(model_ids)} do cache Hermes.

    Arquivo ausente ou payload malformado -> {}  (graceful, nunca levanta).
    """
    p = Path(cache_path)
    if not p.exists():
        logger.warning("Cache Hermes não encontrado: %s", cache_path)
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Cache Hermes ilegível (%s): %s", e, cache_path)
        return {}

    out: dict[str, set[str]] = {}
    for prov, payload in data.items():
        models = (payload or {}).get("models") or []
        out[prov] = {str(m) for m in models if isinstance(m, str) and m}
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    inv = extract_provider_models()
    for prov, ids in sorted(inv.items()):
        print(f"{prov:15s} {len(ids):4d} modelos")
