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

from benchmark_pipe.normalize import passthrough_ids  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


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

    # Providers com fonte -> normaliza
    all_models = []
    nv_raw = metadata.get("nvidia", [])
    all_models += normalize_nvidia(nv_raw)
    or_raw = metadata.get("openrouter", [])
    all_models += normalize_openrouter(or_raw)

    # Providers sem fonte -> passthrough (is_free p/ nvidia/opencode, senão False)
    no_source = [p for p in inventory if p not in ("nvidia", "openrouter")]
    for prov in no_source:
        all_models += passthrough_ids(prov, inventory[prov])

    # AA enrich
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
    parser.add_argument("--json", help="salva artefato JSON em path (opcional)")
    args = parser.parse_args(argv)

    use_cache = not args.refresh
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