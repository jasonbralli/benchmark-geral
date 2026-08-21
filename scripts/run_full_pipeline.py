#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_full_pipeline.py
====================
Orquestrador master: sincroniza modelos do Hermes e atualiza o dashboard.

Uso:
    python run_full_pipeline.py              # sync + update
    python run_full_pipeline.py --refresh    # sync + update com force refresh
    python run_full_pipeline.py --dry-run    # só detecta, não modifica

Fluxo:
    1. sync_hermes_models.py → detecta novos modelos NVIDIA no cache Hermes
    2. update_pipeline.py → aplica merge, filtro, enrich, regenera dashboard
    3. Retorna status consolidado
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def run_step(name: str, cmd: list[str]) -> bool:
    """Roda um passo do pipeline. Retorna True se sucesso."""
    logger.info(f"--- {name} ---")
    result = subprocess.run(
        cmd,
        cwd=BASE,
        capture_output=True,
        text=True,
        timeout=300,
    )
    # Loga saída
    for line in result.stdout.splitlines():
        if line.strip():
            logger.info(f"  {line}")
    for line in result.stderr.splitlines():
        if line.strip():
            logger.warning(f"  {line}")

    if result.returncode != 0:
        logger.error(f"{name} falhou (exit {result.returncode})")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Pipeline completo Hermes→Dashboard")
    parser.add_argument("--refresh", action="store_true", help="Force refresh do models.dev")
    parser.add_argument("--dry-run", action="store_true", help="Só detecta, não modifica")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    logger.info("========================================")
    logger.info("  Pipeline Completo: Hermes → Dashboard")
    logger.info("========================================")

    # Step 1: Sync Hermes
    sync_cmd = [sys.executable, "sync_hermes_models.py"]
    if args.dry_run:
        sync_cmd.append("--dry-run")
    if args.verbose:
        sync_cmd.append("-v")

    if not run_step("1. Sincronização Hermes", sync_cmd):
        logger.error("Sync falhou. Abortando.")
        sys.exit(1)

    # Step 2: Update pipeline
    update_cmd = [sys.executable, "update_pipeline.py"]
    if args.refresh:
        update_cmd.append("--refresh")
    if args.verbose:
        update_cmd.append("-v")

    if not run_step("2. Atualização Pipeline", update_cmd):
        logger.error("Update falhou. Abortando.")
        sys.exit(1)

    logger.info("========================================")
    logger.info("  Pipeline concluído com sucesso!")
    logger.info("========================================")


if __name__ == "__main__":
    main()