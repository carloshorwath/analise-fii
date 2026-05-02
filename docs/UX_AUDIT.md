# UX/UI Audit — App Streamlit (Análise de FIIs)

**Data:** 2026-04-24  
**Escopo:** `app/pages/*.py`, `app/components/*.py`, `app/state.py`  
**Contexto:** App para investidor único, lógica em `src/fii_analysis/`

---

## Resumo — 3 Maiores Problemas

### 1. 🔴 Explosão de sessões em `2_Analise_FII.py` (~15 `get_session_ctx()` por render)
**Impacto:** Performance — cada interação (trocar ticker, mudar período) abre ~15 sessões SQLite sequenciais.  
**Arquivo:** `2_Analise_FII.py:60,82,85,95,110,115,119,127,131,141,153,164,195,203,226,239,250,255`  
**Esforço:** Médio — consolidar chamadas em 1-2 sessões e usar `@st.cache_data` nos loaders.

### 2. 🔴 Lógica de negócio em páginas da UI (violação arquitetural)
**Impacto:** Manutenibilidade, testabilidade e DRY — 4 funções estatísticas (~200 linhas) em `8_Fund_EventStudy.py` deveriam estar em `src/`.  
**Arquivo:** `8_Fund_EventStudy.py:60-292` (`get_events`, `calculate_car`, `_nw_pvalue`, `_block_placebo`)  
**Esforço:** Médio — extrair para `src/fii_analysis/models/event_study_cvm.py`.

### 3. 🔴 Gerenciamento de sessão inconsistente → risco de leak
**Impacto:** Conexões SQLite não-fechadas em caso de exceção.  
**Arquivo:** `carteira_ui.py:22-25,29-45,48-58,61-67` (usa `get_session()` manual) vs. restante do app (`get_session_ctx()`)  
**Esforço:** Baixo — trocar `get_session()`/`close()` por `get_session_ctx()`.

---

## Análise por Página

### `1_Panorama.py` (74 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Crítico** | `1_Panorama.py:44` | `col4.metric("IFIX YTD", "n/d")` — métrica hardcoded que nunca é populada. Usuário vê "n/d" permanente sem explicação. |
| 2 | **Médio** | `1_Panorama.py:25-33` | Duas chamadas `get_session_ctx()` separadas (radar + panorama) que poderiam ser uma só. |
| 3 | **Médio** | `1_Panorama.py:68-72` | `coletado = df.iloc[0]` extraído mas só usado para truthiness check. Bloco `st.info` na linha 72 está dentro do `if not df.empty` (linha 48) — nunca é alcançado. |
| 4 | **Baixo** | `1_Panorama.py:59-63` | `column_config` só define 3 de N colunas — restante usa formatação automática inconsistente com `render_panorama_table`. |
| 5 | **Baixo** | `1_Panorama.py:70` | Mensagem instrui usar CLI para atualizar preços — não há link nem botão na UI. |

### `2_Analise_FII.py` (260 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Crítico** | `2_Analise_FII.py:60,82,85,95,110,115,119,127,131,141,153,164,195,203,226,239,250,255` | ~15 sessões SQLite abertas por render. Cada widget de período causa re-render completo. Anti-pattern documentado no CLAUDE.md. |
| 2 | **Alto** | `2_Analise_FII.py:72-79` | Seleção de período via 7 botões + `st.rerun()` — causa re-render full-page. Deveria usar `st.radio` ou `st.segmented_control`. |
| 3 | **Alto** | `2_Analise_FII.py:87-89` | Caminho hardcoded `C:/ProgramData/anaconda3/python.exe scripts/load_database.py` na mensagem de warning — não portátil, não é ação possível pela UI. |
| 4 | **Médio** | `2_Analise_FII.py:94,106,152,162,201,224,237` | Numeração de seções inconsistente: "0.", "1.", "1b.", "2.", "3.", "4.", "5." — confuso para navegação. |
| 5 | **Médio** | `2_Analise_FII.py:94-259` | Nenhuma seção usa `st.container()` ou `st.tabs()` — página é um scroll vertical longo sem organização visual. |
| 6 | **Médio** | `2_Analise_FII.py:240-241` | `get_pvp_percentil` chamado de novo (já calculado em `116`) — redundância gasta sessão extra. |
| 7 | **Baixo** | `2_Analise_FII.py:246-247` | Labels de métricas do radar misturam inglês/português: "PASSOU"/"FALHOU" dentro de string com "percentil". |

### `3_Carteira.py` (151 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Crítico** | `3_Carteira.py:139` | `carteira_alocacao_pie(consol)` usa `valor_total` (custo) em vez de `valor_mercado`. Gráfico de "alocação" mostra quanto investiu, não quanto vale. Misleading. |
| 2 | **Alto** | `3_Carteira.py:92-97` | Delete por string parsing: `int(to_delete.split(":")[0].replace("ID ", ""))` — frágil, quebra se o ticker contiver ":". Sem confirmação modal. |
| 3 | **Alto** | `3_Carteira.py:30` | `create_tables()` chamado em todo page load — deveria estar na inicialização do app (ex: `app.py`). |
| 4 | **Médio** | `3_Carteira.py:57-77` | Upload CSV sem validação visual — usuário não vê preview dos dados antes de importar. Erro genérico `st.error(f"Erro ao processar CSV: {e}")` sem orientação de correção. |
| 5 | **Médio** | `3_Carteira.py:141-143` | Segunda chamada `carteira_panorama()` (primeira em linha 118) só para mapear segmentos — desperdício de query. |
| 6 | **Baixo** | `3_Carteira.py:101-103` | Posições listadas como texto plano (`st.write`) — sem tabela estruturada, sem ordenação, sem totais parciais. |

### `4_Radar.py` (73 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Médio** | `4_Radar.py:52` | Typo "pregOes" (sem acento, maiúscula incorreta). Repetido na linha 65. |
| 2 | **Médio** | `4_Radar.py:38-45` | Motivos de falha listados como bullets markdown — sem link para a página do FII, sem drill-down. |
| 3 | **Médio** | `4_Radar.py:70-71` | `df.to_csv()` exporta colunas internas (`pvp_baixo`, `dy_gap_alto`, etc.) como booleanos — confuso para usuário final. Deveria usar `render_radar_matriz` antes de exportar. |
| 4 | **Baixo** | `4_Radar.py:49-66` | 4 expanders com textos explicativos estáticos — poderiam ser um tooltip ou help text. Ocupam espaço vertical excessivo. |
| 5 | **Baixo** | `4_Radar.py:21-22` | `radar_matriz()` calculado sem cache — recompute em cada render. |

### `5_Event_Study.py` (148 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Alto** | `5_Event_Study.py:31-146` | Todo o cálculo atrás de um botão — nenhum resultado persiste entre renders. Se usuário rola a página e algo causa rerun, perde tudo. |
| 2 | **Alto** | `5_Event_Study.py:32-146` | ~115 linhas de lógica de apresentação dentro de `if st.button()` — difícil de testar e manter. |
| 3 | **Médio** | `5_Event_Study.py:94-146` | CriticAgent display em layout 3-colunas rígido — em telas menores fica ilegível. Sem resumo executivo antes dos detalhes. |
| 4 | **Médio** | `5_Event_Study.py:98-99` | Check `shuffle["p_value_permutation"] < 0.05` hardcoded — threshold deveria vir do config.yaml. |
| 5 | **Baixo** | `5_Event_Study.py:56-91` | 3 seções CAR (full, treino, teste) renderizadas sequencialmente — sem tabs para organizar. |

### `6_Alertas.py` (53 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Médio** | `6_Alertas.py:48` | `st.markdown(content)` renderiza markdown de arquivo sem sanitização — se o arquivo tiver HTML/JS, será executado. |
| 2 | **Médio** | `6_Alertas.py:40-44` | Selectbox usa `f.stem` como label — formato esperado é data, mas qualquer nome de arquivo .md funciona. Sem validação. |
| 3 | **Baixo** | `6_Alertas.py:19-23` | Botão "Gerar Alertas Agora" sem feedback sobre o que será gerado nem confirmação. |
| 4 | **Baixo** | `6_Alertas.py:53` | Sem `render_footer()` se `st.stop()` é chamado nas linhas 33 ou 38 — footer não aparece em estados de erro. |

### `7_Fundamentos.py` (229 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Alto** | `7_Fundamentos.py:42-228` | Todas as queries e charts dentro de UM `get_session_ctx()` — sessão mantida aberta por toda a renderização (incluindo Plotly chart building). |
| 2 | **Alto** | `7_Fundamentos.py:56-87,150-173,185-208` | 3 gráficos Plotly construídos inline — viola DRY e o padrão de usar `app/components/charts.py`. Funções duplicam lógica existente nos components. |
| 3 | **Médio** | `7_Fundamentos.py:128-133` | `st.session_state["pvp_periodo"]` gerenciado manualmente — `st.radio` já persiste valor automaticamente via `key`. |
| 4 | **Baixo** | `7_Fundamentos.py:53` | `get_payout_historico` não usa cache — reprocessado em cada render. |

### `8_Fund_EventStudy.py` (388 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Crítico** | `8_Fund_EventStudy.py:60-154` | `get_events()` — ~95 linhas de lógica de detecção de eventos CVM diretamente na página. Viola CLAUDE.md §7 ("scripts são wrappers finos — lógica de negócio fica em src/"). |
| 2 | **Crítico** | `8_Fund_EventStudy.py:157-248` | `calculate_car()` — ~90 linhas de modelo estatístico (CAR, market model, fallback) na UI. Deveria estar em `src/fii_analysis/models/`. |
| 3 | **Crítico** | `8_Fund_EventStudy.py:251-292` | `_nw_pvalue()` e `_block_placebo()` — funções estatísticas puras na camada de UI. Importadas do nada, sem teste possível. |
| 4 | **Alto** | `8_Fund_EventStudy.py:21-26` | `statsmodels` import em try/except — se falhar, página renderiza mas `_nw_pvalue` usa fallback silencioso sem informar usuário. |
| 5 | **Alto** | `8_Fund_EventStudy.py:295-387` | Todo o fluxo de resultados atrás de `if st.button()` — sem cache, sem persistência entre renders. |
| 6 | **Médio** | `8_Fund_EventStudy.py:52-57` | Parâmetros na sidebar sem default visível — usuário precisa clicar "Rodar Análise" sem saber o que vai acontecer. |
| 7 | **Médio** | `8_Fund_EventStudy.py:321-322` | `sucessos = int((df_results["car"] < 0).sum())` — "sucesso" assume sinal de venda (CAR<0). Nome genérico, não indica a direção. |

### `9_Otimizador.py` (149 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Crítico** | `9_Otimizador.py:39` | `optimizer.get_signal_hoje(ticker, session, best_params)` usa o `session` do bloco `with get_session_ctx()` da linha 25 — mas essa chamada está FORA do `with` (linha 25-26 fecha a sessão). Se `get_session_ctx` fecha a sessão ao sair do bloco, a linha 39 opera em sessão fechada. |
| 2 | **Alto** | `9_Otimizador.py:143-149` | Sidebar com explicação posta DEPOIS do conteúdo principal — aparece na ordem errada no render. |
| 3 | **Alto** | `9_Otimizador.py` | Sem `render_footer()` — inconsistente com todas as outras páginas. |
| 4 | **Médio** | `9_Otimizador.py:121-138` | Gráfico de sensibilidade varia apenas `pvp_percentil_buy` — não explica por que fixou outros parâmetros, nem permite ao usuário escolher qual variável analisar. |
| 5 | **Baixo** | `9_Otimizador.py:1` | Ausência do boilerplate `sys.path.insert` — funciona por coincidência (import direto), mas inconsistente com as outras 8 páginas. |

---

## Componentes

### `carteira_ui.py` (67 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Crítico** | `carteira_ui.py:22-25` | `get_session()` + `session.close()` manual — se exceção ocorrer entre linha 22 e 24, sessão vaza. Deveria usar `get_session_ctx()`. |
| 2 | **Crítico** | `carteira_ui.py:29-45` | Mesmo padrão em `load_carteira_db()` — 3 funções com o mesmo risco de leak. |
| 3 | **Crítico** | `carteira_ui.py:48-58` | `save_carteira_posicao()` — sem rollback em caso de erro, sessão vaza. |
| 4 | **Crítico** | `carteira_ui.py:61-67` | `delete_carteira_posicao()` — mesmo problema. |
| 5 | **Médio** | `carteira_ui.py:20` | `@st.cache_data(ttl=300)` em `load_tickers_ativos` — cache de 5 min pode retornar tickers desatualizados se usuário acabou de adicionar dados. |

### `charts.py` (258 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Alto** | `charts.py:18,44,86,104` | Datas convertidas para strings (`strftime`) antes de passar ao Plotly — perde zoom/hover nativo de eixo temporal. Plotly suporta `pd.Timestamp` nativamente. |
| 2 | **Alto** | `charts.py:164-171` | `carteira_alocacao_pie` usa coluna `valor_total` (custo) como default — quando chamada de `3_Carteira.py:139`, mostra alocação por custo investido, não por valor de mercado. |
| 3 | **Médio** | `charts.py:175-182` | `carteira_segmento_pie` usa `groupby.size()` (contagem de posições) em vez de soma ponderada por valor — FIIs com mais posições aparecem "maiores". |
| 4 | **Baixo** | `charts.py:6-9` | `_no_gap_layout` definida mas nunca chamada — dead code. |

### `tables.py` (106 linhas)

| # | Severidade | Arquivo:Linha | Problema |
|---|---|---|---|
| 1 | **Médio** | `tables.py:43` | `lambda x: format_number(x) if x else "n/d"` — se `x` for `0.0` (P/VP zero, improvável mas possível), retorna "n/d" em vez de "0.00". Teste de truthiness deveria usar `_is_empty(x)`. |
| 2 | **Baixo** | `tables.py` | Sem formatação condicional por cor (ex: P/VP < 1.0 em verde) — todo texto é preto. |

---

## Problemas Cross-Cutting

| # | Severidade | Arquivos | Problema |
|---|---|---|---|
| 1 | **Crítico** | Todas as páginas | Sem `try/except` global — qualquer erro de dados causa traceback branco. Deveria haver error boundary com `st.error()` amigável. |
| 2 | **Alto** | Todas as páginas exceto `carteira_ui` | Nenhum `@st.cache_data` em queries pesadas — `carteira_panorama`, `get_pvp_serie`, `composicao_ativo` reprocessam a cada render. |
| 3 | **Médio** | `1,2,3,4,5,6,7` | Boilerplate `sys.path.insert` repetido em 8 arquivos — deveria ser resolvido por `pyproject.toml` ou um único `app/__init__.py`. |
| 4 | **Médio** | `2,3,5,7,8,9` | Sem `st.tabs()` ou `st.container()` para organizar seções — scroll infinito em páginas longas (2_Analise_FII tem 260 linhas de conteúdo vertical). |
| 5 | **Baixo** | Todas | Acentuação inconsistente: `Analise` vs `Análise`, `pregOes` vs `pregões` — algunas sem acento, outras com. |

---

## Ranking: Impacto × Esforço

| Prioridade | Problema | Impacto | Esforço | Refs |
|---|---|---|---|---|
| **P0** | Consolidar sessões em `2_Analise_FII.py` (15→2 sessões) | Performance crítica | Médio (2h) | `2_Analise_FII.py:60-255` |
| **P0** | Migrar `carteira_ui.py` para `get_session_ctx()` | Conexões vazando | Baixo (30min) | `carteira_ui.py:22-67` |
| **P1** | Extrair lógica de `8_Fund_EventStudy.py` para `src/` | Manutenibilidade | Médio (3h) | `8_Fund_EventStudy.py:60-292` |
| **P1** | Fix gráfico alocação: custo→mercado | Informação errada | Baixo (15min) | `3_Carteira.py:139`, `charts.py:164-171` |
| **P1** | Fix gráfico segmento: contagem→peso | Informação errada | Baixo (15min) | `charts.py:175-182` |
| **P2** | Extrair charts inline de `7_Fundamentos.py` para components | DRY | Médio (2h) | `7_Fundamentos.py:56-208` |
| **P2** | Trocar 7 botões de período por `st.radio` em `2_Analise_FII` | UX + performance | Baixo (30min) | `2_Analise_FII.py:72-79` |
| **P2** | Adicionar `st.tabs()` em páginas longas (2, 5, 7) | Navegação | Baixo (1h) | `2_Analise_FII`, `5_Event_Study`, `7_Fundamentos` |
| **P3** | Adicionar `@st.cache_data` em queries pesadas | Performance | Baixo (1h) | Componentes + páginas |
| **P3** | IFIX YTD: conectar `get_benchmark_ifix()` ou remover métrica | Funcionalidade | Baixo (30min) | `1_Panorama.py:44` |
| **P3** | Erro boundary global | Robustez | Baixo (30min) | App-wide |
| **P4** | CSV export do Radar usar dados formatados | Usabilidade | Baixo (15min) | `4_Radar.py:70` |
| **P4** | Corrigir typos "pregOes" | Polish | Baixo (5min) | `4_Radar.py:52,65` |
| **P4** | Corrigir `tables.py:43` truthiness de P/VP=0 | Edge case | Baixo (5min) | `tables.py:43` |

---

## Recomendações Implementáveis em Streamlit

### R1. Consolidar sessões (P0)

```python
# ANTES (2_Analise_FII.py — 15 sessões)
with get_session_ctx() as session:
    info = get_info_ticker(ticker, session)
# ... mais 14 blocos iguais

# DEPOIS — 1-2 sessões por render
with get_session_ctx() as session:
    info = get_info_ticker(ticker, session)
    inicio = resolve_periodo(periodo, ticker, session)
    pv_df = get_serie_preco_volume(ticker, session)
    dias_desat = get_dias_desatualizado(ticker, session)
    # ... todas as queries em uma sessão
```

### R2. Migrar carteira_ui para context manager (P0)

```python
# ANTES (carteira_ui.py:22-25)
@st.cache_data(ttl=300)
def load_tickers_ativos() -> list[str]:
    session = get_session()
    result = tickers_ativos(session)
    session.close()
    return result

# DEPOIS
@st.cache_data(ttl=300)
def load_tickers_ativos() -> list[str]:
    with get_session_ctx() as session:
        return tickers_ativos(session)
```

### R3. Trocar botões de período por radio (P2)

```python
# ANTES (2_Analise_FII.py:72-79) — 7 botões + st.rerun()
col_p1, col_p2, ... = st.columns(7)
for i, p in enumerate(PERIODOS):
    with periodo_cols[i]:
        if st.button(p, ...):
            st.session_state.periodo = p
            st.rerun()

# DEPOIS — 1 widget, sem rerun
periodo = st.radio("Período", PERIODOS, index=2, horizontal=True)
```

### R4. Fix gráfico alocação por mercado (P1)

```python
# ANTES (3_Carteira.py:139)
st.plotly_chart(carteira_alocacao_pie(consol), ...)  # usa valor_total

# DEPOIS
st.plotly_chart(carteira_alocacao_pie(
    consol.rename(columns={"valor_mercado": "valor_total"})
), ...)
# Ou alterar charts.py para aceitar coluna parametrizável
```

### R5. Adicionar tabs em página longa (P2)

```python
# ANTES (2_Analise_FII.py) — scroll infinito
st.header("0. Preco e Volume")
# ...
st.header("1. Valuation")
# ...
st.header("2. Saude Financeira")

# DEPOIS
tab_price, tab_val, tab_saude, tab_comp, tab_radar = st.tabs([
    "Preço & Volume", "Valuation", "Saúde", "Composição", "Radar"
])
with tab_price:
    # ...
with tab_val:
    # ...
```

### R6. Error boundary global (P3)

Adicionar em `app.py` ou no entrypoint:

```python
try:
    # conteúdo da página
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.caption("Verifique se os dados foram carregados via CLI: `fii load-database`")
    logging.exception("Page render error")
```

### R7. Datas nativas no Plotly (P1)

```python
# ANTES (charts.py:18) — perde interatividade
labels = [d.strftime("%d/%m") if hasattr(d, "strftime") else str(d) for d in df["data"]]
fig.add_trace(go.Scatter(x=labels, ...))

# DEPOIS — eixo temporal nativo
fig.add_trace(go.Scatter(x=df["data"], ...))
fig.update_xaxes(type="date", tickformat="%d/%m/%y")
```

### R8. Extrair lógica do 8_Fund_EventStudy (P1)

```
# MOVER de:
app/pages/8_Fund_EventStudy.py → get_events(), calculate_car(), _nw_pvalue(), _block_placebo()

# PARA:
src/fii_analysis/models/event_study_cvm.py → mesmas funções, testáveis, importáveis

# PÁGINA fica com:
from src.fii_analysis.models.event_study_cvm import get_events, calculate_car, ...
```

---

## Métricas do Audit

| Métrica | Valor |
|---|---|
| Páginas auditadas | 9 (+ 3 components + state.py) |
| Problemas encontrados | 43 |
| Críticos | 8 |
| Altos | 11 |
| Médios | 15 |
| Baixos | 9 |
| Estimativa total de correção | ~12h |
| P0 (corrigir primeiro) | 2 itens (~2.5h) |
| P1 (corrigir antes de UX) | 3 itens (~3.5h) |
