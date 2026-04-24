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

**Princípio:** nenhuma hipótese não validada é usada como input de decisão. O radar é uma matriz booleana, não um score ponderado arbitrário.

---

## 2. Pilares da Solução

| # | Pilar | Função | Módulos |
|---|---|---|---|
| 1 | Panorama da carteira | Visão consolidada de todos os FIIs | `features/portfolio.py`, `evaluation/panorama.py` |
| 2 | Valuation histórico | P/VP e DY comparados à própria série histórica | `features/indicators.py`, `features/valuation.py` |
| 3 | Saúde financeira | Detecção de destruição de capital, tendência PL, emissões | `features/saude.py`, `features/composicao.py` |
| 4 | Event study | CAR/BHAR, testes estatísticos, walk-forward com gap | `features/dividend_window.py`, `models/statistical.py`, `models/walk_forward.py`, `models/critic.py` |
| 5 | Radar descritivo | Filtros booleanos sem score numérico | `features/radar.py`, `evaluation/radar.py` |
| 6 | Alertas e relatórios | Diff diário, Markdown, alertas por threshold | `evaluation/alertas.py`, `evaluation/reporter.py` |

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
| Benchmark (IFIX) | brapi.dev / yfinance | Fechamento diário armazenado em `benchmark_diario` |
| CDI diário | BCB SGS série 12 | Taxa diária em %; armazenado em `cdi_diario` |

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

**Regra crítica:** P/VP, DY, DY Gap são **calculados** em tempo real, nunca persistidos. CNPJ e metadados de acesso são centralizados em `src/fii_analysis/data/database.py` (`get_cnpj_by_ticker`, `get_session_ctx`, `get_ultima_coleta`, `get_ultimo_preco_date`).

### 3.4 Estrutura de pastas

```
D:/analise-de-acoes/
├── CLAUDE.md                          # Regras operacionais do projeto
├── config.yaml                        # Thresholds e janelas runtime (pisos, CDI, percentis)
├── pyproject.toml
├── dados/
│   ├── cvm/raw/                       # ZIPs CVM (.gitignored)
│   ├── alertas/                       # Markdown diário (evaluation/alertas.py)
│   ├── snapshots/                     # Snapshots do DB para reprodutibilidade (pendente)
│   └── fii_data.db                    # SQLite principal (.gitignored)
├── src/fii_analysis/
│   ├── config.py                      # TICKERS, períodos treino/teste, custos, IR
│   ├── config_yaml.py                 # Loader do config.yaml (get_threshold)
│   ├── cli.py                         # Typer CLI: panorama, fii, carteira, calendario, radar, alertas, consulta
│   ├── data/
│   │   ├── database.py                # SQLAlchemy 2.0: models + engine + session + utilitários DB
│   │   └── ingestion.py              # CVM, yfinance, brapi, BCB SGS
│   ├── features/
│   │   ├── dividend_window.py         # Janela ±10 dias úteis (event study)
│   │   ├── indicators.py              # P/VP, DY trailing (point-in-time)
│   │   ├── valuation.py               # Percentil rolling, DY N-meses, DY Gap
│   │   ├── portfolio.py               # Panorama, alocação, retorno vs IFIX, Herfindahl
│   │   ├── saude.py                   # Tendência PL, flag destruição capital, emissões
│   │   ├── fundamentos.py             # Rentabilidade efetiva/patrimonial, alavancagem, payout
│   │   ├── composicao.py              # Classificação Tijolo/Papel/Híbrido
│   │   ├── data_loader.py             # Agregadores de dados para interfaces
│   │   └── radar.py                   # Matriz booleana (sem score numérico)
│   ├── models/
│   │   ├── statistical.py             # Event study CAR, t-test, Mann-Whitney
│   │   ├── walk_forward.py            # Splits temporais com gap + validação leakage
│   │   ├── critic.py                  # Shuffle/placebo/estabilidade (CriticAgent)
│   │   └── strategy.py                # Simulação dividend capture, otimização, risco
│   ├── evaluation/
│   │   ├── reporter.py                # Relatório técnico (somente dados de teste)
│   │   ├── panorama.py                # rich.Table: render carteira/calendário
│   │   ├── alertas.py                 # Markdown diário + terminal
│   │   └── radar.py                   # Render matriz booleana
│   └── mcp_server/server.py           # MCP: validate_split, detect_leakage, etc
├── app/
│   ├── streamlit_app.py               # Entry point Streamlit
│   ├── state.py                       # Session state initializer
│   ├── pages/
│   │   ├── 1_Panorama.py
│   │   ├── 2_Analise_FII.py
│   │   ├── 3_Carteira.py
│   │   ├── 4_Radar.py
│   │   ├── 5_Event_Study.py
│   │   ├── 6_Alertas.py
│   │   └── 7_Fundamentos.py
│   └── components/
│       ├── charts.py                  # Plotly: gauge, bandas, heatmap, pizza
│       ├── data_loader.py             # Funções de carga para as páginas
│       └── tables.py                  # Formatação de dataframes para exibição
├── scripts/
│   ├── load_database.py               # Orquestra download CVM + carga yfinance
│   ├── run_strategy.py                # Pipeline completo de estratégia
│   ├── plot_car.py                    # Gráfico CAR (PNG)
│   ├── plot_car_adjusted.py           # CAR ajustado (remove efeito mecânico do dividendo)
│   ├── validate_knip11.py             # Validação cruzada vs FundsExplorer
│   ├── check_prices.py                # Debug de preços
│   ├── analise_janela_v2.py           # Estratégias de janela
│   ├── analise_janela_flexivel.py     # Varredura de targets
│   ├── analise_spread_recompra.py     # Simulação spread recompra
│   └── scrape_fundsexplorer.py        # Scraping FundsExplorer
└── docs/
    └── PROJETO.md                     # Este documento
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
| **DY N-meses** (12/24/36) | Soma dividendos com data-com em `[t−N meses, t]` / preço atual. |
| **DY Gap** | `DY 12m − CDI acumulado 12m` (point-in-time). |
| **Percentil DY Gap** | Posição na distribuição da janela de 252 pregões (1 ano) até t−1. |

### 5.2 Saúde financeira e Fundamentos

| Métrica | Definição |
|---|---|
| **Mês Saudável** | `rentab_patrim >= 0` E `rentab_efetiva >= rentab_patrim`. |
| **Alertas de Saúde** | **Erro:** >= `meses_consec_alerta` (default 3) consecutivos não saudáveis. **Aviso:** < 4 meses saudáveis no total dos últimos 6 meses. |
| **Alavancagem** | `Ativo_Total / Patrimonio_Liquido`. Alerta se > `alavancagem_limite`. |
| **Tendência PL** | Regressão linear (6m, 12m) sobre o VP por cota. |
| **Emissões recentes** | Salto em `Cotas_Emitidas` mês a mês > 1%. |

### 5.3 Composição do ativo

| Classificação | Regra |
|---|---|
| **Tijolo** | Imóveis físicos ≥ 60% do ativo |
| **Papel** | Recebíveis (CRI + LCI + LCI_LCA) ≥ 60% |
| **Híbrido** | Caso contrário |

Fonte: arquivo `ativo_passivo` da CVM. Campos: `Direitos_Bens_Imoveis`, `CRI`, `LCI`, `LCI_LCA`, `Disponibilidades`.

### 5.4 Radar descritivo

Matriz booleana — **sem score numérico** até existir backtest validando a fórmula.

| Filtro | Critério |
|---|---|
| P/VP Baixo | Percentil rolling 504d < 30 |
| DY Gap Alto | Percentil rolling 252d > 70 |
| Saúde OK | Sem flag de destruição de capital |
| Liquidez OK | Volume financeiro médio 21d ≥ piso YAML (default: R$ 500.000) |

FIIs com todos os ✓ aparecem no topo. Ordenação por número de ✓.

**Proximidade da data-com não entra no radar** enquanto o event study não validar padrão estatisticamente significativo.

### 5.5 Event study

- **CAR** (Cumulative Abnormal Return): retorno acumulado do FII menos retorno acumulado do benchmark (IFIX) na janela ±10 pregões.
- **BHAR** (Buy-and-Hold Abnormal Return): variação buy-and-hold vs benchmark.
- **Testes:** t-test pareado (pré vs pós), Mann-Whitney U, t-test 1 amostra (dia 0).
- **Correção múltiplas comparações:** Benjamini-Hochberg ao reportar resultado por FII.

### 5.6 Walk-forward com gap

Split temporal (default 60/20/20) com gap de 10 dias úteis entre períodos. Função `validate_no_leakage()` detecta sobreposição automaticamente.

### 5.7 CriticAgent (falsificação)

| Teste | O que faz |
|---|---|
| **Permutation shuffle** | Embaralha sinais de evento e mede acurácia (detecta correlação espúria) |
| **Placebo** | Usa datas aleatórias como falsas datas-com; compara com datas reais via Mann-Whitney |
| **Subperiod stability** | Compara 1ª metade vs 2ª metade dos eventos via t-test |

**Veredito:** aprovado somente se todos os 3 testes passam.

### 5.8 Estratégia de dividend capture

Simulação com preço ajustado, otimização grid search (`dias_antes`, `dias_depois`), métricas de risco (Sharpe, Sortino, drawdown, perdas consecutivas), comparação com buy-and-hold. Custos B3 (0.03% round-trip) e IR 20% sobre ganho de capital descontados.

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
| `consulta TICKER` | **Analítico IA:** Integra indicadores locais com Gemini + Google Search para análise qualitativa em 4 seções. |
| `radar` | Exibe a matriz booleana de filtros (P/VP, DY Gap, Saúde, Liquidez) |
| `alertas` | Gera e exibe alertas diários com base nos thresholds de risco |
| `calendario` | Lista as próximas datas-com previstas para os próximos 30 dias |
| `carteira` | Exibe posições, alocação por segmento e retorno vs IFIX |

### 6.2 Streamlit Dashboard

Entry point: `app/streamlit_app.py`. Layout `wide`, sidebar expandida.

| Página | Arquivo | Conteúdo |
|---|---|---|
| **Panorama** | `1_Panorama.py` | Métricas gerais (FIIs ativos, DY médio, P/VP médio), tabela completa, radar OK |
| **Análise FII** | `2_Analise_FII.py` | Valuation (gauge P/VP, série histórica com bandas), saúde financeira, composição (pizza), datas-com, filtros radar |
| **Carteira** | `3_Carteira.py` | CRUD de posições (form + CSV upload), consolidado, pizza alocação/segmento, Herfindahl |
| **Radar** | `4_Radar.py` | Heatmap booleano, tabela detalhada, exportação CSV, expanders explicando cada filtro |
| **Event Study** | `5_Event_Study.py` | Seleção de ticker, CAR (todos/treino/teste), testes pré/pós, dia 0, CriticAgent com veredito |
| **Alertas** | `6_Alertas.py` | Geração sob demanda, listagem de Markdowns salvos por data |
| **Fundamentos** | `7_Fundamentos.py` | Rentabilidade efetiva vs patrimonial (payout), série P/VP com seletor (YTD, 12m, 3a, Tudo), PL e alavancagem (Ativo/PL). |

**Componentes reutilizáveis** (`app/components/`):

| Componente | Função |
|---|---|
| `charts.py` | Plotly: `pvp_gauge`, `pvp_historico_com_bandas`, `pl_trend_chart`, `composicao_pie`, `car_plot`, `radar_heatmap`, `carteira_alocacao_pie`, `carteira_segmento_pie` |
| `data_loader.py` | Funções de carga: panorama, P/VP, DY, saúde, composição, radar, carteira (CRUD), preços |
| `tables.py` | Formatadores: `format_currency`, `format_pct`, `format_number`, `render_panorama_table`, `render_radar_matriz` |

### 6.3 MCP Server

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
| Ingestão CVM (ZIP → complemento/geral/ativo_passivo) | Implementado | `data/ingestion.py` |
| Ingestão preços yfinance (incremental) | Implementado | `data/ingestion.py` |
| Ingestão dividendos yfinance (ex-date → data-com) | Implementado | `data/ingestion.py` |
| CDI diário (BCB SGS série 12) | Implementado | `data/ingestion.py` |
| Benchmark IFIX (brapi/yfinance) | Implementado | `data/ingestion.py` |
| Conversão ex-date → data-com via calendário B3 | Implementado | `data/ingestion.py` |

### Features

| Componente | Status | Arquivo |
|---|---|---|
| Janela ±10 pregões com retornos | Implementado | `features/dividend_window.py` |
| Retornos anormais (vs benchmark) | Implementado | `features/dividend_window.py` |
| P/VP point-in-time | Implementado | `features/indicators.py` |
| DY trailing (série e valor) | Implementado | `features/indicators.py` |
| Percentil rolling P/VP | Implementado | `features/valuation.py` |
| DY N-meses (12/24/36) | Implementado | `features/valuation.py` |
| DY Gap vs CDI | Implementado | `features/valuation.py` |
| Panorama carteira | Implementado | `features/portfolio.py` |
| Alocação, Herfindahl, retorno vs IFIX | Implementado | `features/portfolio.py` |
| Tendência PL, flag destruição capital | Implementado | `features/saude.py` |
| Análise emissões | Implementado | `features/saude.py` |
| Classificação Tijolo/Papel/Híbrido | Implementado | `features/composicao.py` |
| Matriz booleana radar | Implementado | `features/radar.py` |

### Models

| Componente | Status | Arquivo |
|---|---|---|
| Event study (CAR) | Implementado | `models/statistical.py` |
| t-test pareado, Mann-Whitney | Implementado | `models/statistical.py` |
| t-test dia 0 | Implementado | `models/statistical.py` |
| Walk-forward split com gap | Implementado | `models/walk_forward.py` |
| Validação de leakage | Implementado | `models/walk_forward.py` |
| CriticAgent (shuffle/placebo/estabilidade) | Implementado | `models/critic.py` |
| Simulação dividend capture | Implementado | `models/strategy.py` |
| Otimização grid search | Implementado | `models/strategy.py` |
| Métricas risco (Sharpe, Sortino, drawdown) | Implementado | `models/strategy.py` |
| Buy-and-hold comparison | Implementado | `models/strategy.py` |

### Evaluation

| Componente | Status | Arquivo |
|---|---|---|
| Relatório técnico (reporter) | Implementado | `evaluation/reporter.py` |
| Render panorama (rich.Table) | Implementado | `evaluation/panorama.py` |
| Alertas diários (Markdown + terminal) | Implementado | `evaluation/alertas.py` |
| Render radar (matriz booleana) | Implementado | `evaluation/radar.py` |

### Interfaces

| Componente | Status | Arquivo |
|---|---|---|
| CLI Typer (7 comandos) | Implementado (incluindo `consulta`) | `cli.py` |
| Configuração Python (tickers, períodos) | Implementado | `config.py` |
| Configuração YAML (thresholds runtime) | Implementado | `config_yaml.py` |
| MCP Server (4 tools) | Implementado | `mcp_server/server.py` |
| Streamlit Dashboard (7 páginas) | Implementado | `app/streamlit_app.py` + `app/pages/` |
| Componentes Plotly (8 gráficos) | Implementado | `app/components/charts.py` |
| Data loader (Streamlit) | Implementado | `app/components/data_loader.py` |
| Formatadores de tabela | Implementado | `app/components/tables.py` |

### Scripts

| Script | Status | Função |
|---|---|---|
| `load_database.py` | Operacional | Download ZIPs CVM + carga yfinance |
| `run_strategy.py` | Operacional | Pipeline completo de estratégia |
| `plot_car.py` | Operacional | Gráfico CAR (PNG) |
| `plot_car_adjusted.py` | Operacional | CAR ajustado sem efeito mecânico |
| `validate_knip11.py` | Operacional | Validação cruzada vs FundsExplorer |
| `check_prices.py` | Debug | Inspeção de preços |
| `analise_janela_v2.py` | Operacional | Estratégias de janela |
| `analise_janela_flexivel.py` | Operacional | Varredura de targets |
| `analise_spread_recompra.py` | Operacional | Simulação spread recompra |
| `scrape_fundsexplorer.py` | Operacional | Scraping FundsExplorer |

### Volume de dados

| Tabela | Registros (2026-04-16) |
|---|---|
| `tickers` | 5 ativos |
| `precos_diarios` | 8.184 (6 tickers, SNFF11 preservado) |
| `dividendos` | 355 |
| `relatorios_mensais` | 227 |

### Status Geral

- **Fase 0-5 + Refatoração Arquitetural Concluída.**
- O sistema possui separação clara entre ingestão (data), lógica de negócio (features), análise estatística (models) e visualização (app/evaluation).
- O CLI agora conta com o comando `consulta TICKER` que integra indicadores locais com Gemini + Google Search para análise qualitativa em 4 seções.

---

## 9. Próximos Passos — Plano para amanhã

### PRIORIDADE ALTA
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

### Prioridade 1 — Reprodutibilidade
- Implementar snapshots diários do `fii_data.db` com hash SHA-256.
- Todo relatório grava o hash do snapshot usado no cabeçalho.

### Prioridade 2 — Event study completo
- Rodar event study nos 5 tickers ativos.
- Interpretar resultados: existe padrão? Em quais FIIs? Magnitude?
- Aplicar correção Benjamini-Hochberg para múltiplas comparações.

### Prioridade 3 — Testes
- Criar `tests/` com cobertura dos módulos de features e models.
- Priorizar testes de point-in-time, leakage e integridade temporal.

### Prioridade 4 — Relatórios e histórico
- `fii diario` — diff desde última execução (o que mudou).
- Relatório mensal Markdown: panorama + alertas + event study + radar + proventos.
- Log de decisões de investimento (compra/venda) para backtest futuro vs IFIX.

### Prioridade 5 — Limpeza de configuração
- Reconciliar `config.py` (constantes de escopo) e `config.yaml` (parâmetros de decisão).
- Eliminar duplicações.

### Fora do escopo
- ML / LightGBM enquanto event study não validar padrão.
- Score numérico ponderado no radar (substituído por matriz booleana).
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
| ADR-05 | Radar booleano | Score composto exige pesos arbitrários | Matriz de filtros (P/VP pct, DY Gap pct, saúde, liquidez) | Sem backtest validando pesos, score ponderado é enganoso. Booleanos são honestos. |
| ADR-06 | Data-com via yfinance | CVM não publica data-com | yfinance (ex-date convertida via calendário B3) | Única fonte gratuita e acessível |
| ADR-07 | Preços: yfinance + brapi | Necessidade de histórico longo + atualização diária | yfinance para carga inicial; brapi para updates diários | yfinance tem histórico desde 2015+; brapi é mais rápido para última cotação |
| ADR-08 | Sem ML prematuro | Tentação de aplicar LightGBM antes de validar base | Modelos estatísticos clássicos até event study confirmar padrão | Projeto anterior atingiu 96% de acurácia falsa por data leakage. Validação estatística antes de ML. |
| ADR-09 | KNIP11 como canário | SNFF11 entrou em liquidação | KNIP11 substitui SNFF11 para validação cruzada vs FundsExplorer | Papel (CRI) com histórico desde 2017, dados completos, validável externamente |
| ADR-10 | Token brapi fora do projeto | Segurança de credenciais | `C:\Modelos-AI\Brapi\.env` → `os.getenv("BRAPI_API_KEY")` | Nunca hardcodar nem versionar secrets |
| ADR-11 | CriticAgent como gate | Risco de resultados espúrios | 3 testes obrigatórios (shuffle, placebo, estabilidade) | Resultado reportado somente se passar em todos os testes de falsificação |
| ADR-12 | Eventos sobrepostos descartados | Janelas de FIIs mensais podem se sobrepor | Descartar evento seguinte (não truncar) | Truncar janela introduz viés de seleção |
| ADR-13 | NaN nunca vira zero | Dados faltantes são comuns em FIIs pequenos | Propagar NaN, exibir `n/d` | Zero silencioso mascara ausência de dado e distorce estatísticas |
| ADR-14 | Streamlit como interface web | Necessidade de visualização interativa | Streamlit com 6 páginas | Mais rápido que Flask para prototipagem; componentes Plotly nativos |
| ADR-15 | Proximidade data-com fora do radar | Radar poderia usar data-com como critério | Somente após event study validar padrão por FII | Se o padrão não é estatisticamente significativo, usar data-com como critério é superstição |
| ADR-16 | Python via Anaconda | 3 intérpretes Python instalados na máquina | `C:/ProgramData/anaconda3/python.exe` | Único com todas as dependências instaladas |
