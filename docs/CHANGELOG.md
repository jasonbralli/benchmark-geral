# Changelog — benchmark_geral

## [v2.3.0] — 2026-08-23 — Normalização canónica + Enriquecimento AA Data API

### ✨ Novo: `benchmark_pipe/aa_api.py`
- **Bulk fetch** AA Data API v2: `GET /api/v2/language/models/free?page=N&page_size=200`
  — 1-4 calls por ciclo (616 modelos), não 1/modelo.
- Cache `data/aa_models_raw.json` com **TTL 24h** (= janela da quota Free). `use_cache=True`
  não consome rede (`X-Ratelimit-Remaining: 99→95` validado).
- `build_aa_index_map()` → `{slug_norm: index}` (596 entradas); `lookup_aa_index()` casa
  `canonical_id`↔`slug` tolerando vendor omitido, `:free`, `.`/`_`, prefixo de checkpoint.
- Key `AA_API_KEY_benchmark_geral` (env ou `.env`, sem hardcode). `401/403/429`/offline →
  fallback cache stale → dict curado. Nunca quebra o pipeline.
- **Impacto**: ~8 → **702/1032 modelos ranked com AA index (68%)**.

### 🎯 Normalização canónica de nomes (`normalize.py`, `build.py`, `run_consolidated.py`)
- **`canonicalize()`** resolve aliases de vendor (`deepseek`→`deepseek-ai`,
  `zai-org`→`z-ai`), sufixo de variante (`:free`/`:batch`/`:nitro`) e equivalências
  (`...flash` ↔ `...flash-0731`).
- **`dedup_models()`** colapsa duplicatas **intra-provider** (provider + canónico + variante),
  priorizando o ID exato do Hermes; preserva `aliases`/`divergences`.
- **`enrich_unified()`** agora prioriza o mapa AA API, depois dict curado; propaga AA
  para variantes do mesmo modelo (ex: `z-ai/glm-5.2:free` herda de `z-ai/glm-5.2`).
- **`build.py`** expõe `canonical_id`, `variant`, `aliases`, `divergences` no payload.
- Fonte NVIDIA primária confirmada como `models_dev_cache.json` do Hermes (102 modelos).

### 🔄 Orquestrador
- `run_consolidated.py` chama `dedup_models()` entre normalize e enrich; flag `--refresh-aa`
  força only-AA re-busca; `_maybe_refresh_aa()` usa cache se fresco.

### ⚙️ Infra
- `.gitignore`: adiciona `data/aa_models_raw.json`, `.env`, `.hermes/`,
  `data/hermes_inventory_bruto.*`.
- AA key persistida em `.env` (não commitada).

### 🧪 Testes
- `tests/test_aa_api.py` novo — 12 testes (slug, map, lookup, paginação mockada, cache,
  sem key, 401→stale).
- `test_normalize.py` +97 linhas (regressões GLM/deepseek dedup); `test_enrich_multi.py`
  relaxado p/ aceitar `curado | API`.
- **Gate:** `python -m pytest -q` → **110 passed** (era 98).

### 📊 Impacto CxB (exemplos)
| Modelo | AA curado | AA API v4.1 | Δ | cxb novo |
|---|---|---|---|---|
| `moonshotai/kimi-k3` | 57 | **59.7** | +2.7 | 71.94 |
| `z-ai/glm-5.2` | 51 | **52.6** | +1.6 | 60.52 |
| `minimaxai/minimax-m3` | 44 | **45.4** | +1.4 | 68.88 |
| `deepseek-v4-flash(-0731)` | 50 | **51.8** | +1.8 | 60.36 |

| Métrica | v2.2 | v2.3 |
|---------|------|------|
| Modelos ranked | 1032 | 1032 |
| Com AA index | ~8 | **702 (68%)** |
| Testes pytest | 98 | **110** |
| Fonte AA | curado | **API v2 bulk + curado** |

---

## [v2.2.0] — 2026-08-21 — Sync Hermes + Auto-update

### ✨ Novos Scripts

- **`sync_hermes_models.py`** — Monitora `provider_models_cache.json` do Hermes,
  detecta modelos NVIDIA NIM novos, classifica em (frontier, specialized, variants),
  salva snapshot + TXT.

- **`update_pipeline.py`** — Pipeline auto-completo: merge (models.dev + txt sync),
  filtro Opção A, enrich AA Index, atualiza MD scorecard, regenera dashboard, pytest.

- **`run_full_pipeline.py`** — Orquestrador master: sync + update em 1 comando.

### 🎯 Mudanças Funcionais

- **Cache pipeline**: `nvidia_models_raw.json` agora 101 modelos (era 100).
  Adicionado `moonshotai/kimi-k3` (released 2026-07-16, 2.8T params, 1M context).

- **Scorecard top 10**: novo #1 = `moonshotai/kimi-k3` (AA=57, ★★★★★, Tier S).

- **AA Index calibration**: nova entrada em `nim_pipeline/enrich.py`:
  ```python
  "moonshotai/kimi-k3": {"index": 57, "url": "https://artificialanalysis.ai/models/kimi-k3"}
  ```

- **MD scorecard**: tabela atualizada com kimi-k3 no topo, poolside/laguna-xs-2.1
  como N/D no final.

### 🔄 Cron Job

- Atualizado `benchmark-geral-nim-quinzenal` para usar `run_full_pipeline.py --refresh`
  (antes usava só `run_pipeline.py --refresh`).

### 📚 Skill

- `benchmark-geral-automation` atualizada com:
  - Novos comandos (sync_hermes_models, update_pipeline, run_full_pipeline)
  - Seção "Pipeline Automatizado v2.1"
  - 4 novos pitfalls (Hermes cache filter, scorecard manual vs auto, aa_rank cross-tier, datetime import)

### 🧪 Testes

- 39 testes pytest passando (sem mudanças).
- Novo script `update_pipeline.py` validado end-to-end.

### 📊 Diff resumido

| Métrica | v2.1 | v2.2 |
|---------|------|------|
| Modelos no inventário | 100 | 101 |
| Frontier (Opção A) | 23 | 24 |
| Com AA Index | 7 | 8 |
| Scorecard size | 10 | 10 |
| Scripts Python | 2 | 5 |
| Cron job | manual | auto-sync |

---

## [v2.1.0] — 2026-08-16 — Pipeline Inicial

### Adicionado

- Pipeline Python de ranking NVIDIA NIM.
- Inventário via `models.dev/api.json`.
- Filtro Opção A: tool_call=True AND (reasoning OR release≥2026) AND ctx≥128K.
- AA Intelligence Index v4.1 curado em `enrich.AA_INTELLIGENCE_INDEX`.
- Dashboard estático `dashboard.html` com 4 blocos.
- Cron job quinzenal `benchmark-geral-nim-quinzenal`.
