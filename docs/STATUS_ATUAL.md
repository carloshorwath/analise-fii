# STATUS_ATUAL.md — Estado Factual do Projeto FII

> Gerado em: 2026-11-13 (código e docs lidos na árvore de trabalho, branch `auditoria-metodo`, ainda não commitada); contagens de dados em "Volume de dados" são de 2026-06-11. Regenerar sempre que houver mudança estrutural.
> Não editar manualmente — descreve o que **existe agora**, não o que está planejado.

---

## Estado Geral

**O sistema é descritivo** (PROJETO.md §1 e ADR-31). Um estudo em painel pré-registrado (`docs/pesquisa/painel_2026-11/`: 110 fundos, 55 datas mensais 2022-04 a 2026-10, 100 testes, Benjamini-Hochberg 5%) não achou nenhum indicador do sistema com evidência de prever qual fundo rende mais (0 sobreviventes; candidato não confirmado: `dvp6`, p BH 0,38). O código reflete isso:

- `decision/recommender.py`: `_derivar_acao` sem veto por flag; COMPRAR/VENDER só com sinal com suporte estatístico (trava de `suporte.py`; hoje nenhum passa); toda decisão leva a linha `EVIDENCIA_JSON`.
- `decision/portfolio_advisor.py`: só HOLD/AUMENTAR/REDUZIR; destruição de capital vira "ALERTA DE RISCO (descritivo)" com badge HOLD.
- `features/radar.py`: `RADAR_N_CRITERIOS = 3`; `dy_gap_alto` é regime, fora da contagem.
- `decision/opportunities.py`: candidato = liquidez OK, elegível, CVM não defasada, percentil de P/VP ≤ 30; descritivo.

Resultado do último snapshot (run 41, 2026-11-13; **informado, não reproduzido**): 26 decisões AGUARDAR; 23 posições HOLD, 10 com alerta de risco; `cdi_status` OK em 26/26; radar 0/1/2/3 critérios = 2/23/43/42 fundos; 0 pares de rotação; suíte com 141 testes (contei 136 funções `test_*` em `tests/`; a diferença é provavelmente parametrização, não verificada).

Separação de camadas: ingestão (`data/`), features (`features/`), pesquisa estatística (`models/`), decisão descritiva (`decision/`), scripts CLI (`scripts/`), visualização (`app/`).

---

## Módulos existentes

### `src/fii_analysis/data/`

| Arquivo | Conteúdo |
|---|---|
| `database.py` | SQLAlchemy 2.0: ORM declarativo (19 tabelas: 10 operacionais [inclui `universo`] + 7 snapshot [inclui `snapshot_opportunities`] + 2 diário [`llm_journal`, `decisoes_log`]; `ativo_passivo` ganhou `acoes_sociedades_fii` e `cotas_sociedades_fii`), `get_session_ctx`, `get_session`, `get_cnpj_by_ticker`, `get_ultima_coleta`, `get_ultimo_preco_date`, `get_latest_ready_snapshot_run`. |
| `migrations.py` | Migrações idempotentes (sem Alembic): 10 migrações (001: CDI sensitivity; 002: Focus BCB; 003: risk_metrics; 004: score 0-100; 005: universo; 006: snapshot_opportunities; 007: llm_journal; 008: decisoes_log; 009: colunas `acoes_sociedades_fii`/`cotas_sociedades_fii` em `ativo_passivo`; 010: `snapshot_decisions.pregoes_desde_ultimo_episodio` gravado como BLOB numpy → INTEGER). |
| `ingestion.py` | CVM (ZIP → complemento/geral/ativo_passivo), yfinance (preços + dividendos, com throttle e lista de exclusões em `dados/yfinance_exclusoes.json`), brapi, BCB SGS série 12 (CDI), conversão ex-date → data-com via calendário B3. `refresh_cvm_current_year()` re-baixa o ZIP CVM do ano corrente quando > 7 dias e reingere (chamado pelo `update-prices`). `load_benchmark_yfinance()` usa `XFIX11`. Carga de preços reabre linhas vazias/provisórias (janela de 400 dias; `_linha_precisa_revisao`) e nunca reescreve linhas com `fonte = 'yfinance:invalido'`. Carga de dividendos não insere duplicatas (≤ 7 dias, mesmo valor) e reconcilia base de split; `limpar_dividendos_duplicados()`. `recalcular_fechamento_aj()` reconstrói `fechamento_aj` (retorno total) ao fim de cada carga de preços/dividendos. `calcular_ativo_total()` + `load_ativo_passivo_to_db(..., atualizar_existentes=False)`: `ativo_total` = `Valor_Ativo` do `complemento`, fallback sem dupla contagem; também lê `Acoes_/Cotas_Sociedades_Atividades_FII` (linhas já existentes só recebem as colunas novas com `atualizar_existentes=True`). |
| `corporate_actions.py` | Lógica pura (sem I/O): `detectar_splits`, `ajustar_relatorios` (VP/cota e cotas na base atual), `deduplicar_proximos`, `calcular_retorno_total`. `primeiro_mes_com_cobertura` (pura) + `get_inicio_retorno_total(session)` (lê o banco): início do retorno total válido (fração mínima de cobertura de dividendos 50%; valor medido 2022-03-01, informado). Usado por episódios, otimizador, walk-forward (`ret_total_ok`) e event study CVM. Regras em PROJETO.md §4.9. |
| `ifix.py` | `get_ifix_composition()` — composição teórica do IFIX via B3 (GetPortfolioDay) com fallback `dados/ifix_composicao.csv` (self-healing preserva mapeamentos); resolução de CNPJ via tickers → universo → CSV → StatusInvest; persiste na tabela `universo` com `data_referencia` = data local (não UTC). |
| `cdi.py` | `get_cdi_acumulado_12m(t, session)` — lê apenas `cdi_diario`, desacoplado de `ingestion.py`. Janela semiaberta `(t−12m, t]` (mesma do DY); `None` com < 200 dias. |
| `focus_bcb.py` | `fetch_focus_selic()` — busca expectativas Focus BCB (Selic 3m/6m/12m), cache diário em `dados/cache/focus_selic.json`. Retorna `FocusSelicResult` com status `OK`/`SEM_DADOS`/`ERRO_API`. |

### `src/fii_analysis/features/`

| Arquivo | Conteúdo |
|---|---|
| `dividend_window.py` | Janela ±10 pregões com retornos e retornos anormais vs benchmark |
| `indicators.py` | P/VP point-in-time, DY trailing (série e valor). `get_relatorios_ajustados` / `get_vp_cotas_pit`: VP/cota e cotas na base do preço (split-ajustados) — única fonte de VP/cota para P/VP (`get_pvp`, `get_pvp_serie`, otimizador, episódios, `portfolio`). |
| `valuation.py` | Percentil rolling P/VP (504d até t−1; % estritamente abaixo, com tolerância relativa de empate 1e-9 — `TOL_EMPATE_PVP`), DY N-meses (12/24/36; janela semiaberta `(t−N, t]`), DY Gap vs CDI (CDI 12m também semiaberto), percentil DY Gap (exatamente 252 pregões anteriores a t; dividendos buscados desde 12 meses antes da data mais antiga da janela), z-score P/VP (504d), cap rate (`get_cap_rate_spread`: média das últimas até 6 `rentab_efetiva` mensais, composta `^12`; mínimo 3 informes) + spread vs CDI |
| `portfolio.py` | Panorama carteira, alocação, Herfindahl, retorno vs IFIX. `dy_mes` = `dy_mes_pct` da CVM sem divisão por 100 (já é fração). VP via `get_vp_cotas_pit`. |
| `saude.py` | Tendência PL, saúde graduada (saudável/em_recuperação/alerta/crítica) com score 0–100 (alerta de risco descritivo; não gera ação), análise de emissões, LTV flag. Limiares em % do VP/cota por mês (`config.yaml` seção `saude:`); streak = meses consecutivos de queda do VP/cota (`_meses_queda_vp`). `flag_destruicao_capital`, `tendencia_pl` e `emissoes_recentes` aceitam `t` (point-in-time); o `recommender` passa a data de referência. Lê VP/cota e cotas ajustados por split (`get_relatorios_ajustados`). |
| `fundamentos.py` | Rentabilidade efetiva/patrimonial, alavancagem (Ativo/PL), classificação por alerta. `get_dy_medias`: média anual correta (DY 24m ÷ 2, DY 60m ÷ 5) e percentil em fração. `get_efetiva_vs_patrimonial_resumo` e `get_payout_historico` mantêm o critério efetiva × patrimonial (ver PROJETO.md §5.2). A série histórica de PL/VP/cotas devolve VP e cotas ajustados (nominais em `vp_nominal`/`cotas_nominal`). |
| `composicao.py` | `composicao_ativo` (parcelas mutuamente exclusivas, `pct_outros` residual; `pct_imoveis_total` = diretos + sociedades) e `classificar_fii` (Tijolo ≥ 60% com sociedades incluídas; Papel ≥ 60% recebíveis; Híbrido). Tolera banco sem as colunas de sociedades (migração 009). Regras em PROJETO.md §5.3. |
| `radar.py` | Matriz booleana; `RADAR_N_CRITERIOS = 3`: `vistos` = P/VP baixo + Saúde OK + Liquidez OK (0–3). `dy_gap_alto` é gravado mas fora da contagem (indicador de regime). |
| `score.py` | Score composto 0–100 com 4 sub-scores: `ScoreFII` dataclass, `calcular_score()` e `calcular_score_batch()` (Valuation 35% + Risco 30% + Liquidez 20% + Histórico 15%). Pesos adaptativos: 50/30/20 (P/VP/DY/Zscore quando disponível) ou fallback 60/40 (P/VP/DY). |
| `risk_metrics.py` | `volatilidade_anualizada`, `beta_vs_ifix` (vs XFIX11), `max_drawdown`, `liquidez_media_21d`, `retorno_total_12m` (usa `fechamento` bruto + dividendos), `dy_3m_anualizado`, `yield_on_cost` — todas com parâmetro `session`. |
| `volume_signals.py` | `get_volume_drop_flag` — flag se volume 21d < volume 63d - threshold%; `get_vol_ratio_21_63` — razão volume 21d / volume 63d; `get_volume_profile` — perfil de distribuição de volume. |
| `momentum_signals.py` | `get_momentum_relativo_ifix` — retorno FII 21d vs IFIX 21d (benchmark `XFIX11` lido de `benchmark_diario`, alinhado nas datas da janela do FII); `get_dividend_safety` — análise sustentabilidade (payout_vs_caixa, cortes_24m, flag_insustentavel). Contém também: `get_pl_trend` (PL ÷ cotas ajustadas por split), `get_rentab_divergencia`, `get_dy_momentum`, `get_meses_dy_acima_cdi`. |
| `data_loader.py` | Agregadores de dados para CLI e páginas Streamlit (consultas compostas). `get_historico_pl` (série PL/VP por cota) devolve VP/cota ajustado por split; o nominal fica em `vp_nominal`. |

### `src/fii_analysis/models/`

| Arquivo | Conteúdo |
|---|---|
| `statistical.py` | Event study CAR/BHAR, t-test pareado, Mann-Whitney U, t-test dia 0 |
| `walk_forward.py` | Splits temporais com gap de 10 pregões, `validate_no_leakage()` |
| `critic.py` | CriticAgent: shuffle/placebo/estabilidade (3 testes de falsificação) |
| `strategy.py` | Simulação dividend capture, grid search, Sharpe/Sortino/drawdown, buy-and-hold |
| `trade_simulator.py` | Motor puro de simulação (backtest) que gerencia caixa/CDI, dividendos explícitos (D+1 proxy) e compras pelo preço bruto. |
| `threshold_optimizer_v2.py` | Otimizador de thresholds P/VP + DY Gap + meses_alerta. Grid expandido de 244 combinações válidas (buy [15–50], sell [55–90], spread≥15); `volume_drop_flag` vetorizado filtra BUYs com queda forte de volume. Cache JSON: `save_optimizer_cache(..., test_stats=)`, `load_optimizer_cache()` e `load_optimizer_cache_stats()` — o cache guarda `best_params` e `test_stats` (n thinned, média, deriva, excesso e p do split de teste, usados pela trava de significância). O p do holdout vem de `teste_excesso.excesso_vs_deriva` e **não** é multiplicado pelo tamanho do grid (`n_combinations` = 256 produtos brutos; 244 válidos após `sell − buy ≥ 15`). `get_signal_hoje` não exige `fwd_ret` (usa o último pregão); o ajuste do grid continua exigindo. VP/cota via `get_relatorios_ajustados`. O percentil interno `pvp_pct` (`rolling(504).rank`) inclui o dia atual (pendência). Devolve `p_value_*` = `None` quando n está abaixo do mínimo (antes: p = 1) e expõe `unconditional_mean` (deriva) e `buy_excess_vs_market_independent` (excesso). Retorno forward só a partir de `INICIO_RETORNO_TOTAL`; DY do DY Gap só com `data_com < t`. O cache JSON do otimizador não tem versão da definição (pendência). |
| `walk_forward_rolling.py` | Validação out-of-sample genuína com janela de treino deslizante (thinned). Retorna `sinal_hoje`: extrapolação do threshold da última janela OOS para P/VP atual. `summary[BUY/SELL]` traz `n_effective`, `mean`, `drift`, `excess`, `p_value` (teste do excesso unicaudal). |
| `episodes.py` | Identificação de episódios independentes de P/VP extremo (thinned). Parâmetro `min_gap`. Percentil interno por `pvp_percentil_ate_t_menos_1` (janela exclui o dia atual, ≥ 63 obs.). `summary[buy/sell]` traz `n`, `mean`, `drift`, `excess`, `p_value` (teste do excesso unicaudal). |
| `teste_excesso.py` | `excesso_vs_deriva(retornos_eventos, deriva, direcao, n_min=5)`: t de 1 amostra do excesso (retorno do evento − deriva), unicaudal (BUY `greater`, SELL `less`); `p_value`/`t_stat` = `None` com n < `n_min` ou excesso sem variância. Implementação única dos três sinais; definição da hipótese na docstring de `decision/suporte.py`. |
| `div_capture.py` | Estratégias de captura de dividendo (lógica pura, sem UI): `carregar_dados_ticker`, `analisar_janela_flexivel`, `identificar_dia_minimo_treino`, `estrategia_compra_fixa`, `estrategia_vende_recompra`, `simular_spread_recompra` |
| `event_study_cvm.py` | Event study CVM: `get_events`, `calculate_car`, `_nw_pvalue`, `_block_placebo` — extraído de `8_Fund_EventStudy.py`, usa `info_callback` para desacoplar de Streamlit. Sinais `emissao_cotas` e `pl_queda_2pct` usam cotas ajustadas por split (`get_relatorios_ajustados`). |
| `cdi_sensitivity.py` | Regressão P/VP ~ CDI 12m (nível, OLS+HAC NW maxlags=4, frequência semanal, min 104 obs). Retorna `CdiSensitivityResult` com status `OK`/`DADOS_INSUFICIENTES`/`SEM_CDI`/`CONVERGENCIA_FALHOU`/`ERRO_CODIGO` (exceção de código, distinta de não-convergência; `cdi_focus_explainer` trata o novo status). Batch via `compute_cdi_sensitivity_batch()`. |
| `cdi_comparison.py` | **[PESQUISA — não operacional]** Fase 1 V2 CDI: diagnóstico P/VP bruto vs resíduo CDI-ajustado. |
| `cdi_oos_evaluation.py` | **[PESQUISA — não operacional]** Fase 2 V2 CDI: teste OOS comparativo. Veredito: RESIDUO_PIORA. |

### `src/fii_analysis/decision/` (camada de decisão — Fases 1–4)

| Arquivo | Conteúdo |
|---|---|
| `__init__.py` | Re-exports: `TickerDecision`, `DailyCommandCenter`, `HoldingAdvice`, `AlertaEstrutural`, e todas as funções públicas. |
| `recommender.py` | Motor descritivo: dataclass `TickerDecision` (Sinal/Ação/Risco separados) e funções `decidir_ticker(ticker, session, optimizer_params=None)` e `decidir_universo(...)`. Combina 3 modos + 4 flags de risco. **Sem veto por flag**: `_derivar_acao(n_buy, n_sell, n_validos)` só olha votos; a flag de destruição de capital vira linha "ALERTA (descritivo, nao veta)" no rationale; `EVITAR`/`VETADA` não são mais produzidos (só em snapshots antigos). `_finalizar_votos` anexa `EVIDENCIA_JSON` (`evidencia.linha_evidencia`) em todo rationale. Campos de momentum, cap rate, dividend safety, LTV. Camada CDI V1 (informativa): não altera `_derivar_acao()`. Só sinais com suporte estatístico votam (`suporte.py`); `TickerDecision` ganhou `suporte_sinais` e `bloqueio_compra`; COMPRAR bloqueado por `elegibilidade.py` é rebaixado a AGUARDAR/BAIXA. Chama saúde/emissões com `t=data_ref`. Voto e ação são resolvidos em `_finalizar_votos` depois do BH sobre a família: em `decidir_universo` = todos os sinais BUY/SELL ativos dos `tickers` da chamada; em `decidir_ticker` avulso = os (≤ 3) sinais do ticker. Percentis gravados/exibidos = os da métrica do snapshot (`get_pvp_percentil` 504 até t−1; `get_dy_gap_percentil` 252; constantes `JANELA_PVP_PERCENTIL`/`JANELA_DY_GAP_PERCENTIL`), e os flags `pvp > 95` / `dy_gap < 5` usam os mesmos números. |
| `suporte.py` | Trava de significância: `avaliar_suporte`, `ajustar_bh` + `aplicar_fdr` (Benjamini-Hochberg sobre a família da rodada), `evidencia_otimizador/episodio/walkforward` (teste do excesso sobre a deriva, ver docstring), `conta_no_voto`, `rotulo_sinal` (`BUY (info)` quando sem suporte), `linhas_rationale` / `restaurar_de_rationale` (linhas `SUPORTE_JSON` e `BLOQUEIO_COMPRA` em `rationale_json`), `extrair_stats_otimizador`. Limiares em `config.yaml` seção `decisao:` (PROJETO.md §4.2). |
| `elegibilidade.py` | `motivo_bloqueio_compra`: evento de liquidação/encerramento vigente em `eventos_corporativos` (tipo contendo "liquid"/"encerr", `data <= data_ref`), preço atrasado > `decisao.preco_defasado_dias_uteis` pregões, ou os últimos `decisao.sem_negocios_pregoes` (default 5; chave só no código, não no `config.yaml`) pregões consecutivos com volume 0 ("sem negocios ha N pregoes"; volume NULL interrompe a sequência). `liquidez_intermitente` (≥ 4 zeros nos últimos 10; só com janela completa) existe mas **não é chamada** por nenhum módulo de `src/` (só por testes). `motivo_bloqueio_compra` é consumido por `recommender.py` e `opportunities.py` (candidato de rotação); o `portfolio_advisor.py` (sem AUMENTAR) lê o campo `bloqueio_compra` da `TickerDecision`, sem importar o módulo. |
| `cdi_focus_explainer.py` | Camada de explicação CDI + Focus: `build_cdi_focus_explanation()` → dict com deltas Focus, repricing estimado e linhas de explicação textual. Puramente informativo. |
| `abertos.py` | Detectores de janelas abertas hoje: `detectar_episodio_aberto` (NOVO vs CONTINUAÇÃO); `detectar_janela_captura` (estima próxima data-com pela mediana histórica; `_como_pregao` recua para pregão B3, e estimativa já passada vira `None`, nunca data anterior à referência). |
| `evidencia.py` | Fonte única do resultado do estudo em painel: constante `EVIDENCIA` (110 fundos, 55 datas, 100 testes, BH 5%, 0 sobreviventes, candidato `dvp6`), `linha_evidencia()` (linha `EVIDENCIA_JSON` do rationale), `restaurar_evidencia(rationale)` (None em snapshots antigos), `texto_evidencia()` (lido por `app/components/aviso_ui.py`). Atualizar a constante se um novo estudo mudar o resultado. |
| `carteira_validacao.py` | `validar_posicao(ticker, quantidade, preco, tickers_validos)` → lista de erros (ticker existente, quantidade inteira > 0, preço finito > 0); `tickers_conhecidos(session)` = `tickers` ∪ `universo`. Lógica pura; UI e CLI decidem o que fazer. |
| `portfolio_advisor.py` | Cruzamento decisões × posições da carteira. Dataclass `HoldingAdvice` com badge ∈ {HOLD, AUMENTAR, REDUZIR}; SAIR e EVITAR_NOVOS_APORTES não são mais gerados (existem só em snapshots antigos). Destruição de capital → "ALERTA DE RISCO (descritivo)" no racional (prioridade BAIXA sobe para MEDIA), badge HOLD. Bloqueio factual (liquidação, preço defasado, sem negócios) só impede AUMENTAR. Funções `aconselhar_carteira`, `alertas_estruturais`, `exportar_sugestoes_md/csv`. |
| `daily_report.py` | `DailyCommandCenter` dataclass + `build_daily_command_center()` — agrega decisões, carteira e exportação (MD+CSV). |
| `opportunities.py` | Pares de rotação DESCRITIVOS: lado VENDER usa decisões da carteira; lado COMPRAR usa métricas/radar do snapshot (universo IFIX). Candidato = `liquidez_ok` ∧ CVM não defasada ∧ elegível (`motivo_bloqueio_compra`) ∧ percentil de P/VP ≤ `pvp_percentil_barato` (30); não exige `vistos`. Destruição de capital não exclui (vira `alerta_saude`, aparece como "ALERTA DE RISCO (descritivo)"). Candidatos TURNAROUND rotulados. |
| `opportunities_backtest.py` | **[PESQUISA — não operacional]** Backtest da rotação. NÃO é point-in-time (usa decisões de hoje em datas passadas); não é chamado pelo pipeline. |
| `decision_journal.py` | F4 — Gravação de decisões reais e ex-post reviews de retornos das recomendações vs `XFIX11`. `registrar_decisao` devolve `(decisão | None, avisos)`: recusa ticker inexistente (fora de `tickers`/`universo`) e duplicata, sem levantar exceção. |

### `src/fii_analysis/evaluation/`

| Arquivo | Conteúdo |
|---|---|
| `reporter.py` | Relatório técnico — acessa somente dados de teste |
| `panorama.py` | `rich.Table`: render carteira e calendário |
| `alertas.py` | Geração de alertas diários legados (4 flags: destruição capital, emissões >1%, P/VP >p95, DY Gap <p5) — escreve Markdown + terminal |
| `daily_report.py` | Relatório diário (MD+CSV; sinais ainda sem rótulo "(info)", ver pendências): consome `list[TickerDecision]` e renderiza Markdown com 5 seções (Ações Hoje · Watchlist · Janelas Abertas · Riscos · Apêndice estatístico) + CSV plano. |
| `daily_snapshots.py` | Geração/leitura de snapshots diários desnormalizados (7 tabelas `snapshot_*`). Fases: `generate_base_snapshots` (metrics+radar), `build_snapshot_decisions` (Fase 3), `build_snapshot_portfolio_advices` (Fase 4), `build_snapshot_structural_alerts` (Fase 4). Versionamento por motor, hash de universo/carteira, scopes `curado`/`carteira`/`db_ativos`. Usa cache do otimizador (7d válido). |
| `daily_diff.py` | Diff de snapshots N vs N−1 (`calcular_diff_diario`, `render_diff_markdown`). `rotulo_periodo_diff`: "desde ontem" só se o snapshot anterior for o pregão anterior pelo calendário B3 (`pandas_market_calendars`), senão "desde o snapshot anterior" (também em caso de falha do calendário). `precos_desatualizados`: True se o último preço do banco é anterior ao último pregão até hoje; controla o rodapé "Execute 'fii update-prices'" do `diario`. |
| `radar.py` | Render da matriz booleana |

### `src/fii_analysis/mcp_server/`

| Arquivo | Conteúdo |
|---|---|
| `server.py` | MCP estatístico: `validate_split`, `detect_leakage`, `check_window_overlap`, `summary_report` |

### Navegação Streamlit

A sidebar (`app/streamlit_app.py`) agrupa as páginas em três blocos para refletir o fluxo mental do usuário:

- **Diário**: `13_Hoje.py`, `16_Oportunidades.py`, `3_Carteira.py`, `1_Panorama.py`, `4_Radar.py`
- **Investigação**: `14_Dossie_FII.py`, `6_Alertas.py`, `5_Event_Study.py`
- **Técnico**: `15_Laboratorio.py`

As páginas autônomas `2_Analise_FII.py`, `7_Fundamentos.py`, `8_Fund_EventStudy.py`, `10_Otimizador_V2.py`, `11_Episodios.py` e `12_WalkForward.py` continuam existindo no disco (acessíveis por URL direta), mas foram removidas do `st.navigation` — seu conteúdo é renderizado dentro do **Dossie do FII** (2/7/8) e do **Laboratório** (10/11/12) via `app/components/page_content/*.py`.

### `app/pages/`

| Arquivo | Visível na sidebar | Conteúdo |
|---|---|---|
| `1_Panorama.py` | sim (Diário) | Métricas gerais, rótulo descritivo (`rotulo_acao`) em vez de ação, Score 0–100, radar `n/3`. Universo exibido: carteira ∪ curados (`tickers_universo_exibido`, 26 fundos) com opção de ver o IFIX do snapshot. Error boundary via `@safe_page`. |
| `3_Carteira.py` | sim (Diário) | Aviso de evidência. CRUD de posições com validação (também no CSV importado), consolidado, pizza alocação/segmento (valor_mercado), Herfindahl. Badges (HOLD/AUMENTAR/REDUZIR) com alerta de risco no racional. Alertas estruturais. Aviso "carteira alterada desde o snapshot" e cache do cálculo ao vivo (informado; ver pendências). Flash de sucesso após rerun. Error boundary via `@safe_page`. |
| `4_Radar.py` | sim (Diário) | Aviso de evidência. Heatmap booleano (3 critérios), tabela detalhada, exportação CSV. Universo exibido único. Error boundary via `@safe_page`. |
| `5_Event_Study.py` | sim (Investigação) | Event Study agregado do universo: CAR, testes pré/pós, dia 0, CriticAgent. |
| `6_Alertas.py` | sim (Investigação) | Geração sob demanda, listagem de Markdowns salvos por data. |
| `13_Hoje.py` | sim (Diário) | Painel do dia, lê snapshot por padrão. Aviso de evidência; rótulos descritivos (`rotulo_acao`/`rotulo_flags`); watchlist, carteira cruzada e alertas de risco; tab contexto de juros. Sinais sem suporte exibidos como `(info)`; `rationale_legivel` oculta a linha `SUPORTE_JSON`. Hora do snapshot em horário local; "desatualizado" = anterior ao último pregão já encerrado. Aviso de carteira alterada. |
| `14_Dossie_FII.py` | sim (Investigação) | Aviso de evidência. Visão consolidada por ticker — abas internas Análise FII / Fundamentos / Eventos CVM. Seletor com 110 fundos (informado). Ticker selecionado compartilhado via `st.session_state.dossie_ticker`. |
| `15_Laboratorio.py` | sim (Técnico) | Instrumentos de pesquisa com abas Otimizador V2 / Episódios / Walk-Forward (sem poder preditivo demonstrado). |
| `16_Oportunidades.py` | sim (Diário) | Título da página: "Pares de Rotação" (o arquivo mantém o nome `16_Oportunidades.py`; renomeado só no título/menu em `streamlit_app.py` e `ui_shell.py`). Aviso de evidência; lista descritiva de pares, geração de prompts e registro de decisão (flash de sucesso). |
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
| `aviso_ui.py` | **Novo.** `AVISO_CURTO`, `render_aviso_evidencia()` (aviso fixo + expander com o resumo do estudo, lido de `decision/evidencia.py` com fallback local) — chamado em Hoje, Carteira, Radar, Pares de Rotação (16) e Dossiê; `rotulo_acao` (ex.: COMPRAR/AUMENTAR → "indicadores favoráveis", EVITAR → "alerta de risco", HOLD → "sem destaque"), `rotulo_flags`, `csv_sem_comentarios`. O Panorama importa só `rotulo_acao`. |
| `carteira_ui.py` | Cache Streamlit + CRUD carteira: `load_tickers_ativos`, `load_carteira_db`, `save_posicao`, `delete_posicao`, `validar_posicao` (delega a `decision/carteira_validacao.py`). Cache `@st.cache_data(ttl=300)`. |
| `charts.py` | Plotly: `pvp_gauge`, `pvp_historico_com_bandas`, `pl_trend_chart`, `composicao_pie`, `car_plot`, `radar_heatmap`, `carteira_alocacao_pie` (valor_mercado), `carteira_segmento_pie` (valor_mercado). |
| `tables.py` | Formatadores: `format_currency`, `format_pct`, `format_number`, `render_panorama_table`, `render_radar_matriz`. |
| `snapshot_ui.py` | Helpers de UI para leitura de snapshots diários. Queries às tabelas `snapshot_*` com `@st.cache_data(ttl=300)`. Inclui `load_decisions_snapshot` para Panorama e Carteira, `tickers_universo_exibido`, `render_carteira_alterada`; `finalizado_em` convertido de UTC para São Paulo; `snapshot_desatualizado` compara com o último pregão já encerrado (corte fixo de 18:30, sem fonte; ver pendências). |
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
| `generate_daily_snapshots.py` | CLI para gerar snapshot diário: `--scope {curado,carteira,db_ativos,ifix}`, `--force`. Scope `ifix` = IFIX ∪ curado ∪ carteira (métricas/radar para todos; decisões/advices só para curado ∪ carteira). |
| `load_ifix_universe.py` | Carga inicial do universo IFIX: composição B3 → `universo`, reingestão CVM dos ZIPs locais, preços+dividendos yfinance (~6 min para 107 tickers). |
| `refresh_optimizer_cache.py` | Renova cache de params do otimizador para todos os tickers ativos, gravando também `test_stats` (necessário para a trava de significância). Executar semanalmente. |
| `test_recommender.py` | Sanity check ad-hoc do motor de decisão (KNIP11). |
| `test_saude_score.py` | Diagnóstico de saúde financeira — roda `flag_destruicao_capital` para todos os tickers ativos com tabela comparativa (score, gravidade, tendência, streaks, VP slope). |
| `compare_cvm_headers.py` | Utilidade de debug: compara headers de colunas CVM entre anos. |
| `_aceite` | Teste de aceite V1 CDI (6 itens técnicos + validação analítica). |
| `_aceite_v1_cdi.py` | [PESQUISA] Teste aceite V1 CDI. |
| `_aceite_v2_cdi.py` | [PESQUISA] Teste aceite V2 CDI: diagnóstico + OOS + veredito. Resultado: RESIDUO_PIORA. |
| `_aceite_v3_cdi.py` | Teste aceite V3 CDI: Focus BCB + sensitivity + explainer + decisão inalterada + snapshot com migração. 6/6 testes passaram (29/04/2026). |
| `_patch_database.py` | Patch ad-hoc banco. |
| `_patch_ativo_passivo.py` | Patch ad-hoc ativo/passivo. |
| `_check_db_state.py` | Debug: inspeção ad-hoc do banco (lista tabelas; conta linhas de `universo`, `snapshot_opportunities`, `llm_journal`, `decisoes_log`; resumo de `precos_diarios`/`relatorios_mensais`; últimos 6 `snapshot_runs`). Caminho do DB hardcoded em `D:\analise-de-acoes-v3\dados\fii_data.db`. |
| `run_tests.ps1` | [PowerShell] Executa a suíte de testes com medição de cobertura no PowerShell (Anaconda Python). |


### `.claude/agents/`

| Agente | Especialização |
|---|---|
| `data-scientist.md` | Regras estatísticas: split temporal, leakage, testes |
| `python-pro.md` | Implementação Python: SQLAlchemy, pandas, lógica pura |
| `streamlit-developer.md` | Páginas Streamlit e componentes de visualização |
| `documentation-engineer.md` | Atualização de PROJETO.md e STATUS_ATUAL.md |
| `ux-researcher.md` | Pesquisa UX: síntese de feedback em ações implementáveis |
| `beta-tester-trader.md` | Teste beta: perspectiva de trader B&H real |
| `release-manager.md`, `qa-operator.md`, `onboarding-writer.md` | Presentes em `.claude/agents/` (conteúdo não revisado nesta rodada) |

**Desatualizado:** `data-scientist.md` (linhas 31 e 56) ainda manda correção de Bonferroni; a regra do projeto é Benjamini-Hochberg (ADR-30).

### `tests/` (Suíte de Testes da Fase 0)

| Arquivo/Pasta | Conteúdo / Função |
|---|---|
| `conftest.py` | Fixture do SQLite em memória populado com dados sintéticos (MOCK11/MOCK12, 600 pregões, 24 dividendos/relatórios) e isolamento por função. Fixture autouse `isolar_diretorios_de_saida` redireciona para `tmp_path` os diretórios de saída (alertas, prompts do gateway LLM, cache do otimizador, `yfinance_exclusoes.json`): testes não escrevem mais em `dados/`. |
| `test_audit_calculos.py` | Regressão dos erros de cálculo da auditoria: percentil DY Gap, janela DY 12m semiaberta, `retorno_total_12m` com `fechamento` bruto, `sinal_hoje` do otimizador, momentum relativo (XFIX11), `get_dy_medias`, contagem `vistos` do radar. |
| `test_base_integridade.py` | Regressão da base: dedup de dividendos, reconciliação de base de split, detecção de split/grupamento e VP/cota point-in-time, retorno total / `fechamento_aj` próprio, reabertura de linhas de preço. |
| `test_ingestion_ativo_passivo.py` | Regressão de `ativo_total` (`Valor_Ativo`, fallback sem dupla contagem, recarga de linhas existentes). |
| `test_metodo_audit.py` | Regressão de método: saúde em % do VP/cota, point-in-time de saúde/emissões, trava de significância (suporte, cache com `test_stats`) e elegibilidade (liquidação, preço defasado, advisor, rotação). |
| `test_trava_desenho.py` | Regressão do desenho da trava: teste do excesso calculado à mão, retorno positivo só por deriva não é evidência, SELL unicaudal à esquerda, n pequeno/sem variância sem p, BH com exemplos numéricos e família (p ausente = 1), BH em nível de rodada no `decidir_universo`, p de holdout do otimizador sem multiplicar pelo grid, percentis da decisão iguais aos da métrica, percentil interno de episódios até t−1. |
| `test_reauditoria_pontos_abertos.py` | Regressão da segunda rodada: split não vira emissão/queda de VP (saúde, `get_pl_trend`, event study), bloqueio por 5 pregões com volume 0 e `liquidez_intermitente`, composição com sociedades e sem dupla contagem (e banco sem as colunas novas), CDI 12m semiaberto, janela do DY Gap, `dy_mes` como fração, rótulo "desde ontem" e rodapé de `update-prices`, empate numérico no percentil de P/VP. |
| `test_backend_audit.py` | Regressão da rodada de 2026-11-13 (19 funções): percentil/`get_pvp_series` com janela 0; `cdi_sensitivity` `ERRO_CODIGO` vs `CONVERGENCIA_FALHOU`; serialização numpy e migração 010 (BLOB little-endian → INTEGER); posições a valor de mercado e Herfindahl; `resumo_defasagem` (pregão da maioria); p `None` do otimizador com n pequeno e `deriva`/`excesso` expostos; data-com estimada em pregão e nunca no passado; diff do diário; `validar_posicao`; `registrar_decisao` (ticker inexistente, duplicata); flag de destruição → alerta + HOLD (nunca SAIR/EVITAR_NOVOS_APORTES); `dy_gap_alto` fora de `vistos`; linha `EVIDENCIA_JSON` estável e restaurável; `primeiro_mes_com_cobertura`, `get_inicio_retorno_total` e episódios ignorando retorno pré-`INICIO_RETORNO_TOTAL`. |
| `test_llm.py` | Testes da camada LLM: contexto de ticker/oportunidade, render de prompt, gateway (sucesso, timeout com fallback, sem config), `llm_journal`. |
| `test_indicators.py` | Testes do cálculo do P/VP point-in-time e DY trailing. |
| `test_walk_forward.py` | Testes de make_splits, validate_no_leakage e descarte de eventos sobrepostos (<21d). |
| `test_calculation.py` | Testes de percentil rolling (P/VP e DY Gap), z-score e propagação de NaN. |
| `test_decision.py` | Testes de `_derivar_acao` (sem veto por flag; nunca devolve EVITAR/VETADA) e do cálculo de concordância. |
| `test_saude.py` | Testes de saúde financeira e falsos positivos em eventos de capital. |
| `test_ifix.py` | Testes de composição IFIX obtidos via API da B3 e fallback de CSV. |
| `test_snapshot.py` | Testes de idempotência e marcação de falhas na geração de snapshots. |
| `test_cli_smoke.py` | Smoke tests de comandos do CLI (`diario`, `panorama`, `carteira`, `radar`, `alertas`). |
| `test_opportunities.py` | Testes do motor de oportunidades de rotação, incluindo persistência, vetos e cooldown. |
| `test_decision_memory.py` | Testes da Memória Estratégica: diff diário, registro de decisões e cálculo de retornos ex-post. |

### `financial-advisor/` (Multi-agent ADK - Vertex AI)

| Módulo/Agente | Função |
|---|---|
| `data_analyst` | Coleta relatórios e análises de mercado profundos via Google Search. |
| `trading_analyst` | Desenvolve 5 estratégias alinhadas a risco/período. |
| `execution_analyst` | Cria plano de execução (tipos de ordens, timing, etc.). |
| `risk_analyst` | Avalia risco geral da estratégia de execução. |
| `deployment/deploy.py`| Deploy no Agent Engine do Google Cloud Platform. |

---

## Tabelas de Snapshot Diário (7 tabelas desnormalizadas)

Sistema de cache pré-calculado para as páginas `13_Hoje.py`, `3_Carteira.py`, `4_Radar.py`, `1_Panorama.py` e relatórios diários. Geração via
`evaluation/daily_snapshots.py` + `scripts/generate_daily_snapshots.py`. Leitura via
`app/components/snapshot_ui.py`.

| Tabela | PK | Conteúdo |
|---|---|---|
| `snapshot_runs` | `id` (auto) | Metadados do snapshot: `data_referencia`, `status`, `engine_version_global`, `universe_scope`, `universe_hash`, `carteira_hash`. Campos Focus BCB: `focus_data_referencia`, `focus_coletado_em`, `focus_selic_3m/6m/12m`, `focus_status` |
| `snapshot_ticker_metrics` | `id` (auto) | Métricas pré-calculadas: `preco`, `vp`, `pvp`, `pvp_percentil`, `dy_12m`, `dy_24m`, `rent_12m`, `rent_24m`, `dy_gap`, `dy_gap_percentil`, `volume_21d`, `cvm_defasada`, `segmento`. Score (5 colunas: total + 4 sub-scores). Risk metrics (6 colunas: volatilidade, beta, max_dd, liquidez, retorno_12m, dy_3m_anualizado). |
| `snapshot_radar` | `id` (auto) | Flags booleanas do radar: `pvp_baixo`, `dy_gap_alto`, `saude_ok`, `liquidez_ok`, `vistos` (0-3; `dy_gap_alto` não conta; snapshots antigos podem ter 0-4), `saude_motivo` |
| `snapshot_decisions` | `id` (auto) | Decisões consolidadas: 3 sinais brutos, ação derivada, concordância, flags de risco, janelas abertas, versionamento por motor. Campos CDI/Focus: `cdi_status`, `cdi_beta`, `cdi_r_squared`, `cdi_p_value`, `cdi_residuo_atual`, `cdi_residuo_percentil`, `cdi_delta_focus_12m`, `cdi_repricing_12m`. Score: `score_total`. |
| `snapshot_portfolio_advices` | `id` (auto) | Conselhos de carteira: `badge`, `peso_carteira`, `valor_mercado`, `racional`, `valida_ate` |
| `snapshot_structural_alerts` | `id` (auto) | Alertas estruturais: concentração Herfindahl, top-2 peso, n_tickers — descritivos |
| `snapshot_opportunities` | `id` (auto) | Oportunidades de rotação de carteira: vender, comprar, segmento, spreads, delta_score, custos, persistência, vetos, `critic_veredicto` (sempre "DESCRITIVO" — sem backtest point-in-time válido). |

---

## Bugs menores conhecidos

| Local | Descrição |
|---|---|
| ~~`1_Panorama.py`~~ | ~~IFIX YTD hardcoded como `"n/d"`~~ (**Corrigido**) |
| ~~Panorama CLI/web~~ | ~~Paridade incompleta~~ (**Corrigido**) |
| ~~`recommender.py`: get_pvp_zscore~~ | ~~**Corrigido** — `session=session` como keyword arg~~ |
| ~~`episodes.py`: `min_hold_days`~~ | ~~**Corrigido** — renomeado para `min_gap`~~ |
| ~~`13_Hoje.py`, `3_Carteira.py`~~ | ~~**Corrigido** — `NameError` por imports faltando; mensagens que apontavam o removido `scripts/daily_update.py` agora apontam `fii update-prices`~~ |
| ~~`pyproject.toml`~~ | ~~**Corrigido** — `pandas-market-calendars` declarado em `dependencies`; extra `scripts` (matplotlib, beautifulsoup4) criado~~ |
| ~~`valuation.get_dy_gap_percentil`~~ | ~~**Corrigido** — dividendos buscados desde 12 meses antes da data mais antiga da janela~~ |
| ~~DY 12/24/36m~~ | ~~**Corrigido** — janela semiaberta `(t−N, t]`~~ |
| ~~`risk_metrics.retorno_total_12m`~~ | ~~**Corrigido** — usa `fechamento` bruto (antes dividendos eram contados 2×)~~ |
| ~~`threshold_optimizer_v2.get_signal_hoje`~~ | ~~**Corrigido** — não exige `fwd_ret` (usa o último pregão)~~ |
| ~~`momentum_signals.get_momentum_relativo_ifix`~~ | ~~**Corrigido** — lê `benchmark_diario`/`XFIX11`~~ |
| ~~`fundamentos.get_dy_medias`~~ | ~~**Corrigido** — unidades (fração) e médias anuais~~ |
| ~~`ativo_passivo.ativo_total`~~ | ~~**Corrigido** — `Valor_Ativo` do `complemento`, sem dupla contagem~~ |
| ~~Saúde~~ | ~~**Corrigido** — limiares em % do VP/cota; streak por queda real do VP/cota; chamadas point-in-time~~ |
| ~~Trava de significância~~ | ~~**Corrigido (2ª rodada)** — teste do excesso sobre a deriva (antes: contra zero), p de holdout sem multiplicar pelo grid (antes: Bonferroni), BH sobre a família da rodada; ver PROJETO.md §4.2 / ADR-30~~ |
| ~~Percentis na decisão~~ | ~~**Corrigido** — percentis gravados = os da métrica (504/252), sem segundo percentil de DY Gap~~; percentil interno de episódios exclui o dia atual |
| ~~VP/cotas nominais~~ | ~~**Corrigido** — saúde, `get_pl_trend`, event study CVM (`emissao_cotas`, `pl_queda_2pct`) e séries históricas de PL/cotas usam `get_relatorios_ajustados`~~ |
| ~~`composicao.py`~~ | ~~**Corrigido** — parcelas sobrepostas em `pct_caixa`/`pct_valores_receber`; Tijolo passa a contar sociedades de atividade imobiliária~~ |
| ~~`portfolio.py` `dy_mes`~~ | ~~**Corrigido** — não divide mais `dy_mes_pct` por 100 (já é fração)~~ |
| ~~CDI 12m / percentis~~ | ~~**Corrigido** — CDI 12m em janela semiaberta; janela do percentil de DY Gap com exatamente 252 pregões; tolerância de empate no percentil de P/VP~~ |
| ~~`daily_diff.py` / `ifix.py`~~ | ~~**Corrigido** — rótulo "desde ontem" conferido com o calendário B3; rodapé de `update-prices` só com preço defasado; `data_referencia` do IFIX em data local~~ |
| ~~Docstring do otimizador~~ | ~~**Corrigido** — `_evaluate` descreve a hipótese nova e `meses_alerta` como VP/cota em queda ou efetiva abaixo da patrimonial~~ |
| ~~Decisão com veto por flag~~ | ~~**Corrigido (3ª rodada)** — `_derivar_acao` sem veto; advisor sem SAIR/EVITAR_NOVOS_APORTES; flag vira alerta descritivo (ADR-31)~~ |
| ~~Radar com `dy_gap_alto` na contagem~~ | ~~**Corrigido** — `RADAR_N_CRITERIOS = 3`~~ |
| ~~Retorno "total" antes da cobertura de dividendos~~ | ~~**Corrigido** — `get_inicio_retorno_total` em episódios, otimizador, walk-forward e event study~~ |
| ~~DY com look-ahead no dia da data-com~~ | ~~**Corrigido** — `data_com < t` em `valuation`, `indicators`, `risk_metrics` e otimizador (look-ahead residual por falta de data de anúncio: pendência)~~ |
| ~~`cdi_sensitivity`~~ | ~~**Corrigido** — erro de código vira `ERRO_CODIGO`, não `CONVERGENCIA_FALHOU`; janela 0 em `episodes.py` (`pvp_percentil_ate_t_menos_1`, `get_pvp_series`) não levanta~~ |
| ~~`snapshot_decisions.pregoes_desde_ultimo_episodio`~~ | ~~**Corrigido** — gravado como BLOB numpy; migração 010 converte para INTEGER~~ |
| ~~`fii carteira` / pizzas~~ | ~~**Corrigido** — `posicoes_carteira` a valor de mercado~~ |
| ~~`fii panorama`~~ | ~~**Corrigido** — data exibida = pregão da maioria (`resumo_defasagem`)~~ |
| ~~`abertos.py`~~ | ~~**Corrigido** — data-com estimada cai em pregão e nunca antes da referência~~ |
| ~~Otimizador: p = 1 com n pequeno~~ | ~~**Corrigido** — p `None` quando não calculável; expõe deriva e excesso~~ |
| ~~`registrar_decisao`~~ | ~~**Corrigido** — recusa ticker inexistente e duplicata; devolve `(decisão \| None, avisos)`~~ |
| ~~Posição de carteira sem validação~~ | ~~**Corrigido** — `decision/carteira_validacao.py`, usado pela tela (formulário e CSV)~~ |

Cobertura de regressão dessas correções: `tests/test_audit_calculos.py`, `tests/test_base_integridade.py`, `tests/test_ingestion_ativo_passivo.py`, `tests/test_metodo_audit.py`, `tests/test_trava_desenho.py`, `tests/test_reauditoria_pontos_abertos.py`, `tests/test_backend_audit.py`.

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

## Resultado do último snapshot (run 41, 2026-11-13; informado, não verificável pelo código)

Conforme informado pelo operador (não reproduzido aqui; sem acesso ao banco nesta revisão):

- 26 decisões, todas AGUARDAR.
- Carteira: 23 posições HOLD, 10 com alerta de risco.
- `cdi_status` OK em 26/26.
- Radar com 0/1/2/3 critérios = 2/23/43/42 fundos.
- 0 pares de rotação.
- Suíte com 141 testes.

(O run 40 de 2026-11-12, anterior à mudança do advisor, tinha 13 HOLD / 8 EVITAR_NOVOS_APORTES / 2 SAIR; esses badges não são mais gerados.)

Verificado nesta revisão por Grep nos 26 JSONs de `dados/optimizer_cache/`: o maior `n_buy_thinned`/`n_sell_thinned` do split de teste do otimizador é 10 (SELL; BUY no máximo 7), abaixo do n mínimo de 30.

---

## Volume de dados (referência 2026-06-11, pós carga IFIX; **não remedido em 2026-11-12**, sem shell na revisão — não usar como estado atual)

| Tabela | Registros |
|---|---|
| `tickers` | 26 (curados + posições da carteira) |
| `universo` | 107 FIIs do IFIX (fonte b3_api) |
| `precos_diarios` | ~164.700 (110 tickers, até 2026-06-11) |
| `relatorios_mensais` | ~6.400 (110 CNPJs, 2021–2026, referência até abr/2026) |
| `carteira` | 23 posições |

---

## Experimento V2 CDI — Encerrado

**Hipótese testada:** substituir o sinal P/VP bruto pelo resíduo CDI-ajustado nos motores de episódios e walk-forward rolling.

**Veredito:** RESIDUO_PIORA (2 piora, 1 empata, 1 melhora não-confiável, 4 inconclusivo).

**Decisão:**
- V1 CDI (contexto informativo) permanece inalterada.
- V2 CDI **não segue** para produção. Código mantido como pesquisa interna.

> **A hipótese foi testada e rejeitada em OOS; o projeto mantém apenas a camada CDI informativa da V1.**

---

## CLI (14 comandos)

| Comando | Função |
|---|---|
| `panorama` | Tabela de todos os FIIs monitorados |
| `fii TICKER` | Análise detalhada de um FII |
| `consulta TICKER` | Analítico IA via Gemini + Google Search |
| `radar` | Matriz booleana (3 critérios contados) |
| `alertas` | Alertas diários (descritivos) |
| `calendario` | Próximas datas-com |
| `carteira` | Posições, alocação, retorno vs IFIX |
| `update-prices` | Pipeline diário: preços + dividendos + CDI + XFIX11 + cache otimizador + snapshot |
| `diario` | Painel do dia no terminal (sinais com rótulo "(info)" quando sem suporte, score, percentis) via snapshot. `--diff` exibe mudanças vs snapshot anterior. |
| `oportunidades` | Exibe os pares de rotação (descritivos) do último snapshot |
| `registrar-decisao` | Registra uma operação ou decisão no log de decisões (recusa ticker inexistente e duplicata) |
| `review` | Exibe relatório ex-post das rotações registradas vs XFIX11 (descritivo) |
| `prompt` | Gera Prompt Pack local em Markdown para colagem manual |
| `analise` | Análise qualitativa enriquecida com IA (via gateway ou prompt pack) |


**Workflow diário recomendado** (wrappers `fii.cmd`/`fii.ps1` na raiz):
`.\fii update-prices` (default scope `ifix`: preços+dividendos do universo, refresh CVM automático, CDI, XFIX11 e snapshot com oportunidades) → `.\fii diario` (abre com o diff "o que mudou") → `.\fii oportunidades` → opcional: `.\fii prompt TICKER` / `.\fii analise TICKER` (LLM via n8n ou prompt pack) → registrar operações com `.\fii registrar-decisao` e medir com `.\fii review`.

---

## Pendentes conhecidos

Abertas em 2026-11-13. "Verificado" = conferido no código/arquivos nesta revisão; "informado" = dito pelo operador, não reproduzido.

**Produto e UI**

1. **Relatório MD/CSV exportado da Hoje** (`evaluation/daily_report.py`, `scripts/daily_report.py`) ainda exibe sinais sem o rótulo "(info)" (verificado: `rotulo_sinal` só é usado em `13_Hoje.py` e `cli.py`). Traz a nota "Alertas de risco DESCRITIVOS" (`evaluation/daily_report.py`, linha 196), mas não o aviso de evidência completo.
2. **Primeira carga da Carteira com carteira editada leva > 80 s** (informado); só as seguintes usam o cache.
3. **Upload real de CSV e decisão vinculada a par pela Carteira** não foram exercitados na tela (informado). Há validação e testes de `validar_posicao`, mas não o fluxo de tela.
4. **Corte de 18:30 para "pregão encerrado"** em `app/components/snapshot_ui.py` (`_FECHAMENTO_B3_MIN`) é constante sem fonte (verificado no código).
5. **Atalho `Atualizar Dados (Admin).lnk`** aponta para a carga completa (`scripts/load_database.py`), não para `fii update-prices` (informado; o `.lnk` é binário e não foi lido).
6. **`app/components/page_content/fund_eventstudy.py` ainda aplica Bonferroni** (`p_bonf`, verificado) e `.claude/agents/data-scientist.md` ainda manda Bonferroni (linhas 31 e 56, verificado); a regra do projeto é BH (ADR-30).
7. **`liquidez_intermitente` não está ligada à decisão** (existe em `elegibilidade.py`; só testes a chamam). Só o bloqueio por 5 pregões seguidos com volume 0 está ativo.

**Método**

8. **Efeito de `INICIO_RETORNO_TOTAL` na janela de estimação do event study não medido.**
9. **Limiar de cobertura de 50% dá 2022-03** (`FRACAO_COBERTURA_DIVIDENDOS`, verificado; valor 2022-03-01 informado), enquanto o estudo em painel usou 2022-04 como início da amostra primária.
10. **Cache do otimizador sem versão da definição** (`dados/optimizer_cache/*.json`): o código não distingue um cache gravado antes de uma mudança de definição.
11. **Possível look-ahead residual no DY Gap:** sem data de anúncio do dividendo, `data_com < t` ainda pode usar dividendo não anunciado em t.
12. **Limiares de saúde (+0,1 / −0,5 %/mês) não calibrados:** 53 de 110 fundos sinalizados (informado); no estudo em painel a flag marcou ~47% dos fundos-mês.
13. **n ≥ 30 eventos independentes não é atingível pelo desenho atual.** Otimizador: máximo de 10 eventos no split de teste (verificado por Grep nos 26 JSONs de `dados/optimizer_cache/`; a duração de ~0,9 ano do split é informada). Walk-forward: máximo de 28 (informado). Só episódios BUY chegam a n ≥ 30, em 5 de 52 combinações (informado). Consequência: nenhum sinal tem suporte e toda decisão é AGUARDAR.
14. **Premissas estatísticas da trava (ADR-30):** a deriva é tratada como constante conhecida; o BH assume independência ou dependência positiva entre testes, e os FIIs e os três sinais de um ticker compartilham mercado e dados.
15. **Família BH menor em chamadas parciais:** `decision/opportunities.py` (`decidir_universo(session, sorted(tickers_carteira))` quando `universo_decisoes` não é passado), `app/pages/3_Carteira.py` (fallback sem snapshot de carteira) e `scripts/daily_report.py` rodam o BH sobre um subconjunto, menos conservador que a família do snapshot.
16. **Percentil interno do otimizador ainda inclui o dia atual** (`pvp_pct` = `rolling(504).rank` em `threshold_optimizer_v2.py`, verificado); o de episódios já exclui.
17. **Backtest de rotação não é point-in-time:** `opportunities_backtest.py` é [PESQUISA] (usa decisões de hoje em datas passadas).

**Dados**

18. **HSRE11 sem preço desde 2026-06-11** (informado; ticker novo não identificado). Preço atrasado > 5 pregões bloqueia COMPRAR/AUMENTAR (`elegibilidade.py`), mas o ticker segue na lista curada (`sinais` do `config.yaml`, verificado).
19. **315 ticker-meses com dividendo faltante dentro da cobertura** (informado; a contagem anterior era 57).
20. **Volume 0 simultâneo em RBRR11, RPRI11 e VCJR11 desde 2026-11-06** (informado): pode ser falha da fonte (yfinance); não verificado.
21. **5 fundos com soma da composição > 100,01%** (informado; não identificados). Hipótese não verificada: `pct_outros` é resíduo truncado em 0 (`max(..., 0)`).
22. **MFII11 e TGAR11 viram Tijolo só por participações em sociedades** (informado); a CVM não separa o tipo de sociedade.
23. **Correção de RBVA11 pré-2019** apoiada em evidência indireta (informado; não verificável pelo código).

**Infra**

24. Snapshots reprodutíveis do `fii_data.db` com hash SHA-256 (não implementado).
25. Reconciliar `config.py` ↔ `config.yaml`. A chave `decisao.sem_negocios_pregoes` continua fora do `config.yaml` (vale o default 5 do código, verificado).

Itens que **saíram** da lista: "falso positivo em eventos de capital" (a flag deixou de gerar ação, é só alerta) e "percentil de DY Gap concentrado no topo" (resolvido por reclassificação: DY Gap alto é indicador de regime, fora da contagem do radar).

**Dados alterados nas rodadas (informado, não verificável pelo código):** tabela `ativo_passivo` recarregada com a regra nova de `ativo_total` e, na segunda rodada, com as colunas de sociedades (migração 009); linhas de preço inválidas marcadas com `fonte = 'yfinance:invalido'`; dividendos deduplicados e `fechamento_aj` reconstruído; cache do otimizador regenerado com `test_stats` (o do KNIP11 tem `saved_at` 2026-11-12). O código só garante que a carga respeita essas marcas e que `recalcular_fechamento_aj` é determinístico e idempotente (`tests/test_base_integridade.py`).