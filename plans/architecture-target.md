# Arquitetura Target: Provider Health & Model Inventory

> Registro da visão do usuário (18/09/2026) para implementação futura.

## State Atual vs Target

| Etapa | Estado Atual | Target | Gap |
|-------|-----------|--------|-----|
| **1. Providers** | 7 ativos (gemini, nvidia, openrouter, kilocode, huggingface, nous, opencode-free removido) | Mesmo, + health check diário | ✅ OK |
| **2. Listagem Hermes** | `provider_models_cache.json` (app Hermes) | Idem | ✅ OK |
| **3. Inventário** | `consolidated_models.json` com 1168 modelos | Idem, mas com fonte explícita | ⚠️ Falta coluna `source` normalizada |
| **4. Curadoria** | `normalize.py` (canonicalize, dedup) | + validação automática diária | 🔄 Cron bot não implementado |
| **5. Deduplicação** | `dedup_models()` intra-provider | + cross-provider dedup inteligente | ⚠️ Cross-join existe mas incompleto |
| **6. Compartilhamento info** | `passthrough_ids_enriched` (cross-join) | + fallback hierárquico: Google API → OpenRouter → models.dev | 🔄 Parcial: só models.dev→OpenRouter |
| **7. Enriquecimento** | AA Data API (speed, TTFT, coding, agentic) | + scraping de fontes públicas, + cache perpétuo | 🔄 AA ok, falta outras fontes |

## Ideia Central: Fallback de Metadados

**Problema detectado hoje**: NVIDIA free-tier só expõe reasoning models (kimi-k3). API oficial não tem metadados de ctx/pricing.

**Solução proposta (a implementar)**:

```python
# Nova estratégia em map_source.py ou enrich.py
def get_model_metadata(provider: str, model_id: str) -> ModelMetadata:
    """Tenta múltiplas fontes em ordem de confiança."""
    
    # 1. API oficial do provider (mais atual, mas nem sempre tem todos os campos)
    if provider == "google":
        # Google API não retorna ctx/pricing → skip
        pass
    
    # 2. models.dev cache (Hermes) — tem ctx, pricing, modalities
    if model_id in MODELS_DEV_CACHE:
        return MODELS_DEV_CACHE[model_id]
    
    # 3. OpenRouter API — tem ctx, pricing, tools, reasoning para modelos Google
    if model_id.startswith("google/"):
        or_id = f"google/{model_id.replace('google/', '')}"
        return OPENROUTER_CACHE.get(or_id)
    
    # 4. AA Data API — tem speed, TTFT, coding, agentic
    # ... fallback para AA
    
    return None  # N/D
```

## Cron Diário Proposto

```
Nome: benchmark-curatoria-diario
Schedule: 0 6 * * * (antes do probe health, 07:00)
Script: scripts/curate_daily.py
  1. Refresh provider_models_cache (Hermes app)
  2. Refresh models_dev_cache (se stale >24h)
  3. Refresh openrouter_models_raw.json
  4. Refresh aa_models_raw.json
  5. Rodar dedup + cross-join + propagate
  6. Validar: alerta se modelo count cair >5% (indica deslistagem tipo opencode-free)
  7. Rebuild index.html
  8. Commit + push (opcional)
```

## Decisões de Design

1. **Fonte da verdade**: models.dev > OpenRouter > AA > curadoria manual.
2. **NUNCA inventar**: se não tem fonte, `N/D` explícito (não None implícito).
3. **Deslistagem**: se provider desaparece do `provider_models_cache`, manter modelos por 7 dias com flag `deprecated` antes de remover.
4. **Alertas**: Telegram quando:
   - Provider desaparece da listagem Hermes
   - Count de modelos cai >10% de ontem para hoje
   - Novo provider aparece (oportunidade)

## Próximos Passos (não implementados)

- [ ] Criar `scripts/curate_daily.py`
- [ ] Adicionar flag `deprecated` em `UnifiedModel`
- [ ] Cron `benchmark-curatoria-diario`
- [ ] Testar fallback: remover modelo de models.dev, verificar se OpenRouter supre
