"""benchmark_pipe.extract

Lê o cache de providers do Hermes (provider_models_cache.json) e retorna
{provider: set(model_ids)}. Cache Hermes = single source of IDs (1 leitura,
não N chamadas de API de listagem).

Formato do cache:
    {"nvidia": {"fp": "...", "at": 123, "models": ["a/b", ...]}, ...}
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

def _get_hermes_cache_path() -> Path:
    """Retorna o caminho do cache do Hermes.

    Prioridade:
    1. Variável de ambiente HERMES_PROVIDER_CACHE
    2. Perfil do usuário do Hermes em AppData (portátil, sem hardcode)
    """
    env_path = os.environ.get("HERMES_PROVIDER_CACHE")
    if env_path:
        return Path(env_path)
    # Default: perfil do usuário do Hermes (portátil, sem hardcode de caminho)
    return Path.home() / "AppData" / "Local" / "hermes" / "provider_models_cache.json"

HERMES_CACHE = _get_hermes_cache_path()


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
