"""scripts/run_consolidated.py
=============================

Orquestrador do pipeline consolidado multi-provider.

    extract (cache Hermes) -> map_source (metadados) -> normalize
    -> enrich (AA) -> score (CxB) -> build (dashboard.html)

Flags:
    --refresh   re-busca OpenRouter/model.dev da API (sem cache)
    --use-cache usa cache local (default)

Após gerar, roda pytest no projeto como gate.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_pipe.normalize import passthrough_ids, passthrough_ids_enriched  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _maybe_refresh_aa(use_cache: bool):
    """Refresh AA cache se --refresh ou cache expirado (>24h). Silencioso, nunca quebra."""
    try:
        from benchmark_pipe.aa_api import CACHE as AA_CACHE, TTL_HOURS, fetch_aa_models
        import os
        if not use_cache:
            fetch_aa_models(use_cache=False)
            return
        has_key = any(os.environ.get(k) for k in ("AA_API_KEY_benchmark_geral", "AA_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY"))
        env_file = AA_CACHE.parent.parent / ".env"
        if not has_key and env_file.exists():
            try:
                txt2 = env_file.read_text(encoding="utf-8")
                has_key = "AA_API_KEY" in txt2
                if has_key:
                    for line in txt2.splitlines():
                        line=line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k,v=line.split("=",1)
                        k=k.strip(); v=v.strip().strip(chr(34)).strip(chr(39))
                        if k.startswith("AA_API_KEY") and k not in os.environ:
                            os.environ[k]=v
            except Exception:
                pass
        if has_key:
            fetch_aa_models(use_cache=True, ttl_hours=TTL_HOURS)
    except Exception as e:  # noqa: BLE001
        import logging as _lg
        _lg.getLogger(__name__).warning("AA refresh ignorado: %s", e)

def run(inventory: dict, use_cache: bool, out_json: Path | None):
    from benchmark_pipe.build import build_dashboard
    from benchmark_pipe.enrich import enrich_unified
    from benchmark_pipe.extract import extract_provider_models
    from benchmark_pipe.map_source import build_metadata_index
    from benchmark_pipe.normalize import normalize_nvidia, normalize_openrouter
    from benchmark_pipe.score import score_models

    if not inventory:
        inventory = extract_provider_models()

    metadata = build_metadata_index(inventory, use_cache=use_cache)

    # Cross-join de metadados: índice global reutilizado p/ missing NVIDIA
    from benchmark_pipe.map_source import _load_models_dev_index
    models_dev_index = _load_models_dev_index()

    # Providers com fonte -> normaliza (com merge Hermes IDs × metadados)
    all_models = []
    nv_raw = metadata.get("nvidia", [])
    nvidia_models = normalize_nvidia(nv_raw)
    # Single source of IDs = Hermes cache. IDs do Hermes sem metadados em
    # models_dev (antigos/deprecados) viram passthrough N/D — nunca drop.
    nv_meta_ids = {m.model_id for m in nvidia_models}
    nvidia_missing = set(inventory.get("nvidia", set())) - nv_meta_ids
    all_models += nvidia_models
    all_models += passthrough_ids_enriched("nvidia", nvidia_missing, models_dev_index)

    or_raw = metadata.get("openrouter", [])
    all_models += normalize_openrouter(or_raw, meta_index=models_dev_index)

    # Providers sem fonte -> passthrough com cross-join de metadados
    no_source = [p for p in inventory if p not in ("nvidia", "openrouter")]
    for prov in no_source:
        all_models += passthrough_ids_enriched(prov, inventory[prov], models_dev_index)

    # Dedup intra-provider (provider + canonical + variant) antes do enrich
    from benchmark_pipe.normalize import dedup_models

    all_models = dedup_models(all_models, hermes_inventory=inventory)

    _maybe_refresh_aa(use_cache)
    # AA enrich (por canonical_id — propaga para variantes :free etc)
    # usa cache AA API se existir, senao fallback curado
    enrich_unified(all_models)

    # Score CxB -> split rankable vs N/D
    ranked, non_ranked = score_models(all_models)
    logger.info(
        "ranked=%d  non_ranked=%d  total=%d",
        len(ranked), len(non_ranked), len(all_models),
    )

    out = build_dashboard(ranked, non_ranked)

    if out_json is not None:
        payload = {
            "ranked": [m.to_dict() for m in ranked],
            "non_ranked": [m.to_dict() for m in non_ranked],
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Artefato JSON: %s", out_json)

    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline consolidado multi-provider")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--refresh", action="store_true", help="re-busca APIs, ignora cache")
    group.add_argument("--use-cache", action="store_true", help="usa cache local (default)")
    parser.add_argument("--refresh-aa", action="store_true", help="forca refresh do cache AA (independente de --refresh)")
    parser.add_argument("--json", help="salva artefato JSON em path (opcional)")
    args = parser.parse_args(argv)

    use_cache = not args.refresh
    if args.refresh_aa:
        try:
            from benchmark_pipe.aa_api import fetch_aa_models
            fetch_aa_models(use_cache=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("refresh-aa falhou: %s", e)
    out = run({}, use_cache=use_cache, out_json=Path(args.json) if args.json else None)
    logger.info("Dashboard gerado: %s", out)

    # Gate: roda pytest no projeto
    res = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error("pytest falhou:\n%s", res.stdout or res.stderr)
        return 1
    logger.info("pytest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())