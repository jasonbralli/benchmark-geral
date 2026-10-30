"""nim_pipeline.liveness
=======================

Teste diário de liveness ("ping mínimo") nos modelos do NVIDIA NIM free tier.

Objetivo: identificar quais modelos estão REALMENTE vivos, funcionando e
respondendo ANTES de iniciar os trabalhos do dia — sem perder 10-20 min
aguardando um modelo morto (410/404). Feature do benchmark-geral
(absorve o plano .hermes/plans/2026-10-30_seletor-modelo-diario.md).

Portas rígidas (descarta o modelo):
    1. Liveness  — ping mínimo: POST /v1/chat/completions, max_tokens=1,
                   stream=true, timeout 25 s.
    2. Tipo      — chat/instruct (exclui embeddings/guard/rerank/VL-only,
                   via nim_pipeline.filter.is_excluded + modalities).
    3. Free tier — catálogo NIM é free tier por definição da conta; um
                   modelo só sai se o metadado de custo (models.dev) for
                   conhecido e > US$ 0. Sem metadado → ping decide.

Pontuação (maior = melhor; mortos ficam com score -1):
    +30 família Nemotron (first-party, já validada neste ambiente)
    +0..20 TTFT medido no ping (menor = melhor; 0 s → 20 pts, 10 s+ → 0)
    +0..10 contexto (mesma fórmula de benefit/ctx do benchmark_pipe/score.py)
    +0..15 throughput do AA Data API (tok/s do consolidated, se houver)
    +5  confirmado vivo no dia anterior (histórico do cache)

O script APENAS RECOMENDA — nunca altera config.yaml nem aplica em
produção sem autorização do Jason (regra de ouro do plano).

Cache por dia: data/liveness_daily.json (1 execução/dia; --force re-pinga).

Uso:
    py -3.13 -m nim_pipeline.liveness            # roda o ping (cache do dia se houver)
    py -3.13 -m nim_pipeline.liveness --status   # lê o cache do dia (sem rede)
    py -3.13 -m nim_pipeline.liveness --force    # ignora cache e re-pinga

Integração: scripts/curate_daily.py passo 1.5 (best-effort, alerta só em
anomalia) e scripts/rotate_best_free.py (marca modelos da chain como
🩺 vivo / 🔴 morto no alerta diário do Telegram).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from math import log2
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)

NIM_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"
NIM_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
HERMES_ENV = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"
OUT_PATH = ROOT / "data" / "liveness_daily.json"

TIMEOUT_S = 25.0   # porta rígida do plano: falha rápido, não trava
WORKERS = 4        # pings paralelos limitados (plano: ~4 por vez)

# Mapa de classificação HTTP → status (410/404 = modelo morto, não shed)
_HTTP_STATUS = {
    400: "bad_request",
    401: "auth",
    403: "forbidden",
    404: "not_found",
    410: "gone",
    429: "quota",
}
DEAD_STATUSES = {"gone", "not_found"}  # 410/404 — o alvo do anti-frustração


def read_api_key() -> str:
    """Lê NVIDIA_API_KEY (env primeiro, depois .env do Hermes). Nunca imprime."""
    key = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    if key:
        return key
    try:
        if HERMES_ENV.exists():
            for line in HERMES_ENV.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("NVIDIA_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    raise RuntimeError(
        "NVIDIA_API_KEY não encontrada (env ou %LOCALAPPDATA%/hermes/.env)"
    )


def _post(req: urllib.request.Request, timeout: float):
    """Ponto único de rede (facilita mock nos testes)."""
    return urllib.request.urlopen(req, timeout=timeout)


def ping_model(model_id: str, api_key: str, timeout: float = TIMEOUT_S) -> dict:
    """Ping mínimo de liveness em 1 modelo.

    Requisição única chat/completions, max_tokens=1, stream=true — mede o
    TTFT (1º chunk SSE de conteúdo). Classifica sem nunca expor a key.
    """
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
        "stream": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        NIM_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "benchmark-geral-liveness/1.0",
        },
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with _post(req, timeout) as resp:
            ttft_ms = None
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:") and "[DONE]" not in line:
                    if ttft_ms is None:
                        ttft_ms = (time.monotonic() - t0) * 1000.0
        total_ms = (time.monotonic() - t0) * 1000.0
        return {
            "model_id": model_id, "alive": True, "status": "ok",
            "http_code": 200,
            "ttft_ms": round(ttft_ms) if ttft_ms is not None else None,
            "total_ms": round(total_ms),
        }
    except urllib.error.HTTPError as e:
        e.close()
        status = _HTTP_STATUS.get(e.code, "server" if e.code >= 500 else "http_error")
        return {
            "model_id": model_id, "alive": False, "status": status,
            "http_code": e.code, "error": str(e.reason)[:120],
        }
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {
            "model_id": model_id, "alive": False, "status": "network",
            "http_code": None, "error": str(e)[:120],
        }


def fetch_catalog_ids(api_key: str) -> list[str]:
    """IDs do catálogo NIM ao vivo (GET /v1/models — o que a conta enxerga)."""
    req = urllib.request.Request(
        NIM_MODELS_URL,
        headers={"Authorization": f"Bearer {api_key}",
                 "User-Agent": "benchmark-geral-liveness/1.0"},
    )
    with _post(req, 30.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    items = data.get("data") or []
    ids = [it.get("id") for it in items if it.get("id")]
    if not ids:
        raise RuntimeError("catálogo NIM /v1/models vazio")
    logger.info("Catálogo NIM: %d modelos", len(ids))
    return ids


def load_metadata() -> dict[str, dict]:
    """Metadados por id (models.dev via nim_pipeline.fetch, best-effort).

    Acrescenta tok/s medido pelo AA Data API do cache consolidado.
    Falha aqui NÃO bloqueia: sem metadados, todas as portas estáticas
    passam e o ping decide.
    """
    metas: dict[str, dict] = {}
    try:
        from nim_pipeline.fetch import fetch_nvidia_models
        for m in fetch_nvidia_models(use_cache=False):
            metas[m["id"]] = m
        logger.info("Metadados models.dev: %d modelos", len(metas))
    except Exception as e:  # noqa: BLE001 — best-effort
        logger.warning("models.dev indisponível (%s) — portas estáticas relaxadas", e)
    try:
        cons = json.loads(
            (ROOT / "data" / "consolidated_models.json").read_text(encoding="utf-8")
        )
        for m in cons.get("ranked", []):
            mid = m.get("model_id")
            if not mid:
                continue
            meta = metas.setdefault(mid, {"id": mid})
            tok = (m.get("tok_s") or m.get("tokens_per_s")
                   or m.get("tok_per_s")
                   or m.get("median_output_tokens_per_second"))
            if tok:
                meta["tok_s"] = tok
    except Exception:  # noqa: BLE001
        pass
    return metas


def select_candidates(catalog_ids: list[str], metas: dict[str, dict]) -> list[str]:
    """Portas estáticas do plano (tipo chat/instruct + free) sobre o catálogo."""
    from nim_pipeline.filter import is_excluded
    out: list[str] = []
    for mid in catalog_ids:
        meta = metas.get(mid) or {}
        blob = {
            "id": mid,
            "family": meta.get("family"),
            "name": meta.get("name", ""),
            "description": meta.get("description", ""),
            "modalities": meta.get("modalities") or {"input": ["text"], "output": ["text"]},
        }
        if meta and is_excluded(blob):
            continue  # embeddings/guard/rerank/VL-only/specialistas
        if meta:
            cost = meta.get("cost") or {}
            if (cost.get("input") or 0) > 0 or (cost.get("output") or 0) > 0:
                continue  # pago conhecido → fora do free tier
            mods = meta.get("modalities") or {}
            if mods and ("text" not in mods.get("input", [])
                         or "text" not in mods.get("output", [])):
                continue  # sem texto in/out → não é chat geral
        out.append(mid)
    return out


def score_model(result: dict, meta: dict | None, prev_alive: bool) -> float:
    """Score composto do plano. Mortos → -1 (sempre embaixo)."""
    if not result.get("alive"):
        return -1.0
    s = 0.0
    if "nemotron" in result["model_id"].lower():
        s += 30.0
    ttft = result.get("ttft_ms")
    if ttft is not None:
        s += max(0.0, 20.0 - (ttft / 1000.0) * 2.0)
    ctx = ((meta or {}).get("limit") or {}).get("context") or 0
    if ctx:
        s += min(10.0, 10.0 * (log2(max(ctx / 1024, 8)) - 3) / 14)
    tok = (meta or {}).get("tok_s") or 0
    if tok:
        s += min(15.0, tok * 0.15)
    if prev_alive:
        s += 5.0
    return round(s, 1)


def run_liveness(
    force: bool = False,
    workers: int = WORKERS,
    timeout: float = TIMEOUT_S,
    out_path: Path = OUT_PATH,
    _ping: Callable | None = None,
) -> dict:
    """Roda o ciclo completo do dia (ou devolve o cache se já rodou hoje).

    _ping é injetável para os testes (default: ping_model real).
    """
    ping = _ping or ping_model
    today = date.today().isoformat()
    prev = load_daily(out_path)
    if prev and prev.get("date") == today and not force:
        logger.info("Liveness de hoje já existe (%s) — reusando cache", out_path)
        return prev

    key = read_api_key()
    metas = load_metadata()
    try:
        ids = fetch_catalog_ids(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("Catálogo NIM falhou (%s) — usando models.dev", e)
        ids = sorted(metas.keys())
        if not ids:
            raise RuntimeError("Nem catálogo NIM nem models.dev disponíveis") from e

    cands = select_candidates(ids, metas)
    logger.info("Candidatos ao ping: %d/%d", len(cands), len(ids))
    prev_alive = {r.get("model_id") for r in (prev or {}).get("results", [])
                  if r.get("alive")}

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(lambda m: ping(m, key, timeout), cands):
            res["score"] = score_model(res, metas.get(res["model_id"]),
                                       res["model_id"] in prev_alive)
            results.append(res)
    results.sort(key=lambda r: -(r.get("score") or -1.0))

    prev_by_id = {r.get("model_id"): r for r in (prev or {}).get("results", [])}
    new_dead = [
        {"model_id": r["model_id"], "status": r["status"], "http_code": r.get("http_code")}
        for r in results
        if r["status"] in DEAD_STATUSES and prev_by_id.get(r["model_id"], {}).get("alive")
    ]
    new_alive = [r["model_id"] for r in results
                 if r["alive"] and not prev_by_id.get(r["model_id"], {}).get("alive")
                 and prev_by_id]

    alive = [r for r in results if r["alive"]]
    lv = {
        "date": today,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "integrate.api.nvidia.com/v1/models + models.dev",
        "total_catalog": len(ids),
        "total_candidates": len(cands),
        "alive_count": len(alive),
        "dead_count": len(results) - len(alive),
        "recommended": alive[0]["model_id"] if alive else None,
        "new_dead": new_dead,
        "new_alive": new_alive,
        "results": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(lv, f, ensure_ascii=False, indent=2)
    logger.info("Liveness salvo: %s (%d vivos / %d candidatos)",
                out_path, len(alive), len(cands))
    return lv


def anomalies(lv: dict) -> list[str]:
    """Linhas de alerta SÓ em anomalia (dia normal → [] — stdout limpo)."""
    out: list[str] = []
    if (lv.get("alive_count") or 0) == 0:
        out.append("🩺 LIVENESS: NENHUM modelo NIM free vivo hoje!")
    nd = lv.get("new_dead") or []
    if nd:
        det = ", ".join(f"{d['model_id']} ({d['status']})" for d in nd[:10])
        out.append(f"🩺 Liveness: novos mortos (410/404) desde ontem: {det}")
    return out


def build_summary(lv: dict, top: int = 3) -> str:
    """Resumo curto em texto puro (stdout / --status)."""
    d = lv.get("date", "?")
    rec = lv.get("recommended") or "—"
    lines = [
        f"🩺 Liveness NIM {d}: {lv.get('alive_count', 0)} vivos / "
        f"{lv.get('total_candidates', 0)} candidatos "
        f"(catálogo {lv.get('total_catalog', 0)})",
        f"Recomendado: {rec}",
    ]
    alive = [r for r in lv.get("results", []) if r.get("alive")]
    if alive:
        rank = " > ".join(
            f"{r['model_id']} ({r.get('ttft_ms') or '?'}ms, {r.get('score')})"
            for r in alive[:top]
        )
        lines.append(f"Top {min(top, len(alive))}: {rank}")
    dead = [r for r in lv.get("results", []) if not r.get("alive")]
    if dead:
        rank = ", ".join(f"{r['model_id']} ({r['status']})" for r in dead[:15])
        extra = f" … +{len(dead) - 15}" if len(dead) > 15 else ""
        lines.append(f"Mortos ({len(dead)}): {rank}{extra}")
    return "\n".join(lines)


def ping_label(res: dict) -> str:
    """Rótulo curto p/ o alerta do rotate_best_free (chain atual)."""
    if res.get("alive"):
        ttft = res.get("ttft_ms")
        return f"🩺 ok {ttft}ms" if ttft is not None else "🩺 ok"
    code = res.get("http_code") or res.get("status") or "?"
    return f"🔴 {code}"


def liveness_map(path: Path | None = None) -> dict[str, dict]:
    """{model_id: result} do liveness DE HOJE ({} se arquivo ausente/velho).

    Override de caminho via env LIVENESS_JSON (mesmo padrão de
    PROVIDERS_DATA_DIR/HERMES_CONFIG_YAML do projeto).
    """
    p = Path(os.environ.get("LIVENESS_JSON", "")) if os.environ.get("LIVENESS_JSON") \
        else (path or OUT_PATH)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("date") != date.today().isoformat():
            return {}
        return {r.get("model_id"): r for r in d.get("results", []) if r.get("model_id")}
    except Exception:  # noqa: BLE001 — ausente/ilegível = sem dados
        return {}


def load_daily(path: Path = OUT_PATH) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Liveness diário dos modelos NIM free")
    ap.add_argument("--force", action="store_true", help="ignora cache do dia e re-pinga")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--timeout", type=float, default=TIMEOUT_S)
    ap.add_argument("--top", type=int, default=3, help="modelos no resumo")
    ap.add_argument("--status", action="store_true",
                    help="lê o cache do dia (sem rede)")
    ap.add_argument("--json", action="store_true", help="imprime o JSON completo")
    args = ap.parse_args(argv)

    if args.status:
        lv = load_daily()
        if not lv:
            print("Sem liveness de hoje. Rode: py -3.13 -m nim_pipeline.liveness")
            return 2
        print(build_summary(lv, top=args.top))
        return 0

    try:
        lv = run_liveness(force=args.force, workers=max(1, args.workers),
                          timeout=args.timeout)
    except Exception as e:  # noqa: BLE001
        logger.error("Liveness falhou: %s", e)
        return 2
    if args.json:
        print(json.dumps(lv, ensure_ascii=False, indent=2))
    else:
        print(build_summary(lv, top=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
