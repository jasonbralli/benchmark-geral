"""scripts/curate_daily.py
=======================

Curadoria diária do benchmark_geral — executada após probe health (07:30).

Fluxo:
1.  **Provider health check** — probe em todos os providers configurados
    (acumula em provider_health.jsonl). Identifica providers inativos.
2.  **Refresh caches** — models.dev, OpenRouter, AA (se expirados >24h).
3.  **Snapshot anterior** — conta modelos em consolidated_models.json
    (para detectar quedas >5% = possível deslistagem).
4.  **Pipeline completo** — extract → map_source → normalize → dedup →
    enrich (AA) → score → build → consolidated_models.json + index.html.
5.  **Validação mudanças**:
    - Provider desapareceu da listagem Hermes → alerta
    - Count caiu >5% vs ontem → alerta
    - Novo provider apareceu → alerta informativo
6.  **Auto-commit** se dashboard mudou.
7.  **Auto-push para GitHub** se confirmado.

Telegram: alertas via send_telegram() (probe_health.py), silencioso em caso verde.

Uso: `python scripts/curated_daily.py` (projeto cwd).
Exit codes: 0=ok silencioso, 1=alertas, 2=falha crítica.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from benchmark_pipe.extract import extract_provider_models  # noqa: E402
from benchmark_pipe.probe_health import (  # noqa: E402
    aggregate,
    append_jsonl,
    detect_alert,
    read_jsonl,
    run as probe_run,
    send_telegram,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("curate_daily")

# Diretórios-chave
DATA_DIR = ROOT / "data"
CONSOLIDATED = DATA_DIR / "consolidated_models.json"
PREV_SNAPSHOT = DATA_DIR / "consolidated_prev.json"
PROVIDER_HEALTH_JSONL = DATA_DIR / "provider_health.jsonl"
PROVIDER_HEALTH_JSON = DATA_DIR / "provider_health.json"

# Thresholds
DROP_THRESHOLD_PCT = 5.0  # alerta se modelos caírem >5% vs ontem
MIN_MODELS = 50  # sanity check


def _run_cmd(cmd: list[str], check=True, timeout=300) -> tuple[int, str, str]:
    """Roda comando no ROOT, captura stdout/stderr."""
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        logger.error("Comando falhou: %s\n%s", cmd, p.stderr[-300:])
    return p.returncode, p.stdout, p.stderr


def _snapshot_counts() -> dict:
    """Snapshot do consolidated atual para detectar deltas."""
    if not CONSOLIDATED.exists():
        return {}
    d = json.loads(CONSOLIDATED.read_text(encoding="utf-8"))
    ranked = d.get("ranked", [])
    non_ranked = d.get("non_ranked", [])
    by_provider = {}
    for m in ranked + non_ranked:
        p = m.get("provider", "?")
        by_provider[p] = by_provider.get(p, 0) + 1
    return {
        "ranked_count": len(ranked),
        "non_ranked_count": len(non_ranked),
        "total": len(ranked) + len(non_ranked),
        "by_provider": by_provider,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def _save_snapshot(snap: dict):
    PREV_SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_prev_snapshot() -> dict | None:
    if not PREV_SNAPSHOT.exists():
        return None
    try:
        return json.loads(PREV_SNAPSHOT.read_text(encoding="utf-8"))
    except Exception:
        return None


def _check_alerts(curr: dict, prev: dict | None, alerts: list[str]):
    """Detecta anomalias no inventário."""
    if prev:
        prev_total = prev.get("total", 0)
        curr_total = curr.get("total", 0)
        if prev_total > 0:
            drop_pct = 100 * (prev_total - curr_total) / prev_total
            if drop_pct > DROP_THRESHOLD_PCT:
                alerts.append(
                    f"⚠️ Count caiu {drop_pct:.1f}% ({prev_total} → {curr_total})"
                )

        # Provider desapareceu?
        prev_provs = set(prev.get("by_provider", {}).keys())
        curr_provs = set(curr.get("by_provider", {}).keys())
        missing = prev_provs - curr_provs
        new = curr_provs - prev_provs
        if missing:
            alerts.append(f"⚠️ Providers REMOVIDOS: {', '.join(sorted(missing))}")
        if new:
            alerts.append(f"ℹ️ Providers NOVOS: {', '.join(sorted(new))}")

    # Sanity check total
    if curr.get("total", 0) < MIN_MODELS:
        alerts.append(f"⚠️ Total muito baixo: {curr['total']} < {MIN_MODELS}")


def main() -> int:
    alerts: list[str] = []
    logger.info("=== benchmark-curatoria-diario ===")

    # 1. PROVIDER HEALTH — probe antes de qualquer coisa
    logger.info("Passo 1: provider health probe...")
    probe_cfg = json.loads((ROOT / "scripts" / "probe_config.json").read_text(encoding="utf-8"))
    probe_res = probe_run(
        config_path=ROOT / "scripts" / "probe_config.json",
        jsonl_path=PROVIDER_HEALTH_JSONL,
        aggregate_path=PROVIDER_HEALTH_JSON,
        alert=True,
    )
    if probe_res["alerts"]:
        alerts.extend([f"🏥 {a}" for a in probe_res["alerts"]])

    # 2. REFRESH CACHES — models.dev / OpenRouter / AA
    logger.info("Passo 2: refresh caches (--refresh)...")
    # Forçamos refresh das APIs (modelos.dev, OpenRouter, AA) de forma leve.
    # run_consolidated.py --refresh faz isso, mas com build. Queremos só
    # refresh aqui, build vem depois.
    code_refresh, _, err_refresh = _run_cmd(
        [sys.executable, "scripts/run_consolidated.py", "--refresh", "--json", str(CONSOLIDATED)],
        check=False,
        timeout=300,
    )
    if code_refresh != 0:
        # fallback: tentar com use-cache se refresh falhar (offline mode)
        logger.warning("Refresh falhou (%s), tentando --use-cache", err_refresh[-200:])
        code_cache, _, err_cache = _run_cmd(
            [sys.executable, "scripts/run_consolidated.py", "--use-cache", "--json", str(CONSOLIDATED)],
            check=False,
            timeout=300,
        )
        if code_cache != 0:
            alerts.append("⚠️ Pipeline falhou mesmo com --use-cache")
            send_telegram("\n".join(alerts))
            return 2

    # 3. SNAPSHOT — comparar com anterior
    logger.info("Passo 3: validando mudanças no inventário...")
    curr = _snapshot_counts()
    prev = _load_prev_snapshot()
    _check_alerts(curr, prev, alerts)
    _save_snapshot(curr)

    # 4. AUTO-COMMIT — commit se consolidated mudou
    logger.info("Passo 4: auto-commit...")
    git_status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    dirty = [l for l in git_status.stdout.splitlines() if l.strip()]
    if dirty:
        # Commit consolidado + index.html
        add_msg = f"dashboard curadoria {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
        _run_cmd(["git", "add", "data/consolidated_models.json", "data/provider_health.json",
                  "data/provider_health.jsonl", "index.html"], check=False)
        commit_res = _run_cmd(
            ["git", "commit", "-m", add_msg],
            check=False,
        )
        if commit_res[0] == 0:
            logger.info("Commit criado: %s", add_msg)
            # 5. AUTO-PUSH
            logger.info("Passo 5: push automático...")
            push_res = _run_cmd(["git", "push", "origin", "main"], check=False)
            if push_res[0] != 0:
                alerts.append(f"⚠️ Push falhou: {push_res[2][-200:]}")
            else:
                logger.info("Push OK: origin main")
        else:
            msg = (commit_res[1] + commit_res[2]).lower()
            if "nothing to commit" not in msg:
                alerts.append(f"⚠️ Commit falhou: {commit_res[2][-200:]}")
            else:
                logger.info("Nada novo para commitar.")
    else:
        logger.info("Working tree limpo — nada a commitar.")

    # Report
    logger.info("=== Resultado: %d alertas ===", len(alerts))
    for a in alerts:
        logger.warning(a)

    if alerts:
        # Envia pro Telegram em modo consolidado
        header = "🤖 benchmark-curatoria-diario\n"
        send_telegram(header + "\n".join(alerts))
        # Saída com os alertas (Hermes cron delivera pro Telegram quando exit != 0)
        print("\n".join(alerts))
        return 1

    return 0  # silencioso


if __name__ == "__main__":
    raise SystemExit(main())
