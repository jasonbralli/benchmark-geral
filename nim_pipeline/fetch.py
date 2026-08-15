"""
nim_pipeline.fetch
==================

Puxa o inventário atualizado de modelos NVIDIA NIM via models.dev (open-source
database mantido pela comunidade, atualizado diariamente a partir da API oficial
integrate.api.nvidia.com/v1).

Retorna uma lista de dicionários com metadados por modelo:
    - id, name, description, family
    - attachment, reasoning, tool_call, structured_output
    - modalities (input/output)
    - open_weights, limit.context, cost.input/output
    - release_date, last_updated, knowledge

Uso:
    from nim_pipeline.fetch import fetch_nvidia_models
    models = fetch_nvidia_models()
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

MODELS_DEV_API = "https://models.dev/api.json"
PROVIDER = "nvidia"
CACHE_PATH = Path(__file__).parent.parent / "data" / "nvidia_models_raw.json"


def fetch_nvidia_models(use_cache: bool = False) -> list[dict[str, Any]]:
    """Retorna lista de modelos NVIDIA do models.dev.

    Args:
        use_cache: Se True, lê do cache local em data/nvidia_models_raw.json.
                   Útil para testes offline ou fallback se a API falhar.

    Returns:
        Lista de dicionários com metadados de cada modelo. Chave "id" sempre
        presente (ex: "deepseek-ai/deepseek-v4-flash").

    Raises:
        RuntimeError: Se a API falhar e não houver cache disponível.
    """
    if use_cache and CACHE_PATH.exists():
        logger.info(f"Lendo inventário do cache: {CACHE_PATH}")
        with CACHE_PATH.open(encoding="utf-8") as f:
            return json.load(f)

    logger.info(f"Buscando inventário atualizado: {MODELS_DEV_API}")
    try:
        req = Request(MODELS_DEV_API, headers={"User-Agent": "benchmark-geral/1.0"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError) as e:
        if CACHE_PATH.exists():
            logger.warning(f"API falhou ({e}). Usando cache: {CACHE_PATH}")
            with CACHE_PATH.open(encoding="utf-8") as f:
                return json.load(f)
        raise RuntimeError(f"Falha ao buscar models.dev: {e}") from e

    provider = data.get(PROVIDER, {})
    models = list(provider.get("models", {}).values())
    logger.info(f"Encontrados {len(models)} modelos NVIDIA no models.dev")

    # Salva cache para uso futuro
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(models, f, ensure_ascii=False, indent=2)
    logger.info(f"Cache salvo: {CACHE_PATH}")

    return models


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    models = fetch_nvidia_models()
    print(f"Total: {len(models)} modelos NVIDIA")
    for m in models[:5]:
        print(f"  {m['id']:50s} tool_call={m.get('tool_call')} reasoning={m.get('reasoning')}")
