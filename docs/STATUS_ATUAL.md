# STATUS_ATUAL.md — Estado Factual do Projeto FII

> Gerado em: 2026-06-11. Regenerar sempre que houver mudança estrutural.
> Não editar manualmente — descreve o que **existe agora**, não o que está planejado.

---

## Estado Geral

**Fases 0–5 estatísticas + Camada de Decisão (F1–F7) + Motor V2 (Fase 1–3) + Validação V3 concluídas.**

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
| `database.py` | SQLAlchemy 2.0: ORM declarativo (15 tabelas: 9 operacionais + 6 snapshot), `get_session_ctx`, `get_session`, `get_cnpj_by_ticker`, `get_ultima_coleta`, `get_ultimo_preco_date`, `get_latest_ready_snapshot_run`. |
| `migrations.py` | Migrações idempotentes (sem Alembic): 4 migrações (001: CDI sensitivity em snapshot_decisions; 002: Focus BCB + CDI deltas; 003: risk_metrics em snapshot_ticker_metrics; 004: score 0–100). Função `run_migrations(db_path)`. |
| `ingestion.py` | CVM (ZIP → complemento/geral/ativo_passivo), yfinance (preços + dividendos), brapi (atualização diária), BCB SGS série 12 (CDI), conversão ex-date → data-com via calendário B3. `load_benchmark_yfinance()` usa `XFIX11` (substituiu ^IFIX). |
| `cdi.py` | `get_cdi_acumulado_12m(t, session)` — lê apenas `cdi_diario`, desacoplado de `ingestion.py` |
| `focus_bcb.py` | `fetch_focus_selic()` — busca expectativas Focus BCB (Selic 3m/6m/12m), cache diário em `dados/cache/focus_selic.json`. Retorna `FocusSelicResult` com status `OK`/`SEM_DADOS`/`ERRO_API`. |

### `src/fii_analysis/features/`

| Arquivo | Conteúdo |
|---|---|
| `dividend_window.py` | Janela ±10 pregões com retornos e retornos anormais vs benchmark |
| `indicators.py` | P/VP point-in-time, DY trailing (série e valor) |
| `valuation.py` | Percentil rolling P/VP (504d), DY N-meses (12/24/36), DY Gap vs CDI, percentil DY Gap (252d), z-score P/VP (504d), cap rate anualizado + spread vs CDI |
| `portfolio.py` | Panorama carteira, alocação, Herfindahl, retorno vs IFIX |
| `saude.py` | Tendência PL, flag destruição de capital, análise de emissões, LTV (leverage to value) flag |
| `fundamentos.py` | Rentabilidade efetiva/patrimonial, alavancagem (Ativo/PL), classificação por alerta |
| `composicao.py` | Classificação Tijolo/Papel/Híbrido via `ativo_passivo` CVM |
| `radar.py` | Matriz booleana (P/VP pct, DY Gap pct, Saúde, Liquidez) |
| `score.py` | Score composto 0–100 com 4 sub-scores: `ScoreFII` dataclass, `calcular_score()` e `calcular_score_batch()` (Valuation 35% + Risco 30% + Liquidez 20% + Histórico 15%). Pesos adaptativos: 50/30/20 (P/VP/DY/Zscore quando disponível) ou fallback 60/40 (P/VP/DY). |
| `risk_metrics.py` | `volatilidade_anualizada`, `beta_vs_ifix` (vs XFIX11), `max_drawdown`, `liquidez_media_21d`, `retorno_total_12m`, `dy_3m_anualizado`, `yield_on_cost` — todas com parâmetro `session`. |
| `volume_signals.py` | `get_volume_drop_flag` — flag se volume 21d < volume 63d - threshold%; `get_vol_ratio_21_63` — razão volume 21d / volume 63d; `get_volume_profile` — perfil de distribuição de volume. |
| `momentum_signals.py` | `get_momentum_relativo_ifix` — retorno FII 21d vs IFIX 21d; `get_dividend_safety` — análise sustentabilidade (payout_vs_caixa, cortes_24m, flag_insustentavel). Contém também: `get_pl_trend`, `get_rentab_divergencia`, `get_dy_momentum`, `get_meses_dy_acima_cdi`. |
| `data_loader.py` | Agregadores de dados para CLI e páginas Streamlit (consultas compostas) |

### `src/fii_analysis/models/`

| Arquivo | Conteúdo |
|---|---|
| `statistical.py` | Event study CAR/BHAR, t-test pareado, Mann-Whitney U, t-test dia 0 |
| `walk_forward.py` | Splits temporais com gap de 10 pregões, `validate_no_leakage()` |
| `critic.py` | CriticAgent: shuffle/placebo/estabilidade (3 testes de falsificação) |
| `strategy.py` | Simulação dividend capture, grid search, Sharpe/Sortino/drawdown, buy-and-hold |
| `trade_simulator.py` | Motor puro de simulação (backtest) que gerencia caixa/CDI, dividendos explícitos (D+1 proxy) e compras pelo preço bruto. |
| `threshold_optimizer_v2.py` | Otimizador de thresholds P/VP + DY Gap + meses_alerta. Grid expandido de 244 combinações válidas (buy [15–50], sell [55–90], spread≥15); `volume_drop_flag` vetorizado filtra BUYs com queda forte de volume. Cache JSON: `save_optimizer_cache()` e `load_optimizer_cache()`. |
| `walk_forward_rolling.py` | Validação out-of-sample genuína com janela de treino deslizante (thinned). Retorna `sinal_hoje`: extrapolação do threshold da última janela OOS para P/VP atual. |
| `episodes.py` | Identificação de episódios independentes de P/VP extremo (thinned). Parâmetro `min_gap`. |
| `div_capture.py` | Estratégias de captura de dividendo (lógica pura, sem UI): `carregar_dados_ticker`, `analisar_janela_flexivel`, `identificar_dia_minimo_treino`, `estrategia_compra_fixa`, `estrategia_vende_recompra`, `simular_spread_recompra` |
| `event_study_cvm.py` | Event study CVM: `get_events`, `calculate_car`, `_nw_pvalue`, `_block_placebo` — extraído de `8_Fund_EventStudy.py`, usa `info_callback` para desacoplar de Streamlit |
| `cdi_sensitivity.py` | Regressão P/VP ~ CDI 12m (nível, OLS+HAC NW maxlags=4, frequência semanal, min 104 obs). Retorna `CdiSensitivityResult` com status `OK`/`DADOS_INSUFICIENTES`/`SEM_CDI`/`CONVERGENCIA_FALHOU`. Batch via `compute_cdi_sensitivity_batch()`. |
| `cdi_comparison.py` | **[PESQUISA — não operacional]** Fase 1 V2 CDI: diagnóstico P/VP bruto vs resíduo CDI-ajustado. |
| `cdi_oos_evaluation.py` | **[PESQUISA — não operacional]** Fase 2 V2 CDI: teste OOS comparativo. Veredito: RESIDUO_PIORA. |

### `src/fii_analysis/decision/` (camada de decisão — Fases 1–4)

| Arquivo | Conteúdo |
|---|---|
| `__init__.py` | Re-exports: `TickerDecision`, `DailyCommandCenter`, `HoldingAdvice`, `AlertaEstrutural`, e todas as funções públicas. |
| `recommender.py` | Motor central: dataclass `TickerDecision` (Sinal/Ação/Risco separados) e funções `decidir_ticker(ticker, session, optimizer_params=None)` e `decidir_universo(...)`. Combina 3 modos + 4 flags de risco. Veto absoluto: BUY com `flag_destruicao_capital` → EVITAR/VETADA. Motor V2 F3: campos de momentum, cap rate, dividend safety, LTV. Camada CDI V1 (informativa): não altera `_derivar_acao()`. |
| `cdi_focus_explainer.py` | Camada de explicação CDI + Focus: `build_cdi_focus_explanation()` → dict com deltas Focus, repricing estimado e linhas de explicação textual. Puramente informativo. |
| `abertos.py` | Detectores de oportunidades abertas hoje: `detectar_episodio_aberto` (NOVO vs CONTINUAÇÃO); `detectar_janela_captura` (estima próxima data-com pela mediana histórica). |
| `portfolio_advisor.py` | Cruzamento decisões × posições da carteira. Dataclass `HoldingAdvice` com badge ∈ {HOLD, AUMENTAR, REDUZIR, SAIR, EVITAR_NOVOS_APORTES}. Funções `aconselhar_carteira`, `alertas_estruturais`, `exportar_sugestoes_md/csv`. |
| `daily_report.py` | `DailyCommandCenter` dataclass + `build_daily_command_center()` — agrega decisões, carteira e exportação (MD+CSV). |

### `src/fii_analysis/evaluation/`

| Arquivo | Conteúdo |
|---|---|
| `reporter.py` | Relatório técnico — acessa somente dados de teste |
| `panorama.py` | `rich.Table`: render carteira e calendário |
| `alertas.py` | Geração de alertas diários legados (4 flags: destruição capital, emissões >1%, P/VP >p95, DY Gap <p5) — escreve Markdown + terminal |
| `daily_report.py` | Relatório diário acionável (Fase 2): consome `list[TickerDecision]` e renderiza Markdown com 5 seções (Ações Hoje · Watchlist · Janelas Abertas · Riscos · Apêndice estatístico) + CSV plano. |
| `daily_snapshots.py` | Geração/leitura de snapshots diários desnormalizados (6 tabelas). Fases: `generate_base_snapshots` (metrics+radar), `build_snapshot_decisions` (Fase 3), `build_snapshot_portfolio_advices` (Fase 4), `build_snapshot_structural_alerts` (Fase 4). Versionamento por motor, hash de universo/carteira, scopes `curado`/`carteira`/`db_ativos`. Usa cache do otimizador (7d válido). |
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
| `1_Panorama.py` | sim (Diário) | Métricas gerais, coluna Ação Hoje, coluna Score 0–100, radar OK. Error boundary via `@safe_page`. |
| `3_Carteira.py` | sim (Diário) | CRUD de posições, consolidado, pizza alocação/segmento (valor_mercado), Herfindahl. Sugestões operacionais (badge). Alertas estruturais. Error boundary via `@safe_page`. |
| `4_Radar.py` | sim (Diário) | Heatmap booleano, tabela detalhada, exportação CSV. Error boundary via `@safe_page`. |
| `5_Event_Study.py` | sim (Investigação) | Event Study agregado do universo: CAR, testes pré/pós, dia 0, CriticAgent. |
| `6_Alertas.py` | sim (Investigação) | Geração sob demanda, listagem de Markdowns salvos por data. |
| `13_Hoje.py` | sim (Diário) | Cockpit operacional que lê snapshot por padrão: recomendações diárias, watchlist, carteira cruzada e riscos. Tab contexto de juros. |
| `14_Dossie_FII.py` | sim (Investigação) | Visão consolidada por ticker — abas internas Análise FII / Fundamentos / Eventos CVM. Ticker selecionado compartilhado via `st.session_state.dossie_ticker`. |
| `15_Laboratorio.py` | sim (Técnico) | Tela de auditoria/backtest com abas Otimizador V2 / Episódios / Walk-Forward. |
| `2_Analise_FII.py` | não | Wrapper standalone — chama `app.components.page_content.analise_fii.render(ticker)`. |
| `7_Fundamentos.py` | não | Wrapper standalone — chama `app.components.page_content.fundamentos.render(ticker)`. |
| `8_Fund_EventStudy.py` | não | Wrapper standalone — chama `app.components.page_content.fund_eventstudy.render()`. |
| `10_Otimizador_V2.py` | não | Wrapper standalone — chama `app.components.page_content.otimizador_v2.render()`. |
| `11_Episodios.py` | não | Wrapper standalone — chama `app.components.page_content.episodios.render()`. |
| `12_WalkForward.py` | não | Wrapper standalone — chama `app.components.page_content.walkforward.render()`. |

### `app/components/`

| Arquivo | Conteúdo |
|---|---|
| `page_content/` | Módulos `analise_fii.py`, `fundamentos.py`, `fund_eventstudy.py`, `otimizador_v2.py`, `episodios.py`, `walkforward.py`. Cada um expõe `render(...)`. Otimizador V2 tem 7 abas incluindo "Grid Completo" com heatmap interativo de 244 combinações. |
| `carteira_ui.py` | Cache Streamlit + CRUD carteira: `load_tickers_ativos`, `load_carteira_db`, `save_posicao`, `delete_posicao`. Cache `@st.cache_data(ttl=300)`. |
| `charts.py` | Plotly: `pvp_gauge`, `pvp_historico_com_bandas`, `pl_trend_chart`, `composicao_pie`, `car_plot`, `radar_heatmap`, `carteira_alocacao_pie` (valor_mercado), `carteira_segmento_pie` (valor_mercado). |
| `tables.py` | Formatadores: `format_currency`, `format_pct`, `format_number`, `render_panorama_table`, `render_radar_matriz`. |
| `snapshot_ui.py` | Helpers de UI para leitura de snapshots diários. Queries às tabelas `snapshot_*` com `@st.cache_data(ttl=300)`. Inclui `load_decisions_snapshot` para Panorama e Carteira. |
| `state.py` | Error boundary global: `@safe_page` decorator com `functools.wraps` + `logging` — aplicado a todas as páginas. |
| `ui_shell.py` | Helpers de UI (headers, notes, sidebar). |

### `scripts/` (wrappers CLI finos — main() + impressão, lógica em src/)

| Script | Função |
|---|---|
| `load_database.py` | Download ZIPs CVM + carga yfinance + XFIX11 |
| `run_strategy.py` | Pipeline completo de estratégia |
| `run_event_study.py` | Event study em todos os tickers ativos + CriticAgent |
| `run_event_study_car_ajustado.py` | Event study com CAR ajustado |
| `plot_car.py` | Gráfico CAR (PNG) |
| `plot_car_adjusted.py` | Gráfico CAR ajustado (PNG) |
| `validate_knip11.py` | Validação cruzada vs FundsExplorer |
| `check_prices.py` | Inspeção de preços (debug) |
| `analise_janela_v2.py` | Wrapper — lógica em `models/div_capture.py` |
| `analise_janela_flexivel.py` | Wrapper — lógica em `models/div_capture.py` |
| `analise_spread_recompra.py` | Wrapper — lógica em `models/div_capture.py` |
| `scrape_fundsexplorer.py` | Scraping FundsExplorer |
| `daily_report.py` | CLI do relatório diário (Fase 2): MD+CSV em `dados/alertas/`. Flags: `--tickers`, `--com-otimizador`, `--output-dir`. |
| `generate_daily_snapshots.py` | CLI para gerar snapshot diário: `--scope {curado,carteira,db_ativos}`, `--force`. |
| `refresh_optimizer_cache.py` | Renova cache de params do otimizador para todos os tickers ativos. Executar semanalmente. |
| `test_recommender.py` | Sanity check ad-hoc do motor de decisão (KNIP11). |
| `test_saude_score.py` | Diagnóstico de saúde financeira — roda `flag_destruicao_capital` para todos os tickers ativos com tabela comparativa (score, gravidade, tendência, streaks, VP slope). |
| `compare_cvm_headers.py` | Utilidade de debug: compara headers de colunas CVM entre anos. |
| `_aceite` | Teste de aceite V1 CDI (6 itens técnicos + validação analítica). |
| `_aceite_v1_cdi.py` | [PESQUISA] Teste aceite V1 CDI. |
| `_aceite_v2_cdi.py` | [PESQUISA] Teste aceite V2 CDI: diagnóstico + OOS + veredito. Resultado: RESIDUO_PIORA. |
| `_aceite_v3_cdi.py` | Teste aceite V3 CDI: Focus BCB + sensitivity + explainer + decisão inalterada + snapshot com migração. 6/6 testes passaram (29/04/2026). |
| `_patch_database.py` | Patch ad-hoc banco. |
| `_patch_ativo_passivo.py` | Patch ad-hoc ativo/passivo. |

### `.claude/agents/`

| Agente | Especialização |
|---|---|
| `data-scientist.md` | Regras estatísticas: split temporal, leakage, testes |
| `python-pro.md` | Implementação Python: SQLAlchemy, pandas, lógica pura |
| `streamlit-developer.md` | Páginas Streamlit e componentes de visualização |
| `documentation-engineer.md` | Atualização de PROJETO.md e STATUS_ATUAL.md |
| `ux-researcher.md` | Pesquisa UX: síntese de feedback em ações implementáveis |
| `beta-tester-trader.md` | Teste beta: perspectiva de trader B&H real |

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
| `snapshot_runs` | `id` (auto) | Metadados do snapshot: `data_referencia`, `status`, `engine_version_global`, `universe_scope`, `universe_hash`, `carteira_hash`. Campos Focus BCB: `focus_data_referencia`, `focus_coletado_em`, `focus_selic_3m/6m/12m`, `focus_status` |
| `snapshot_ticker_metrics` | `id` (auto) | Métricas pré-calculadas: `preco`, `vp`, `pvp`, `pvp_percentil`, `dy_12m`, `dy_24m`, `rent_12m`, `rent_24m`, `dy_gap`, `dy_gap_percentil`, `volume_21d`, `cvm_defasada`, `segmento`. Score (5 colunas: total + 4 sub-scores). Risk metrics (6 colunas: volatilidade, beta, max_dd, liquidez, retorno_12m, dy_3m_anualizado). |
| `snapshot_radar` | `id` (auto) | Flags booleanas do radar: `pvp_baixo`, `dy_gap_alto`, `saude_ok`, `liquidez_ok`, `vistos` (0-4), `saude_motivo` |
| `snapshot_decisions` | `id` (auto) | Decisões consolidadas: 3 sinais brutos, ação derivada, concordância, flags de risco, janelas abertas, versionamento por motor. Campos CDI/Focus: `cdi_status`, `cdi_beta`, `cdi_r_squared`, `cdi_p_value`, `cdi_residuo_atual`, `cdi_residuo_percentil`, `cdi_delta_focus_12m`, `cdi_repricing_12m`. Score: `score_total`. |
| `snapshot_portfolio_advices` | `id` (auto) | Conselhos de carteira: `badge`, `peso_carteira`, `valor_mercado`, `racional`, `valida_ate` |
| `snapshot_structural_alerts` | `id` (auto) | Alertas estruturais: concentração Herfindahl, top-2 peso, n_tickers — descritivos |

---

## Bugs menores conhecidos

| Local | Descrição |
|---|---|
| ~~`1_Panorama.py`~~ | ~~IFIX YTD hardcoded como `"n/d"`~~ (**Corrigido**) |
| ~~Panorama CLI/web~~ | ~~Paridade incompleta~~ (**Corrigido**) |
| ~~`recommender.py`: get_pvp_zscore~~ | ~~**Corrigido** — `session=session` como keyword arg~~ |
| ~~`episodes.py`: `min_hold_days`~~ | ~~**Corrigido** — renomeado para `min_gap`~~ |

---

## Documentação auxiliar

> **Governança de documentação:** `docs/PROJETO.md` é a fonte única de verdade (SSOT).
> Arquivos de IA (`CLAUDE.md`, `AGENTS.md`, `.gemini/GEMINI.md`) são thin wrappers —
> nunca duplicam conteúdo. Veja PROJETO.md §12 para regras completas.

| Arquivo | Função |
|---|---|
| `docs/PROJETO.md` | ★ **SSOT** — regras, arquitetura, ADRs, metodologia, governança, status |
| `docs/STATUS_ATUAL.md` | Este arquivo — snapshot factual do estado corrente |
| `CLAUDE.md` | Thin wrapper para Claude Code — ponteiro para `docs/PROJETO.md` |
| `AGENTS.md` | Thin wrapper para Codex — ponteiro para `docs/PROJETO.md` |
| `.gemini/GEMINI.md` | Thin wrapper para Gemini CLI — ponteiro para `docs/PROJETO.md` |
| `docs/UX_AUDIT.md` | Auditoria UX: 43 problemas identificados (P0→P4) |
| `docs/BETA_TESTER_REPORT.md` | Relatório de teste beta com persona trader |
| `docs/V3_EVALUATION_LOG.md` | Log de avaliação da validação V3 |
| `docs/VARIAVEIS_ANALISE_FII_BRASIL.md` | Referência de variáveis para análise de FIIs |

---

## O que foi removido / renomeado

| Item | O que aconteceu |
|---|---|
| `app/components/data_loader.py` | Deletado — carga de dados migrada para `src/fii_analysis/features/data_loader.py` e `app/components/carteira_ui.py` |
| `app/pages/8_Sinais.py` | Deletado — consolidado em outras páginas |
| `src/fii_analysis/features/sinais.py` | Deletado — lógica distribuída em `valuation.py` e `threshold_optimizer_v2.py` |
| `app/pages/6_Fund_EventStudy.py` | Renomeado para `8_Fund_EventStudy.py` + refatorado para eventos discretos CVM |
| `scripts/analise_janela_flexivel.py`, `analise_janela_v2.py`, `analise_spread_recompra.py` | Convertidos em wrappers finos — lógica extraída para `models/div_capture.py` |
| `src/fii_analysis/models/threshold_optimizer.py` | Deletado — funcionalidade consolidada em `threshold_optimizer_v2.py` |
| `scripts/daily_update.py` | Deletado — substituído pelo CLI `fii update-prices` |
| `agents/data-scientist.toml` | Deletado — substituído por `data-scientist.md` em `.claude/agents/` |
| `test_import.py` | Removido — script solto não utilizado |

---

## Auditoria Estatística e Robustez

- **Thinning**: Todos os testes estatísticos e simulações acumuladas utilizam dados "thinned" (uma observação a cada `forward_days` ou garantindo gaps) para assegurar a independência de retornos forward sobrepostos.
- **Simulação vs Estatística**: Desacoplamento total entre a inferência (sinal puro) e o backtest operacional. O `trade_simulator.py` isola a complexidade de CDI, dividendos variáveis e prazos de liquidação.
- **Anualização do Sharpe**: Corrigida de `sqrt(252)` para `sqrt(252 / forward_days)` para retornos de múltiplos dias.
- **Classificação de Overfitting**: OOS com desempenho artificialmente superior ao treino é sinalizado como `SUSPEITO`.
- **Validação de Bootstrap**: Block bootstrap circular com detecção de degenerescência (`n < 2*block_size`).

---

## Volume de dados (referência 2026-04-16)

| Tabela | Registros |
|---|---|
| `tickers` | 6 ativos + 1 inativo (SNFF11) |
| `precos_diarios` | 8.184 (6+ tickers) |
| `dividendos` | 355 |
| `relatorios_mensais` | 227 |

---

## Experimento V2 CDI — Encerrado

**Hipótese testada:** substituir o sinal P/VP bruto pelo resíduo CDI-ajustado nos motores de episódios e walk-forward rolling.

**Veredito:** RESIDUO_PIORA (2 piora, 1 empata, 1 melhora não-confiável, 4 inconclusivo).

**Decisão:**
- V1 CDI (contexto informativo) permanece inalterada.
- V2 CDI **não segue** para produção. Código mantido como pesquisa interna.

> **A hipótese foi testada e rejeitada em OOS; o projeto mantém apenas a camada CDI informativa da V1.**

---

## CLI (9 comandos)

| Comando | Função |
|---|---|
| `panorama` | Tabela de todos os FIIs monitorados |
| `fii TICKER` | Análise detalhada de um FII |
| `consulta TICKER` | Analítico IA via Gemini + Google Search |
| `radar` | Matriz booleana de filtros |
| `alertas` | Alertas diários |
| `calendario` | Próximas datas-com |
| `carteira` | Posições, alocação, retorno vs IFIX |
| `update-prices` | Pipeline diário: preços + dividendos + CDI + XFIX11 + cache otimizador + snapshot |
| `diario` | Cockpit do dia no terminal (sinais, score, percentis) via snapshot |

**Workflow diário recomendado:** `fii update-prices` → aguarde ±30s → `fii diario` ou abra Streamlit.

---

## Pendentes conhecidos

1. **Falso positivo em eventos de capital**: `flag_destruicao_capital` e `dividend_safety_flag`
   disparam incorretamente quando FII vende ativo e distribui ganho pontual. **Decisão pendente.**
2. Snapshots reprodutíveis do `fii_data.db` com hash SHA-256
3. `fii diario` com diff desde última execução
4. Reconciliar `config.py` ↔ `config.yaml`
5. Criar `tests/` (pyproject já configura pytest)