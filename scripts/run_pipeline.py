"""
run_pipeline.py — entrypoint autônomo do pipeline NIM.

Executa o pipeline completo (fetch → filter → enrich → build) e opcionalmente
roda os testes de sanidade. Usado pelo cronjob quinzenal do Hermes e também
manualmente.

Uso:
    python run_pipeline.py                # usa cache se existir
    python run_pipeline.py --refresh      # força re-busca do inventário
    python run_pipeline.py --test         # roda pytest após o build
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))


def main() -> int:
    parser = argparse.ArgumentParser(description="Roda o pipeline NIM completo.")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-busca inventário (ignora cache).")
    parser.add_argument("--test", action="store_true",
                        help="Roda pytest após o build.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Log detalhado.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Usa cache existente (default).")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    build_args = []
    if args.refresh:
        build_args.append("--refresh")
    else:
        build_args.append("--use-cache")

    # Roda build_dashboard (que importa fetch/filter/enrich)
    import build_dashboard as bd
    # Chama a função main com os args apropriados
    sys.argv = ["build_dashboard.py"] + build_args
    try:
        bd.main()
    except SystemExit as e:
        logging.error(f"build_dashboard falhou: {e}")
        return 1

    if args.test:
        logging.info("Rodando suite de testes...")
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=str(BASE),
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            logging.info(f"Testes OK:\n{res.stdout}")
        else:
            logging.error(f"Testes FALHARAM:\n{res.stdout}{res.stderr}")
            return 1

    logging.info("Pipeline concluído com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())