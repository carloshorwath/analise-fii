# PROJETO.md — FII Analysis

Documentação técnica do sistema de análise de FIIs. Descreve o que o código faz e o que a evidência sustenta (revisão de 2026-11-13).

---

## 1. Visão e Objetivos

**O que o sistema É:** um painel **descritivo** de FIIs. Mostra o estado de cada fundo (P/VP, DY, VP/cota, liquidez, composição, saúde do VP/cota), a posição e a estrutura da carteira do investidor, e emite **alertas factuais** (risco do fundo, concentração da carteira, fundo em liquidação, preço parado). O investidor decide; nada aqui é recomendação.

**O que o sistema NÃO é:** um gerador de sinais de compra/venda. Nenhum indicador do sistema tem evidência de prever qual fundo rende mais.

**Evidência** (`docs/pesquisa/painel_2026-11/`, pré-registro em `PREREGISTRO.md`, escrito antes de qualquer análise preditor × retorno):

- Painel de 110 fundos, 55 datas mensais de formação (2022-04 a 2026-10), horizontes de 1/3/6/12 meses, retorno em excesso ao universo equal-weight.
- Fama-MacBeth + quintis, 100 testes (25 indicadores × 4 horizontes), Benjamini-Hochberg a 5%: **zero sobreviventes** (Bonferroni também zero).
- Testados: percentil de P/VP próprio e vs pares, episódios BUY/SELL, DY, DY Gap, score, saúde, momentum, alavancagem, liquidez, volatilidade, contagem do radar.
- Único candidato, **não confirmado**: variação % do VP/cota em 6 meses (`dvp6`; p BH = 0,38 em 6m). Foi achado exploratório dentro de 100 testes.
- Limites: ~4,5 anos úteis; 3,6 períodos independentes no horizonte de 12 meses; universo = IFIX de uma data (viés de sobrevivência); dividendos com cobertura só desde 2022-03/04. Ausência de evidência não prova ausência de efeito: o estudo tem pouco poder, mas o sistema não pode se apresentar como previsão.

**Perguntas que o sistema responde (descritivamente):**

| # | Pergunta | Componente |
|---|---|---|
| 1 | Como está minha carteira? | Panorama / Carteira |
| 2 | Este FII está caro ou barato vs seu próprio histórico? (descrição, não previsão) | Valuation |
| 3 | O VP/cota deste fundo está caindo? | Alerta de risco (saúde) |
| 4 | Onde olhar primeiro? | Radar (3 critérios, descritivo) |
| 5 | O que mudou desde ontem? | Diff, alertas e relatórios |

**Princípio (ADR-31):** nenhuma ação é derivada de indicador sem evidência. Hoje COMPRAR/VENDER (e AUMENTAR/REDUZIR na carteira) só existem se um sinal passar na trava de significância (§4.2) — e nenhum passa. O resultado normal é AGUARDAR/HOLD.

---

## 2. Componentes

Os componentes abaixo **descrevem** ou servem de instrumento de pesquisa. Nenhum tem poder preditivo demonstrado (§1).

| # | Componente | Função | Módulos |
|---|---|---|---|
| 1 | Panorama da carteira | Visão consolidada (descritivo) | `features/portfolio.py`, `evaluation/panorama.py` |
| 2 | Valuation histórico | P/VP e DY vs a própria série (descritivo) | `features/indicators.py`, `features/valuation.py` |
| 3 | Alerta de risco (saúde) | VP/cota em queda, tendência, emissões — alerta factual, não gera ação | `features/saude.py`, `features/composicao.py` |
| 4 | Event study | CAR/BHAR, testes, walk-forward com gap — instrumento de pesquisa | `features/dividend_window.py`, `models/statistical.py`, `models/walk_forward.py`, `models/critic.py` |
| 5 | Radar | Matriz booleana de 3 critérios (P/VP baixo, saúde OK, liquidez OK); DY Gap alto é indicador de regime, fora da contagem | `features/radar.py`, `evaluation/radar.py` |
| 6 | Score 0–100 | Resumo comunicativo; não altera decisões | `features/score.py`, `features/risk_metrics.py` |
| 7 | Alertas e relatórios | Diff diário, Markdown, alertas | `evaluation/alertas.py`, `evaluation/reporter.py` |
| 8 | Pares de rotação | Lista descritiva de pares intra-segmento (candidato = liquidez OK, elegível, percentil de P/VP ≤ 30); sem validação de retorno | `decision/opportunities.py`, `app/pages/16_Oportunidades.py` |
| 9 | Otimizador / episódios / walk-forward | Instrumentos de pesquisa; alimentam a trava de significância, que hoje barra todos os sinais | `models/threshold_optimizer_v2.py`, `models/episodes.py`, `models/walk_forward_rolling.py` |
| 10 | Evidência | Constante única do resultado do estudo, gravada em todo rationale e lida pela UI | `decision/evidencia.py`, `app/components/aviso_ui.py` |
| 11 | Síntese LLM | Análise qualitativa e prompt packs; nunca altera a ação | `llm/context_builder.py`, `llm/gateway.py`, `llm/prompts.py` |


---

## 3. Arquitetura de Dados e Tecnologia

### 3.1 Fontes de dados

| Dado | Fonte | Observação |
|---|---|---|
| Preços históricos OHLCV | yfinance (`TICKER.SA`) | Carga inicial; `auto_adjust=False`; sufixo `.SA` obrigatório. `fechamento_aj` **não** é o Adj Close do Yahoo: é reconstruído pelo projeto (§4.9) |
| Data-com de dividendos | yfinance | CVM **não** tem esta informação; ex-date convertida para data-com via calendário B3; duplicatas removidas (§4.9) |
| VP por cota, PL, cotas, DY% | CVM dados abertos | Arquivo `complemento` dos ZIPs; encoding `latin1`; separador `;` |
| Dados cadastrais (segmento, mandato) | CVM dados abertos | Arquivo `geral` dos ZIPs; campo `Data_Entrega` para point-in-time |
| Composição do ativo | CVM dados abertos | Arquivo `ativo_passivo` dos ZIPs; `ativo_total` vem do campo `Valor_Ativo` do arquivo `complemento` (§4.9) |
| Atualização diária de preços | brapi.dev | 15.000 req/mês; token externo em `C:\Modelos-AI\Brapi\.env` |
| Benchmark (XFIX11) | yfinance (`XFIX11`) | Substituiu IFIX/^IFIX.SA (inválidos no yfinance) |
| CDI diário | BCB SGS série 12 | Taxa diária em %; armazenado em `cdi_diario` |
| Expectativas Focus BCB | BCB Focus (Selic 3m/6m/12m) | Cache diário em `dados/cache/focus_selic.json` |
| Composição IFIX | B3 (GetPortfolioDay) | Fallback obrigatório: `dados/ifix_composicao.csv` (mantido por self-healing); CNPJ resolvido via DB → CSV → StatusInvest; persistido em `universo` com `data_referencia` = data local do operador (não UTC); `atualizado_em` em UTC |

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
pandas-market-calendars = ">=4.0"
numpy = ">=1.26"
scipy = ">=1.12"
statsmodels = ">=0.14"
loguru = ">=0.7"
typer = ">=0.9"
rich = ">=13.0"
pyyaml = ">=6.0"

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov", "ruff"]
mcp = ["mcp>=1.1", "pydantic>=2.6"]
web = ["flask>=3.0", "streamlit>=1.30", "plotly>=5.18"]
ml  = ["lightgbm>=4.3"]
scripts = ["matplotlib>=3.8", "beautifulsoup4>=4.12"]   # plot_car*.py, scrape_fundsexplorer.py
```

`pandas-market-calendars` é dependência obrigatória (conversão ex-date → data-com e `update-prices`). O extra `scripts` cobre apenas os scripts de gráfico/scraping. `python-dateutil` é importado por `features/valuation.py` mas não é declarado no `pyproject.toml` (vem transitivamente do pandas).

**Runtime:** Anaconda em `C:/ProgramData/anaconda3/python.exe`.

### 3.3 Schema do banco (SQLite via SQLAlchemy 2.0)

Arquivo: `dados/fii_data.db` — ORM declarativo em `src/fii_analysis/data/database.py`.
Migrações idempotentes em `src/fii_analysis/data/migrations.py`.

**19 tabelas (contagem das classes ORM em `database.py`): 10 operacionais + 7 de snapshot diário (cache desnormalizado) + 2 de diário (LLM e decisões do investidor).**

#### Tabelas operacionais

| Tabela | PK | Colunas principais |
|---|---|---|
| `tickers` | `cnpj` | `ticker` (unique), `nome`, `segmento`, `mandato`, `tipo_gestao`, `codigo_isin`, `data_inicio`, `inativo_em` |
| `precos_diarios` | (`ticker`, `data`) | `abertura`, `maxima`, `minima`, `fechamento`, `fechamento_aj`, `volume`, `fonte`, `coletado_em` |
| `dividendos` | (`ticker`, `data_com`) | `valor_cota`, `fonte` |
| `relatorios_mensais` | (`cnpj`, `data_referencia`) | `data_entrega`, `vp_por_cota`, `patrimonio_liq`, `cotas_emitidas`, `dy_mes_pct`, `rentab_efetiva`, `rentab_patrim` |
| `ativo_passivo` | (`cnpj`, `data_referencia`) | `data_entrega`, `direitos_bens_imoveis`, `cri`, `cri_cra`, `lci`, `lci_lca`, `disponibilidades`, `total_investido`, `total_necessidades_liquidez`, `valores_receber`, `contas_receber_aluguel`, `outros_valores_mobliarios`, `ativo_total` (= `Valor_Ativo` do `complemento`; §4.9), `acoes_sociedades_fii`, `cotas_sociedades_fii` (participações em sociedades de atividade imobiliária; migração 009; NULL até a recarga do `ativo_passivo`) |
| `cdi_diario` | `data` | `taxa_diaria_pct`, `coletado_em` |
| `benchmark_diario` | (`ticker`, `data`) | `fechamento`, `coletado_em` |
| `eventos_corporativos` | `id` (auto) | `ticker`, `cnpj`, `data`, `tipo`, `cnpj_antigo`, `cnpj_novo`, `observacao` |
| `carteira` | `id` (auto) | `ticker`, `quantidade`, `preco_medio`, `data_compra` |
| `universo` | (`ticker`, `data_referencia`) | `cnpj`, `em_ifix`, `peso_ifix`, `fonte`, `atualizado_em` (universo IFIX; ADR-23) |

#### Tabelas de snapshot diário (cache desnormalizado)

| Tabela | PK | Conteúdo |
|---|---|---|
| `snapshot_runs` | `id` (auto) | Metadados: `data_referencia`, `status` (running/ready/failed), `engine_version_global`, `universe_scope`, `universe_hash`, `carteira_hash` + campos Focus BCB |
| `snapshot_ticker_metrics` | `id` (auto) | Métricas pré-calculadas: `preco`, `vp`, `pvp`, `pvp_percentil`, `dy_12m`, `dy_24m`, `dy_gap`, `dy_gap_percentil`, `volume_21d`, `segmento` + score 0–100 (5 colunas) + risk_metrics (6 colunas) |
| `snapshot_radar` | `id` (auto) | Flags booleanas: `pvp_baixo`, `dy_gap_alto` (regime; fora da contagem), `saude_ok`, `liquidez_ok`, `vistos` (0-3 = `RADAR_N_CRITERIOS`) |
| `snapshot_decisions` | `id` (auto) | Decisões: 3 sinais brutos, ação derivada, concordância, flags de risco, janelas abertas, versionamento por motor + CDI/Focus + score. Linhas `EVIDENCIA_JSON` e `SUPORTE_JSON` em `rationale_json` |
| `snapshot_portfolio_advices` | `id` (auto) | Conselhos de carteira: `badge` (HOLD/AUMENTAR/REDUZIR; SAIR e EVITAR_NOVOS_APORTES só em snapshots antigos), `peso_carteira`, `valor_mercado`, `racional`, `valida_ate` |
| `snapshot_structural_alerts` | `id` (auto) | Alertas estruturais: concentração, peso, n_tickers |
| `snapshot_opportunities` | `id` (auto) | Oportunidades de rotação por `run_id`: `vender`, `comprar`, `segmento`, spreads, `delta_score`, custo, `dias_persistencia`, `racional_json`, `vetos_json`, `critic_veredicto` |

#### Tabelas de diário

| Tabela | PK | Conteúdo |
|---|---|---|
| `llm_journal` | `id` (auto) | Log de chamadas ao LLM: `data`, `template`, `prompt_version`, `modelo`, `ticker`, `snapshot_run_id`, `resposta_md`, `latencia_ms` |
| `decisoes_log` | `id` (auto) | Decisões reais do investidor: `data`, `tipo` (COMPRA/VENDA/ROTACAO/IGNORADA), `ticker_vendido`, `ticker_comprado`, `quantidade`, `preco`, `opportunity_id`, `racional_usuario`. `registrar_decisao` recusa ticker inexistente e duplicata (devolve `(decisão ou None, avisos)`) |

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
│   ├── cli.py                         # Typer CLI: 14 comandos (panorama, fii, consulta, radar, alertas, calendario, carteira, update-prices, diario, oportunidades, registrar-decisao, review, prompt, analise)
│   ├── __main__.py                    # Entry point para `python -m fii_analysis`
│   ├── data/
│   │   ├── database.py                # SQLAlchemy 2.0: 19 tabelas (10 operacionais + 7 snapshot + 2 diário)
│   │   ├── migrations.py              # Migrações idempotentes (sem Alembic): 010 migrações (009: colunas de sociedades em ativo_passivo; 010: `pregoes_desde_ultimo_episodio` gravado como BLOB numpy → INTEGER)
│   │   ├── ingestion.py              # CVM (+refresh automático do ZIP do ano), yfinance, brapi, BCB SGS; ativo_total (Valor_Ativo), dedup de dividendos, recálculo de fechamento_aj
│   │   ├── corporate_actions.py      # Lógica pura: detecção de splits pela CVM, VP ajustado, dedup de dividendos, retorno total, `get_inicio_retorno_total` (§4.9)
│   │   ├── ifix.py                   # Composição IFIX (B3 + fallback CSV) → tabela universo
│   │   ├── cdi.py                    # get_cdi_acumulado_12m() — desacoplado de ingestion
│   │   └── focus_bcb.py              # fetch_focus_selic() — expectativas Focus BCB com cache
│   ├── decision/                      # Camada de decisão (Sinal → Ação)
│   │   ├── __init__.py                # Re-exports: TickerDecision, DailyCommandCenter, etc
│   │   ├── recommender.py             # Motor de decisões descritivo: COMPRAR/VENDER só com sinal com suporte estatístico; sem veto por flag
│   │   ├── evidencia.py               # Constante EVIDENCIA (resultado do estudo em painel) + linha EVIDENCIA_JSON do rationale
│   │   ├── carteira_validacao.py      # Validação de posição de carteira (ticker existente, quantidade inteira > 0, preço finito > 0)
│   │   ├── abertos.py                 # Detecção de oportunidades abertas
│   │   ├── portfolio_advisor.py       # Conselhos de carteira: só HOLD/AUMENTAR/REDUZIR; flag de destruição de capital = alerta de risco descritivo
│   │   ├── daily_report.py            # DailyCommandCenter: agregação decisão + carteira + CSV
│   │   ├── cdi_focus_explainer.py     # Explicação CDI + Focus BCB (informativo, não altera ação)
│   │   ├── suporte.py                 # Trava de significância: sinal só vota com n independente ≥ 30 e p ajustado por Benjamini-Hochberg < 0,05 (§4.2)
│   │   ├── elegibilidade.py           # Bloqueio de COMPRAR/AUMENTAR/rotação: fundo em liquidação/encerrado, preço defasado ou 5 pregões seguidos sem negócios (§4.2)
│   │   ├── opportunities.py           # Pares de rotação DESCRITIVOS (candidato = liquidez OK, elegível, percentil de P/VP ≤ 30)
│   │   ├── opportunities_backtest.py  # [PESQUISA] Backtest da rotação (NÃO point-in-time; não usado no pipeline)
│   │   └── decision_journal.py        # Log de decisões reais e ex-post reviews (Fase 4)
│   ├── llm/                           # Camada LLM (Fase 3)
│   │   ├── context_builder.py         # Construtor de contextos quantitativos
│   │   ├── prompts.py                 # Templates de prompts versionados
│   │   ├── gateway.py                 # Integração n8n e exportação de prompt packs
│   │   └── journal.py                 # Log e auditoria de respostas do LLM
│   ├── features/

│   │   ├── dividend_window.py         # Janela ±10 dias úteis (event study)
│   │   ├── indicators.py              # P/VP, DY trailing (point-in-time); get_relatorios_ajustados / get_vp_cotas_pit (VP/cota na base do preço)
│   │   ├── valuation.py               # Percentil rolling, DY N-meses, DY Gap, z-score P/VP, cap rate
│   │   ├── portfolio.py               # Panorama, alocação, retorno vs IFIX, Herfindahl
│   │   ├── saude.py                   # Tendência PL, flag destruição capital, emissões, LTV
│   │   ├── fundamentos.py             # Rentabilidade efetiva/patrimonial, alavancagem, payout
│   │   ├── composicao.py              # Classificação Tijolo/Papel/Híbrido
│   │   ├── data_loader.py             # Agregadores de dados para src/ (CLI e páginas)
│   │   ├── radar.py                   # Matriz booleana; RADAR_N_CRITERIOS = 3 (P/VP baixo, Saúde, Liquidez); DY Gap alto gravado mas fora da contagem
│   │   ├── score.py                   # Score 0–100 com 4 sub-scores (pesos adaptativos)
│   │   ├── risk_metrics.py            # Volatilidade, beta vs XFIX11, max drawdown, yield on cost
│   │   ├── volume_signals.py          # Volume drop flag, volume ratio 21/63, perfil volume
│   │   └── momentum_signals.py        # Momentum relativo IFIX 21d, dividend safety, DY momentum
│   ├── models/
│   │   ├── statistical.py             # Event study CAR, t-test, Mann-Whitney
│   │   ├── walk_forward.py            # Splits temporais com gap + validação leakage
│   │   ├── walk_forward_rolling.py    # Validação out-of-sample deslizante (thinned) + sinal_hoje
│   │   ├── episodes.py                # Identificação de episódios thinned (min_gap)
│   │   ├── teste_excesso.py           # Teste do excesso sobre a deriva (t de 1 amostra unicaudal); chamado por otimizador, episódios e walk-forward (§4.2)
│   │   ├── critic.py                  # Shuffle/placebo/estabilidade (CriticAgent)
│   │   ├── strategy.py                # Simulação dividend capture, otimização, risco
│   │   ├── trade_simulator.py         # Motor puro de simulação (caixa/CDI, dividendos, preço bruto)
│   │   ├── threshold_optimizer_v2.py  # Otimizador V2: grid 244 combinações, volume drop filter, cache JSON (best_params + test_stats)
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
│   │   ├── daily_report.py            # Relatório diário (MD+CSV, 5 seções); sinais ainda sem rótulo "(info)"
│   │   ├── daily_snapshots.py         # Geração/leitura de snapshots diários (7 tabelas)
│   │   ├── daily_diff.py              # Diff de snapshots N vs N-1 (Fase 4)
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
│   │   ├── 15_Laboratorio.py          # Técnico — Auditoria (Otimizador/Episódios/WalkForward)
│   │   └── 16_Oportunidades.py        # Diário — "Pares de Rotação" (título da página; arquivo mantém o nome antigo)
│   └── components/
│       ├── page_content/              # Módulos reutilizáveis por Dossie/Laboratório + wrappers
│       │   ├── analise_fii.py         # render(ticker) — análise por FII
│       │   ├── episodios.py           # render() — episódios thinned
│       │   ├── fund_eventstudy.py     # render() — eventos discretos CVM
│       │   ├── fundamentos.py         # render(ticker) — DY, P/VP, PL, distribuição
│       │   ├── otimizador_v2.py       # render() — backtest com thresholds (7 abas + grid completo)
│       │   └── walkforward.py         # render() — validação deslizante + sinal_hoje
│       ├── aviso_ui.py                # Aviso fixo de evidência (render_aviso_evidencia), rotulo_acao/rotulo_flags (rótulos descritivos)
│       ├── carteira_ui.py             # Cache Streamlit + CRUD carteira (load/save/delete) + validação de posição/CSV
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
│   ├── _check_db_state.py             # Debug: inspeção ad-hoc do banco (tabelas, contagens, últimos snapshot_runs); caminho do DB hardcoded
│   ├── run_tests.ps1                  # [PowerShell] Suíte de testes com cobertura
│   ├── analise_janela_v2.py           # Wrapper: estratégias de janela (lógica em div_capture)
│   ├── analise_janela_flexivel.py     # Wrapper: varredura de targets (lógica em div_capture)
│   ├── analise_spread_recompra.py     # Wrapper: simulação spread recompra (lógica em div_capture)
│   ├── scrape_fundsexplorer.py        # Scraping FundsExplorer
│   ├── daily_report.py                # CLI do relatório diário (MD+CSV) com --com-otimizador
│   ├── generate_daily_snapshots.py    # CLI para gerar snapshot diário (--scope {curado,carteira,db_ativos,ifix})
│   ├── load_ifix_universe.py          # Carga inicial do universo IFIX (B3 + CVM + yfinance)
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
    ├── pesquisa/painel_2026-11/       # Estudo em painel pré-registrado (PREREGISTRO.md, out_*.txt, tabela_prereg.csv, scripts)
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

Parâmetros de filtro e de descrição são centralizados na seção `thresholds` do `config.yaml`. Os limiares são **convenções de descrição, não pontos de corte validados** (§1): o estudo em painel não achou evidência para nenhum deles, e os de saúde nunca foram calibrados.

| Parâmetro | Descrição | Default |
|---|---|---|
| `pvp_percentil_barato` | Percentil P/VP abaixo do qual o radar marca "P/VP baixo" e a lista de pares de rotação aceita candidato (≤) | 30 |
| `dy_gap_percentil_caro` | Percentil DY Gap acima do qual o radar marca "DY Gap alto" (indicador de regime, fora da contagem) | 70 |
| `meses_consec_alerta` | Meses consecutivos com rentabilidade patrimonial negativa (VP/cota em queda no mês) para erro de saúde | 3 |
| `alavancagem_limite` | Razão Ativo/PL considerada alavancagem significativa | 1.05 |
| `piso_liquidez` | Volume financeiro médio 21d mínimo | 500.000 |
| `dias_staleness` | Dias de atraso permitidos na coleta de preço | 3 |

Seções adicionais do `config.yaml` (lidas por `config_yaml.get_saude_param` / `get_decisao_param`, com default no código):

| Seção.chave | Descrição | Default |
|---|---|---|
| `saude.vp_pct_mes_saudavel` / `vp_pct_mes_severo` | Limiares da inclinação do VP/cota em **% ao mês** (slope / VP médio da janela): acima do primeiro = sem destruição; abaixo do segundo = severo | +0,1 / −0,5 |
| `saude.tendencia_delta_pct_mes` | Diferença 3m vs 6m (p.p./mês) para melhorando/piorando | 0,1 |
| `decisao.suporte_n_min` / `fdr_q` | Um sinal só vota se tiver n eventos independentes fora da amostra ≥ n_min e p ajustado por Benjamini-Hochberg (família = sinais BUY/SELL ativos da rodada) < fdr_q | 30 / 0,05 |
| `decisao.preco_defasado_dias_uteis` | Atraso (pregões) do último preço acima do qual o ticker não recebe compra | 5 |
| `decisao.sem_negocios_pregoes` | Pregões consecutivos com volume 0 a partir dos quais o ticker não recebe compra. Chave **ausente do `config.yaml`**: vale o default do código | 5 |

As chaves `decisao.testes_episodio`, `decisao.testes_walkforward` e `decisao.suporte_p_max` não existem mais (nem no `config.yaml` nem no código): o multiplicador de testes foi substituído pela correção BH (ADR-30).

**Regra de decisão vigente (ADR-31):** `recommender._derivar_acao` não tem veto por flag de risco. A ação só é COMPRAR/VENDER se 2 ou 3 sinais com suporte concordarem; sem suporte, AGUARDAR. A flag de destruição de capital e a de queda forte com volume alto viram linha "ALERTA (descritivo, nao veta)" no rationale quando há BUY; DY Gap < p5 vira linha "Atencao" numa ação COMPRAR. `EVITAR` e nível `VETADA` não são mais produzidos (existem só em snapshots antigos). Toda decisão carrega a linha `EVIDENCIA_JSON` (`decision/evidencia.py`). `portfolio_advisor` só gera HOLD, AUMENTAR (COMPRAR com suporte + folga de peso, sem bloqueio) e REDUZIR (VENDER com suporte); destruição de capital vira "ALERTA DE RISCO (descritivo)" no racional, com badge HOLD; SAIR e EVITAR_NOVOS_APORTES não são mais gerados.

Sinal sem suporte continua gravado e exibido como informativo (`BUY (info)`), mas não entra em `n_concordam_*`; o status vai em `rationale_json` (linha `SUPORTE_JSON`). Ticker nunca recebe COMPRAR/AUMENTAR nem entra como candidato de rotação (`decision/elegibilidade.py`, `motivo_bloqueio_compra`) se tiver: (1) evento de liquidação/encerramento vigente (`eventos_corporativos`); (2) preço defasado (> `preco_defasado_dias_uteis` pregões); (3) os últimos `sem_negocios_pregoes` pregões consecutivos com volume 0 (mensagem "sem negocios ha N pregoes"; volume NULL interrompe a sequência, não conta como zero). `liquidez_intermitente` (≥ 4 pregões com volume 0 nos últimos 10) existe em `elegibilidade.py` mas **não está ligada** ao `recommender` nem a nenhum consumidor em `src/`: não bloqueia nem aparece na decisão (só testes a chamam).

Definição única da hipótese (docstring de `decision/suporte.py`, cálculo em `models/teste_excesso.py`): H0 = o retorno forward (20 pregões) após o sinal é igual ao retorno forward **incondicional do mesmo ativo no mesmo período de avaliação** (média de todos os dias elegíveis, incluindo os de evento); estatística = t de 1 amostra do excesso (retorno do evento thinned − deriva), **unicaudal na direção do sinal** (BUY: excesso > 0; SELL: excesso < 0). Vale para otimizador, episódios e walk-forward. Correção: **Benjamini-Hochberg** (FDR `decisao.fdr_q`) sobre a família = todos os sinais BUY/SELL ativos da rodada (`decidir_universo`; em `decidir_ticker` avulso, os sinais ativos do ticker); o p ajustado (`p_bh`) é o "p corrigido" da trava. O p do split de teste do otimizador (holdout) **não** é multiplicado pelo tamanho do grid (a seleção ocorre em treino/validação). Origem de n e p por sinal: otimizador = split de **teste** (`n_*_thinned`, média, deriva, excesso e p), lido do campo `test_stats` do cache `dados/optimizer_cache/<ticker>.json` (cache sem `test_stats` ou com `best_params` diferentes dos usados = sinal sem suporte até ser regenerado por `scripts/refresh_optimizer_cache.py`; `update-prices` só regenera cache com mais de 7 dias; o JSON não guarda versão da definição, então o código não distingue um cache gravado antes desta definição); episódios = `n` thinned, `mean`, `drift`, `p_value`; walk-forward = `n_effective`, `mean`, `drift`, `p_value`. O p só é calculado com n mínimo de eventos (otimizador: 4, com p = 1 abaixo disso; episódios e walk-forward: 5, `N_MIN_TESTE` em `teste_excesso.py`, p ausente abaixo disso); sinal ativo sem p entra na família BH com p = 1. Percentis gravados na decisão são **os mesmos da métrica do snapshot**: `pvp_percentil` = `get_pvp_percentil` (janela 504 pregões até t−1) e `dy_gap_percentil` = `get_dy_gap_percentil` (janela 252), as mesmas chamadas de `evaluation/daily_snapshots.py`; os flags `flag_pvp_caro` (> 95) e `flag_dy_gap_baixo` (< 5) usam esses mesmos números. O percentil interno de episódios (que só gera `sinal_episodio`) também exclui o dia atual da janela; o do otimizador (`pvp_pct`, `rolling(504).rank`) ainda inclui o dia atual (pendência; ver `docs/STATUS_ATUAL.md`). Limitações conhecidas da trava (n ≥ 30 não atingível pelo desenho atual, deriva tratada como constante, premissa de independência do BH, família menor em chamadas parciais): `docs/STATUS_ATUAL.md`, "Pendentes conhecidos".

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

O VP usado em qualquer razão com o preço é o **VP/cota na base do preço** (ajustado por splits), obtido por `features/indicators.get_vp_cotas_pit` / `get_relatorios_ajustados` — nunca o `vp_por_cota` nominal cru (§4.9).

### 4.4 P/VP e DY são calculados, nunca armazenados

```python
pvp_em_t = preco_em_t / vp_vigente_em_t(data_entrega <= t)
dy_trailing_t = soma(dividendos com t-365d < data_com < t) / ultimo_preco_ate_t   # indicators.get_dy_trailing
```

**Dividendo só entra a partir do pregão seguinte à data-com** (`data_com < t`, estrito): no dia da data-com o preço ainda carrega o dividendo, e contá-lo seria look-ahead. A regra vale em `features/valuation.py` (DY N-meses, DY Gap e seu percentil), `features/indicators.py`, `features/risk_metrics.py` (`dy_3m_anualizado`, `yield_on_cost`, retorno total) e no DY Gap do otimizador (`models/threshold_optimizer_v2.py`). Possível look-ahead residual: a data de anúncio do dividendo não existe no banco, então o DY Gap usa dividendos que, no dia t, podem ainda não ter sido anunciados (a data-com é conhecida antes do pagamento, mas a data de anúncio não está armazenada).

### 4.5 Janela da data-com: ±10 dias úteis

Janelas maiores (ex: ±30 dias) se sobrepõem porque FIIs pagam mensalmente. Sobreposição viola independência estatística do event study.

Quando duas datas-com distam < 21 dias úteis, **o evento seguinte é descartado** — não truncar janela (viés de seleção).

### 4.6 Ingestão idempotente

Antes de coletar dados, verificar se já existem no banco. Nunca sobrescrever sem verificação. O preço ajustado do yfinance é recalculado retroativamente — sempre salvar `coletado_em`. Exceções controladas na carga de preços: linhas vazias (abertura/máxima/mínima/volume = 0 ou nulos) ou coletadas no próprio pregão (fechamento possivelmente provisório) são reabertas e regravadas numa janela de 400 dias; linhas com `fonte = 'yfinance:invalido'` nunca são reescritas pela carga. `fechamento_aj` é recalculado por inteiro ao fim de cada carga de preços/dividendos (§4.9).

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

### 4.9 Base única de cotas, dividendos e retorno total

Lógica pura em `src/fii_analysis/data/corporate_actions.py`; aplicada na ingestão (`data/ingestion.py`) e na leitura (`features/indicators.py`).

- **Base única:** preço (`fechamento` = `Close` do yfinance, já ajustado por split), dividendo por cota (`dividendos.valor_cota`) e VP/cota usado em P/VP ficam na base da **quantidade atual de cotas**. O VP/cota da CVM é nominal (contemporâneo ao informe) e é convertido por `ajustar_relatorios`.
- **Detecção de split (só com `relatorios_mensais`):** entre dois informes consecutivos, `cotas_emitidas` varia por fator F (≥ 1,8 ou ≤ 1/1,8), VP/cota varia por ~1/F e o PL fica estável (±20%) — emissão/amortização mexem no PL e não são confundidas. F é arredondado ao fator "redondo" mais próximo (tolerância 8%); sem fator redondo, o evento é ignorado como ambíguo. O evento é ancorado no **primeiro informe pós-split**: só muda a unidade (P/VP inalterado), sem vazamento de informação futura.
- **Dividendos:** duplicata = mesmo valor por cota com data-com a ≤ 7 dias de outra linha (o Yahoo revisa ex-dates); mantém a data na convenção correta, senão a mais antiga (`deduplicar_proximos`, `limpar_dividendos_duplicados`; a carga também não insere duplicatas). Linha gravada que é múltiplo de split do valor atual do Yahoo é regravada com o valor do Yahoo (`_reconciliar_base_split`); diferenças < 1,8× (ajustes de subscrição) são preservadas.
- **`fechamento_aj` = série de retorno total do projeto**, recalculada por inteiro (`recalcular_fechamento_aj`) a partir de `fechamento` + `dividendos`: dividendo reinvestido no primeiro pregão com preço após a data-com; série escalada para terminar igual ao último `fechamento`. Não usa o Adj Close do Yahoo. Uso: retornos relativos (event study, otimizador, momentum, risco). Como o nível muda a cada dividendo novo, nunca compará-lo com `fechamento` em data passada nem somar dividendos sobre ele.
- **Janela de validade do retorno total** (`corporate_actions.get_inicio_retorno_total`): o yfinance só tem dividendos com cobertura ampla a partir de 2022-03/04; antes disso `fechamento_aj` é retorno de **preço**. `INICIO_RETORNO_TOTAL` é calculado do dado (primeiro mês da sequência final em que ≥ 50% dos fundos com preço têm dividendo; `FRACAO_COBERTURA_DIVIDENDOS`), não é constante no código; valor medido: 2022-03-01 (informado, não reproduzido nesta revisão). Episódios, otimizador, walk-forward e event study CVM descartam retorno forward anterior a essa data. O limiar de 50% dá 2022-03, enquanto o estudo em painel usou 2022-04 como início da amostra primária. Efeito sobre a janela de estimação do event study não medido.
- **Retorno total 12m** (`risk_metrics.retorno_total_12m`) = `(P_t − P_t−252 + Σ dividendos) / P_t−252` com `fechamento` bruto (com `fechamento_aj` os dividendos seriam contados 2×).
- **`ativo_total`** (`ativo_passivo`) = `Valor_Ativo` informado pelo fundo no arquivo `complemento`; fallback (ausente/≤ 0) = `Total_Investido + Total_Necessidades_Liquidez + Valores_Receber`, sem somar de novo os componentes já contidos em `Total_Investido` (ex.: `Direitos_Bens_Imoveis`) nem `Contas_Receber_*` (`calcular_ativo_total`). `load_ativo_passivo_to_db(..., atualizar_existentes=True)` regrava linhas existentes (recarga após correção de regra).

Consumidores de VP/cotas na base ajustada (`get_relatorios_ajustados`): P/VP e otimizador/episódios, saúde (`saude.py`: `flag_destruicao_capital`, `tendencia_pl`, `emissoes_recentes`), momentum (`get_pl_trend`), event study CVM (`emissao_cotas`, `pl_queda_2pct`) e as séries históricas de PL/VP/cotas exibidas em gráficos (`features/data_loader.py`, `features/fundamentos.py`, `llm/context_builder.py`). Os valores nominais do informe só sobrevivem em colunas `vp_nominal`/`cotas_nominal` (`data_loader`, `fundamentos`) e, no contexto LLM o nominal segue em `vp_por_cota`, ao lado de `vp_por_cota_ajustado`. Em split, isso evita falsa emissão e falsa queda de VP/PL.

---

## 5. Métricas e Metodologia

### 5.1 Valuation

| Métrica | Definição |
|---|---|
| **P/VP em t** | `preco_em_t / vp_vigente(data_entrega <= t)` — VP do último relatório CVM entregue antes de t. |
| **Percentil P/VP rolling** | Posição na distribuição da janela de 504 pregões (2 anos) até t−1 (`get_pvp_percentil`): % de observações **estritamente abaixo** do P/VP de t; valores a menos de 1e-9 (relativo) de t contam como empate, não como "abaixo" (`TOL_EMPATE_PVP`); P/VP de t no máximo da janela = 100. Exige ≥ 63 observações. |
| **Z-score P/VP** | `(pvp - media_504d) / desvio_504d` — normalização do P/VP. |
| **DY N-meses** (12/24/36) | Soma dividendos com data-com em `(t−N meses, t)` (início aberto: não conta 13 pagamentos em 12m; fim estrito: dividendo só entra a partir do pregão seguinte à data-com, §4.4) / preço atual. |
| **DY Gap** | `DY 12m − CDI acumulado 12m` (point-in-time). O CDI acumulado 12m (`data/cdi.py`) usa janela `(t−12m, t]` (o dia t−12m fica fora); exige ≥ 200 dias de CDI. Possível look-ahead residual: sem data de anúncio do dividendo (§4.4). |
| **Percentil DY Gap** | Posição na distribuição da janela de **exatamente 252 pregões** (1 ano) anteriores a t (t excluído; `_datas_janela`); os dividendos são buscados desde 12 meses antes da data mais antiga da janela, para que o DY 12m de cada ponto da janela seja completo. É indicador de **regime**, não de seleção: a fração de fundos com percentil > 70 foi de 0% a 99% conforme a data (estudo em painel, `out_05.txt`: 94% na última data), então "DY Gap alto" descreve o mercado, não o fundo. |
| **Média anual de DY** (`fundamentos.get_dy_medias`) | `DY 24m / 2` e `DY 60m / 5` (`get_dy_n_meses` devolve a soma do período); `dy_mes_pct` e DY 12m são frações e comparados como fração. |
| **Retorno total 12m** | Ver §4.9 (`fechamento` bruto + dividendos). |
| **Cap Rate anualizado** (`valuation.get_cap_rate_spread`) | Média das últimas até 6 `rentab_efetiva` mensais da CVM entregues até t (mínimo 3), composta: `(1 + média_mensal)^12 − 1`. É um rendimento distribuído contábil (rentabilidade efetiva), **não** uma taxa de capitalização sobre receita de aluguel nem sobre o preço de mercado. |
| **Cap Rate spread** | `Cap Rate anualizado − CDI acumulado 12m` (`None` sem CDI suficiente). |
| **DY 3m anualizado** (`risk_metrics.dy_3m_anualizado`) | Dividendos dos últimos 63 pregões × 4 ÷ preço atual; é uma métrica distinta do cap rate, gravada em `snapshot_ticker_metrics.dy_3m_anualizado`. |

### 5.2 Saúde financeira e Fundamentos

| Métrica | Definição |
|---|---|
| **Mês Saudável** | `rentab_patrim >= 0` E `rentab_efetiva >= rentab_patrim`. Nota: `efetiva − patrimonial ≡ dy_mes_pct` (identidade exata nos dados da CVM), logo o critério mede apenas VP/cota não caindo no mês e DY ≥ 0 — **não** mede "distribuir mais do que gera". |
| **Alertas de Saúde** | **Erro:** >= `meses_consec_alerta` (default 3) consecutivos não saudáveis. **Aviso:** < 4 meses saudáveis no total dos últimos 6 meses. |
| **Alavancagem** | `Ativo_Total / Patrimonio_Liquido`. Alerta se > `alavancagem_limite`. |
| **LTV (Leverage to Value)** | `max(0, ativo_total - PL) / ativo_total`. |
| **Destruição de capital** (`saude.flag_destruicao_capital`) — **alerta de risco descritivo** | No estudo em painel a flag marcou ~47% dos fundos-mês (48,6% na última data, n = 109) e a diferença de retorno em excesso flagged − não flagged foi −0,11% (1m), −0,13% (3m), −0,99% (6m), −1,25% (12m), nenhuma significativa (p ≥ 0,18; `out_05.txt`, 8A). Não há evidência de que a flag antecipe retorno pior, e por isso ela não veta nem gera ação (ADR-31). Limiares não calibrados. Usa o **VP/cota** (não a identidade acima). Limiares em **% do VP/cota por mês** (slope da regressão 3m/6m ÷ VP médio da janela × 100; `saude.vp_pct_mes_saudavel` / `vp_pct_mes_severo`, §4.2), logo cota cara e barata têm a mesma régua. Streak = meses consecutivos em que o VP/cota **caiu** mais que `vp_pct_mes_saudavel` no mês (substituiu o critério "efetiva > patrimonial", que equivale a `dy_mes_pct > 0`). Tendência = slope 3m vs 6m (`tendencia_delta_pct_mes`). Chamada com `t` (point-in-time: só `data_entrega <= t`); o `recommender` passa a data de referência, os demais chamadores usam hoje. |
| **Tendência PL** | Regressão linear (6m, 12m) sobre o VP por cota (`saude.tendencia_pl`, também com `t`). Usa VP/cota ajustado por split (§4.9). `momentum_signals.get_pl_trend` (CRESCENDO/CAINDO/ESTAVEL em 3 meses) usa PL ÷ cotas ajustadas. |
| **Emissões recentes** | Salto em `Cotas_Emitidas` mês a mês > 1%, com cotas na base ajustada por split (um desdobramento/grupamento não é emissão). O sinal `emissao_cotas` do event study CVM usa o mesmo critério com limiar de 2%. |

### 5.3 Composição do ativo

| Classificação | Regra |
|---|---|
| **Tijolo** | Imóveis ≥ 60% do ativo, onde imóveis = imóveis diretos (`Direitos_Bens_Imoveis`) + participações em sociedades de atividade imobiliária (`acoes_sociedades_fii` + `cotas_sociedades_fii`). Sem as colunas de sociedades no banco (migração 009 não aplicada), só imóveis diretos |
| **Papel** | Recebíveis (CRI + CRI_CRA + LCI + LCI_LCA) ≥ 60% |
| **Híbrido** | Caso contrário |

Fonte: arquivo `ativo_passivo` da CVM (`composicao_ativo` / `classificar_fii` em `features/composicao.py`). A CVM não separa o tipo da sociedade: um fundo cujo ativo está em sociedades que não detêm imóveis pode ser classificado como Tijolo. As parcelas devolvidas por `composicao_ativo` são mutuamente exclusivas (imóveis, sociedades, recebíveis, caixa, outros investimentos, valores a receber, outros mobiliários; `pct_outros` = resíduo): `Valores_Receber` já contém `Contas_Receber_Aluguel` e `Total_Necessidades_Liquidez` já contém `Disponibilidades` (caixa = o maior dos dois), e `Total_Investido` é descontado de imóveis, sociedades e títulos para não contar duas vezes. Cotas de outros FIIs não entram em imóveis.

### 5.4 Radar descritivo

Matriz booleana — 3 critérios contados (`RADAR_N_CRITERIOS = 3`, `features/radar.py`), sem ponderação, mais 1 indicador de regime fora da contagem:

| Filtro | Critério | Na contagem `vistos` |
|---|---|---|
| P/VP Baixo | Percentil rolling 504d < 30 | sim |
| Saúde OK | Sem flag de destruição de capital | sim |
| Liquidez OK | Volume financeiro médio 21d ≥ piso YAML (default: R$ 500.000) | sim |
| DY Gap Alto | Percentil rolling 252d > 70 | **não** (regime de mercado, §5.1) |

Ordenação por número de ✓ (0–3), desempate alfabético. **A contagem descreve; não seleciona.** No estudo em painel, `vistos` e `vistos == 4` (versão antiga de 4 critérios) não tiveram evidência de prever retorno (`out_04.txt`, p BH ≥ 0,81). Último snapshot (run 41, informado): 0/1/2/3 critérios = 2/23/43/42 fundos.

**Proximidade da data-com não entra no radar** (ADR-15): o event study não achou padrão utilizável.

### 5.5 Score 0–100 (comunicativo)

Score 0–100 com 4 sub-scores ponderados (não altera decisões; resumo de leitura, **sem evidência de prever retorno** — no estudo em painel, `score` teve p BH ≥ 0,81 em todos os horizontes):

| Sub-score | Peso | Composição |
|---|---|---|
| Valuation | 35% | P/VP percentil (invertido) + DY Gap percentil + z-score (pesos adaptativos 50/30/20 ou fallback 60/40) |
| Risco | 30% | Volatilidade + Beta vs XFIX11 + Max Drawdown (percentis no universo) |
| Liquidez | 20% | Faixas fixas em R$/dia (< R$ 200k: 20 pts; R$ 1–5M: 75 pts; ≥ R$ 5M: 90 pts) |
| Histórico | 15% | Consistência DY 24m (CV invertido: CV ≤ 0.5 → 100 pts) |

Score é **puramente informativo**: não entra na decisão nem em cálculos de risco.

### 5.6 Event study (instrumento de pesquisa)

- **CAR** (Cumulative Abnormal Return): retorno acumulado do FII menos retorno acumulado do benchmark (IFIX) na janela ±10 pregões.
- **BHAR** (Buy-and-Hold Abnormal Return): variação buy-and-hold vs benchmark.
- **Testes:** t-test pareado (pré vs pós), Mann-Whitney U, t-test 1 amostra (dia 0).
- **Correção múltiplas comparações:** Benjamini-Hochberg é a regra do projeto (ADR-30). Inconsistência conhecida: `app/components/page_content/fund_eventstudy.py` ainda exibe correção de Bonferroni (`p_bonf`).
- Usa só retorno a partir de `INICIO_RETORNO_TOTAL` (§4.9). Não há evidência de que a data-com gere padrão operável.

### 5.7 Walk-forward com gap (instrumento de pesquisa)

Split temporal (default 60/20/20) com gap de 10 dias úteis entre períodos. Função `validate_no_leakage()` detecta sobreposição automaticamente. `walk_forward_rolling.py` produz `sinal_hoje`, um dos três sinais da trava (§4.2), que hoje não passa.

### 5.8 CriticAgent (falsificação)

| Teste | O que faz |
|---|---|
| **Permutation shuffle** | Embaralha sinais de evento e mede acurácia (detecta correlação espúria) |
| **Placebo** | Usa datas aleatórias como falsas datas-com; compara com datas reais via Mann-Whitney |
| **Subperiod stability** | Compara 1ª metade vs 2ª metade dos eventos via t-test |

**Veredito:** aprovado somente se todos os 3 testes passam.

### 5.9 Estratégia de dividend capture (instrumento de pesquisa; sem validação)

Simulação com preço ajustado, otimização grid search (244 combinações: buy [15–50], sell [55–90], spread≥15), métricas de risco (Sharpe, Sortino, drawdown, perdas consecutivas), comparação com buy-and-hold. Custos B3 (0.03% round-trip) e IR 20% sobre ganho de capital descontados. Volume drop flag vetorizado filtra BUYs com queda forte de volume.

### 5.10 Camada CDI V1 (informativa)

- **CDI Sensitivity:** regressão P/VP ~ CDI 12m (OLS+HAC NW, frequência semanal, min 104 obs). Retorna beta, R², p-value, resíduo atual e percentil. Status: `OK`, `DADOS_INSUFICIENTES`, `SEM_CDI`, `CONVERGENCIA_FALHOU` ou `ERRO_CODIGO` (exceção de código, antes confundida com não-convergência).
- **Focus BCB:** expectativas Selic 3m/6m/12m com cache diário.
- **CDI Focus Explainer:** combina beta + delta Focus + resíduo percentil para explicação textual.
- **Não altera `_derivar_acao()`** — é puramente informativo, enriquece rationale.

### 5.11 Volume e Momentum (descritivos; momentum sem evidência de previsão no estudo em painel)

| Sinal | Definição |
|---|---|
| **Volume drop flag** | Volume 21d < volume 63d − threshold% (filtra BUYs no otimizador) |
| **Volume ratio 21/63** | Razão volume 21d / volume 63d |
| **Momentum relativo IFIX** | Retorno FII 21d (`fechamento_aj`) vs retorno 21d do benchmark `XFIX11` (`benchmark_diario`), alinhado nas mesmas datas da janela do FII; `None` se não houver benchmark no banco |
| **Dividend safety** | Análise payout vs caixa, cortes 24m, flag insustentável |

---

## 6. Interfaces do Sistema

### 6.1 Como usar o CLI

O CLI é independente do Streamlit e deve ser executado no terminal utilizando o interpretador do Anaconda:

**Comando base (wrappers na raiz do projeto, cuidam de PYTHONPATH e encoding):**
- PowerShell: `.\fii COMANDO`  (ex.: `.\fii diario`)
- cmd.exe: `fii COMANDO`
- Forma explícita: `C:/ProgramData/anaconda3/python.exe -m src.fii_analysis COMANDO` (a partir da raiz)

| Comando | Função |
|---|---|
| `panorama` | Tabela de todos os FIIs monitorados com métricas-chave; a data exibida é a do pregão da maioria dos fundos (`evaluation/panorama.resumo_defasagem`), não a do mais atrasado |
| `fii TICKER` | Análise detalhada de um FII (valuation, saúde, composição, datas-com) |
| `consulta TICKER` | **Analítico IA:** Integra indicadores locais com Gemini + Google Search para análise qualitativa em 4 seções |
| `radar` | Exibe a matriz booleana (3 critérios contados: P/VP, Saúde, Liquidez; DY Gap como regime) |
| `alertas` | Gera e exibe alertas diários (descritivos) com base nos thresholds de risco |
| `calendario` | Lista as próximas datas-com previstas para os próximos 30 dias |
| `carteira` | Exibe posições, alocação por segmento (a valor de mercado) e retorno vs IFIX |
| `update-prices` | Pipeline diário completo: preços + dividendos + CDI + XFIX11 + cache otimizador + snapshot. Default `--scope ifix` (IFIX ∪ curado ∪ carteira); métricas/radar para todo o universo, decisões só para curado ∪ carteira |
| `diario` | Cockpit do dia no terminal (sinais 3 motores, score 0–100, percentis) lendo do snapshot. `--diff` exibe mudanças; o rótulo é "desde ontem" só se o snapshot anterior for o pregão anterior pelo calendário B3 (`evaluation/daily_diff.rotulo_periodo_diff`), senão "desde o snapshot anterior". O rodapé que sugere `fii update-prices` só aparece com preço defasado (`precos_desatualizados`: último preço do banco anterior ao último pregão até hoje). |
| `oportunidades` | Exibe os pares de rotação (descritivos) do último snapshot |
| `registrar-decisao` | Registra uma operação ou decisão no log de decisões; recusa ticker inexistente e duplicata |
| `review` | Exibe relatório ex-post das rotações registradas vs XFIX11 (descritivo; não valida o método) |
| `prompt` | Gera Prompt Pack local em Markdown para colagem manual |
| `analise` | Análise qualitativa enriquecida com IA (via gateway ou prompt pack) |


### 6.2 Streamlit Dashboard

Entry point: `app/streamlit_app.py`. Layout `wide`, sidebar expandida com 3 grupos.

**Navegação (sidebar):**

- **Diário:** `13_Hoje.py`, `16_Oportunidades.py`, `3_Carteira.py`, `1_Panorama.py`, `4_Radar.py`
- **Investigação:** `14_Dossie_FII.py`, `6_Alertas.py`, `5_Event_Study.py`
- **Técnico:** `15_Laboratorio.py`

As páginas 2/7/8/10/11/12 são wrappers standalone (não na sidebar) — seu conteúdo é renderizado dentro do Dossie (2/7/8) e do Laboratório (10/11/12) via `app/components/page_content/*.py`.

| Página | Sidebar | Conteúdo |
|---|---|---|
| **1_Panorama** | Diário | Métricas gerais, coluna de rótulo descritivo (`rotulo_acao`), Score 0–100, radar `n/3`. Universo exibido: carteira ∪ curados (26), com opção de ver o IFIX do snapshot (`tickers_universo_exibido`) |
| **3_Carteira** | Diário | CRUD de posições (validação de ticker/quantidade/preço, inclusive no CSV importado), cálculo ao vivo com cache, aviso de carteira alterada desde o snapshot, badges HOLD/AUMENTAR/REDUZIR com alerta de risco no racional, alertas estruturais de concentração |
| **4_Radar** | Diário | Heatmap booleano (3 critérios), tabela detalhada, exportação CSV |
| **16_Oportunidades** | Diário | Título "Pares de Rotação": lista descritiva de pares intra-segmento (sem validação de retorno; 0 pares no run 41), geração de prompts e registro de decisão |
| **13_Hoje** | Diário | Painel do dia: leitura por ticker, watchlist, carteira cruzada, alertas de risco, contexto de juros. Sinais sem suporte aparecem como `BUY (info)`/`SELL (info)` (§4.2); hora do snapshot em horário local; "desatualizado" = anterior ao último pregão já encerrado (corte 18:30, sem fonte); sem snapshot, orienta `fii update-prices` |
| **14_Dossie_FII** | Investigação | Consolidado por ticker (seletor com os 110 fundos) — abas Análise FII / Fundamentos / Eventos CVM |
| **5_Event_Study** | Investigação | Event study agregado: CAR, testes, CriticAgent |
| **6_Alertas** | Investigação | Geração sob demanda, listagem de Markdowns por data |
| **15_Laboratorio** | Técnico | Instrumentos de pesquisa — abas Otimizador V2 / Episódios / Walk-Forward (sem poder preditivo demonstrado) |
| **2_Analise_FII** | Não | Wrapper → `page_content/analise_fii.py` |
| **7_Fundamentos** | Não | Wrapper → `page_content/fundamentos.py` |
| **8_Fund_EventStudy** | Não | Wrapper → `page_content/fund_eventstudy.py` |
| **10_Otimizador_V2** | Não | Wrapper → `page_content/otimizador_v2.py` |
| **11_Episodios** | Não | Wrapper → `page_content/episodios.py` |
| **12_WalkForward** | Não | Wrapper → `page_content/walkforward.py` |

**Componentes reutilizáveis** (`app/components/`):

| Componente | Função |
|---|---|
| `aviso_ui.py` | `render_aviso_evidencia` (aviso fixo + resumo do estudo, lido de `decision/evidencia.py`) em Hoje, Carteira, Radar, Pares de Rotação (16) e Dossiê; `rotulo_acao` / `rotulo_flags` (rótulos descritivos, ex.: COMPRAR → "indicadores favoráveis", EVITAR → "alerta de risco"); `csv_sem_comentarios`. Panorama usa só `rotulo_acao` |
| `carteira_ui.py` | Cache Streamlit + CRUD carteira: `load_tickers_ativos`, `load_carteira_db`, `save_posicao`, `delete_posicao`, `validar_posicao` (delega a `decision/carteira_validacao.py`) |
| `charts.py` | Plotly: `pvp_gauge`, `pvp_historico_com_bandas`, `pl_trend_chart`, `composicao_pie`, `car_plot`, `radar_heatmap`, `carteira_alocacao_pie`, `carteira_segmento_pie` |
| `tables.py` | Formatadores: `format_currency`, `format_pct`, `format_number`, `render_panorama_table`, `render_radar_matriz` |
| `snapshot_ui.py` | Helpers de UI para leitura de snapshots diários com `@st.cache_data(ttl=300)`, incluindo `load_decisions_snapshot` |
| `ui_shell.py` | Helpers de UI (headers, notes, sidebar) |

### 6.3 Agentes Claude Code

Agentes sub-task em `.claude/agents/` — carregados automaticamente pelo Claude Code:

| Agente | Arquivo | Especialização |
|---|---|---|
| **data-scientist** | `data-scientist.md` | Regras estatísticas do projeto: split temporal, leakage, testes. **Desatualizado:** ainda manda Bonferroni; a regra do projeto é Benjamini-Hochberg (ADR-30) |
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
| HSRE11 | Tijolo | Tijolo | — | 2020-12 (sem preço desde 2026-06-11; ticker novo não identificado) |
| KNIP11 | Papel (CRI) | Papel | **Validação cruzada** | 2017-10 |
| SNEL11 | — | — | — | — |

### Inativos

| Ticker | CNPJ | Motivo | Ação |
|---|---|---|---|
| SNFF11 | 40.011.225/0001-68 | Liquidação/descontinuação | Preservar histórico; `inativo_em` marcado; excluído de panorama/radar/alertas |

**Regra (ADR-23 — universo dual; reinterpretada pelo ADR-31):** a lista curada acima (mais as posições da carteira) é o universo para o qual o snapshot calcula as decisões (3 sinais) e os conselhos de carteira; as telas exibem por padrão esse universo único (carteira ∪ curados = 26 fundos). Como o sistema é descritivo, isso define o que é **descrito com mais detalhe**, não onde há sinal confiável. O **universo IFIX** (tabela `universo`, ~107 FIIs) recebe métricas + radar no snapshot e alimenta o lado COMPRAR da lista de pares; pode ser exibido por opção. Os seletores de Dossiê/Análise/Fundamentos listam os 110 fundos com dados. Um FII do IFIX só vira posição se o investidor decidir manualmente.

---

## 8. Estado Atual de Implementação

### Dados

| Componente | Status | Arquivo |
|---|---|---|
| Schema SQLite (19 tabelas) | Implementado | `data/database.py` |
| Migrações idempotentes (001–010) | Implementado | `data/migrations.py` |
| Ingestão CVM (ZIP → complemento/geral/ativo_passivo) | Implementado | `data/ingestion.py` |
| Ingestão preços yfinance (incremental) | Implementado | `data/ingestion.py` |
| Ingestão dividendos yfinance (ex-date → data-com) | Implementado | `data/ingestion.py` |
| CDI diário (BCB SGS série 12) | Implementado | `data/ingestion.py` |
| CDI acumulado 12m | Implementado | `data/cdi.py` |
| Benchmark XFIX11 (yfinance) | Implementado | `data/ingestion.py` |
| Expectativas Focus BCB (Selic) | Implementado | `data/focus_bcb.py` |
| Conversão ex-date → data-com via calendário B3 | Implementado | `data/ingestion.py` |
| Dedup de dividendos, detecção de splits pela CVM, retorno total (`fechamento_aj` próprio) | Implementado | `data/corporate_actions.py`, `data/ingestion.py` |
| Janela de validade do retorno total (`get_inicio_retorno_total`) | Implementado | `data/corporate_actions.py` |
| `ativo_total` = `Valor_Ativo` (`complemento`) com fallback sem dupla contagem | Implementado | `data/ingestion.py` |

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
| Tendência PL, flag destruição capital (alerta descritivo; limiares não calibrados) | Implementado | `features/saude.py` |
| LTV (Leverage to Value) flag | Implementado | `features/saude.py` |
| Análise emissões | Implementado | `features/saude.py` |
| Classificação Tijolo/Papel/Híbrido (Tijolo = imóveis diretos + sociedades de atividade imobiliária; parcelas exclusivas) | Implementado | `features/composicao.py` |
| Matriz booleana radar (3 critérios contados + DY Gap como regime) | Implementado | `features/radar.py` |
| Score 0–100 (4 sub-scores, pesos adaptativos; informativo) | Implementado | `features/score.py` |
| Volatilidade, beta vs XFIX11, max drawdown, yield on cost | Implementado | `features/risk_metrics.py` |
| Volume drop flag, volume ratio 21/63 | Implementado | `features/volume_signals.py` |
| Momentum relativo IFIX 21d, dividend safety | Implementado | `features/momentum_signals.py` |
| Rentabilidade efetiva/patrimonial, alavancagem | Implementado | `features/fundamentos.py` |
| VP/cota na base do preço (`get_relatorios_ajustados`, `get_vp_cotas_pit`) | Implementado | `features/indicators.py` |

### Models

Todos os itens abaixo são instrumentos de pesquisa/descrição, sem poder preditivo demonstrado (§1). "Implementado" significa que o código existe e roda, não que o resultado foi validado.

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
| Teste do excesso sobre a deriva (t 1 amostra unicaudal; usado por otimizador, episódios e walk-forward) | Implementado | `models/teste_excesso.py` |
| Estratégias div capture (janela flexível, compra fixa, vende-recompra, spread) | Implementado | `models/div_capture.py` |
| Event study CVM (CAR, NW HAC, block bootstrap placebo) | Implementado | `models/event_study_cvm.py` |
| CDI sensitivity (regressão OLS+HAC, batch) | Implementado | `models/cdi_sensitivity.py` |
| CDI comparison [PESQUISA] | Implementado | `models/cdi_comparison.py` |
| CDI OOS evaluation [PESQUISA] | Implementado | `models/cdi_oos_evaluation.py` |

### Decision

| Componente | Status | Arquivo |
|---|---|---|
| Motor de decisões descritivo (sem veto por flag; COMPRAR/VENDER só com sinal com suporte; linha `EVIDENCIA_JSON`) | Implementado | `decision/recommender.py` |
| Constante de evidência do estudo em painel | Implementado | `decision/evidencia.py` |
| Validação de posição de carteira | Implementado | `decision/carteira_validacao.py` |
| CDI Focus Explainer (informativo) | Implementado | `decision/cdi_focus_explainer.py` |
| Detecção de oportunidades abertas (data-com estimada em pregão, nunca no passado) | Implementado | `decision/abertos.py` |
| Conselhos de carteira (HOLD/AUMENTAR/REDUZIR; alerta de risco descritivo; export MD/CSV) | Implementado | `decision/portfolio_advisor.py` |
| Pares de rotação descritivos | Implementado | `decision/opportunities.py` |
| DailyCommandCenter (agregação + relatório) | Implementado | `decision/daily_report.py` |
| Trava de significância dos sinais (n ≥ 30, p ajustado por Benjamini-Hochberg < 0,05; ADR-30) | Implementado | `decision/suporte.py`, `models/teste_excesso.py` |
| Elegibilidade de compra (liquidação/encerramento, preço defasado, 5 pregões seguidos com volume 0) | Implementado | `decision/elegibilidade.py` |
| `liquidez_intermitente` (≥ 4 pregões com volume 0 em 10) | Implementado como função, **não ligada** à decisão | `decision/elegibilidade.py` |

### Evaluation

| Componente | Status | Arquivo |
|---|---|---|
| Relatório técnico (reporter) | Implementado | `evaluation/reporter.py` |
| Render panorama (rich.Table) | Implementado | `evaluation/panorama.py` |
| Alertas diários (Markdown + terminal) | Implementado | `evaluation/alertas.py` |
| Relatório diário (MD+CSV, 5 seções; sinais exportados sem o rótulo "(info)") | Implementado | `evaluation/daily_report.py` |
| Snapshots diários (7 tabelas desnormalizadas) | Implementado | `evaluation/daily_snapshots.py` |
| Render radar (matriz booleana) | Implementado | `evaluation/radar.py` |
| Diff de snapshots (rótulo "desde ontem" conferido pelo calendário B3) | Implementado | `evaluation/daily_diff.py` |

### Interfaces

| Componente | Status | Arquivo |
|---|---|---|
| CLI Typer (14 comandos) | Implementado | `cli.py` |
| Configuração Python (tickers, períodos) | Implementado | `config.py` |
| Configuração YAML (thresholds runtime) | Implementado | `config_yaml.py` |
| MCP Server (4 tools) | Implementado | `mcp_server/server.py` |
| Streamlit Dashboard (15 arquivos de página, 9 na sidebar + Início) | Implementado | `app/streamlit_app.py` + `app/pages/` |
| Aviso fixo de evidência e rótulos descritivos | Implementado | `app/components/aviso_ui.py` |
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
| `_check_db_state.py` | Debug | Inspeção ad-hoc do banco: lista tabelas, conta linhas de `universo`/`snapshot_opportunities`/`llm_journal`/`decisoes_log`, resumo de preços/relatórios e últimos `snapshot_runs` |
| `load_ifix_universe.py` | Operacional | Carga inicial do universo IFIX (B3 + CVM + yfinance) |
| `run_tests.ps1` | Operacional | [PowerShell] Executa a suíte de testes com cobertura |

### Volume de dados

> **Medido em 2026-04-16 e não remedido desde então** (sem acesso a shell na revisão de 2026-11-12). Ver "Volume de dados" em `docs/STATUS_ATUAL.md` para a medição mais recente (2026-06-11, também defasada). Não usar estes números como estado atual.

| Tabela | Registros (2026-04-16) |
|---|---|
| `tickers` | 6 ativos + 1 inativo (SNFF11) |
| `precos_diarios` | 8.184 (6+ tickers, SNFF11 preservado) |
| `dividendos` | 355 |
| `relatorios_mensais` | 227 |

### Status Geral

- **O sistema é descritivo** (ADR-31). O código de ingestão, features, snapshots, CLI e telas está implementado; a camada de "sinal" (otimizador, episódios, walk-forward, trava de significância) existe como instrumento de pesquisa e hoje não produz nenhuma ação: no último snapshot informado (run 41, 2026-11-13) as 26 decisões são AGUARDAR e as 23 posições são HOLD, 10 delas com alerta de risco. Estado detalhado e pendências: `docs/STATUS_ATUAL.md`.
- Separação: ingestão (`data`), features (`features`), pesquisa estatística (`models`), decisão descritiva (`decision`), cache de snapshots (`evaluation/daily_snapshots`), visualização (`app`, `evaluation`).
- CLI com **14 comandos** (§6.1). **15 arquivos de página** Streamlit com error boundary global; 9 na sidebar.
- Snapshots diários: 7 tabelas desnormalizadas, versionamento por motor, hash de universo/carteira.
- Camada CDI V1 informativa (não altera `_derivar_acao()`); CDI V2 (resíduo como sinal) testada e **rejeitada** em OOS (ADR-22).
- Benchmark XFIX11 substituiu IFIX/^IFIX.SA (inválidos no yfinance).

---

## 9. Próximos Passos

Recomendação do estudo em painel (`docs/pesquisa/painel_2026-11/`). Nada abaixo está implementado.

1. **Um único teste pré-registrado de `dvp6`** (variação % do VP/cota em 6 meses; único candidato, p BH = 0,38), em dados novos, com hipótese, direção, horizonte (6m) e critério de sobrevivência escritos antes de olhar os retornos. Mais de um teste volta a diluir o poder (o estudo teve 100).
2. **Ampliar o histórico de dividendos e informes (2016–2021):** a cobertura de dividendos só começa em 2022-03/04, o que limita a amostra a ~4,5 anos e a 3,6 períodos independentes em 12 meses.
3. **Universo livre de viés de sobrevivência:** o painel usa o IFIX de uma data; incluir fundos que saíram do índice, foram liquidados ou incorporados.
4. **Data de anúncio de dividendos:** necessária para eliminar o possível look-ahead residual do DY Gap (§4.4).

Pendências de implementação e de dados (bugs, cobertura, calibração): `docs/STATUS_ATUAL.md`, "Pendentes conhecidos".

Opcional, só descritivo (sem efeito em decisão): vacância/ABL e cap rate real a partir de `inf_mensal_fii_imovel.csv`; WALT; indexadores de FIIs de Papel. Qualquer indicador novo só entra como decisão após teste pré-registrado (ADR-31).

---

## 10. Roadmap

### Prioridade 1 — Testes
- [x] Criar `tests/` com cobertura de features, models, snapshot, e CLI (Fase 0 Concluída).
- [x] Testes de point-in-time, leakage e integridade temporal implementados.

### Prioridade 2 — Relatórios e histórico
- [x] `fii diario` — diff desde última execução (o que mudou) (Fase 4 Concluída).
- [x] Log de decisões de investimento (compra/venda) para backtest futuro vs IFIX (Fase 4 Concluída).
- Relatório mensal Markdown: panorama + alertas + radar + proventos (descritivo).

### Prioridade 3 — Reprodutibilidade
- Implementar snapshots reprodutíveis do `fii_data.db` com hash SHA-256.
- Todo relatório grava o hash do snapshot usado no cabeçalho.

### Prioridade 4 — Limpeza de configuração
- Reconciliar `config.py` (constantes de escopo) e `config.yaml` (parâmetros de decisão).
- Eliminar duplicações.

### Fora do escopo
- ML / LightGBM (nenhum indicador tem evidência; ADR-08, ADR-31).
- Qualquer novo sinal de compra/venda sem teste pré-registrado em dados novos (ADR-31).
- Streamlit/Flask adicionais (dashboard atual é suficiente).
- Multi-usuário, autenticação, notificações push.
- Exportação para IR.
- Adicionar novos FIIs à **lista curada de decisão** automaticamente (o universo IFIX de observação é automatizado — ADR-23).

---

## 11. Registro de Decisões (ADR)

| # | Decisão | Contexto | Escolha | Motivo |
|---|---|---|---|---|
| ADR-01 | Banco de dados | Projeto solo, sem concorrência | SQLite via SQLAlchemy 2.0 | Arquivo único, backup simples, migração para PostgreSQL = trocar connection string |
| ADR-02 | P/VP e DY como cálculo | Risco de inconsistência com dados históricos | Nunca persistir, sempre calcular | Evita divergência entre preço ajustado retroativo e VP salvo |
| ADR-03 | Point-in-time no VP | VP muda com cada relatório CVM | Filtrar por `Data_Entrega`, não `Data_Referencia` | Elimina lookahead bias — o investidor só conhece o VP após a entrega à CVM |
| ADR-04 | Janela ±10 dias úteis | FIIs pagam dividendos mensalmente | ±10 pregões, não ±30 | Janelas de ±30 se sobrepõem entre dividendos consecutivos; sobreposição viola independência estatística |
| ADR-05 | Radar booleano + Score comunicativo (Fase 2) | Matriz honesta (sem ponderação) + Score 0–100 informativo | Filtros booleanos + Score 4 sub-scores ponderados (não altera decisões) | Booleanos são honestos e testáveis; score é complemento comunicativo que não entra na lógica de decisão. **Parcialmente substituído pelo ADR-31** (2026-11-13): o radar passou a 3 critérios contados (DY Gap alto saiu da contagem, é regime) e radar/score são descritivos, sem evidência de seleção |
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
| ADR-18 | Camada de decisão separada | Sinais estatísticos não eram acionáveis | `decision/recommender.py` com Sinal/Ação/Risco separados | Sinal é estatístico puro; Ação é derivada com veto; Risco é independente. Concordância heurística, nunca IC. **Parcialmente substituído pelo ADR-31:** a separação Sinal/Ação/Risco continua, mas a Ação não tem mais veto por flag de risco (a flag virou alerta descritivo) e só sai de sinal com suporte estatístico |
| ADR-19 | CLI `consulta` com Gemini | Indicadores locais não cobriam análise qualitativa | Integração Gemini + Google Search | 4 seções: contexto, fundamentos, riscos, veredito. Não substitui análise local, complementa |
| ADR-20 | Governança de documentação | Múltiplas IAs com configs duplicadas e dessincronizadas | SSOT em `docs/PROJETO.md` + thin wrappers por IA | Elimina ~950 linhas de duplicação; drift impossível; nova IA = novo wrapper de 15 linhas |
| ADR-21 | Benchmark XFIX11 | ^IFIX e IFIX11.SA inválidos no yfinance (404/delisted) | `XFIX11` via yfinance (period=max) | ETF que replica IFIX; histórico completo disponível; substitui ^IFIX para beta e momentum |
| ADR-22 | CDI V2 rejeitada | Hipótese: resíduo CDI-ajustado melhor que P/VP bruto | Manter P/VP bruto + CDI V1 informativo | Resíduo piora em OOS (2 piora, 1 empata, 1 não-confiável); CDI é parte do sinal, não ruído |
| ADR-23 | Universo dual | Necessidade de observar mercado sem automatizar carteira | Carteira curada (decisão) + IFIX (observação) | Mantém controle e robustez na carteira, enquanto radar e rotação ganham cross-section. **Reinterpretado pelo ADR-31:** "decisão" não significa mais sinal confiável; as telas exibem por padrão o universo único carteira ∪ curados (26) e o IFIX é opção (§7) |
| ADR-24 | LLM via gateway n8n | Integrar análise qualitativa sem contaminar a decisão | Webhook n8n com fallback local para prompt pack | LLM nunca altera Ação final; secrets ficam fora do repositório; permite troca fácil de modelo |
| ADR-25 | Motor de rotação relativa | Responder o que comprar e vender com honestidade estatística | Motor intra-segmento DESCRITIVO (filtros + custos + persistência + cooldown). Lado COMPRAR consome métricas/radar do snapshot; lado VENDER consome decisões da carteira | Sem backtest point-in-time válido, o motor é rotulado DESCRITIVO. `opportunities_backtest.py` é [PESQUISA] — usa decisões de hoje sobre datas passadas e violaria §4.1 se exibido como validação. Silêncio é resultado válido. **Reafirmado pelo ADR-31:** a página virou "Pares de Rotação"; candidato = liquidez OK, elegível, CVM não defasada e percentil de P/VP ≤ 30; destruição de capital não exclui (alerta descritivo); 0 pares no run 41 |
| ADR-27 | Turnaround não é vetado | Veto absoluto por destruição de capital bloqueava compra na baixa | Saúde graduada (saudável/em_recuperação/alerta/crítica): "em recuperação" não veta — vira candidato TURNAROUND com rótulo explícito de risco | Quando o VP volta a subir após destruição passada, o mercado pode já ter precificado o pior; o investidor decide com o risco exposto, não às cegas. **Superseded pelo ADR-31:** nenhum veto por flag de risco existe mais (nem o absoluto, nem o graduado); o rótulo TURNAROUND e a saúde graduada permanecem como descrição |
| ADR-28 | Trava de significância e elegibilidade | Sinais com poucos eventos independentes votavam igual aos demais; fundos em liquidação/sem preço recente podiam receber COMPRAR | Sinal só vota com n independente fora da amostra ≥ 30 e p corrigido < 0,05 (`decisao.*` no `config.yaml`); sinal sem suporte é gravado e exibido como `(info)`. Fundo com liquidação/encerramento vigente ou preço defasado > 5 pregões não recebe COMPRAR/AUMENTAR nem entra como candidato de rotação | Coerente com o princípio "nenhuma hipótese não validada é input de decisão" (§1): o silêncio (AGUARDAR) é resultado válido; a posição existente continua listada. **Parcialmente substituído pelo ADR-30** (2026-11-12): o critério "p corrigido" e o teste contra zero aqui descritos foram trocados; a elegibilidade (liquidação, preço defasado) segue vigente e ganhou o bloqueio por volume 0 (§4.2) |
| ADR-29 | Base única de cotas e `fechamento_aj` próprio | Splits e dividendos duplicados distorciam P/VP e DY; o Adj Close do Yahoo muda retroativamente | Preço, dividendo e VP/cota na base da quantidade atual de cotas (splits detectados pela CVM); `fechamento_aj` reconstruído como retorno total a partir de `fechamento` + `dividendos` (§4.9) | Reprodutível e auditável com dados do próprio banco; recalculável por inteiro a cada carga |
| ADR-26 | Diário de Decisões e Review Ex-Post | Necessidade de fechar ciclo de aprendizado do investidor | Comparador de Snapshots (Daily Diff) + decisoes_log no SQLite + ex-post review vs XFIX11 | Permite ao investidor avaliar se suas decisões reais bateram o mercado, medindo custo de oportunidade de sugestões ignoradas e hit-rate real das recomendações. |
| ADR-30 | Trava de significância redesenhada (substitui o critério de significância do ADR-28) | O teste anterior comparava o retorno após o sinal com zero (a deriva positiva do ativo contava como evidência) e corrigia o p multiplicando pelo tamanho do grid / nº de testes (Bonferroni; ×256 no otimizador, segundo o registro anterior) | H0 única para os três sinais: retorno forward de 20 pregões após o sinal = retorno forward incondicional do mesmo ativo no mesmo período. Estatística: t de 1 amostra do excesso (retorno do evento thinned − deriva), unicaudal na direção do sinal, sobre eventos independentes (`models/teste_excesso.py`). O p de holdout do otimizador não é multiplicado pelo grid. Correção de múltiplos testes por Benjamini-Hochberg (`decisao.fdr_q` = 0,05) sobre a família de todos os sinais BUY/SELL ativos da rodada (`decidir_universo`; chamada avulsa: família do ticker). n mínimo de 30 eventos independentes mantido. Chaves `testes_episodio`/`testes_walkforward`/`suporte_p_max` removidas | Um ativo que sobe em média passaria no teste contra zero sem qualquer poder preditivo do sinal; o excesso sobre a deriva mede o que o sinal acrescenta. BH controla a taxa de falsas descobertas sobre o conjunto realmente testado, em vez de um multiplicador arbitrário. Limitações assumidas (deriva tratada como constante, BH assume independência/dependência positiva, n ≥ 30 não atingível pelo desenho atual) ficam em STATUS_ATUAL, "Pendentes conhecidos" |
| ADR-31 | Sistema descritivo: nenhuma ação derivada de indicador sem evidência (2026-11-13) | Estudo em painel pré-registrado (110 fundos, 55 datas mensais 2022-04 a 2026-10, horizontes 1/3/6/12m, excesso ao universo equal-weight, Fama-MacBeth + quintis, 100 testes, BH 5%): zero sobreviventes; nenhum indicador (P/VP pct próprio e vs pares, episódios BUY/SELL, DY, DY Gap, score, saúde, momentum, alavancagem, contagem do radar) prevê qual fundo rende mais. Candidato não confirmado: `dvp6` (p BH 0,38). Limites: ~4,5 anos, 3,6 períodos independentes em 12m, universo IFIX de uma data, dividendos desde 2022-03/04 | (1) O sistema é descritivo. COMPRAR/VENDER (e AUMENTAR/REDUZIR) só com sinal estatisticamente suportado pela trava do ADR-30; hoje nenhum. (2) Flag de destruição de capital = "ALERTA DE RISCO (descritivo)", sem veto, badge HOLD; SAIR e EVITAR_NOVOS_APORTES e a ação EVITAR não são mais gerados. (3) Radar = 3 critérios; DY Gap alto é regime. (4) Pares de rotação: candidato = liquidez OK ∧ elegível ∧ percentil P/VP ≤ 30, descritivo. (5) `INICIO_RETORNO_TOTAL` limita os retornos forward; DY só conta dividendo com `data_com < t`. (6) Toda decisão grava `EVIDENCIA_JSON` e toda tela de decisão mostra o aviso de evidência (`app/components/aviso_ui.py`) | Afirmar previsão sem evidência é pior que silêncio; o investidor precisa ver o que o dado sustenta. O estudo tem pouco poder, então a decisão é "não afirmar", não "provado que não funciona". **O que mudaria esta decisão:** replicação pré-registrada de `dvp6` em dados novos (um teste, 6m); dados 2016–2021 (dividendos e informes); universo sem viés de sobrevivência; data de anúncio de dividendos (elimina look-ahead residual do DY Gap). Substitui parcialmente ADR-05, ADR-18, ADR-27; reinterpreta ADR-23; reafirma ADR-25, ADR-28 e ADR-30 |

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