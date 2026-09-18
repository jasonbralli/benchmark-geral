# Plano: Limitar Ranking (v2.7 backlog)

> Status: aprovado, aguardando implementação. Escolha: **B+C híbrido**.
> Data: 18/09/2026

## Decisão
1074 modelos ranked → render inicial de **top 50**, com barra "mostrar mais".

## Spec B + C

### Estado
```js
state.limit = 50  // default
// persistido em localStorage['bench_limit']
```

### Render
- `renderRanked()`
  - `var filtered = DATA.ranked.filter(...todas guards...)` ← filtra dataset inteiro
  - `var visible = filtered.slice(0, state.limit)`
  - Renderiza só `visible`
  - Após `<tbody>`, renderiza barra de limite em `<div id="limitBar">`

### Barra de limite
```
Mostrando 50 de 1074   [+50]  [+200]  [Todos]   (| Top 50 ▲  quando state.limit = Infinity)
```
- Botões: `+50`, `+200`, `Todos` (= `Infinity`), e quando todos: `Top 50 ▲` para re-colapsar.
- Sempre mostrar "X de Y" respeitando filtros ativos no momento.

### Persistência
- `localStorage.setItem('bench_limit', state.limit)` a cada mudança
- No boot: `state.limit = parseInt(localStorage.getItem('bench_limit')) || 50`

### Interações
- `applyPreset()` reseta `state.limit = 50` (novo contexto = default)
- Mudança em qualquer filtro NÃO reseta limit (usuário que expandiu quer ver)
- `state.sortKey` muda: mantém limit

### Bônus
- Botão "📋 Copiar top 10 markdown" no header do Ranking — cola direto em notes/reddit.

## Arquivos tocando
- `template_consolidado.html` (único)
  - `<div id="limitBar">` após a tabela
  - `renderLimitBar(total, limit)` nova função
  - patches em `renderRanked` (slice) + init (carrega localStorage) + applyPreset (reset)
- Testes: acrescentar `tests/test_build.py::test_payload_limit_meta` se expormos via payload (opcional; como é front-end, talvez dispense teste Python)

## Por que NÃO as outras
- **Paginação clássica**: quebra ctrl+F, ruins para comparação entre posições distantes.
- **Virtualização/scroll infinito**: complexidade alta, ganho marginal com só 1074 linhas.
- **Cluster hierárquico**: muda paradigma de rank linear — perde a leitura de score.

## Validação
1. Chrome headless dump-dom confere `#limitBar` e só 50 rows no DOM.
2. Click "Todos" fluxo manual (browser test) → 1074 rows.
3. `localStorage` persiste após reload.
4. Idempotência do build.
