"""benchmark_pipe.map_source
===========================

Anexa metadados por provider. NVIDIA é lido de models_dev_cache.json (fonte
de verdade, 102 modelos — inclui os 2 novos deepseek-v4-flash-0731 +
moonshotai/kimi-k3 que faltam no data/nvidia_models_raw.json stale).
OpenRouter tem adapter próprio; demais providers ficam como passthrough.

Cache OpenRouter em data/openrouter_models_raw.json.

A "single source of IDs" continua sendo o provider_models_cache.json do
Hermes, mas os METADADOS NVIDIA vêm do models_dev_cache.json do Hermes
(não do cache stale do projeto). O orquestrador faz o merge: IDs do Hermes
que não batem em models_dev (antigos/deprecados) caem para passthrough N/D.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Permite import de nim_pipeline sem instalar pacote
sys.path.insert(0, str(Path(__file__).parent.parent))
from nim_pipeline.fetch import fetch_nvidia_models  # noqa: E402

logger = logging.getLogger(__name__)

def _get_hermes_models_dev_cache() -> Path:
    """Retorna o caminho do models_dev_cache do Hermes."""
    env_path = os.environ.get("HERMES_MODELS_DEV_CACHE")
    if env_path:
        return Path(env_path)
    return Path(r"C:\Users\Jason\AppData\Local\hermes\models_dev_cache.json")

def _get_nous_recommended_cache() -> Path:
    """Retorna o caminho do cache de modelos recomendados do Nous."""
    env_path = os.environ.get("HERMES_NOUS_RECOMMENDED_CACHE")
    if env_path:
        return Path(env_path)
    return Path(r"C:\Users\Jason\AppData\Local\hermes\cache\nous_recommended_cache.json")

HERMES_MODELS_DEV_CACHE = _get_hermes_models_dev_cache()
NOUS_RECOMMENDED_DISK_CACHE = _get_nous_recommended_cache()
NOUS_RECOMMENDED_API = "https://portal.nousresearch.com/api/nous/recommended-models"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"

# Catálogos live dos providers sem fonte nativa de metadados no models.dev nvidia
# (Kilo Code, Nous Portal). Usados para: (a) preço real -> is_free confiável,
# (b) ctx/tool_call/reasoning para modelos que faltam no models.dev (ex.: Ornith).
from .catalog import fetch_catalog, catalog_ids, is_zero_priced, KILO_API, NOUS_API  # noqa: E402

NOUS_METADATA_CACHE = Path(__file__).parent.parent / "data" / "nous_models_raw.json"
KILO_METADATA_CACHE = Path(__file__).parent.parent / "data" / "kilo_models_raw.json"


def fetch_nous_metadata(use_cache: bool = True) -> dict[str, dict[str, Any]]:
    """Catálogo live do Nous Portal: {model_id: metadado funcional}.

    Campos úteis: id, name, context_length, pricing, architecture, supported_parameters,
    reasoning. Preço vem do provider (fonte de verdade p/ is_free do Nous).
    """
    items = fetch_catalog("nous", use_cache=use_cache)
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        mid = it.get("id")
        if not mid:
            continue
        pricing = it.get("pricing") or {}
        arch = it.get("architecture") or {}
        out[mid] = {
            "id": mid,
            "name": it.get("name") or mid,
            "context_length": it.get("context_length"),
            "price_in": _to_usd_m(pricing.get("prompt")),
            "price_out": _to_usd_m(pricing.get("completion")),
            "modalities_in": arch.get("input_modalities") or [],
            "modalities_out": arch.get("output_modalities") or [],
            "tool_call": "tools" in (it.get("supported_parameters") or []),
            "reasoning": "reasoning" in (it.get("supported_parameters") or []),
            "attachment": bool(it.get("isCustomLlm")) or "image" in (arch.get("input_modalities") or []),
        }
    logger.info("Nous metadata live: %d modelos", len(out))
    return out


def fetch_kilocode_metadata(use_cache: bool = True) -> dict[str, dict[str, Any]]:
    """Catálogo live do Kilo Code: {model_id: metadado funcional}."""
    items = fetch_catalog("kilocode", use_cache=use_cache)
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        mid = it.get("id")
        if not mid:
            continue
        pricing = it.get("pricing") or {}
        arch = it.get("architecture") or {}
        out[mid] = {
            "id": mid,
            "name": it.get("name") or mid,
            "context_length": it.get("context_length"),
            "price_in": _to_usd_m(pricing.get("prompt")),
            "price_out": _to_usd_m(pricing.get("completion")),
            "modalities_in": arch.get("input_modalities") or [],
            "modalities_out": arch.get("output_modalities") or [],
            "tool_call": "tools" in (it.get("supported_parameters") or []),
            "reasoning": "reasoning" in (it.get("supported_parameters") or []),
            "attachment": "image" in (arch.get("input_modalities") or []),
        }
    logger.info("Kilo metadata live: %d modelos", len(out))
    return out


def _to_usd_m(tok_price: str | float | None) -> float | None:
    if tok_price is None:
        return None
    try:
        return round(float(tok_price) * 1_000_000, 6)
    except (TypeError, ValueError):
        return None


def _family_key(model_id: str) -> str:
    """Nome base da família: remove sufixos de variante/versão/parametro.

    mistralai/mistral-large-4-1t-a52b -> mistral-large-4
    ornith-ai/ornith-1.5-122b -> ornith-1-5-122b
    """
    import re as _re

    s = model_id.split("/")[-1].lower().split("@")[0]
    token = _re.compile(
        r"[-_.](?:1t|a\d+b|b\d+a\d+b|m\d+b|\d{1,2}b|v\d+(?:\.\d+)*|instruct|chat|it|preview|latest|free|tuned)$",
        _re.I,
    )
    for _ in range(5):
        new = token.sub("", s)
        if new == s:
            break
        s = new
    return _re.sub(r"[-_.]+", "-", s).strip("-")


def resolve_nvidia_family(
    model_id: str,
    models_dev_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve metadados de um modelo NVIDIA ausente do bloco nvidia do models.dev
    por correspondência de família (nome base) entre TODOS os providers do
    models.dev_cache.

    Usa MODO (valor mais frequente) de ctx e tool_call entre os candidatos da
    família, em vez de exigir unanimidade — provedores distintos podem expor
    janelas de contexto diferentes para o mesmo modelo lógico.

    Retorna meta dict (sem preço — preço NVIDIA é por-conta) ou None.
    """
    if "/" not in model_id:
        return None
    fkey = _family_key(model_id)
    cands = [
        m for mid, m in models_dev_index.items()
        if isinstance(mid, str) and isinstance(m, dict) and _family_key(mid) == fkey
    ]
    if not cands:
        return None

    def _mode(vals):
        from collections import Counter as _C
        common = _C(v for v in vals if v is not None).most_common(1)
        return common[0][0] if common else None

    ctxs = [((m.get("limit") or {}).get("context")) for m in cands
            if isinstance(m.get("limit"), dict) and (m.get("limit") or {}).get("context")]
    tools = [m.get("tool_call") for m in cands if "tool_call" in m]
    ctx = _mode(ctxs)
    tool = _mode(tools)
    if ctx is None and tool is None:
        return None

    meta: dict[str, Any] = {}
    for m in cands:
        for k, v in m.items():
            if k == "cost":
                continue
            if k not in meta or meta[k] in (None, "", [], {}):
                meta[k] = v
    meta["limit"] = {"context": ctx} if ctx is not None else {}
    if tool is not None:
        meta["tool_call"] = tool
    meta["_family_candidates"] = len(cands)
    return meta




def fetch_nous_free_ids(use_cache: bool = True) -> set[str]:
    """Retorna IDs free do Nous Portal (freeRecommendedModels).

    fonte 1 (cache): ~/AppData/Local/hermes/cache/nous_recommended_cache.json
    fonte 2 (live):  GET portal.nousresearch.com/api/nous/recommended-models
                     (público, sem auth; só tentado quando use_cache=False)

    Retorna set de IDs bare+sufixados (lowercase). Falha -> set() (graceful).
    """
    ids: set[str] = set()

    def _harvest(payload: dict) -> None:
        block = payload.get("freeRecommendedModels")
        if not isinstance(block, list):
            return
        for item in block:
            if isinstance(item, dict):
                name = item.get("modelName")
            else:
                name = item
            if isinstance(name, str) and name.strip():
                ids.add(name.strip().lower())

    if use_cache and NOUS_RECOMMENDED_DISK_CACHE.exists():
        try:
            blob = json.loads(NOUS_RECOMMENDED_DISK_CACHE.read_text(encoding="utf-8"))
            for entry in (blob or {}).values():
                if isinstance(entry, dict) and isinstance(entry.get("data"), dict):
                    _harvest(entry["data"])
            if ids:
                logger.info("Nous free IDs (disk cache): %d", len(ids))
                return ids
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("nous_recommended_cache ilegível (%s); tentando live", e)

    if not use_cache:
        try:
            req = Request(NOUS_RECOMMENDED_API, headers={"User-Agent": "benchmark-geral/1.0"})
            with urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            _harvest(payload if isinstance(payload, dict) else {})
            logger.info("Nous free IDs (live API): %d", len(ids))
        except (URLError, HTTPError, json.JSONDecodeError, OSError) as e:
            logger.warning("Nous recommended-models live falhou: %s", e)
            # fallback: tenta disk cache se existir
            if NOUS_RECOMMENDED_DISK_CACHE.exists():
                try:
                    blob = json.loads(NOUS_RECOMMENDED_DISK_CACHE.read_text(encoding="utf-8"))
                    for entry in (blob or {}).values():
                        if isinstance(entry, dict) and isinstance(entry.get("data"), dict):
                            _harvest(entry["data"])
                except (json.JSONDecodeError, OSError):
                    pass
    return ids
OR_CACHE = Path(__file__).parent.parent / "data" / "openrouter_models_raw.json"
# Cache de fallback (stale) usado só quando models_dev_cache indisponível
LEGACY_PROJECT_CACHE = Path(__file__).parent.parent / "data" / "nvidia_models_raw.json"


def fetch_nvidia_from_models_dev_cache() -> list[dict[str, Any]]:
    """Lê metadados NVIDIA de ~/AppData/Local/hermes/models_dev_cache.json.

    Retorna lista de dicts no mesmo formato que fetch_nvidia_models.
    Levanta RuntimeError se o cache não existir/formato inválido.
    """
    if not HERMES_MODELS_DEV_CACHE.exists():
        raise RuntimeError(f"models_dev_cache ausente: {HERMES_MODELS_DEV_CACHE}")
    data = json.loads(HERMES_MODELS_DEV_CACHE.read_text(encoding="utf-8"))
    models = data.get("nvidia", {}).get("models", {})
    # models é dict{id: meta} ou lista; normaliza para lista
    if isinstance(models, dict):
        out = list(models.values())
    else:
        out = list(models)
    logger.info("models_dev_cache NVIDIA: %d modelos", len(out))
    return out


# Aliases: nome do provider Hermes -> nome no models_dev_cache (se diferente).
PROVIDER_ALIASES = {
    "kilocode": "kilo",
    "opencode-free": "opencode",
}


def _load_models_dev_index() -> dict[str, dict[str, Any]]:
    """Índice global de metadados: {model_id: meta} — preenche campos por
    provider, mantendo preço/custo do primeiro provider que expõe cada campo.
    Evita que um modelo free do nvidia infecte kilocode/nous (que cobram).
    """
    if not HERMES_MODELS_DEV_CACHE.exists():
        return {}
    try:
        data = json.loads(HERMES_MODELS_DEV_CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for prov_data in data.values():
        if not isinstance(prov_data, dict):
            continue
        models = prov_data.get("models") or {}
        if not isinstance(models, dict):
            continue
        for mid, meta in models.items():
            if not (isinstance(mid, str) and isinstance(meta, dict)):
                continue
            entry = out.setdefault(mid, {})
            if "cost" not in entry and "cost" in meta:
                entry["cost"] = meta.get("cost")
            if "limit" not in entry and "limit" in meta:
                entry["limit"] = meta.get("limit")
            if "tool_call" not in entry and "tool_call" in meta:
                entry["tool_call"] = meta.get("tool_call")
            if "reasoning" not in entry and "reasoning" in meta:
                entry["reasoning"] = meta.get("reasoning")
            if "attachment" not in entry and "attachment" in meta:
                entry["attachment"] = meta.get("attachment")
            if "open_weights" not in entry and "open_weights" in meta:
                entry["open_weights"] = meta.get("open_weights")
            if "release_date" not in entry and "release_date" in meta:
                entry["release_date"] = meta.get("release_date")
            if "name" not in entry and "name" in meta:
                entry["name"] = meta.get("name")
            # v2.5: campos de capability/modalidade ausentes (causavam perda
            # de modalities_in/out, family, structured_output, knowledge no
            # cross-join de kilocode/nous/huggingface/opencode-free).
            if "modalities" not in entry and "modalities" in meta:
                entry["modalities"] = meta.get("modalities")
            if "family" not in entry and "family" in meta:
                entry["family"] = meta.get("family")
            if "structured_output" not in entry and "structured_output" in meta:
                entry["structured_output"] = meta.get("structured_output")
            if "knowledge" not in entry and "knowledge" in meta:
                entry["knowledge"] = meta.get("knowledge")
    return out


def enrich_passthrough_with_models_dev(
    provider: str,
    ids: set[str] | list[str],
) -> dict[str, dict[str, Any]]:
    """Cross-join: {model_id: meta} priorizando o provider correto (via alias)."""
    if not ids:
        return {}
    index = _load_models_dev_index()
    return {mid: index[mid] for mid in ids if mid in index}


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
            # Fonte de verdade: models_dev_cache do Hermes (102 modelos)
            out["nvidia"] = fetch_nvidia_from_models_dev_cache()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "models_dev_cache falhou (%s); fallback p/ cache stale do projeto", e
            )
            try:
                out["nvidia"] = fetch_nvidia_models(use_cache=True)
            except Exception as e2:  # noqa: BLE001
                logger.warning("Fallback NVIDIA também falhou: %s", e2)
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
