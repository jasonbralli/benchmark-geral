"""benchmark_pipe.map_source
===========================

Anexa metadados por provider. NVIDIA reusa nim_pipeline.fetch; OpenRouter tem
adapter novo; demais providers ficam como passthrough (sem fonte confiável).

Cache OpenRouter em data/openrouter_models_raw.json (mesmo padrão do NVIDIA).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Permite import de nim_pipeline sem instalar pacote
sys.path.insert(0, str(Path(__file__).parent.parent))
from nim_pipeline.fetch import fetch_nvidia_models  # noqa: E402

logger = logging.getLogger(__name__)

OPENROUTER_API = "https://openrouter.ai/api/v1/models"
OR_CACHE = Path(__file__).parent.parent / "data" / "openrouter_models_raw.json"


def fetch_openrouter(use_cache: bool = False) -> list[dict[str, Any]]:
    """Retorna lista de modelos da OpenRouter (data[])."""
    if use_cache and OR_CACHE.exists():
        logger.info("Lendo OpenRouter do cache: %s", OR_CACHE)
        with OR_CACHE.open(encoding="utf-8") as f:
            return json.load(f)

    logger.info("Buscando OpenRouter: %s", OPENROUTER_API)
    try:
        req = Request(OPENROUTER_API, headers={"User-Agent": "benchmark-geral/1.0"})
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError, OSError) as e:
        if OR_CACHE.exists():
            logger.warning("OpenRouter falhou (%s). Usando cache.", e)
            with OR_CACHE.open(encoding="utf-8") as f:
                return json.load(f)
        raise RuntimeError(f"Falha OpenRouter: {e}") from e

    models = list(payload.get("data", []))
    OR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with OR_CACHE.open("w", encoding="utf-8") as f:
        json.dump(models, f, ensure_ascii=False, indent=2)
    logger.info("OpenRouter: %d modelos, cache salvo em %s", len(models), OR_CACHE)
    return models


def build_metadata_index(
    hermes_inventory: dict[str, set[str]],
    use_cache: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Retorna {provider: [raw_meta_dict,...]} apenas para providers com fonte.

    Providers sem fonte (gemini/kilocode/huggingface/nous/opencode-free) não
    aparecem aqui — o orquestrador usa passthrough_ids() para eles.
    """
    out: dict[str, list[dict[str, Any]]] = {}

    if "nvidia" in hermes_inventory:
        try:
            out["nvidia"] = fetch_nvidia_models(use_cache=use_cache)
        except Exception as e:  # noqa: BLE001
            logger.warning("NVIDIA fetch falhou: %s", e)
            out["nvidia"] = []

    if "openrouter" in hermes_inventory:
        try:
            out["openrouter"] = fetch_openrouter(use_cache=use_cache)
        except Exception as e:  # noqa: BLE001
            logger.warning("OpenRouter fetch falhou: %s", e)
            out["openrouter"] = []

    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    or_models = fetch_openrouter(use_cache=True)
    print(f"OpenRouter: {len(or_models)} modelos")
    for m in or_models[:3]:
        print(f"  {m.get('id','?'):50s} ctx={m.get('context_length')}")
