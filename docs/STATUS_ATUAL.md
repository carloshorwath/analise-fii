# STATUS_ATUAL.md — Estado Factual do Projeto FII

> Gerado em: 2026-05-05. Regenerar sempre que houver mudança estrutural.
> Não editar manualmente — descreve o que **existe agora**, não o que está planejado.

---

## Estado Geral

**Fases 0–5 estatísticas + Camada de Decisão (F1–F4) concluídas.**

O sistema possui separação clara entre ingestão (`data/`), lógica de negócio (`features/`),
análise estatística (`models/`), camada de decisão (`decision/`), scripts CLI (`scripts/`)
e visualização (`app/`).

A **camada de decisão** transforma a saída estatística em recomendações acionáveis:
combina os 3 modos (Otimizador, Episódios, WalkForward) com flags de risco, separando
explicitamente **Sinal** (estatístico) de **Ação** (derivada com veto) de **Risco**
(independente). Concordância é tratada como heurística (3/3, 2/3, 1/3), nunca como IC.

---

## Módulos existentes

### `src/fii_analysis/data/`

| Arquivo | Conteúdo |
|---|---|
| `database.py` | SQLAlchemy 2.0: ORM declarativo (15 tabelas: 9 operacionais + 6 snapshot), `get_session_ctx`, `get_session`, `get_cnpj_by_ticker`, `get_ultima_coleta`, `get_ultimo_preco_date`, `get_latest_ready_snapshot_run`. **Migração 002**: 8 colunas novas (6 Focus em `snapshot_runs` + 2 CDI em `snapshot_decisions`). **Migração 004**: 5 colunas de score (0–100) em `SnapshotTickerMetrics` e `score_total` em `SnapshotDecisions`. |
| `ingestion.py` | CVM (ZIP → complemento/geral/ativo_passivo), yfinance (preços + dividendos), brapi (atualização diária), BCB SGS série 12 (CDI), conversão ex-date → data-com via calendário B3. **Novo (Maio 2026)**: `load_ifix_to_db(session, anos=5)` carrega IFIX via yfinance (^IFIX primário, IFIX11.SA fallback) ou brapi (fallback com history=true, range adaptativo), armazena como ticker='IFIX11' em PrecoDiario. |
| `cdi.py` | `get_cdi_acumulado_12m(t, session)` — lê apenas `cdi_diario`, desacoplado de `ingestion.py` |
| `focus_bcb.py` | `fetch_focus_selic()` — busca expectativas Focus BCB (Selic 3m/6m/12m), cache diário em `dados/cache/focus_selic.json`. Retorna `FocusSelicResult` com status `OK`/`SEM_DADOS`/`ERRO_API`. |

### `src/fii_analysis/features/`

| Arquivo | Conteúdo |
|---|---|
| `dividend_window.py` | Janela ±10 pregões com retornos e retornos anormais vs benchmark |
| `indicators.py` | P/VP point-in-time, DY trailing (série e valor) |
| `valuation.py` | Percentil rolling P/VP (504d), DY N-meses (12/24/36), DY Gap vs CDI, percentil DY Gap (252d). **Novo (Maio 2026)**: `get_pvp_zscore(ticker, session)` — z-score de P/VP (média 504d, desvio 504d); `get_cap_rate_spread(ticker, session)` — cap rate anualizado + spread vs CDI 12m. |
| `portfolio.py` | Panorama carteira, alocação, Herfindahl, retorno vs IFIX |
| `saude.py` | Tendência PL, flag destruição de capital, análise de emissões. **Novo (Maio 2026)**: `get_ltv_flag(ticker, session)` — LTV = max(0, ativo_total - pl) / ativo_total. |
| `volume_signals.py` | **NOVO (Maio 2026)**: `get_volume_drop_flag(ticker, session, threshold_pct=20)` — flag se volume 21d < volume 63d - threshold%; `get_vol_ratio_21_63(ticker, session)` — razão volume 21d / volume 63d; `get_volume_profile(ticker, session, dias=252)` — perfil de distribuição de volume. |
| `momentum_signals.py` | **NOVO (Maio 2026)**: `get_momentum_relativo_ifix(ticker, session, dias=21)` — retorno FII 21d vs IFIX 21d; `get_dividend_safety(ticker, session, session_cvm=None)` — análise sustentabilidade (payout_vs_caixa, cortes_24m, flag_insustentavel). Contém também: `get_pl_trend`, `get_rentab_divergencia`, `get_dy_momentum`, `get_meses_dy_acima_cdi` (já existentes). |
| `fundamentos.py` | Rentabilidade efetiva/patrimonial, alavancagem (Ativo/PL), classificação por alerta |
| `composicao.py` | Classificação Tijolo/Papel/Híbrido via `ativo_passivo` CVM |
| `radar.py` | Matriz booleana (P/VP pct, DY Gap pct, Saúde, Liquidez) |
| `score.py` | Score composto 0–100 com 4 sub-scores: `ScoreFII` dataclass, `calcular_score()` e `calcular_score_batch()` (Valuation 35% + Risco 30% + Liquidez 20% + Histórico 15%). **Atualizado (Maio 2026)**: `score_valuation` agora aceita `pvp_zscore`; pesos adaptativos 50/30/20 (P/VP/DY/Zscore quando disponível) ou fallback 60/40 (P/VP/DY). |
| `data_loader.py` | Agregadores de dados para CLI e páginas Streamlit (consultas compostas) |

### `src/fii_analysis/models/`

| Arquivo | Conteúdo |
|---|---|
| `statistical.py` | Event study CAR/BHAR, t-test pareado, Mann-Whitney U, t-test dia 0 |
| `walk_forward.py` | Splits temporais com gap de 10 pregões, `validate_no_leakage()` |
| `critic.py` | CriticAgent: shuffle/placebo/estabilidade (3 testes de falsificação) |
| `strategy.py` | Simulação dividend capture, grid search, Sharpe/Sortino/drawdown, buy-and-hold |
| `trade_simulator.py` | Motor puro de simulação (backtest) que gerencia caixa/CDI, dividendos explícitos (D+1 proxy) e compras pelo preço bruto. |
| `threshold_optimizer.py` | Otimizador de thresholds P/VP + DY Gap + meses_alerta: NW HAC com df efetivos (n/h), block bootstrap bicaudal para BUY, placebo SELL unicaudal, Bonferroni ×36, grid 3×3×2×2 |
| `threshold_optimizer_v2.py` | Extensão do otimizador V1 com métricas de robustez, Sharpe, Sortino e diagnóstico de overfitting. Integra o `trade_simulator` para backtest no conjunto de teste. **Atualizado (Maio 2026)**: grid expandido de 9 para 244 combinações válidas (buy grid [15–50], sell grid [55–90], spread≥15); `volume_drop_flag` vetorizado filtra BUYs com queda forte de volume + volume absoluto alto. |
| `walk_forward_rolling.py` | Validação out-of-sample genuína com janela de treino deslizante (thinned). Utiliza o motor `trade_simulator` para simulação operacional. |
| `episodes.py` | Identificação de episódios independentes de P/VP extremo (thinned). Permite tradução de episódios em sinais operacionais para backtest realista. |
| `div_capture.py` | Estratégias de captura de dividendo (lógica pura, sem UI): `carregar_dados_ticker`, `analisar_janela_flexivel`, `identificar_dia_minimo_treino`, `estrategia_compra_fixa`, `estrategia_vende_recompra`, `simular_spread_recompra` |
| `event_study_cvm.py` | Event study CVM: `get_events`, `calculate_car`, `_nw_pvalue`, `_block_placebo` — extraído de `8_Fund_EventStudy.py`, usa `info_callback` para desacoplar de Streamlit |
| `cdi_comparison.py` | **[PESQUISA — não operacional]** Fase 1 V2 CDI: diagnóstico P/VP bruto vs resíduo CDI-ajustado. Regressão expanding semanal OLS+HAC, merge_asof diário. |
| `cdi_oos_evaluation.py` | **[PESQUISA — não operacional]** Fase 2 V2 CDI: teste OOS comparativo (episódios + walk-forward) entre baseline P/VP e resíduo CDI. Veredito: RESIDUO_PIORA. |
| `cdi_sensitivity.py` | Regressão P/VP ~ CDI 12m (nível, OLS+HAC NW maxlags=4, frequência semanal, min 104 obs). Retorna `CdiSensitivityResult` com status `OK`/`DADOS_INSUFICIENTES`/`SEM_CDI`/`CONVERGENCIA_FALHOU`. Inclui beta, R², p-value, resíduo atual e percentil. Batch via `compute_cdi_sensitivity_batch()`. |

### `src/fii_analysis/decision/` (camada de decisão — Fases 1–4)

| Arquivo | Conteúdo |
|---|---|
| `recommender.py` | Motor central: dataclass `TickerDecision` (Sinal/Ação/Risco separados) e funções `decidir_ticker(ticker, session, optimizer_params=None)` e `decidir_universo(...)`. Combina 3 modos + 4 flags de risco. Veto absoluto: BUY com `flag_destruicao_capital` → EVITAR/VETADA. Concordância heurística: ALTA (3/3 sem flag), MEDIA (2/3 sem flag), BAIXA (1/3 ou 2+/2 com indisponíveis), VETADA. Sem stop sugerido — `drawdown_tipico_buy` é descritivo (pior fwd_ret entre BUYs históricos). **Camada CDI V1** (informativa): campos opcionais `cdi_status`, `cdi_beta`, `cdi_r_squared`, `cdi_p_value`, `cdi_residuo_atual`, `cdi_residuo_percentil`, `cdi_delta_focus_12m`, `cdi_repricing_12m`. Aceita `cdi_sensitivity_por_ticker` e `focus_explanation_por_ticker` — enriquece rationale com "Leitura macro" e "CDI-ajustado". **Não altera `_derivar_acao()`**. **Atualizado (Maio 2026 — Motor V2 Fase 1–3)**: 6 novos campos F3 em `TickerDecision` — `momentum_ifix_21d`, `cap_rate_anualizado`, `cap_rate_spread_cdi`, `dividend_safety_flag`, `payout_vs_caixa`, `cortes_24m`. Função `decidir_ticker()` coleta todos esses sinais com try/except; alertas automáticos no rationale (spread negativo, payout>110%, ≥4 cortes DY). Fix: `get_pvp_zscore` chamada com `session=session` (keyword arg). |
| `cdi_focus_explainer.py` | Camada de explicação CDI + Focus: `build_cdi_focus_explanation(ticker, session, focus_data, cdi_sensitivity)` → dict com deltas Focus, repricing estimado e linhas de explicação textual. Heurística combina beta CDI + delta Focus + resíduo percentil + R². Puramente informativo, não gera score. |
| `abertos.py` | Detectores de oportunidades abertas hoje: `detectar_episodio_aberto(df_pvp, ...)` distingue NOVO (gap ≥ forward_days) de CONTINUAÇÃO; `detectar_janela_captura(ticker, session, ...)` estima próxima data-com pela mediana histórica de espaçamentos (sem previsão temporal). |
| `portfolio_advisor.py` | Cruzamento decisões × posições da carteira. Dataclass `HoldingAdvice` com badge ∈ {HOLD, AUMENTAR, REDUZIR, SAIR, EVITAR_NOVOS_APORTES}. Funções `aconselhar_carteira(decisoes, holdings, ...)`, `alertas_estruturais(advices, ...)` (Herfindahl, top-2 peso, n_tickers — descritivos), `exportar_sugestoes_md/csv(...)` com disclaimer "NÃO é ordem executável". Validade default = próxima segunda-feira. |

### `src/fii_analysis/evaluation/`

| Arquivo | Conteúdo |
|---|---|
| `reporter.py` | Relatório técnico — acessa somente dados de teste |
| `panorama.py` | `rich.Table`: render carteira e calendário |
| `alertas.py` | Geração de alertas diários legados (4 flags: destruição capital, emissões >1%, P/VP >p95, DY Gap <p5) — escreve Markdown + terminal |
| `daily_report.py` | Relatório diário acionável (Fase 2): consome `list[TickerDecision]` e renderiza Markdown com 5 seções (Ações Hoje · Watchlist · Janelas Abertas · Riscos · Apêndice estatístico) + CSV plano. Apêndice cobre acionados + watchlist + vetados (auditoria do veto). |
| `daily_snapshots.py` | Geração/leitura de snapshots diários desnormalizados (6 tabelas). Fases: `generate_base_snapshots` (metrics+radar), `build_snapshot_decisions` (Fase 3), `build_snapshot_portfolio_advices` (Fase 4), `build_snapshot_structural_alerts` (Fase 4). Versionamento por motor, hash de universo/carteira, scopes `curado`/`carteira`/`db_ativos`. |
| `radar.py` | Render da matriz booleana |

### `src/fii_analysis/mcp_server/`

| Arquivo | Conteúdo |
|---|---|
| `server.py` | MCP estatístico: `validate_split`, `detect_leakage`, `check_window_overlap`, `summary_report` |

### Navegação Streamlit

A sidebar (`app/streamlit_app.py`) agrupa as páginas em três blocos para refletir o fluxo mental do usuário:

- **Diário**: `13_Hoje.py`, `3_Carteira.py`, `1_Panorama.py`, `4_Radar.py`
- **Investigação**: `14_Dossie_FII.py`, `6_Alertas.py`, `5_Event_Study.py`
- **Técnico**: `15_Laboratorio.py`

As páginas autônomas `2_Analise_FII.py`, `7_Fundamentos.py`, `8_Fund_EventStudy.py`, `10_Otimizador_V2.py`, `11_Episodios.py` e `12_WalkForward.py` continuam existindo no disco (acessíveis por URL direta), mas foram removidas do `st.navigation` — seu conteúdo é renderizado dentro do **Dossie do FII** (2/7/8) e do **Laboratório** (10/11/12) via `app/components/page_content/*.py`.

### `app/pages/`

| Arquivo | Visível na sidebar | Conteúdo |
|---|---|---|
| `1_Panorama.py` | sim (Diário) | Métricas gerais, tabela completa, radar OK. Error boundary via `@safe_page`. |
| `3_Carteira.py` | sim (Diário) | CRUD de posições, consolidado, pizza alocação/segmento (valor_mercado), Herfindahl. **Seção "Sugestões Operacionais"** (Fase 4): tabela com badge HOLD/AUMENTAR/REDUZIR/SAIR/EVITAR_NOVOS_APORTES, expander com racional por holding, botões export MD/CSV com disclaimer. **Seção "Alertas Estruturais"**: Herfindahl, top-2 peso, n_tickers. Error boundary via `@safe_page`. |
| `4_Radar.py` | sim (Diário) | Heatmap booleano, tabela detalhada, exportação CSV. Error boundary via `@safe_page`. |
| `5_Event_Study.py` | sim (Investigação) | Event Study agregado do universo: CAR, testes pré/pós, dia 0, CriticAgent. |
| `6_Alertas.py` | sim (Investigação) | Geração sob demanda, listagem de Markdowns salvos por data. |
| `13_Hoje.py` | sim (Diário) | Cockpit operacional que lê snapshot por padrão: recomendações diárias, watchlist, carteira cruzada e riscos. Tab **Contexto de Juros** recebe `snapshot_scope` e `meta_hash` explicitamente (sem ler de `st.session_state`). |
| `14_Dossie_FII.py` | sim (Investigação) | **Novo (Apr 2026)**: visão consolidada por ticker — abas internas Análise FII / Fundamentos / Eventos CVM. Ticker selecionado no topo é compartilhado entre abas via `st.session_state.dossie_ticker`. Substitui o trio 2/7/8 no fluxo cotidiano. |
| `15_Laboratorio.py` | sim (Técnico) | **Novo (Apr 2026)**: tela de auditoria/backtest com abas Otimizador V2 / Episódios / Walk-Forward. Substitui as 3 entradas separadas 10/11/12 na sidebar. |
| `2_Analise_FII.py` | não | Wrapper standalone — chama `app.components.page_content.analise_fii.render(ticker)`. |
| `7_Fundamentos.py` | não | Wrapper standalone — chama `app.components.page_content.fundamentos.render(ticker)`. |
| `8_Fund_EventStudy.py` | não | Wrapper standalone — chama `app.components.page_content.fund_eventstudy.render()`. |
| `10_Otimizador_V2.py` | não | Wrapper standalone — chama `app.components.page_content.otimizador_v2.render()`. |
| `11_Episodios.py` | não | Wrapper standalone — chama `app.components.page_content.episodios.render()`. |
| `12_WalkForward.py` | não | Wrapper standalone — chama `app.components.page_content.walkforward.render()`. |

### `app/components/`

| Arquivo | Conteúdo |
|---|---|
| `page_content/` | **Novo (Apr 2026)**: módulos `analise_fii.py`, `fundamentos.py`, `fund_eventstudy.py`, `otimizador_v2.py`, `episodios.py`, `walkforward.py`. Cada um expõe `render(...)` sem decorators ou `safe_set_page_config`, importável por Dossie/Laboratório e pelas páginas wrappers homônimas. **Atualizado (Maio 2026 — Motor V2 Fase 3)**: `otimizador_v2.py` adicionou 7ª aba "Grid Completo" com heatmap interativo de todas as 244 combinações buy×sell, seletor de métrica (retorno/win rate/n trades/p-value), destaque da melhor combinação em azul. |
| `carteira_ui.py` | Cache Streamlit + CRUD carteira: `load_tickers_ativos`, `load_carteira_db`, `save_posicao`, `delete_posicao` |
| `charts.py` | Plotly: `pvp_gauge`, `pvp_historico_com_bandas`, `pl_trend_chart`, `composicao_pie`, `car_plot`, `radar_heatmap`, `carteira_alocacao_pie` (valor_mercado), `carteira_segmento_pie` (valor_mercado). Séries temporais usam eixos de data nativos Plotly (`type="date"`, `tickformat`). Dead `_no_gap_layout` removido. |
| `tables.py` | Formatadores: `format_currency`, `format_pct`, `format_number`, `render_panorama_table`, `render_radar_matriz`. P/VP formatting usa `if x is not None` (corrige edge case P/VP=0.0). |
| `snapshot_ui.py` | Helpers de UI para leitura de snapshots diários. Queries às tabelas `snapshot_*` com `@st.cache_data(ttl=300)`. Funções principais: `load_latest_snapshot_meta`, `load_panorama_snapshot`, `load_radar_snapshot`, `load_portfolio_advices_snapshot`, `load_structural_alerts_snapshot`, `load_command_center_snapshot`, `load_carteira_advices_snapshot`, `render_snapshot_info`. **Leitura de campos Focus** (delta_focus_12m, repricing_12m) em `load_command_center_snapshot`. |
| `state.py` | Error boundary global: `@safe_page` decorator com `functools.wraps` + `logging` — aplicado a todas as 13 páginas. |

### `scripts/` (wrappers CLI finos — main() + impressão, lógica em src/)

| Script | Função |
|---|---|
| `load_database.py` | Download ZIPs CVM + carga yfinance |
| `run_strategy.py` | Pipeline completo de estratégia |
| `run_event_study.py` | Event study em todos os tickers ativos + CriticAgent |
| `run_event_study_car_ajustado.py` | Event study com CAR ajustado (remove efeito mecânico do dividendo) |
| `plot_car.py` | Gráfico CAR (PNG) |
| `plot_car_adjusted.py` | Gráfico CAR ajustado (PNG) |
| `validate_knip11.py` | Validação cruzada vs FundsExplorer |
| `check_prices.py` | Inspeção de preços (debug) |
| `analise_janela_v2.py` | Wrapper — lógica em `models/div_capture.py` |
| `analise_janela_flexivel.py` | Wrapper — lógica em `models/div_capture.py` |
| `analise_spread_recompra.py` | Wrapper — lógica em `models/div_capture.py` |
| `scrape_fundsexplorer.py` | Scraping FundsExplorer |
| `daily_report.py` | CLI do relatório diário (Fase 2): roda `decidir_universo()` e salva MD+CSV em `dados/alertas/{data}_recomendacoes.{md,csv}`. Flags: `--tickers X,Y,Z`, `--com-otimizador` (lento — roda `optimize()` por ticker), `--output-dir`. Sem `--com-otimizador`, sinal do otimizador fica como INDISPONIVEL e a concordância usa apenas Episódios + WalkForward. |
| `generate_daily_snapshots.py` | CLI para gerar snapshot diário: `--scope {curado,carteira,db_ativos}`, `--force`. Lógica em `evaluation/daily_snapshots.py`. |
| `refresh_optimizer_cache.py` | Renova cache de params do otimizador para todos os tickers ativos. Executar semanalmente. |
| `test_recommender.py` | Sanity check ad-hoc do motor de decisão (KNIP11). Útil para validar mudanças no `recommender.py`. |
| `compare_cvm_headers.py` | Utilidade de debug: compara headers de colunas CVM entre anos. |
| `_aceite_v2_cdi.py` | **[PESQUISA]** Teste de aceite V2 CDI: diagnóstico + OOS + veredito. Resultado: RESIDUO_PIORA. |
| `_aceite_v3_cdi.py` | Teste de aceite V3 CDI: Focus BCB + sensitivity + explainer + decisão inalterada + snapshot com migração. 6/6 testes passaram (29/04/2026). |

### `.claude/agents/`

| Agente | Especialização |
|---|---|
| `data-scientist.md` | Regras estatísticas: split temporal, leakage, testes |
| `python-pro.md` | Implementação Python: SQLAlchemy, pandas, lógica pura |
| `streamlit-developer.md` | Páginas Streamlit e componentes de visualização |
| `documentation-engineer.md` | Atualização de PROJETO.md e STATUS_ATUAL.md |
| `ux-researcher.md` | Pesquisa UX: síntese de feedback em ações implementáveis (modelo sonnet) |
| `beta-tester-trader.md` | Teste beta: perspectiva de trader B&H real (modelo sonnet) |

### `financial-advisor/` (Multi-agent ADK - Vertex AI)

| Módulo/Agente | Função |
|---|---|
| `data_analyst` | Coleta relatórios e análises de mercado profundos via Google Search. |
| `trading_analyst` | Desenvolve 5 estratégias alinhadas a risco/período. |
| `execution_analyst` | Cria plano de execução (tipos de ordens, timing, etc.). |
| `risk_analyst` | Avalia risco geral da estratégia de execução. |
| `deployment/deploy.py`| Deploy no Agent Engine do Google Cloud Platform. |

---

## Tabelas de Snapshot Diário (6 tabelas desnormalizadas)

Sistema de cache pré-calculado para as páginas `13_Hoje.py`, `3_Carteira.py`, `4_Radar.py`, `1_Panorama.py` e relatórios diários. Geração via
`evaluation/daily_snapshots.py` + `scripts/generate_daily_snapshots.py`. Leitura via
`app/components/snapshot_ui.py`.

| Tabela | PK | Conteúdo |
|---|---|---|
| `snapshot_runs` | `id` (auto) | Metadados do snapshot: `data_referencia`, `status` (running/ready/failed), `engine_version_global`, `universe_scope` (curado/carteira/db_ativos), `universe_hash`, `carteira_hash`. **Campos Focus BCB**: `focus_data_referencia`, `focus_coletado_em`, `focus_selic_3m`, `focus_selic_6m`, `focus_selic_12m`, `focus_status` |
| `snapshot_ticker_metrics` | `id` (auto) | Métricas pré-calculadas por ticker: `preco`, `vp`, `pvp`, `pvp_percentil`, `dy_12m`, `dy_24m`, `rent_12m`, `rent_24m`, `dy_gap`, `dy_gap_percentil`, `volume_21d`, `cvm_defasada`, `segmento` |
| `snapshot_radar` | `id` (auto) | Flags booleanas do radar: `pvp_baixo`, `dy_gap_alto`, `saude_ok`, `liquidez_ok`, `vistos` (0-4), `saude_motivo` |
| `snapshot_decisions` | `id` (auto) | Decisões consolidadas: 3 sinais brutos (otimizador/episódio/walkforward), ação derivada, concordância, flags de risco, janelas abertas, versionamento por motor. **Campos CDI Focus**: `cdi_status`, `cdi_beta`, `cdi_r_squared`, `cdi_p_value`, `cdi_residuo_atual`, `cdi_residuo_percentil`, `cdi_delta_focus_12m`, `cdi_repricing_12m` |
| `snapshot_portfolio_advices` | `id` (auto) | Conselhos de carteira: `badge` (HOLD/AUMENTAR/REDUZIR/SAIR/EVITAR_NOVOS_APORTES), `peso_carteira`, `valor_mercado`, `racional`, `valida_ate` |
| `snapshot_structural_alerts` | `id` (auto) | Alertas estruturais: concentração Herfindahl, top-2 peso, n_tickers — descritivos |

---

## Bugs menores conhecidos

| Local | Descrição |
|---|---|
| ~~`1_Panorama.py`~~ | ~~IFIX YTD hardcoded como `"n/d"`~~ (**Corrigido** — conectado a `get_ifix_ytd`) |
| ~~Panorama CLI/web~~ | ~~Paridade incompleta — faltam Rent. Acum., DY 24m, Tipo na web~~ (**Corrigido**) |
| ~~`recommender.py`: get_pvp_zscore chamada errada~~ | ~~**Corrigido (Maio 2026)** — agora `session=session` como keyword arg~~ |
| ~~`episodes.py`: parâmetro `min_hold_days`~~ | ~~**Corrigido (Maio 2026)** — renomeado para `min_gap` na função `identify_episodes()`~~ |

---

## Documentação auxiliar

| Arquivo | Conteúdo |
|---|---|
| `docs/PROJETO.md` | Documentação técnica unificada do sistema |
| `docs/STATUS_ATUAL.md` | Este arquivo — estado factual (regenerar quando mudar) |
| `docs/UX_AUDIT.md` | Auditoria UX: 43 problemas identificados (P0→P4), estimativa 12h total |
| `docs/BETA_TESTER_REPORT.md` | Relatório de teste beta com persona trader (15 dores por severidade) |

---

## O que foi removido / renomeado

| Item | O que aconteceu |
|---|---|
| `app/components/data_loader.py` | Deletado — carga de dados migrada para `src/fii_analysis/features/data_loader.py` e `app/components/carteira_ui.py` |
| `app/pages/8_Sinais.py` | Deletado — consolidado em outras páginas |
| `src/fii_analysis/features/sinais.py` | Deletado — lógica distribuída em `valuation.py` e `threshold_optimizer.py` |
| `app/pages/6_Fund_EventStudy.py` | Renomeado para `8_Fund_EventStudy.py` + refatorado para eventos discretos CVM |
| `scripts/analise_janela_flexivel.py`, `analise_janela_v2.py`, `analise_spread_recompra.py` | Convertidos em wrappers finos — lógica extraída para `models/div_capture.py` |
| `agents/data-scientist.toml` | Deletado — substituído por `data-scientist.md` em `.claude/agents/` |
| `test_import.py` | Removido — script solto não utilizado |

---

## Auditoria Estatística e Robustez

Recentemente (abril 2026), foi realizada uma auditoria completa nos modelos estatísticos, resultando nas seguintes melhorias:

- **Thinning**: Todos os testes estatísticos (t-test, Mann-Whitney, Bootstrap) e simulações acumuladas agora utilizam dados "thinned" (uma observação a cada `forward_days` ou garantindo gaps) para assegurar a independência de retornos forward sobrepostos.
- **Simulação vs Estatística**: Desacoplamento total entre a inferência (sinal puro) e o backtest operacional. O `trade_simulator.py` isola a complexidade de CDI, dividendos variáveis e prazos de liquidação, evitando poluição dos testes de hipótese.
- **Anualização do Sharpe**: Corrigida de `sqrt(252)` para `sqrt(252 / forward_days)` para retornos de múltiplos dias.
- **Classificação de Overfitting**: OOS com desempenho artificialmente superior ao treino é agora sinalizado como `SUSPEITO` (artefato de seleção) em vez de `ROBUSTO`.
- **Validação de Bootstrap**: Implementação de block bootstrap circular com detecção de degenerescência (`n < 2*block_size`).

---

## Volume de dados (referência 2026-04-16)

| Tabela | Registros |
|---|---|
| `tickers` | 5 ativos + 1 inativo (SNFF11) |
| `precos_diarios` | 8.184 (6 tickers) |
| `dividendos` | 355 |
| `relatorios_mensais` | 227 |

---

## Experimento V2 CDI — Encerrado

**Hipótese testada:** substituir o sinal P/VP bruto pelo resíduo CDI-ajustado (regressão expanding OLS+HAC semanal de P/VP ~ CDI 12m) nos motores de episódios e walk-forward rolling.

**Tickers testados:** KNIP11, HSRE11, CPSH11, GARE11 (CPTS11 implícito no diagnóstico batch).

**Resultado OOS (29/04/2026):**

| Ticker | Motor | Baseline WR | Resíduo WR | ΔWR | Baseline Ret | Resíduo Ret | ΔRet |
|--------|-------|-------------|------------|-----|-------------|-------------|------|
| KNIP11 | Episódios | 100% | 66.7% | -33.3pp | 4.22% | 1.16% | -3.06pp |
| KNIP11 | Walk-Fwd | 78.9% | 60.0% | -18.9pp | 1.58% | 0.78% | -0.79pp |
| HSRE11 | Episódios | 80.0% | 83.3% | +3.3pp | 3.38% | 3.24% | -0.14pp |
| HSRE11 | Walk-Fwd | 83.3% | 100%* | +16.7pp | 2.43% | 5.74%* | +3.31pp |

*HSRE11 WF experimental: n_effective=1 (não confiável)

**Veredito:** RESIDUO_PIORA (2 piora, 1 empata, 1 melhora não-confiável, 4 inconclusivo).

**Interpretação:** Para KNIP11 (melhor R²=0.74 com CDI), remover o efeito CDI destrói informação que o mercado já precifica. O CDI não é ruído a ser removido — é parte do sinal.

**Decisão tomada:**
- V1 CDI (contexto informativo em `recommender.py` e `13_Hoje.py`) permanece inalterada.
- V2 CDI **não segue** para Fase 3 (shadow mode) nem entra na camada de decisão.
- Resíduo **não é promovido** a sinal. `_derivar_acao()` inalterado.
- Código V2 mantido como **pesquisa interna** (`cdi_comparison.py`, `cdi_oos_evaluation.py`, `_aceite_v2_cdi.py`) com marcação `[PESQUISA — não operacional]` nas docstrings.

> **A hipótese de substituir ou ajustar o sinal por resíduo CDI-ajustado foi testada e rejeitada em OOS; o projeto mantém apenas a camada CDI informativa da V1.**

---

## Motor V2 Fase 6 — Daily Workflow Fast-Path (Maio 2026) — ✅ Concluído

**Script Daily Update (`scripts/daily_update.py`):**
- Novo script de atualização rápida diária que orquestra ingestão incremental:
  - Preços: yfinance incremental para todos os tickers ativos (a partir do último dia coletado)
  - CDI: BCB SGS série 12 (completo, sem gaps)
  - IFIX: benchmark via brapi com `history=true` (yfinance ^IFIX inválido)
  - Cache otimizador: renova params para tickers com cache desatualizado (max_age=7 dias)
  - Snapshot diário: geração idempotente (sem `--force`, pula se já feito hoje)
- Uso: `python scripts/daily_update.py` (sem argumentos obrigatórios)
- Idempotência: snapshots não são sobrescrito se já existem para a data do dia

**Fix: `src/fii_analysis/data/ingestion.py`:**
- `load_benchmark_yfinance()` corrigido: `period='1d'` em vez de `period='max'`
- Motivo: `period='max'` para ^IFIX.SA retorna warning e falha; `period='1d'` busca preço de hoje com sucesso

**Fix: `scripts/load_database.py`:**
- Removida duplicação: etapa 4.1 (IFIX loading) escrita duas vezes no código; agora apenas uma

**UI: `app/pages/1_Panorama.py`:**
- Nova coluna `acao` ("Ação Hoje"): carrega decisões de snapshot, exibe COMPRAR/VENDER/AGUARDAR/EVITAR por ticker
- Nova coluna `score_total`: score composto 0–100 com `ProgressColumn` visual (cor adaptativa conforme quintil)
- Função `_build_display_df()` agora aceita parâmetro `decisions_df` (carregado via `load_decisions_snapshot`)
- Integração com `app/components/snapshot_ui.py::load_decisions_snapshot()`

**UI: `app/pages/13_Hoje.py`:**
- Fix visual de cores para tickers VETADOS (destruição de capital ou safe score <30): agora exibem gray + "⚠️ {score} (VETADA)"
- Antes: verde (visualmente enganoso para um veto), agora claro que é um sinal negativo

**UI Helper: `app/components/snapshot_ui.py`:**
- Nova função `load_decisions_snapshot(scope='curado')` com caching `@st.cache_data(ttl=300)`
- Retorna `(meta, df)` com colunas: `ticker`, `acao`, `nivel_concordancia`, `sinal_otimizador`, `sinal_episodio`, `sinal_walkforward`, `flag_destruicao_capital`
- Alimenta as novas colunas em `1_Panorama.py` e sugestões operacionais em `3_Carteira.py`

**Status de dados (2026-05-05):**
- Todos 6 tickers ativos com cache otimizador atualizado (arquivo JSON em `dados/optimizer_cache/`)
- Snapshot run_id=28 gerado para 2026-05-05, scope=curado
- Workflow recomendado: `python scripts/daily_update.py` → aguarde ±30s → abra Streamlit app

---

## Motor V2 Fase 7 — CLI Daily Workflow + Performance (Maio 2026) — ✅ Concluído

**CLI: `src/fii_analysis/cli.py`:**
- Nova sub-comando `fii diario`: tabela Rich no terminal com cockpit do dia (sinais dos 3 motores, score 0–100, percentis P/VP e DY Gap) lendo do snapshot mais recente
- Nova sub-comando `fii update-prices`: pipeline diário completo via CLI (preços yfinance + dividendos + CDI 12m + IFIX + renovação cache otimizador + geração snapshot) — substitui chamadas manuais a `scripts/daily_update.py`

**Performance (app/components/):**
- `carteira_ui.py::load_carteira_db()`: adicionado `@st.cache_data(ttl=300)` — função era chamada em 3 páginas diárias (13_Hoje, 3_Carteira) sem cache, agora reutiliza resultado por 5 minutos
- `analise_fii.py::load_dados_analise()`: pré-computa `dy_gap_pct` na sessão única; `render_visao_geral` não abre mais sessão extra (eliminada redundância engine+session)

**UX: `app/components/page_content/analise_fii.py`:**
- Banner "Sinal do dia" no Dossiê FII agora exibe nota explicativa quando `nivel_concordancia == "VETADA"` com link para aba "Saúde" (diagnóstico da destruição de capital ou score baixo)

**Consistência de mensagens:**
- Todas as referências ao script legado `generate_daily_snapshots.py` substituídas por `daily_update.py` em:
  - `app/components/snapshot_ui.py` (comentários)
  - `app/pages/1_Panorama.py` (instrução ao usuário)
  - `app/state.py` (docstring error boundary)

---

## Próximos passos decididos

### Motor V2 Fases 1–3 (Maio 2026) — ✅ Concluído

**Fase 1 — Sinais de Volume e Momentum (Maio 2026):**
- `volume_signals.py`: implementado (volume drop flag, volume ratio 21/63, perfil volume)
- `momentum_signals.py`: implementado (momentum relativo IFIX 21d, dividend safety com análise payout/caixa/cortes)

**Fase 2 — Indicadores Avançados de Valuation e Saúde (Maio 2026):**
- `valuation.py` estendido: P/VP z-score (504d), cap rate anualizado + spread vs CDI
- `saude.py` estendido: LTV (leverage to value) flag
- `score.py` atualizado: nova ponderação adaptativa para valuation (P/VP 50% / DY 30% / Zscore 20%, com fallback)

**Fase 3 — UI Grid Completo do Otimizador (Maio 2026):**
- Grid expandido de 9 para 244 combinações (buy [15–50], sell [55–90], spread≥15)
- Volume drop flag vetorizado para filtro BUYs
- Nova aba "Grid Completo" em `otimizador_v2.py` com heatmap interativo (244×métrica)
- Seletor de métrica (retorno/win rate/n trades/p-value), destaque azul da melhor combinação

**Fase 4 — Ingestão IFIX (Maio 2026):**
- `load_ifix_to_db(session, anos=5)` implementado em `ingestion.py`
- **yfinance não funciona** para ^IFIX nem IFIX11.SA (confirmado em prod — 404/delisted)
- Brapi exclusivo: `history=true`, range `max` para carga inicial, `5d` para incremental
- Etapa 4.1 em `load_database.py`
- `momentum_ifix_21d` fica `None` até primeira execução bem-sucedida de `load_database.py` com o fix

**Fase 5 — Página `13_Hoje.py` (cockpit operacional)**
**Status:** ✅ Implementada e operacional.

**Decisões já tomadas (não reabrir):**

- Score numérico 0–100 implementado (Fase 2) — ponderação 4 sub-scores (Valuation/Risco/Liquidez/Histórico). Score é comunicativo, não substitui concordância heurística (ALTA/MEDIA/BAIXA/VETADA)
- Sem aparência de automação total — toda recomendação tem disclaimer e caminho para auditoria
- Vocabulário de carteira: HOLD / AUMENTAR / REDUZIR / SAIR / EVITAR_NOVOS_APORTES (não "BUY/SELL")
- Selo do dia **descritivo** (ex: `2 COMPRAR · 1 SAIR · 1 WATCHLIST · 1 VETADO`), nunca narrativo
- Cada linha de recomendação usa `st.expander` com rationale completo
- Bloco "Carteira cruzada" **condicional**: oculta se carteira vazia
- Riscos em seção **separada** (não embutidos) — esconder gera otimismo viesado

### Motor V2 Fase 5 — Cache + Walk-Forward + UX (Maio 2026) — ✅ Concluído

**Cache do Otimizador:**
- `save_optimizer_cache()` e `load_optimizer_cache()` em `threshold_optimizer_v2.py`
- `_build_optimizer_params_map()` em `evaluation/daily_snapshots.py` usa cache (7d válido), só roda `optimize()` em cache miss
- Script `scripts/refresh_optimizer_cache.py` para renovação semanal (todos os tickers ativos)
- Cache populado: 6 tickers com params salvos em `dados/optimizer_cache/{ticker}.json`

**Walk-Forward "Sinal Hoje":**
- `walk_forward_roll()` em `walk_forward_rolling.py` retorna `sinal_hoje`: extrapolação do threshold da última janela de treino OOS para P/VP atual
- `recommender.py` (seção 4) usa `sinal_hoje` como sinal primário WalkForward (com fallback ao último OOS quando indisponível)
- `app/components/page_content/walkforward.py` renderiza sinal_hoje com cor (verde=BUY, vermelho=SELL, laranja=NEUTRO) + threshold + data do último OOS

**Fix Episodes `min_gap`:**
- Parâmetro renomeado de `min_hold_days` → `min_gap` em `identify_episodes()` (`models/episodes.py`)
- `app/components/page_content/episodios.py` exibe "Estado atual e distância ao próximo sinal" (pontos percentuais)

**UX Polish:**
- `app/pages/4_Radar.py`: exportação CSV usa colunas formatadas ("Sim/Não" em vez de booleanos raw)
- `app/pages/3_Carteira.py`: fallback carrega optimizer_params do cache quando snapshot indisponível

### Outros pendentes

1. **Falso positivo em eventos de capital**: `flag_destruicao_capital` e `dividend_safety_flag`
   disparam incorretamente quando FII vende ativo e distribui ganho pontual (ex: GARE11 2026-05).
   Três opções discutidas (janela de exclusão, flag evento pontual, tabela manual); **decisão
   pendente com o usuário**. Não implementar sem escolha explícita.
2. Snapshots reprodutíveis do `fii_data.db` com hash SHA-256
3. Fase 7: `fii diario` (diff), relatório mensal Markdown/HTML, log de decisões
4. Reconciliar `config.py` ↔ `config.yaml`
5. Criar `tests/` (pyproject já configura pytest)
