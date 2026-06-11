# PROJETO.md — FII Analysis

Documentação técnica unificada do sistema de análise estatística de FIIs.

---

## 1. Visão e Objetivos

Identificar padrões estatísticos de comportamento de preço de FIIs em janelas ao redor da data-com de dividendos, apoiando decisões de investimento pessoal. O sistema **informa** — o investidor **decide**.

**Perguntas que o sistema responde:**

| # | Pergunta | Pilar |
|---|---|---|
| 1 | Como está minha carteira? | Panorama |
| 2 | Este FII está caro ou barato vs seu próprio histórico? | Valuation |
| 3 | Este fundo é sustentável ou está devolvendo capital? | Saúde financeira |
| 4 | Existe padrão estatisticamente significativo na data-com? | Event study |
| 5 | Onde olhar primeiro? | Radar descritivo |
| 6 | O que mudou desde ontem? | Alertas e relatórios |

**Princípio:** nenhuma hipótese não validada é usada como input de decisão. O radar é uma matriz booleana; o score é uma camada comunicativa que não substitui a concordância heurística de sinais estatísticos.

---

## 2. Pilares da Solução

| # | Pilar | Função | Módulos |
|---|---|---|---|
| 1 | Panorama da carteira | Visão consolidada de todos os FIIs | `features/portfolio.py`, `evaluation/panorama.py` |
| 2 | Valuation histórico | P/VP e DY comparados à própria série histórica | `features/indicators.py`, `features/valuation.py` |
| 3 | Saúde financeira | Detecção de destruição de capital, tendência PL, emissões | `features/saude.py`, `features/composicao.py` |
| 4 | Event study | CAR/BHAR, testes estatísticos, walk-forward com gap | `features/dividend_window.py`, `models/statistical.py`, `models/walk_forward.py`, `models/critic.py` |
| 5 | Radar descritivo | Matriz booleana (P/VP pct, DY Gap pct, Saúde, Liquidez) | `features/radar.py`, `evaluation/radar.py` |
| 6 | Score comunicativo (Fase 2) | Score 0–100 com 4 sub-scores (Valuation/Risco/Liquidez/Histórico) | `features/score.py`, `features/risk_metrics.py` |
| 7 | Alertas e relatórios | Diff diário, Markdown, alertas por threshold | `evaluation/alertas.py`, `evaluation/reporter.py` |

---

## 3. Arquitetura de Dados e Tecnologia

### 3.1 Fontes de dados

| Dado | Fonte | Observação |
|---|---|---|
| Preços históricos OHLCV | yfinance (`TICKER.SA`) | Carga inicial; `auto_adjust=False`; sufixo `.SA` obrigatório |
| Data-com de dividendos | yfinance | CVM **não** tem esta informação; ex-date convertida para data-com via calendário B3 |
| VP por cota, PL, cotas, DY% | CVM dados abertos | Arquivo `complemento` dos ZIPs; encoding `latin1`; separador `;` |
| Dados cadastrais (segmento, mandato) | CVM dados abertos | Arquivo `geral` dos ZIPs; campo `Data_Entrega` para point-in-time |
| Composição do ativo | CVM dados abertos | Arquivo `ativo_passivo` dos ZIPs |
| Atualização diária de preços | brapi.dev | 15.000 req/mês; token externo em `C:\Modelos-AI\Brapi\.env` |
| Benchmark (XFIX11) | yfinance (`XFIX11`) | Substituiu IFIX/^IFIX.SA (inválidos no yfinance) |
| CDI diário | BCB SGS série 12 | Taxa diária em %; armazenado em `cdi_diario` |
| Expectativas Focus BCB | BCB Focus (Selic 3m/6m/12m) | Cache diário em `dados/cache/focus_selic.json` |

**URLs CVM:**

```
https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2023.zip
https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2024.zip
https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2025.zip
https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2026.zip
```

### 3.2 Stack tecnológica

```toml
[project.dependencies]
sqlalchemy = ">=2.0"
pandas = ">=2.2"
yfinance = ">=0.2.40"
requests = ">=2.31"
python-dotenv = ">=1.0"
numpy = ">=1.26"
scipy = ">=1.12"
statsmodels = ">=0.14"
loguru = ">=0.7"
typer = ">=0.12"
rich = ">=13.0"
pandas_market_calendars = ">=4.0"
python-dateutil = ">=2.9"
pyyaml = ">=6.0"
plotly = ">=5.0"
streamlit = ">=1.30"

[project.optional-dependencies]
dev = ["pytest", "ruff"]
mcp = ["mcp>=1.1", "pydantic>=2.6"]
ml  = ["lightgbm>=4.3"]
```

**Runtime:** Anaconda em `C:/ProgramData/anaconda3/python.exe`.

### 3.3 Schema do banco (SQLite via SQLAlchemy 2.0)

Arquivo: `dados/fii_data.db` — ORM declarativo em `src/fii_analysis/data/database.py`.
Migrações idempotentes em `src/fii_analysis/data/migrations.py`.

**15 tabelas: 9 operacionais + 6 de snapshot diário (cache desnormalizado).**

#### Tabelas operacionais

| Tabela | PK | Colunas principais |
|---|---|---|
| `tickers` | `cnpj` | `ticker` (unique), `nome`, `segmento`, `mandato`, `tipo_gestao`, `codigo_isin`, `data_inicio`, `inativo_em` |
| `precos_diarios` | (`ticker`, `data`) | `abertura`, `maxima`, `minima`, `fechamento`, `fechamento_aj`, `volume`, `fonte`, `coletado_em` |
| `dividendos` | (`ticker`, `data_com`) | `valor_cota`, `fonte` |
| `relatorios_mensais` | (`cnpj`, `data_referencia`) | `data_entrega`, `vp_por_cota`, `patrimonio_liq`, `cotas_emitidas`, `dy_mes_pct`, `rentab_efetiva`, `rentab_patrim` |
| `ativo_passivo` | (`cnpj`, `data_referencia`) | `data_entrega`, `direitos_bens_imoveis`, `cri`, `cri_cra`, `lci`, `lci_lca`, `disponibilidades`, `ativo_total` |
| `cdi_diario` | `data` | `taxa_diaria_pct`, `coletado_em` |
| `benchmark_diario` | (`ticker`, `data`) | `fechamento`, `coletado_em` |
| `eventos_corporativos` | `id` (auto) | `ticker`, `cnpj`, `data`, `tipo`, `cnpj_antigo`, `cnpj_novo`, `observacao` |
| `carteira` | `id` (auto) | `ticker`, `quantidade`, `preco_medio`, `data_compra` |

#### Tabelas de snapshot diário (cache desnormalizado)

| Tabela | PK | Conteúdo |
|---|---|---|
| `snapshot_runs` | `id` (auto) | Metadados: `data_referencia`, `status` (running/ready/failed), `engine_version_global`, `universe_scope`, `universe_hash`, `carteira_hash` + campos Focus BCB |
| `snapshot_ticker_metrics` | `id` (auto) | Métricas pré-calculadas: `preco`, `vp`, `pvp`, `pvp_percentil`, `dy_12m`, `dy_24m`, `dy_gap`, `dy_gap_percentil`, `volume_21d`, `segmento` + score 0–100 (5 colunas) + risk_metrics (6 colunas) |
| `snapshot_radar` | `id` (auto) | Flags booleanas: `pvp_baixo`, `dy_gap_alto`, `saude_ok`, `liquidez_ok`, `vistos` (0-4) |
| `snapshot_decisions` | `id` (auto) | Decisões: 3 sinais brutos, ação derivada, concordância, flags de risco, janelas abertas, versionamento por motor + CDI/Focus + score |
| `snapshot_portfolio_advices` | `id` (auto) | Conselhos de carteira: `badge`, `peso_carteira`, `valor_mercado`, `racional`, `valida_ate` |
| `snapshot_structural_alerts` | `id` (auto) | Alertas estruturais: concentração, peso, n_tickers |

**Regra crítica:** P/VP, DY, DY Gap são **calculados** em tempo real, nunca persistidos (exceto nas tabelas de snapshot que os armazenam como cache pré-calculado). CNPJ e metadados de acesso são centralizados em `src/fii_analysis/data/database.py` (`get_cnpj_by_ticker`, `get_session_ctx`, `get_ultima_coleta`, `get_ultimo_preco_date`, `get_latest_ready_snapshot_run`).

### 3.4 Estrutura de pastas

```
D:/analise-de-acoes-v3/
├── AGENTS.md                          # Regras operacionais do projeto
├── config.yaml                        # Thresholds e janelas runtime (pisos, CDI, percentis)
├── pyproject.toml
├── dados/
│   ├── cvm/raw/                       # ZIPs CVM (.gitignored)
│   ├── alertas/                       # Markdown diário (evaluation/alertas.py)
│   ├── optimizer_cache/               # Cache JSON do otimizador por ticker
│   ├── cache/                         # Cache Focus BCB e outros
│   ├── snapshots/                     # Snapshots do DB para reprodutibilidade (pendente)
│   └── fii_data.db                    # SQLite principal (.gitignored)
├── src/fii_analysis/
│   ├── config.py                      # TICKERS, períodos treino/teste, custos, IR
│   ├── config_yaml.py                 # Loader do config.yaml (get_threshold)
│   ├── cli.py                         # Typer CLI: 9 comandos (panorama, fii, carteira, calendario, radar, alertas, consulta, update-prices, diario)
│   ├── __main__.py                    # Entry point para `python -m fii_analysis`
│   ├── data/
│   │   ├── database.py                # SQLAlchemy 2.0: 15 tabelas (9 operacionais + 6 snapshot)
│   │   ├── migrations.py              # Migrações idempotentes (sem Alembic): 004 migrações
│   │   ├── ingestion.py              # CVM, yfinance, brapi, BCB SGS
│   │   ├── cdi.py                    # get_cdi_acumulado_12m() — desacoplado de ingestion
│   │   └── focus_bcb.py              # fetch_focus_selic() — expectativas Focus BCB com cache
│   ├── decision/                      # Camada de decisão (Sinal → Ação)
│   │   ├── __init__.py                # Re-exports: TickerDecision, DailyCommandCenter, etc
│   │   ├── recommender.py             # Motor central de decisões (Motor V2 Fase 1–3)
│   │   ├── abertos.py                 # Detecção de oportunidades abertas
│   │   ├── portfolio_advisor.py       # Conselhos de carteira (HOLD/AUMENTAR/REDUZIR/SAIR)
│   │   ├── daily_report.py            # DailyCommandCenter: agregação decisão + carteira + CSV
│   │   └── cdi_focus_explainer.py     # Explicação CDI + Focus BCB (informativo, não altera ação)
│   ├── features/
│   │   ├── dividend_window.py         # Janela ±10 dias úteis (event study)
│   │   ├── indicators.py              # P/VP, DY trailing (point-in-time)
│   │   ├── valuation.py               # Percentil rolling, DY N-meses, DY Gap, z-score P/VP, cap rate
│   │   ├── portfolio.py               # Panorama, alocação, retorno vs IFIX, Herfindahl
│   │   ├── saude.py                   # Tendência PL, flag destruição capital, emissões, LTV
│   │   ├── fundamentos.py             # Rentabilidade efetiva/patrimonial, alavancagem, payout
│   │   ├── composicao.py              # Classificação Tijolo/Papel/Híbrido
│   │   ├── data_loader.py             # Agregadores de dados para src/ (CLI e páginas)
│   │   ├── radar.py                   # Matriz booleana (P/VP, DY Gap, Saúde, Liquidez)
│   │   ├── score.py                   # Score 0–100 com 4 sub-scores (pesos adaptativos)
│   │   ├── risk_metrics.py            # Volatilidade, beta vs XFIX11, max drawdown, yield on cost
│   │   ├── volume_signals.py          # Volume drop flag, volume ratio 21/63, perfil volume
│   │   └── momentum_signals.py        # Momentum relativo IFIX 21d, dividend safety, DY momentum
│   ├── models/
│   │   ├── statistical.py             # Event study CAR, t-test, Mann-Whitney
│   │   ├── walk_forward.py            # Splits temporais com gap + validação leakage
│   │   ├── walk_forward_rolling.py    # Validação out-of-sample deslizante (thinned) + sinal_hoje
│   │   ├── episodes.py                # Identificação de episódios thinned (min_gap)
│   │   ├── critic.py                  # Shuffle/placebo/estabilidade (CriticAgent)
│   │   ├── strategy.py                # Simulação dividend capture, otimização, risco
│   │   ├── trade_simulator.py         # Motor puro de simulação (caixa/CDI, dividendos, preço bruto)
│   │   ├── threshold_optimizer_v2.py  # Otimizador V2: grid 244 combinações, volume drop filter, cache JSON
│   │   ├── div_capture.py             # Estratégias de captura: janela flexível, compra fixa,
│   │   │                                vende-recompra, spread-recompra (lógica pura sem UI)
│   │   ├── event_study_cvm.py         # Event study CVM: CAR, NW HAC, block bootstrap placebo
│   │   ├── cdi_sensitivity.py         # Regressão P/VP ~ CDI 12m (OLS+HAC NW, batch)
│   │   ├── cdi_comparison.py          # [PESQUISA] Fase 1 V2 CDI: diagnóstico P/VP vs resíduo
│   │   └── cdi_oos_evaluation.py      # [PESQUISA] Fase 2 V2 CDI: teste OOS (veredito: RESIDUO_PIORA)
│   ├── evaluation/
│   │   ├── reporter.py                # Relatório técnico (somente dados de teste)
│   │   ├── panorama.py                # rich.Table: render carteira/calendário
│   │   ├── alertas.py                 # Markdown diário + terminal
│   │   ├── daily_report.py            # Relatório diário acionável (MD+CSV, 5 seções)
│   │   ├── daily_snapshots.py         # Geração/leitura de snapshots diários (6 tabelas)
│   │   └── radar.py                   # Render matriz booleana
│   └── mcp_server/
│       └── server.py                  # MCP: validate_split, detect_leakage, etc
├── app/
│   ├── streamlit_app.py               # Entry point Streamlit (3 grupos: Diário, Investigação, Técnico)
│   ├── state.py                       # Session state initializer + @safe_page error boundary
│   ├── pages/
│   │   ├── 1_Panorama.py              # Diário — Métricas gerais, ação hoje, score, radar OK
│   │   ├── 2_Analise_FII.py           # Wrapper standalone (não na sidebar)
│   │   ├── 3_Carteira.py              # Diário — CRUD, sugestões operacionais, alertas estruturais
│   │   ├── 4_Radar.py                 # Diário — Heatmap booleano, exportação CSV
│   │   ├── 5_Event_Study.py           # Investigação — Event study agregado
│   │   ├── 6_Alertas.py               # Investigação — Geração alertas sob demanda
│   │   ├── 7_Fundamentos.py           # Wrapper standalone (não na sidebar)
│   │   ├── 8_Fund_EventStudy.py       # Wrapper standalone (não na sidebar)
│   │   ├── 10_Otimizador_V2.py        # Wrapper standalone (não na sidebar)
│   │   ├── 11_Episodios.py            # Wrapper standalone (não na sidebar)
│   │   ├── 12_WalkForward.py          # Wrapper standalone (não na sidebar)
│   │   ├── 13_Hoje.py                 # Diário — Cockpit operacional (snapshots)
│   │   ├── 14_Dossie_FII.py           # Investigação — Consolidado por ticker (Análise/Fundamentos/Eventos)
│   │   └── 15_Laboratorio.py          # Técnico — Auditoria (Otimizador/Episódios/WalkForward)
│   └── components/
│       ├── page_content/              # Módulos reutilizáveis por Dossie/Laboratório + wrappers
│       │   ├── analise_fii.py         # render(ticker) — análise por FII
│       │   ├── episodios.py           # render() — episódios thinned
│       │   ├── fund_eventstudy.py     # render() — eventos discretos CVM
│       │   ├── fundamentos.py         # render(ticker) — DY, P/VP, PL, distribuição
│       │   ├── otimizador_v2.py       # render() — backtest com thresholds (7 abas + grid completo)
│       │   └── walkforward.py         # render() — validação deslizante + sinal_hoje
│       ├── carteira_ui.py             # Cache Streamlit + CRUD carteira (load/save/delete)
│       ├── charts.py                  # Plotly: gauge, bandas, heatmap, pizza
│       ├── tables.py                  # Formatação de dataframes para exibição
│       ├── snapshot_ui.py             # Helpers de UI para leitura de snapshots (caching 5min)
│       └── ui_shell.py                # Helpers de UI (headers, notes, sidebar)
├── scripts/                               # Wrappers CLI finos: main() + impressão, sem lógica
│   ├── load_database.py               # Orquestra download CVM + carga yfinance + XFIX11
│   ├── run_strategy.py                # Pipeline completo de estratégia
│   ├── run_event_study.py             # Event study em todos os tickers ativos + CriticAgent
│   ├── run_event_study_car_ajustado.py # CAR ajustado (remove efeito mecânico do dividendo)
│   ├── plot_car.py                    # Gráfico CAR (PNG)
│   ├── plot_car_adjusted.py           # Gráfico CAR ajustado (PNG)
│   ├── validate_knip11.py             # Validação cruzada vs FundsExplorer
│   ├── check_prices.py                # Debug de preços
│   ├── analise_janela_v2.py           # Wrapper: estratégias de janela (lógica em div_capture)
│   ├── analise_janela_flexivel.py     # Wrapper: varredura de targets (lógica em div_capture)
│   ├── analise_spread_recompra.py     # Wrapper: simulação spread recompra (lógica em div_capture)
│   ├── scrape_fundsexplorer.py        # Scraping FundsExplorer
│   ├── daily_report.py                # CLI do relatório diário (MD+CSV) com --com-otimizador
│   ├── generate_daily_snapshots.py    # CLI para gerar snapshot diário (--scope {curado,carteira,db_ativos})
│   ├── refresh_optimizer_cache.py     # Renova cache de params do otimizador (executar semanalmente)
│   ├── test_recommender.py            # Sanity check do motor de decisão
│   ├── test_saude_score.py            # Diagnóstico de saúde financeira para todos os ativos
│   ├── compare_cvm_headers.py         # Utilidade de debug: compara headers CVM entre anos
│   ├── _aceite                        # Teste de aceite V1 CDI
│   ├── _aceite_v1_cdi.py              # [PESQUISA] Teste aceite V1 CDI
│   ├── _aceite_v2_cdi.py              # [PESQUISA] Teste aceite V2 CDI (veredito: RESIDUO_PIORA)
│   ├── _aceite_v3_cdi.py              # Teste aceite V3 CDI (Focus + sensitivity + explainer)
│   ├── _patch_database.py             # Patch ad-hoc banco
│   └── _patch_ativo_passivo.py        # Patch ad-hoc ativo/passivo
├── financial-advisor/                     # Multi-agent ADK (Vertex AI) financeiro experimental
│   ├── financial_advisor/             # Agentes (data, trading, execution, risk)
│   ├── deployment/                    # Deploy no Agent Engine
│   └── eval/                          # Testes e avaliação ADK
├── .claude/agents/                        # Agentes Claude Code
│   ├── data-scientist.md
│   ├── python-pro.md
│   ├── streamlit-developer.md
│   ├── documentation-engineer.md
│   ├── ux-researcher.md
│   ├── beta-tester-trader.md
│   ├── release-manager.md
│   ├── qa-operator.md
│   └── onboarding-writer.md
└── docs/
    ├── PROJETO.md                     # ★ Documentação técnica unificada (SSOT)
    ├── STATUS_ATUAL.md                # Estado factual (regenerar quando mudar)
    ├── UX_AUDIT.md                    # Auditoria UX (43 problemas, P0→P4)
    ├── BETA_TESTER_REPORT.md          # Relatório de teste beta (persona trader)
    ├── V3_EVALUATION_LOG.md           # Log de avaliação da validação V3
    └── VARIAVEIS_ANALISE_FII_BRASIL.md # Referência de variáveis para análise de FIIs
```

---

## 4. Regras de Integridade de Dados

### 4.1 Separação temporal de períodos

```
|--- Treino ---|--- gap (10d) ---|--- Validação ---|--- gap (10d) ---|--- Teste ---|
```

- Sem shuffle em nenhuma etapa
- Gap mínimo entre períodos: 10 dias úteis
- Métricas finais **somente** do conjunto de teste
- Nunca usar dados futuros para calcular features do passado

### 4.2 Centralização de Thresholds (config.yaml)

Parâmetros de decisão e filtros são centralizados na seção `thresholds` do `config.yaml`:

| Parâmetro | Descrição | Default |
|---|---|---|
| `pvp_percentil_barato` | Percentil P/VP para sinal verde no radar | 30 |
| `dy_gap_percentil_caro` | Percentil DY Gap para sinal vermelho no radar | 70 |
| `meses_consec_alerta` | Meses distribuindo mais que gera para erro de saúde | 3 |
| `alavancagem_limite` | Razão Ativo/PL considerada alavancagem significativa | 1.05 |
| `piso_liquidez` | Volume financeiro médio 21d mínimo | 500.000 |
| `dias_staleness` | Dias de atraso permitidos na coleta de preço | 3 |

A função `classificar_alerta_distribuicao` (`fundamentos.py`) utiliza esses thresholds para categorizar o risco de destruição de capital (Success, Warning, Error).

### 4.3 Point-in-time obrigatório no VP

O VP por cota vem dos Informes Mensais da CVM. Cada relatório tem duas datas:
- `Data_Referencia` — mês do relatório (**não** usar para filtro)
- `Data_Entrega` — quando foi entregue à CVM (**usar** para filtro)

```python
vp = SELECT Valor_Patrimonial_Cotas
     FROM relatorios_mensais
     WHERE cnpj = X AND data_entrega <= t
     ORDER BY data_referencia DESC LIMIT 1
```

### 4.4 P/VP e DY são calculados, nunca armazenados

```python
pvp_em_t = preco_em_t / vp_vigente_em_t(data_entrega <= t)
dy_trailing_t = soma_dividendos_12m_ate_t / preco_medio_periodo
```

### 4.5 Janela da data-com: ±10 dias úteis

Janelas maiores (ex: ±30 dias) se sobrepõem porque FIIs pagam mensalmente. Sobreposição viola independência estatística do event study.

Quando duas datas-com distam < 21 dias úteis, **o evento seguinte é descartado** — não truncar janela (viés de seleção).

### 4.6 Ingestão idempotente

Antes de coletar dados, verificar se já existem no banco. Nunca sobrescrever sem verificação. O preço ajustado do yfinance é recalculado retroativamente — sempre salvar `coletado_em`.

### 4.7 Proteções contra data leakage

| Proteção | Mecanismo |
|---|---|
| Point-in-time no VP | Usar `Data_Entrega` da CVM, não `Data_Referencia` |
| Preço ajustado rastreável | Salvar `coletado_em` (timestamp) em cada registro |
| Walk-forward com gap | Gap entre treino e validação absorve lookback das features |
| MCP como portão | Pipeline não avança sem aprovação do MCP Estatístico |
| CriticAgent | Tenta ativamente falsificar os resultados antes de reportar |
| Reporter lacrado | Módulo de relatório acessa somente dados de teste |

### 4.8 Dados faltantes

- **CVM defasada (> 45 dias sem relatório novo):** exibir aviso `[CVM defasada]`. Não preencher com valor futuro.
- **FII sem histórico suficiente:** percentis rolling exigem ≥ 252 pregões; abaixo, exibir `n/d`.
- **Dividendo sem data-com:** excluir da análise de event study, manter no panorama.
- **NaN nunca vira zero silenciosamente.**

---

## 5. Métricas e Metodologia

### 5.1 Valuation

| Métrica | Definição |
|---|---|
| **P/VP em t** | `preco_em_t / vp_vigente(data_entrega <= t)` — VP do último relatório CVM entregue antes de t. |
| **Percentil P/VP rolling** | Posição na distribuição da janela de 504 pregões (2 anos) até t−1. |
| **Z-score P/VP** | `(pvp - media_504d) / desvio_504d` — normalização do P/VP. |
| **DY N-meses** (12/24/36) | Soma dividendos com data-com em `[t−N meses, t]` / preço atual. |
| **DY Gap** | `DY 12m − CDI acumulado 12m` (point-in-time). |
| **Percentil DY Gap** | Posição na distribuição da janela de 252 pregões (1 ano) até t−1. |
| **Cap Rate anualizado** | `DY_3m × 4` anualizado. |
| **Cap Rate spread** | `Cap Rate anualizado − CDI acumulado 12m`. |

### 5.2 Saúde financeira e Fundamentos

| Métrica | Definição |
|---|---|
| **Mês Saudável** | `rentab_patrim >= 0` E `rentab_efetiva >= rentab_patrim`. |
| **Alertas de Saúde** | **Erro:** >= `meses_consec_alerta` (default 3) consecutivos não saudáveis. **Aviso:** < 4 meses saudáveis no total dos últimos 6 meses. |
| **Alavancagem** | `Ativo_Total / Patrimonio_Liquido`. Alerta se > `alavancagem_limite`. |
| **LTV (Leverage to Value)** | `max(0, ativo_total - PL) / ativo_total`. |
| **Tendência PL** | Regressão linear (6m, 12m) sobre o VP por cota. |
| **Emissões recentes** | Salto em `Cotas_Emitidas` mês a mês > 1%. |

### 5.3 Composição do ativo

| Classificação | Regra |
|---|---|
| **Tijolo** | Imóveis físicos ≥ 60% do ativo |
| **Papel** | Recebíveis (CRI + LCI + LCI_LCA) ≥ 60% |
| **Híbrido** | Caso contrário |

Fonte: arquivo `ativo_passivo` da CVM. Campos: `Direitos_Bens_Imoveis`, `CRI`, `LCI`, `LCI_LCA`, `Disponibilidades`.

### 5.4 Radar descritivo (Fase 1)

Matriz booleana — 4 filtros independentes, sem ponderação:

| Filtro | Critério |
|---|---|
| P/VP Baixo | Percentil rolling 504d < 30 |
| DY Gap Alto | Percentil rolling 252d > 70 |
| Saúde OK | Sem flag de destruição de capital |
| Liquidez OK | Volume financeiro médio 21d ≥ piso YAML (default: R$ 500.000) |

FIIs com todos os ✓ aparecem no topo. Ordenação por número de ✓.

**Proximidade da data-com não entra no radar** enquanto o event study não validar padrão estatisticamente significativo.

### 5.5 Score comunicativo (Fase 2)

Score 0–100 com 4 sub-scores ponderados (não altera decisões, apenas comunica qualidade geral):

| Sub-score | Peso | Composição |
|---|---|---|
| Valuation | 35% | P/VP percentil (invertido) + DY Gap percentil + z-score (pesos adaptativos 50/30/20 ou fallback 60/40) |
| Risco | 30% | Volatilidade + Beta vs XFIX11 + Max Drawdown (percentis no universo) |
| Liquidez | 20% | Faixas fixas em R$/dia (< R$ 200k: 20 pts; R$ 1–5M: 75 pts; ≥ R$ 5M: 90 pts) |
| Histórico | 15% | Consistência DY 24m (CV invertido: CV ≤ 0.5 → 100 pts) |

Score é **purely informativo** — não substitui concordância heurística de sinais (BUY/SELL/HOLD) nem aparece em cálculos de risco.

### 5.6 Event study

- **CAR** (Cumulative Abnormal Return): retorno acumulado do FII menos retorno acumulado do benchmark (IFIX) na janela ±10 pregões.
- **BHAR** (Buy-and-Hold Abnormal Return): variação buy-and-hold vs benchmark.
- **Testes:** t-test pareado (pré vs pós), Mann-Whitney U, t-test 1 amostra (dia 0).
- **Correção múltiplas comparações:** Benjamini-Hochberg ao reportar resultado por FII.

### 5.7 Walk-forward com gap

Split temporal (default 60/20/20) com gap de 10 dias úteis entre períodos. Função `validate_no_leakage()` detecta sobreposição automaticamente.

### 5.8 CriticAgent (falsificação)

| Teste | O que faz |
|---|---|
| **Permutation shuffle** | Embaralha sinais de evento e mede acurácia (detecta correlação espúria) |
| **Placebo** | Usa datas aleatórias como falsas datas-com; compara com datas reais via Mann-Whitney |
| **Subperiod stability** | Compara 1ª metade vs 2ª metade dos eventos via t-test |

**Veredito:** aprovado somente se todos os 3 testes passam.

### 5.9 Estratégia de dividend capture

Simulação com preço ajustado, otimização grid search (244 combinações: buy [15–50], sell [55–90], spread≥15), métricas de risco (Sharpe, Sortino, drawdown, perdas consecutivas), comparação com buy-and-hold. Custos B3 (0.03% round-trip) e IR 20% sobre ganho de capital descontados. Volume drop flag vetorizado filtra BUYs com queda forte de volume.

### 5.10 Camada CDI V1 (informativa)

- **CDI Sensitivity:** regressão P/VP ~ CDI 12m (OLS+HAC NW, frequência semanal, min 104 obs). Retorna beta, R², p-value, resíduo atual e percentil.
- **Focus BCB:** expectativas Selic 3m/6m/12m com cache diário.
- **CDI Focus Explainer:** combina beta + delta Focus + resíduo percentil para explicação textual.
- **Não altera `_derivar_acao()`** — é puramente informativo, enriquece rationale.

### 5.11 Volume e Momentum (Motor V2 Fase 1)

| Sinal | Definição |
|---|---|
| **Volume drop flag** | Volume 21d < volume 63d − threshold% (filtra BUYs no otimizador) |
| **Volume ratio 21/63** | Razão volume 21d / volume 63d |
| **Momentum relativo IFIX** | Retorno FII 21d vs IFIX 21d |
| **Dividend safety** | Análise payout vs caixa, cortes 24m, flag insustentável |

---

## 6. Interfaces do Sistema

### 6.1 Como usar o CLI

O CLI é independente do Streamlit e deve ser executado no terminal utilizando o interpretador do Anaconda:

**Comando base:**
`C:/ProgramData/anaconda3/python.exe -m fii_analysis COMANDO`

| Comando | Função |
|---|---|
| `panorama` | Tabela de todos os FIIs monitorados com métricas-chave |
| `fii TICKER` | Análise detalhada de um FII (valuation, saúde, composição, datas-com) |
| `consulta TICKER` | **Analítico IA:** Integra indicadores locais com Gemini + Google Search para análise qualitativa em 4 seções |
| `radar` | Exibe a matriz booleana de filtros (P/VP, DY Gap, Saúde, Liquidez) |
| `alertas` | Gera e exibe alertas diários com base nos thresholds de risco |
| `calendario` | Lista as próximas datas-com previstas para os próximos 30 dias |
| `carteira` | Exibe posições, alocação por segmento e retorno vs IFIX |
| `update-prices` | Pipeline diário completo: preços + dividendos + CDI + XFIX11 + cache otimizador + snapshot |
| `diario` | Cockpit do dia no terminal (sinais 3 motores, score 0–100, percentis) lendo do snapshot |

### 6.2 Streamlit Dashboard

Entry point: `app/streamlit_app.py`. Layout `wide`, sidebar expandida com 3 grupos.

**Navegação (sidebar):**

- **Diário:** `13_Hoje.py`, `3_Carteira.py`, `1_Panorama.py`, `4_Radar.py`
- **Investigação:** `14_Dossie_FII.py`, `6_Alertas.py`, `5_Event_Study.py`
- **Técnico:** `15_Laboratorio.py`

As páginas 2/7/8/10/11/12 são wrappers standalone (não na sidebar) — seu conteúdo é renderizado dentro do Dossie (2/7/8) e do Laboratório (10/11/12) via `app/components/page_content/*.py`.

| Página | Sidebar | Conteúdo |
|---|---|---|
| **1_Panorama** | Diário | Métricas gerais, coluna Ação Hoje, coluna Score 0–100, radar OK |
| **3_Carteira** | Diário | CRUD de posições, sugestões operacionais (badge HOLD/AUMENTAR/REDUZIR/SAIR), alertas estruturais |
| **4_Radar** | Diário | Heatmap booleano, tabela detalhada, exportação CSV |
| **13_Hoje** | Diário | Cockpit operacional: recomendações diárias, watchlist, carteira cruzada, riscos, contexto de juros |
| **14_Dossie_FII** | Investigação | Consolidado por ticker — abas Análise FII / Fundamentos / Eventos CVM |
| **5_Event_Study** | Investigação | Event study agregado: CAR, testes, CriticAgent |
| **6_Alertas** | Investigação | Geração sob demanda, listagem de Markdowns por data |
| **15_Laboratorio** | Técnico | Auditoria/backtest — abas Otimizador V2 / Episódios / Walk-Forward |
| **2_Analise_FII** | Não | Wrapper → `page_content/analise_fii.py` |
| **7_Fundamentos** | Não | Wrapper → `page_content/fundamentos.py` |
| **8_Fund_EventStudy** | Não | Wrapper → `page_content/fund_eventstudy.py` |
| **10_Otimizador_V2** | Não | Wrapper → `page_content/otimizador_v2.py` |
| **11_Episodios** | Não | Wrapper → `page_content/episodios.py` |
| **12_WalkForward** | Não | Wrapper → `page_content/walkforward.py` |

**Componentes reutilizáveis** (`app/components/`):

| Componente | Função |
|---|---|
| `carteira_ui.py` | Cache Streamlit + CRUD carteira: `load_tickers_ativos`, `load_carteira_db`, `save_posicao`, `delete_posicao` |
| `charts.py` | Plotly: `pvp_gauge`, `pvp_historico_com_bandas`, `pl_trend_chart`, `composicao_pie`, `car_plot`, `radar_heatmap`, `carteira_alocacao_pie`, `carteira_segmento_pie` |
| `tables.py` | Formatadores: `format_currency`, `format_pct`, `format_number`, `render_panorama_table`, `render_radar_matriz` |
| `snapshot_ui.py` | Helpers de UI para leitura de snapshots diários com `@st.cache_data(ttl=300)`, incluindo `load_decisions_snapshot` |
| `ui_shell.py` | Helpers de UI (headers, notes, sidebar) |

### 6.3 Agentes Claude Code

Agentes sub-task em `.claude/agents/` — carregados automaticamente pelo Claude Code:

| Agente | Arquivo | Especialização |
|---|---|---|
| **data-scientist** | `data-scientist.md` | Regras estatísticas do projeto: split temporal, leakage, testes |
| **python-pro** | `python-pro.md` | Implementação Python: SQLAlchemy, pandas, lógica pura sem UI |
| **streamlit-developer** | `streamlit-developer.md` | Páginas Streamlit e componentes de visualização |
| **documentation-engineer** | `documentation-engineer.md` | Atualização de PROJETO.md e STATUS_ATUAL.md |
| **ux-researcher** | `ux-researcher.md` | Pesquisa UX: síntese de feedback em ações implementáveis |
| **beta-tester-trader** | `beta-tester-trader.md` | Teste beta: perspectiva de trader B&H real |

### 6.4 MCP Server

Arquivo: `src/fii_analysis/mcp_server/server.py`. Ferramentas disponíveis:

| Tool | Função |
|---|---|
| `validate_split` | Verifica separação temporal treino/validação/teste sem overlap |
| `detect_leakage` | Cruza metadados de features com boundaries do split |
| `check_window_overlap` | Verifica sobreposição de janelas de event study |
| `summary_report` | Relatório resumo com métricas de validação |

---

## 7. FIIs Monitorados

### Ativos

| Ticker | Segmento | Tipo | Canário | Histórico desde |
|---|---|---|---|---|
| CPTS11 | Papel | Papel | — | 2015-09 |
| CPSH11 | Híbrido | Híbrido | — | 2023-07 |
| GARE11 | Tijolo | Tijolo | — | 2024-03 |
| HSRE11 | Tijolo | Tijolo | — | 2020-12 |
| KNIP11 | Papel (CRI) | Papel | **Validação cruzada** | 2017-10 |
| SNEL11 | — | — | — | — |

### Inativos

| Ticker | CNPJ | Motivo | Ação |
|---|---|---|---|
| SNFF11 | 40.011.225/0001-68 | Liquidação/descontinuação | Preservar histórico; `inativo_em` marcado; excluído de panorama/radar/alertas |

**Regra:** lista curada, escolhida a dedo — não automatizar adição de novos FIIs.

---

## 8. Estado Atual de Implementação

### Dados

| Componente | Status | Arquivo |
|---|---|---|
| Schema SQLite (9 tabelas) | Implementado | `data/database.py` |
| Migrações idempotentes (004) | Implementado | `data/migrations.py` |
| Ingestão CVM (ZIP → complemento/geral/ativo_passivo) | Implementado | `data/ingestion.py` |
| Ingestão preços yfinance (incremental) | Implementado | `data/ingestion.py` |
| Ingestão dividendos yfinance (ex-date → data-com) | Implementado | `data/ingestion.py` |
| CDI diário (BCB SGS série 12) | Implementado | `data/ingestion.py` |
| CDI acumulado 12m | Implementado | `data/cdi.py` |
| Benchmark XFIX11 (yfinance) | Implementado | `data/ingestion.py` |
| Expectativas Focus BCB (Selic) | Implementado | `data/focus_bcb.py` |
| Conversão ex-date → data-com via calendário B3 | Implementado | `data/ingestion.py` |

### Features

| Componente | Status | Arquivo |
|---|---|---|
| Janela ±10 pregões com retornos | Implementado | `features/dividend_window.py` |
| Retornos anormais (vs benchmark) | Implementado | `features/dividend_window.py` |
| P/VP point-in-time | Implementado | `features/indicators.py` |
| DY trailing (série e valor) | Implementado | `features/indicators.py` |
| Percentil rolling P/VP | Implementado | `features/valuation.py` |
| Z-score P/VP (504d) | Implementado | `features/valuation.py` |
| DY N-meses (12/24/36) | Implementado | `features/valuation.py` |
| DY Gap vs CDI | Implementado | `features/valuation.py` |
| Cap Rate anualizado + spread CDI | Implementado | `features/valuation.py` |
| Panorama carteira | Implementado | `features/portfolio.py` |
| Alocação, Herfindahl, retorno vs IFIX | Implementado | `features/portfolio.py` |
| Tendência PL, flag destruição capital | Implementado | `features/saude.py` |
| LTV (Leverage to Value) flag | Implementado | `features/saude.py` |
| Análise emissões | Implementado | `features/saude.py` |
| Classificação Tijolo/Papel/Híbrido | Implementado | `features/composicao.py` |
| Matriz booleana radar | Implementado | `features/radar.py` |
| Score 0–100 (4 sub-scores, pesos adaptativos) | Implementado | `features/score.py` |
| Volatilidade, beta vs XFIX11, max drawdown, yield on cost | Implementado | `features/risk_metrics.py` |
| Volume drop flag, volume ratio 21/63 | Implementado | `features/volume_signals.py` |
| Momentum relativo IFIX 21d, dividend safety | Implementado | `features/momentum_signals.py` |
| Rentabilidade efetiva/patrimonial, alavancagem | Implementado | `features/fundamentos.py` |

### Models

| Componente | Status | Arquivo |
|---|---|---|
| Event study (CAR) | Implementado | `models/statistical.py` |
| t-test pareado, Mann-Whitney | Implementado | `models/statistical.py` |
| t-test dia 0 | Implementado | `models/statistical.py` |
| Walk-forward split com gap | Implementado | `models/walk_forward.py` |
| Validação de leakage | Implementado | `models/walk_forward.py` |
| Walk-forward rolling (thinned) + sinal_hoje | Implementado | `models/walk_forward_rolling.py` |
| Episódios de P/VP extremo (thinned, min_gap) | Implementado | `models/episodes.py` |
| CriticAgent (shuffle/placebo/estabilidade) | Implementado | `models/critic.py` |
| Simulação dividend capture | Implementado | `models/strategy.py` |
| Otimização grid search | Implementado | `models/strategy.py` |
| Métricas risco (Sharpe, Sortino, drawdown) | Implementado | `models/strategy.py` |
| Buy-and-hold comparison | Implementado | `models/strategy.py` |
| Motor puro de simulação (trade_simulator) | Implementado | `models/trade_simulator.py` |
| Otimizador V2 (grid 244 combos, volume drop, cache) | Implementado | `models/threshold_optimizer_v2.py` |
| Estratégias div capture (janela flexível, compra fixa, vende-recompra, spread) | Implementado | `models/div_capture.py` |
| Event study CVM (CAR, NW HAC, block bootstrap placebo) | Implementado | `models/event_study_cvm.py` |
| CDI sensitivity (regressão OLS+HAC, batch) | Implementado | `models/cdi_sensitivity.py` |
| CDI comparison [PESQUISA] | Implementado | `models/cdi_comparison.py` |
| CDI OOS evaluation [PESQUISA] | Implementado | `models/cdi_oos_evaluation.py` |

### Decision

| Componente | Status | Arquivo |
|---|---|---|
| Motor central de decisões (Motor V2 F1–F3) | Implementado | `decision/recommender.py` |
| CDI Focus Explainer (informativo) | Implementado | `decision/cdi_focus_explainer.py` |
| Detecção de oportunidades abertas | Implementado | `decision/abertos.py` |
| Conselhos de carteira (badge + export MD/CSV) | Implementado | `decision/portfolio_advisor.py` |
| DailyCommandCenter (agregação + relatório) | Implementado | `decision/daily_report.py` |

### Evaluation

| Componente | Status | Arquivo |
|---|---|---|
| Relatório técnico (reporter) | Implementado | `evaluation/reporter.py` |
| Render panorama (rich.Table) | Implementado | `evaluation/panorama.py` |
| Alertas diários (Markdown + terminal) | Implementado | `evaluation/alertas.py` |
| Relatório diário acionável (MD+CSV, 5 seções) | Implementado | `evaluation/daily_report.py` |
| Snapshots diários (6 tabelas desnormalizadas) | Implementado | `evaluation/daily_snapshots.py` |
| Render radar (matriz booleana) | Implementado | `evaluation/radar.py` |

### Interfaces

| Componente | Status | Arquivo |
|---|---|---|
| CLI Typer (9 comandos) | Implementado | `cli.py` |
| Configuração Python (tickers, períodos) | Implementado | `config.py` |
| Configuração YAML (thresholds runtime) | Implementado | `config_yaml.py` |
| MCP Server (4 tools) | Implementado | `mcp_server/server.py` |
| Streamlit Dashboard (14 arquivos página, 8 na sidebar) | Implementado | `app/streamlit_app.py` + `app/pages/` |
| Componentes Plotly | Implementado | `app/components/charts.py` |
| CRUD carteira Streamlit | Implementado | `app/components/carteira_ui.py` |
| Data loader (src/) | Implementado | `features/data_loader.py` |
| Formatadores de tabela | Implementado | `app/components/tables.py` |
| Snapshot UI helpers | Implementado | `app/components/snapshot_ui.py` |
| Error boundary global (@safe_page) | Implementado | `app/state.py` |

### Scripts

| Script | Status | Função |
|---|---|---|
| `load_database.py` | Operacional | Download ZIPs CVM + carga yfinance + XFIX11 |
| `run_strategy.py` | Operacional | Pipeline completo de estratégia |
| `run_event_study.py` | Operacional | Event study em todos os tickers ativos + CriticAgent |
| `run_event_study_car_ajustado.py` | Operacional | Event study com CAR ajustado |
| `plot_car.py` | Operacional | Gráfico CAR (PNG) |
| `plot_car_adjusted.py` | Operacional | Gráfico CAR ajustado (PNG) |
| `validate_knip11.py` | Operacional | Validação cruzada vs FundsExplorer |
| `check_prices.py` | Debug | Inspeção de preços |
| `analise_janela_v2.py` | Wrapper | Estratégias de janela (lógica em `models/div_capture.py`) |
| `analise_janela_flexivel.py` | Wrapper | Varredura de targets (lógica em `models/div_capture.py`) |
| `analise_spread_recompra.py` | Wrapper | Simulação spread recompra (lógica em `models/div_capture.py`) |
| `scrape_fundsexplorer.py` | Operacional | Scraping FundsExplorer |
| `daily_report.py` | Operacional | CLI do relatório diário (MD+CSV) com `--com-otimizador` |
| `generate_daily_snapshots.py` | Operacional | CLI para gerar snapshot diário |
| `refresh_optimizer_cache.py` | Operacional | Renova cache do otimizador (executar semanalmente) |
| `test_recommender.py` | Debug | Sanity check do motor de decisão |
| `test_saude_score.py` | Debug | Diagnóstico de saúde financeira para todos os ativos |
| `compare_cvm_headers.py` | Debug | Comparação de headers CVM entre anos |
| `_aceite` | Teste aceite | Teste de aceite V1 CDI |
| `_aceite_v1_cdi.py` | [PESQUISA] | Teste aceite V1 CDI |
| `_aceite_v2_cdi.py` | [PESQUISA] | Teste aceite V2 CDI (veredito: RESIDUO_PIORA) |
| `_aceite_v3_cdi.py` | Teste aceite | Teste aceite V3 CDI (Focus + sensitivity) |
| `_patch_database.py` | Debug | Patch ad-hoc banco |
| `_patch_ativo_passivo.py` | Debug | Patch ad-hoc ativo/passivo |

### Volume de dados

| Tabela | Registros (2026-04-16) |
|---|---|
| `tickers` | 6 ativos + 1 inativo (SNFF11) |
| `precos_diarios` | 8.184 (6+ tickers, SNFF11 preservado) |
| `dividendos` | 355 |
| `relatorios_mensais` | 227 |

### Status Geral

- **Fase 0–5 + Refatoração Arquitetural + Camada de Decisão (F1–F7) + Motor V2 (Fase 1–3) + Validação V3 Concluídos.**
- O sistema possui separação clara entre ingestão (data), lógica de negócio (features), análise estatística (models), camada de decisão (decision), cache de snapshots (evaluation/daily_snapshots) e visualização (app/evaluation).
- O CLI conta com **9 comandos** incluindo `consulta TICKER`, `update-prices` e `diario`.
- **14 arquivos de página** Streamlit com error boundary global; 8 visíveis na sidebar (3 grupos: Diário, Investigação, Técnico).
- Sistema de snapshots diários com 6 tabelas desnormalizadas, versionamento por motor e hash de universo/carteira.
- Score comunicativo 0–100 implementado com pesos adaptativos (não altera decisões).
- Camada CDI V1 informativa (sensitivity + Focus BCB + explainer) — não altera `_derivar_acao()`.
- Camada CDI V2 (resíduo como sinal) testada e **rejeitada** em OOS.
- Benchmark XFIX11 substituiu IFIX/^IFIX.SA (inválidos no yfinance).

---

## 9. Próximos Passos

### PRIORIDADE ALTA
- **Falso positivo em eventos de capital:** `flag_destruicao_capital` e `dividend_safety_flag` disparam incorretamente quando FII vende ativo e distribui ganho pontual. Decisão pendente.
- **Ingestão do `inf_mensal_fii_imovel.csv`:** Utilizar o mesmo ZIP da CVM já baixado para extrair dados de imóveis.
- **Cálculo de Vacância e ABL:** Calcular Vacância Física e Área Bruta Locável (ABL) por fundo.
- **Persistência:** Adicionar a tabela `imoveis` no banco de dados SQLite.
- **Radar:** Expor novo filtro no Radar: `Vacância < 10%`.

### PRIORIDADE MÉDIA
- **Cap Rate da Carteira:** Cruzar dados de `ativo_passivo` com a receita de aluguel para calcular o Cap Rate real.
- **WALT:** Calcular o prazo médio dos contratos (Weighted Average Lease Term).

### PRIORIDADE BAIXA
- **Indexadores (IPCA+/CDI+):** Identificar indexadores para FIIs de Papel (requer ingestão do informe trimestral estruturado da CVM).

---

## 10. Roadmap

### Prioridade 1 — Testes
- Criar `tests/` com cobertura dos módulos de features e models.
- Priorizar testes de point-in-time, leakage e integridade temporal.

### Prioridade 2 — Relatórios e histórico
- `fii diario` — diff desde última execução (o que mudou).
- Relatório mensal Markdown: panorama + alertas + event study + radar + proventos.
- Log de decisões de investimento (compra/venda) para backtest futuro vs IFIX.

### Prioridade 3 — Reprodutibilidade
- Implementar snapshots reprodutíveis do `fii_data.db` com hash SHA-256.
- Todo relatório grava o hash do snapshot usado no cabeçalho.

### Prioridade 4 — Limpeza de configuração
- Reconciliar `config.py` (constantes de escopo) e `config.yaml` (parâmetros de decisão).
- Eliminar duplicações.

### Fora do escopo
- ML / LightGBM enquanto event study não validar padrão.
- Streamlit/Flask adicionais (dashboard atual é suficiente).
- Multi-usuário, autenticação, notificações push.
- Exportação para IR.
- Adicionar novos FIIs ao universo (lista curada, não automatizar).

---

## 11. Registro de Decisões (ADR)

| # | Decisão | Contexto | Escolha | Motivo |
|---|---|---|---|---|
| ADR-01 | Banco de dados | Projeto solo, sem concorrência | SQLite via SQLAlchemy 2.0 | Arquivo único, backup simples, migração para PostgreSQL = trocar connection string |
| ADR-02 | P/VP e DY como cálculo | Risco de inconsistência com dados históricos | Nunca persistir, sempre calcular | Evita divergência entre preço ajustado retroativo e VP salvo |
| ADR-03 | Point-in-time no VP | VP muda com cada relatório CVM | Filtrar por `Data_Entrega`, não `Data_Referencia` | Elimina lookahead bias — o investidor só conhece o VP após a entrega à CVM |
| ADR-04 | Janela ±10 dias úteis | FIIs pagam dividendos mensalmente | ±10 pregões, não ±30 | Janelas de ±30 se sobrepõem entre dividendos consecutivos; sobreposição viola independência estatística |
| ADR-05 | Radar booleano + Score comunicativo (Fase 2) | Matriz honesta (sem ponderação) + Score 0–100 informativo | Filtros booleanos + Score 4 sub-scores ponderados (não altera decisões) | Booleanos são honestos e testáveis; score é complemento comunicativo que não entra na lógica de decisão |
| ADR-06 | Data-com via yfinance | CVM não publica data-com | yfinance (ex-date convertida via calendário B3) | Única fonte gratuita e acessível |
| ADR-07 | Preços: yfinance + brapi | Necessidade de histórico longo + atualização diária | yfinance para carga inicial; brapi para updates diários | yfinance tem histórico desde 2015+; brapi é mais rápido para última cotação |
| ADR-08 | Sem ML prematuro | Tentação de aplicar LightGBM antes de validar base | Modelos estatísticos clássicos até event study confirmar padrão | Projeto anterior atingiu 96% de acurácia falsa por data leakage. Validação estatística antes de ML |
| ADR-09 | KNIP11 como canário | SNFF11 entrou em liquidação | KNIP11 substitui SNFF11 para validação cruzada vs FundsExplorer | Papel (CRI) com histórico desde 2017, dados completos, validável externamente |
| ADR-10 | Token brapi fora do projeto | Segurança de credenciais | `C:\Modelos-AI\Brapi\.env` → `os.getenv("BRAPI_API_KEY")` | Nunca hardcodar nem versionar secrets |
| ADR-11 | CriticAgent como gate | Risco de resultados espúrios | 3 testes obrigatórios (shuffle, placebo, estabilidade) | Resultado reportado somente se passar em todos os testes de falsificação |
| ADR-12 | Eventos sobrepostos descartados | Janelas de FIIs mensais podem se sobrepor | Descartar evento seguinte (não truncar) | Truncar janela introduz viés de seleção |
| ADR-13 | NaN nunca vira zero | Dados faltantes são comuns em FIIs pequenos | Propagar NaN, exibir `n/d` | Zero silencioso mascara ausência de dado e distorce estatísticas |
| ADR-14 | Streamlit como interface web | Necessidade de visualização interativa | Streamlit com 3 grupos de navegação (Diário/Investigação/Técnico) | Mais rápido que Flask para prototipagem; componentes Plotly nativos |
| ADR-15 | Proximidade data-com fora do radar | Radar poderia usar data-com como critério | Somente após event study validar padrão por FII | Se o padrão não é estatisticamente significativo, usar data-com como critério é superstição |
| ADR-16 | Python via Anaconda | 3 intérpretes Python instalados na máquina | `C:/ProgramData/anaconda3/python.exe` | Único com todas as dependências instaladas |
| ADR-17 | Snapshots diários desnormalizados | Queries compostas na página Hoje eram lentas | 6 tabelas de cache pré-calculado | Uma query simples substitui 10+ queries por ticker. Versionamento por motor para rastreabilidade |
| ADR-18 | Camada de decisão separada | Sinais estatísticos não eram acionáveis | `decision/recommender.py` com Sinal/Ação/Risco separados | Sinal é estatístico puro; Ação é derivada com veto; Risco é independente. Concordância heurística, nunca IC |
| ADR-19 | CLI `consulta` com Gemini | Indicadores locais não cobriam análise qualitativa | Integração Gemini + Google Search | 4 seções: contexto, fundamentos, riscos, veredito. Não substitui análise local, complementa |
| ADR-20 | Governança de documentação | Múltiplas IAs com configs duplicadas e dessincronizadas | SSOT em `docs/PROJETO.md` + thin wrappers por IA | Elimina ~950 linhas de duplicação; drift impossível; nova IA = novo wrapper de 15 linhas |
| ADR-21 | Benchmark XFIX11 | ^IFIX e IFIX11.SA inválidos no yfinance (404/delisted) | `XFIX11` via yfinance (period=max) | ETF que replica IFIX; histórico completo disponível; substitui ^IFIX para beta e momentum |
| ADR-22 | CDI V2 rejeitada | Hipótese: resíduo CDI-ajustado melhor que P/VP bruto | Manter P/VP bruto + CDI V1 informativo | Resíduo piora em OOS (2 piora, 1 empata, 1 não-confiável); CDI é parte do sinal, não ruído |

---

## 12. Governança de Documentação

> **Regra fundamental:** `docs/PROJETO.md` é a fonte única de verdade (SSOT) deste projeto.
> Todo arquivo de configuração de IA (`CLAUDE.md`, `AGENTS.md`, `.gemini/GEMINI.md`) é um
> **ponteiro fino** que referencia este documento — **nunca** duplica seu conteúdo.

### 12.1 Hierarquia de documentos

```
┌───────────────────────────────────────────────────────┐
│  docs/PROJETO.md                                      │
│  ★ FONTE ÚNICA DE VERDADE (SSOT)                      │
│  Regras, arquitetura, decisões (ADR), metodologia,    │
│  interfaces, governança, status, próximos passos      │
├───────────────────────────────────────────────────────┤
│  docs/STATUS_ATUAL.md                                 │
│  Snapshot factual do estado corrente (módulos, bugs,  │
│  dados). Regenerado quando há mudança estrutural.     │
├───────────────────────────────────────────────────────┤
│  CLAUDE.md         → ponteiro + notas Claude-specific │
│  AGENTS.md         → ponteiro + notas Codex-specific  │
│  .gemini/GEMINI.md → ponteiro + notas Gemini-specific │
│  (thin wrappers — 5-20 linhas cada, ZERO duplicação)  │
├───────────────────────────────────────────────────────┤
│  docs/UX_AUDIT.md, docs/BETA_TESTER_REPORT.md, etc.  │
│  Documentação auxiliar — referenciada pelo SSOT       │
└───────────────────────────────────────────────────────┘
```

### 12.2 Regras para qualquer IA (Claude, Codex, Gemini, Cursor, etc.)

1. **Antes de qualquer alteração no projeto:** LEIA `docs/PROJETO.md` na íntegra.
2. **Nunca copie conteúdo** de `docs/PROJETO.md` para `CLAUDE.md`, `AGENTS.md` ou qualquer outro arquivo de configuração de IA — use referência (`→ veja docs/PROJETO.md §X`).
3. **Após mudança estrutural** (novo módulo, nova tabela, nova página, novo script): atualize `docs/STATUS_ATUAL.md`.
4. **Após mudança arquitetural** (novo ADR, regra nova, decisão de design): atualize `docs/PROJETO.md`.
5. **Após mudança cosmética ou bugfix menor**: sem obrigação de atualizar docs.
6. **Se inseguro se deve documentar**: documente. Remover é mais fácil que lembrar.

### 12.3 Checklist pós-tarefa (toda IA deve executar ao final de cada tarefa)

```
- [ ] A mudança afeta arquitetura ou regras do projeto?
      → Sim: atualizar seções relevantes de docs/PROJETO.md
- [ ] A mudança afeta o estado factual (módulos, bugs, status, dados)?
      → Sim: atualizar docs/STATUS_ATUAL.md
- [ ] A mudança cria ou remove arquivos/módulos?
      → Sim: atualizar ambos PROJETO.md (estrutura) e STATUS_ATUAL.md (módulos)
- [ ] A mudança é cosmética (UI, formatação, comentários)?
      → Sem ação de documentação necessária
```

### 12.4 Procedimento ao criar um novo arquivo de configuração de IA

Se uma nova IA for adicionada ao projeto (ex: Cursor, Copilot, etc.), criar um thin wrapper
no local esperado por essa ferramenta com o seguinte template:

```markdown
# [NOME_DA_IA].md — Projeto FII Analysis

> **Fonte única de verdade:** `docs/PROJETO.md`
> Este arquivo é apenas um ponteiro. TODAS as regras, arquitetura e status estão documentados lá.

## Agentes específicos do [NOME_DA_IA]
<!-- Listar apenas o que é EXCLUSIVO desta IA: caminho dos agentes, config específica, etc. -->

## Observação
Antes de qualquer alteração no código, leia `docs/PROJETO.md` na íntegra.
Após alterações, execute o checklist de governança (PROJETO.md §12.3).
```

### 12.5 O que NÃO fazer

| ❌ Proibido | ✅ Correto |
|---|---|
| Copiar regras de PROJETO.md para CLAUDE.md | Referenciar: `→ veja docs/PROJETO.md §X` |
| Editar STATUS_ATUAL.md manualmente com planejamentos | Documentar apenas o que **existe agora** |
| Criar novo arquivo .md no raiz com regras do projeto | Adicionar conteúdo em PROJETO.md e referenciar |
| Deixar de atualizar docs após mudança estrutural | Executar checklist §12.3 ao final de toda tarefa |
| Manter múltiplas versões da mesma informação | Um conceito = um local no SSOT |