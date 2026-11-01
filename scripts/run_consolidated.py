"""scripts/run_consolidated.py
=============================

Orquestrador do pipeline consolidado multi-provider.

    extract (cache Hermes) -> map_source (metadados) -> normalize
    -> enrich (AA) -> score (CxB) -> build (index.html)

Flags:
    --refresh   re-busca OpenRouter/model.dev da API (sem cache)
    --use-cache usa cache local (default)

Após gerar, roda pytest no projeto como gate.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_pipe.normalize import passthrough_ids, passthrough_ids_enriched  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _resolve_gate_exe() -> str:
    """Interpreter do gate pytest.

    Chain (11/10/2026): BENCH_PYTEST_PYTHON > `py` launcher > python3 > sys.executable.
    Motivo do `py` à frente de python3: o Windows recriou os aliases
    python3.exe/python.exe em WindowsApps (stub da Store,
    AppInstallerPythonRedirector — 09/10 14:05). shutil.which('python3') acha o
    stub, que imprime "Python não foi encontrado..." em CP1252 e mata a reader
    thread do subprocess com UnicodeDecodeError (byte 0xe3 = 'ã' na posição 8)
    → stdout/stderr=None → "pytest falhou: None". `py` (PSF Python Manager) é
    launcher real: roda o 3.13 instalado com pytest.
    """
    env_exe = os.environ.get("BENCH_PYTEST_PYTHON", "")
    if env_exe:
        return env_exe
    py_exe = shutil.which("py")
    if py_exe:
        return py_exe
    return shutil.which("python3") or sys.executable


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
    from benchmark_pipe.map_source import (
        build_metadata_index,
        fetch_kilocode_metadata,
        fetch_nous_metadata,
        resolve_nvidia_family,
    )
    from benchmark_pipe.normalize import normalize_nvidia, normalize_openrouter
    from benchmark_pipe.reconcile import format_report, reconcile
    from benchmark_pipe.score import score_models

    if not inventory:
        inventory = extract_provider_models()

    # Nous free-tier: popula o conjunto dinâmico ANTES de qualquer derive_is_free.
    # Fonte: ~/AppData/Local/hermes/cache/nous_recommended_cache.json (ou live com --refresh).
    from benchmark_pipe.map_source import fetch_nous_free_ids
    from benchmark_pipe.normalize import set_nous_free_ids
    try:
        nous_free = fetch_nous_free_ids(use_cache=use_cache)
        if nous_free:
            set_nous_free_ids(nous_free)
            logger.info("Nous free IDs carregados: %s", sorted(nous_free))
            # Augmentar inventário: 4 IDs free do Portal não constam no cache
            # provider_models_cache (hermes não os expõe). Adicionar bare IDs
            # para que apareçam no inventário Nous como free.
            nous_inv = inventory.setdefault("nous", set())
            before = len(nous_inv)
            for fid in nous_free:
                bare = fid.replace(":free", "")
                if bare not in nous_inv:
                    nous_inv.add(bare)
            if len(nous_inv) > before:
                logger.info("Nous inventário augmentado: %d -> %d (%d adicionados)",
                            before, len(nous_inv), len(nous_inv) - before)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_nous_free_ids falhou (%s); Nous seguirá sem tier free", e)

    # Metadados live dos providers sem fonte nativa (Nous, Kilo Code).
    # Fonte de preço real -> is_free confiável; ctx/tool_call para modelos
    # ausentes do models.dev (ex.: Ornith no Nous).
    kilo_free_ids: set[str] = set()
    nous_free_ids_live: set[str] = set()
    try:
        nous_meta = fetch_nous_metadata(use_cache=use_cache)
        kilo_meta = fetch_kilocode_metadata(use_cache=use_cache)
        for mid, m in kilo_meta.items():
            if m.get("price_in") == 0 and m.get("price_out") == 0:
                kilo_free_ids.add(mid)
        for mid, m in nous_meta.items():
            if m.get("price_in") == 0 and m.get("price_out") == 0:
                nous_free_ids_live.add(mid)
    except Exception as e:  # noqa: BLE001
        logger.warning("metadata live falhou (%s); Nous/Kilo seguem sem preço real", e)
        nous_meta = {}
        kilo_meta = {}

    metadata = build_metadata_index(inventory, use_cache=use_cache)

    # Cross-join de metadados: índice global (models.dev) + metadados live
    # de Nous/Kilo Code (preço real + campos funcionais).
    from benchmark_pipe.map_source import _load_models_dev_index
    models_dev_index = _load_models_dev_index()
    merged_meta = dict(models_dev_index)
    merged_meta.update(nous_meta)
    merged_meta.update(kilo_meta)

    # Providers com fonte -> normaliza (com merge Hermes IDs × metadados)
    all_models = []
    nv_raw = metadata.get("nvidia", [])
    nvidia_models = normalize_nvidia(nv_raw, hermes_inventory=inventory)
    # Single source of IDs = Hermes cache. IDs do Hermes sem metadados em
    # models_dev (antigos/deprecados) tentam resolução por família (ex.:
    # mistralai/mistral-large-4-1t-a52b -> família mistral-large-4) e,
    # falhando, viram passthrough N/D — nunca drop.
    nv_meta_ids = {m.model_id for m in nvidia_models}
    nvidia_missing = set(inventory.get("nvidia", set())) - nv_meta_ids
    all_models += nvidia_models
    nvidia_resolved: list = []
    for mid in sorted(nvidia_missing):
        fam = resolve_nvidia_family(mid, models_dev_index)
        if fam:
            from benchmark_pipe.normalize import (
                UnifiedModel,
                apply_canonical,
                derive_is_free,
            )
            limit = fam.get("limit") or {}
            ctx = limit.get("context")
            modalities = fam.get("modalities") or {}
            um = UnifiedModel(
                provider="nvidia",
                model_id=mid,
                display_name=fam.get("name") or mid,
                context_k=(ctx // 1024) if isinstance(ctx, int) else None,
                tool_call=fam.get("tool_call"),
                reasoning=fam.get("reasoning"),
                multimodal=fam.get("attachment")
                or "image" in (modalities.get("input") or []),
                open_weights=fam.get("open_weights"),
                family=fam.get("family"),
                structured_output=fam.get("structured_output"),
                price_in=None,
                price_out=None,
                is_free=derive_is_free("nvidia", mid, None, None),
                source="models.dev-family",
                release_date=fam.get("release_date"),
                modalities_in=fam.get("modalities_in"),
                modalities_out=fam.get("modalities_out"),
                max_output_tokens=limit.get("output"),
                knowledge_cutoff=fam.get("knowledge"),
                attachment=fam.get("attachment"),
            )
            apply_canonical(um)
            nvidia_resolved.append(um)
    all_models += nvidia_resolved
    nvidia_still_missing = nvidia_missing - {m.model_id for m in nvidia_resolved}
    all_models += passthrough_ids_enriched(
        "nvidia", nvidia_still_missing, models_dev_index, hermes_inventory=inventory
    )

    or_raw = metadata.get("openrouter", [])
    all_models += normalize_openrouter(or_raw, meta_index=models_dev_index)

    # Providers sem fonte -> passthrough com metadados live (preço real p/ is_free)
    no_source = [p for p in inventory if p not in ("nvidia", "openrouter")]
    live_free = {
        "kilocode": kilo_free_ids,
        "nous": nous_free_ids_live,
    }
    for prov in no_source:
        all_models += passthrough_ids_enriched(
            prov,
            inventory[prov],
            merged_meta,
            hermes_inventory=inventory,
            live_free_ids=live_free.get(prov),
        )

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

    # Guarda de paridade: compara o dashboard com os catálogos live. Qualquer
    # divergência (modelo do provider sem display, preço 0 fora do filtro FREE)
    # é registrada em data/catalog_parity.json e lançada como alerta no cron.
    try:
        from benchmark_pipe.catalog import fetch_all
        live_catalogs = fetch_all(use_cache=use_cache)
        parity = reconcile(all_models, live_catalogs, hermes_inventory=inventory)
        parity_path = Path("data") / "catalog_parity.json"
        parity_path.parent.mkdir(parents=True, exist_ok=True)
        parity_path.write_text(
            json.dumps(parity, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for line in format_report(parity):
            logger.info("paridade: %s", line)
    except Exception as e:  # noqa: BLE001
        logger.warning("reconciliação de catálogo falhou (não bloqueia): %s", e)

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

    # Gate: roda pytest no projeto.
    # Interpreter resolvido por _resolve_gate_exe() (nível de módulo, testável):
    # chain BENCH_PYTEST_PYTHON > `py` launcher > python3 > sys.executable.
    # Histórico: (1) tools/python-3.X+... do Hermes é recriado a cada `hermes
    # update` e perde os pip pkgs (25/09, 28/09, 01/10); (2) 10-11/10 o
    # python3 do PATH era o stub da Microsoft Store (aliases recriados 09/10
    # 14:05) → UnicodeDecodeError 0xe3 → "pytest falhou: None". `py` = PSF
    # Python Manager, launcher real com pytest.
    gate_exe = _resolve_gate_exe()
    res = subprocess.run(
        [gate_exe, "-m", "pytest", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # stderr do subprocess pode vir em CP1252 — nunca decodifica explodindo
    )
    if res.returncode != 0:
        logger.error("pytest falhou:\n%s", res.stdout or res.stderr)
        return 1
    logger.info("pytest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())