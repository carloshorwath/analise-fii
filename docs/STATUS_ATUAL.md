# STATUS_ATUAL.md — Estado do projeto em 2026-04-17

## 1. Schema do banco (database.py)

4 tabelas SQLAlchemy 2.0, declarativas:

| Tabela | PK | Colunas |
|---|---|---|
| `tickers` | `cnpj` | `ticker` (unique), `nome`, `segmento`, `mandato`, `tipo_gestao`, `codigo_isin`, `data_inicio` |
| `precos_diarios` | (`ticker`, `data`) | `abertura`, `maxima`, `minima`, `fechamento`, `fechamento_aj`, `volume`, `fonte`, `coletado_em` |
| `dividendos` | (`ticker`, `data_com`) | `valor_cota`, `fonte` |
| `relatorios_mensais` | (`cnpj`, `data_referencia`) | `data_entrega`, `vp_por_cota`, `patrimonio_liq`, `cotas_emitidas`, `dy_mes_pct`, `rentab_efetiva`, `rentab_patrim` |

Funções auxiliares: `get_engine()`, `get_session()`, `create_tables()`.

## 2. Ingestão (ingestion.py)

- **`_ex_to_data_com()`** — converte ex-date (yfinance) para data-com via calendário B3 (pandas_market_calendars).
- **`load_cvm_zip()`** — extrai CSVs de `complemento`, `geral`, `ativo_passivo` de um ZIP CVM.
- **`load_cvm_to_db()`** — filstra complemento por CNPJs monitorados, cruza com `geral` para obter `data_entrega`, persiste em `relatorios_mensais`. Não sobrescreve registros existentes.
- **`load_prices_yfinance()`** — busca preços OHLCV (auto_adjust=False) incrementais a partir do último registro. Grava `fechamento_aj` e `coletado_em`.
- **`load_dividends_yfinance()`** — busca dividendos, converte ex-date para data-com, persiste na tabela `dividendos`.

## 3. Scripts

| Script | Função |
|---|---|
| `load_database.py` | Orquestra download de ZIPs CVM (2023–2026) + carga CVM + preços/dividendos yfinance para todos os tickers. |
| `run_strategy.py` | Pipeline completo: otimiza (dias_antes, dias_depois) no treino, aplica no teste, compara com buy-and-hold, roda CriticAgent, calcula métricas de risco. |
| `analise_janela_v2.py` | Duas estratégias: compra no dia médio do mínimo e recompra ao preço anterior. |
| `analise_janela_flexivel.py` | Varre targets (0.25%–2%) na janela ±10 pregões, calcula taxa de acerto por target. |
| `analise_spread_recompra.py` | Simula venda a P+target e recompra a P, para investidor que já possui o FII. |
| `plot_car.py` | Gera gráfico CAR (Cumulative Abnormal Return) no treino para os 5 tickers. Salva PNG. |
| `plot_car_adjusted.py` | CAR ajustado — remove o efeito mecânico do dividendo no dia +1 para isolar o sinal real. |
| `check_prices.py` | Debug: imprime preços ao redor de datas específicas do KNIP11. |
| `validate_knip11.py` | Compara dados do banco com Excel exportado do FundsExplorer para validação cruzada. |
| `scrape_fundsexplorer.py` | Scraping de P/VP, DY e VP atual do FundsExplorer para os 5 tickers. |

## 4. Features / Evaluation / Models

| Arquivo | Estado |
|---|---|
| `features/dividend_window.py` | **Implementado** — `get_dividend_windows()` (janela ±10 pregões com retornos) e `get_abnormal_returns()` (subtrai benchmark). |
| `features/indicators.py` | **Implementado** — `get_pvp()` (point-in-time via `data_entrega`), `get_dy_trailing()`, `get_pvp_serie()`, `get_dy_serie()`. |
| `features/valuation.py` | **Implementado** — `get_pvp_percentil_rolling()`, `get_dy_n_meses()`, `get_dy_gap()`. |
| `features/portfolio.py` | **Implementado** — panorama da carteira, alocacao, retorno vs IFIX, indice Herfindahl. |
| `features/saude.py` | **Implementado** — tendencia PL, flag destruicao capital, analise emissoes. |
| `features/composicao.py` | **Implementado** — classificacao Tijolo/Papel/Hibrido com base em ativo_passivo CVM. |
| `features/radar.py` | **Implementado** — matriz booleana de criterios (sem score numerico ponderado). |
| `evaluation/panorama.py` | **Implementado** — rich.Table: render carteira, calendario de dividendos. |
| `evaluation/alertas.py` | **Implementado** — alertas diarios em Markdown + terminal. |
| `evaluation/radar.py` | **Implementado** — render da matriz booleana do radar. |
| `evaluation/reporter.py` | **Implementado** — `print_report()` com P/VP, DY, event study, testes estatísticos. |
| `models/statistical.py` | **Implementado** — `event_study()` (CAR), `test_pre_vs_post()` (t-test pareado + Mann-Whitney), `test_day0_return()` (t-test 1 amostra). |
| `models/walk_forward.py` | **Implementado** — `make_splits()` (split temporal 60/20/20 com gap), `validate_no_leakage()` (detecta sobreposição), `print_splits_summary()`. |
| `models/critic.py` | **Implementado** — `shuffle_test()` (permutação de sinais), `placebo_test()` (datas aleatórias), `subperiod_stability()` (1ª vs 2ª metade), `run_critic()` (orchestrador com veredito). |
| `models/strategy.py` | **Implementado** — `simulate_strategy()` (dividend capture com preço ajustado), `compute_risk_metrics()` (Sharpe, Sortino, drawdown, perdas consecutivas), `optimize_strategy()` (grid search), `buy_and_hold_return()`, `print_strategy_report()`. |
| `mcp_server/server.py` | **Implementado** — MCP com 4 tools: `validate_split`, `detect_leakage`, `check_window_overlap`, `summary_report`. |
| `config.py` | **Implementado** — Tickers (CPTS11, CPSH11, GARE11, HSRE11, KNIP11), períodos treino/teste, ranges de otimização, custos, IR. |
| `config_yaml.py` | **Implementado** — loader do config.yaml (thresholds e janelas runtime). |
| `cli.py` | **Implementado** — CLI typer com comandos: panorama, fii, carteira, calendario, radar, alertas. |

## 5. Testes

Não existe diretório `tests/` nem arquivos de teste.

## 6. Configuração

- **pyproject.toml** — deps principais (sqlalchemy, pandas, yfinance, scipy, statsmodels, loguru, numpy); opcionais: dev (pytest, ruff), mcp (mcp>=1.1, pydantic), web (flask), ml (lightgbm). Ruff line-length=88, pytest testpaths=["tests"].
- **.gitignore** — ignora `dados/`, `*.db`, `.env`, `__pycache__`, etc.
- **.env** — não existe no projeto (token brapi carregado de `C:\Modelos-AI\Brapi\.env` externo).
- **docs/** — `PROJETO.md`, `PLANO_EXPANSAO.md`, `PLANO_EXPANSAO_V2.md`.

## 7. CLI (cli.py)

Comandos do typer CLI disponíveis:
- `panorama`: Panorama geral do mercado de FIIs
- `fii`: Análise detalhada de um FII específico
- `carteira`: Posições da carteira, alocação e retorno vs IFIX
- `calendario`: Próximos dividendos (data com, data ex, pagamento)
- `radar`: Matriz de FIIs baseada em critérios booleanos
- `alertas`: Alertas diários com base em thresholds

## 8. Dados coletados (fii_data.db)

Banco existe com **8.771 registros** no total:

| Tabela | Registros |
|---|---|
| `tickers` | 5 (CPTS11, CPSH11, GARE11, HSRE11, KNIP11) |
| `precos_diarios` | 8.184 (6 tickers; SNFF11 tem 1.234 registros mas não está em `tickers`) |
| `dividendos` | 355 (6 tickers) |
| `relatorios_mensais` | 227 (6 CNPJs, 37–38 relatórios cada) |

Períodos de preços: CPTS11 desde 2015-09, KNIP11 desde 2017-10, HSRE11 desde 2020-12, SNFF11 desde 2021-05, CPSH11 desde 2023-07, GARE11 desde 2024-03. Todos atualizados até 2026-04-16.
