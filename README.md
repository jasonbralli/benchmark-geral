# Benchmark Consolidado Multi-Provider

Dashboard estático (file:// e GitHub Pages) que ranqueia **modelos LLM por custo × benefício (CxB)**, cobrindo todos os providers do Hermes, atualizado automaticamente por um pipeline Python puro (stdlib, sem novas deps).

## O que é

Uma única visão ranqueada dos modelos que o Hermes realmente serve, pontuados por
**benefit (capacidade) ÷ custo**, calibrada pelo **Artificial Analysis Intelligence Index v4.1** e alimentada em bulk pela **AA Data API v2** (fetch automático, cache 24h).

**Providers com fonte de metadados (entram no ranking CxB):** `nvidia`, `openrouter`.
**Providers sem fonte (inventário N/D, fora do ranking):** `gemini`, `kilocode`,
`huggingface`, `nous`, `opencode-free` — listados por ID para referência.

## Arquitetura do pipeline

```
provider_models_cache.json ──► benchmark_pipe/extract.py      ({provider: set(ids)})
                                    │
                                    ▼
       benchmark_pipe/map_source.py (metadados: models_dev cache p/ nvidia,
                                    │  openrouter API p/ openrouter)
                                    ▼
       benchmark_pipe/normalize.py  ├─ canonicalize()  (alias vendor/sufixo variante)
       (schema unificado)          ├─ dedup_models()   (intra-provider, 1 linha/modelo)
                                    ├─ normalize_nvidia() / normalize_openrouter()
                                    └─ passthrough_ids() → N/D
                                    │
                                    ▼
       benchmark_pipe/enrich.py  (+ AA Data API v2 bulk → aa_index; curado=fallback)
                                    │
                                    ▼
       benchmark_pipe/score.py   (benefit + cxb_score; split rankable vs N/D)
                                    │
                                    ▼
       benchmark_pipe/build.py   (injeta payload em template_consolidado.html,
                                  marker //CONSOLIDATED_DATA//) → dashboard.html (idempotente)
```

## Ranking CxB (score.py)

```python
benefit(m) = min(40, 40·(log2(ctx_k)-3)/14)   # ctx 8K→0 … ~1M→40
           + 15·tool_call + 15·reasoning + 10·multimodal
           + 20·(aa_index/100) se houver
cxb(m) = benefit(m) / (cost + 1)   # free→cost=0 (domina); pagos rank por B/C
```

`is_rankable(m)` = tem `context_k` OU `tool_call` (capacidade de dados completos).
`aa_index` sozinho NÃO rankeia — passthrough N/D ficam fora do ranking.

## Normalização canónica (nomes de modelos)

Resolvido em 22-23/08/2026 — o mesmo modelo lógico não mais duplica no dashboard:

- **`canonicalize()`** resolve aliases de vendor (`deepseek`→`deepseek-ai`, `zai-org`→`z-ai`),
  sufixo de variante (`:free`/`:batch`/`:nitro`) e equivalências conhecidas
  (`...flash` ↔ `...flash-0731`).
- **`dedup_models()`** colapsa duplicatas **intra-provider** (mesmo provider + canónico +
  mesma variante), preservando `aliases` e `divergences`.
- **AA enrich** propaga o mesmo `aa_index` para variantes do mesmo modelo
  (ex: `z-ai/glm-5.2:free` herda AA de `z-ai/glm-5.2`).
- **`data/consolidated_models.json`** expõe `canonical_id`, `variant`, `aliases`,
  `divergences` por modelo — verdade preservada, sem linhas duplicadas.

## Enriquecimento AA Data API v2 (`benchmark_pipe/aa_api.py`)

Bulk fetch paginado: `GET /api/v2/language/models/free?page=N&page_size=200`
(1-4 calls/ciclo, 616 modelos). Cache `data/aa_models_raw.json` TTL 24h (= quota Free).
Key em `AA_API_KEY_benchmark_geral` (env ou `.env`). `401/403/429`/offline → cache
stale → dict curado. Resultado: **~68% dos modelos ranked com AA index** (antes ~8/1032).

## Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `benchmark_pipe/` | Módulos do pipeline: extract, map_source, normalize, enrich, score, build, aa_api |
| `scripts/run_consolidated.py` | **Orquestrador principal** (`--refresh`/`--use-cache`/`--refresh-aa`/`--json`) |
| `scripts/sync_hermes_models.py` | Sincroniza cache do Hermes (detecta modelos NVIDIA NIM novos) |
| `scripts/update_pipeline.py` | Merge + filter + enrich + MD scorecard |
| `scripts/run_full_pipeline.py` | Orquestrador master (sync + update em 1 comando) |
| `template_consolidado.html` | **Canónico** com marker `//CONSOLIDATED_DATA//` (edite aqui para layout/JS) |
| `dashboard.html` | **Output** gerado — nunca edite manualmente |
| `template.html` | **LEGADO NVIDIA** (arquivado, intocado). Marker `//NIM_RANKING_DATA//` |
| `data/aa_models_raw.json` | Cache AA API v2 (gitignored, regenera) |
| `data/nvidia_models_raw.json` | Cache models.dev NVIDIA (gitignored, regenera) |
| `data/openrouter_models_raw.json` | Cache OpenRouter (gitignored, regenera) |
| `data/consolidated_models.json` | Artefato JSON intermediário (versionado) |
| `nim_pipeline/` | Fonte de metadados NVIDIA legada (`fetch/enrich.py` usados pelo consolidado) |
| `tests/` | Suíte pytest (110 testes) |

## Uso

```bash
cd "C:/Users/Jason/Desktop/PROJETOS/02 - WORKING/benchmark_geral"

# Regenerar dashboard (usa caches locais) + roda pytest como gate
python scripts/run_consolidated.py --use-cache --json data/consolidated_models.json

# Re-busca APIs (models.dev + OpenRouter + AA Data API) e regenera
python scripts/run_consolidated.py --refresh --json data/consolidated_models.json

# Apenas rodar testes
python -m pytest -q
```

## GitHub Pages

O dashboard consolidado é publicado em GitHub Pages para acesso web:
https://<usuario>.github.io/benchmark-geral-nim/.

**IMPORTANTE:** GitHub Pages serve apenas arquivos **da raiz** da branch de publicação.
`dashboard.html` deve residir na **raiz** (renomeado/posicionado como o index servido),
não em subdiretório. Após push, a página fica acessível em ~2 min.

## Agendamento quinzenal

Hermes cron job **`benchmark-geral-nim-quinzenal`** roda
`scripts/run_consolidated.py --refresh` a cada segundo segundas-feiras,
com fallback `--use-cache` se rede falhar (local-first).

## Assinatura obrigatória

Todo HTML `index`/`dashboard` inclui no rodapé (`<footer class="site-footer">`) um
link para `https://inovatudo.com` com `target="_blank" rel="noopener"`.

## Scorecard (Top 10 por AA Index — curado)

| AA Rank | Modelo | AA Index | AA ★ |
|--------:|--------|---------:|:----:|
| 1 | `moonshotai/kimi-k3` | 57 | ★★★★★ |
| 2 | `deepseek-ai/deepseek-v4-flash-0731` | 50 | ★★★★★ |
| 3 | `minimaxai/minimax-m3` | 44 | ★★★★☆ |
| 4 | `moonshotai/kimi-k2.6` | 43 | ★★★★☆ |
| 5 | `z-ai/glm-5.2` | 51 | ★★★★★ |
| 6 | `thinkingmachines/inkling` | 41 | ★★★★☆ |
| 7 | `nvidia/nemotron-3-ultra-550b-a55b` | 38 | ★★★★☆ |
| 8 | `nvidia/nemotron-3-super-120b-a12b` | 26 | ★★★☆☆ |

> O dashboard live usa a AA Data API v2 (v4.1, valores mais frescos que o curado).

## Notas

- **`models_dev_cache.json` do Hermes** é a fonte de verdade dos metadados NVIDIA
  (`~/AppData/Local/hermes/models_dev_cache.json`, 102 modelos) — manter antes de
  `data/nvidia_models_raw.json`.
- Free com mesma capability sempre domina pago (é "mais custo-benefício", não "melhor").