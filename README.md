# NIM Ranking — Dashboard de Capacidade de Modelos NVIDIA

Dashboard estático (file://) que visualiza o ranking de capacidade dos modelos
NVIDIA NIM, atualizado automaticamente por um pipeline de dados.

## O que é

Ranking de **LLMs de chat/instruct** do NVIDIA NIM (23 modelos — Tier S + A),
filtrando apenas modelos com capacidade agentic moderna:

- `tool_call=True` (essencial para uso em agentes)
- `reasoning=True` **OU** lançado em >= 2026
- `limit.context >= 128K`
- Exclui: embeddings, vision-only pequenos, safety, translation, retrieval

Os rankings são **calibrados** pelo **Artificial Analysis Intelligence Index
v4.1** — score agregado third-party (0-100) que combina:
- **Agents (34%)** — AA-Omniscience, Terminal-Bench, SWE-bench agentic
- **Coding (24%)** — AA-Coding-Agent Index
- **Scientific Reasoning (24%)** — GPQA-Diamond, MMLU-Pro-Sci
- **General (18%)** — MMLU-Pro, HLE

Calibração de estrelas AA: 5★ ≥50 | 4★ ≥35 | 3★ ≥20 | 2★ ≥10 | 1★ <10
> Fonte: https://artificialanalysis.ai/methodology/intelligence-benchmarking

## Arquitetura

```
models.dev/api.json ──► nim_pipeline/fetch.py ──► data/nvidia_models_raw.json (cache)
                             │
                             ▼
                     nim_pipeline/filter.py  (critério Opção A → 23 modelos)
                             │
                             ▼
                     nim_pipeline/enrich.py  (+ AA Index v4.1, + display_name)
                             │
                             ▼
                     build_dashboard.py  (monta payload + injeta em template.html)
                             │
                             ▼
                          dashboard.html   (output final)
```

## Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `nim_pipeline/fetch.py` | Busca inventário atualizado do models.dev (open-source) |
| `nim_pipeline/filter.py` | Aplica critério Opção A (tool_call + reasoning/recent + 128K) |
| `nim_pipeline/enrich.py` | Adiciona AA Index + estrelas calibradas + display_name |
| `build_dashboard.py` | Orquestrador — lê MD, monta JSON, injeta em template.html |
| `run_pipeline.py` | Entrypoint — roda pipeline completo + opcional pytest |
| `template.html` | Template canônico com marker `//NIM_RANKING_DATA//` |
| `dashboard.html` | **Output** gerado (não edite manualmente) |
| `MODELOS_NVIDIA_NIM_RANKING.md` | Curadoria humana (scorecard top 10 por AA) |
| `tests/` | Suíte pytest (39 testes) |

## Uso

```bash
# Regenerar dashboard (usa cache se existir)
python run_pipeline.py

# Forçar re-busca do inventário + rodar testes
python run_pipeline.py --refresh --test

# Roda apenas a suíte de testes
python -m pytest -q
```

## Agendamento quinzenal

O Hermes cron job **`benchmark-geral-nim-quinzenal`** roda o pipeline a cada
15 dias (`0 7 */15 * *`) e reporta os resultados no chat.

## Scorecard (Top 10 por AA Index)

Ranking ordenado pelo **AA Index** (fonte third-party oficial). Modelos sem
score AA aparecem no final com `N/D`.

| AA Rank | Modelo | AA Index | AA ★ | Tier |
|--------:|--------|---------:|:----:|:----:|
| 1 | `z-ai/glm-5.2` | 51 | ★★★★★ | S |
| 2 | `deepseek-ai/deepseek-v4-flash-0731` | 50 | ★★★★★ | S |
| 3 | `minimaxai/minimax-m3` | 44 | ★★★★☆ | S |
| 4 | `moonshotai/kimi-k2.6` | 43 | ★★★★☆ | S |
| 5 | `thinkingmachines/inkling` | 41 | ★★★★☆ | S |
| 6 | `nvidia/nemotron-3-ultra-550b-a55b` | 38 | ★★★★☆ | S |
| 7 | `nvidia/nemotron-3-super-120b-a12b` | 26 | ★★★☆☆ | A |
| 8 | `openai/gpt-oss-120b` | 24 | ★★★☆☆ | — |

## ⚠️ Notas importantes

- **Modelo Hermes atual**: `deepseek-ai/deepseek-v4-flash` (exibido como
  `-0731` para refletir o checkpoint 31/jul/2026 servido pela API NIM).
- **V4-Flash vs V4-Pro**: são modelos distintos. V4-Flash-0731 supera
  V4-Pro-Preview em agent tasks (Terminal-Bench 82.7% vs 72.1%).
- **Tier C/D removidos** (14/08/2026): Code Specialist (8 modelos) e Vision/VLM
  (11 modelos) não competem com LLMs de chat/instruct atuais.
- **AA Index**: apenas ~7/23 modelos têm score oficial third-party. Os demais
  aparecem como N/D — não inventar scores.

## Regeneração

- Para mudar o **filtro** (critério): edite `nim_pipeline/filter.py`.
- Para mudar o **layout/JS** do dashboard: edite `template.html` (mantendo o
  marker `//NIM_RANKING_DATA//`), depois rode `python run_pipeline.py`.