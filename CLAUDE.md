# CLAUDE.md — Regras do Projeto FII

Este arquivo é lido automaticamente por qualquer IA que trabalhe neste projeto.
**Não ignore estas regras. Elas existem por razões específicas documentadas abaixo.**

---

## O que é este projeto

Análise estatística de FIIs (Fundos de Investimento Imobiliário brasileiros) para identificar
padrões de comportamento de preço ao redor da data-com de dividendos.
Objetivo: apoiar decisões de investimento pessoal.

Documentação completa: `docs/PROJETO.md`

---

## Regras inegociáveis

### 1. NUNCA misture períodos de treino, validação e teste

O projeto anterior chegou a 96% de acurácia falsa por violar esta regra.
Separação obrigatória e sempre nesta ordem cronológica:

```
|--- Treino ---|--- gap ---|--- Validação ---|--- gap ---|--- Teste ---|
```

- Sem shuffle em nenhuma etapa
- Gap mínimo entre períodos: 10 dias úteis
- Métricas finais SOMENTE do conjunto de teste
- Nunca use dados futuros para calcular features do passado

### 2. P/VP e DY são CALCULADOS, nunca armazenados

```python
# ERRADO — nunca fazer isso
relatorio.pvp = preco / vp  # salvar no banco

# CERTO — calcular sempre na hora com dados históricos corretos
pvp_em_t = preco_em_t / vp_vigente_em_t(data_entrega <= t)
```

### 3. Point-in-time obrigatório no VP

O VP por cota vem dos Informes Mensais da CVM. Cada relatório tem duas datas:
- `Data_Referencia` — mês do relatório (NÃO usar para filtro)
- `Data_Entrega` — quando foi entregue à CVM (USAR para filtro)

```python
# CERTO: VP disponível na data t
vp = SELECT Valor_Patrimonial_Cotas
     FROM relatorios_mensais
     WHERE cnpj = X AND data_entrega <= t
     ORDER BY data_referencia DESC LIMIT 1

# ERRADO: usa VP que ainda não era público
vp = SELECT Valor_Patrimonial_Cotas
     WHERE data_referencia <= t  # ERRADO
```

### 4. Janela da data-com: ±10 dias úteis

Janelas maiores (ex: ±30 dias) se sobrepõem porque FIIs pagam mensalmente.
Sobreposição viola independência estatística do event study.

```python
JANELA_ANTES = 10  # dias úteis antes da data-com
JANELA_DEPOIS = 10  # dias úteis depois da data-com
```

### 5. Nunca sobrescreva dados históricos sem verificar

Antes de coletar dados, verificar se já existem no banco:

```python
# SEMPRE verificar antes de coletar
ultimo_registro = SELECT MAX(data) FROM precos_diarios WHERE ticker = X
if ultimo_registro:
    coletar_apenas_a_partir_de(ultimo_registro + 1 dia)
else:
    coletar_historico_completo()
```

O preço ajustado do yfinance é recalculado retroativamente. Salvar sempre `coletado_em` (timestamp).

### 6. Token brapi nunca fica no projeto

### 7. Scripts são wrappers finos — lógica de negócio fica em `src/`

```
# ERRADO — lógica de cálculo dentro de scripts/
scripts/analise_janela.py:
    def calcular_ciclos(ticker, session):  # ← lógica de negócio aqui
        ...
    def main():
        calcular_ciclos(...)

# CERTO — scripts só orquestram e imprimem
scripts/analise_janela.py:
    from src.fii_analysis.models.div_capture import analisar_janela_flexivel  # ← importa de src/
    def imprimir_resultado(ciclos): ...    # ← só formatação CLI
    def main():
        ciclos = analisar_janela_flexivel(...)
        imprimir_resultado(ciclos)
```

**Por quê:** a `app/` (Streamlit) não consegue importar de `scripts/`. Se a lógica está
em `scripts/`, ela fica inacessível para a interface gráfica e gera duplicação inevitável.
Qualquer função que possa ser útil na UI deve nascer em `src/`.

**Regra de ouro para novos arquivos:**
- `src/fii_analysis/` → funções puras, retornam dados, zero `print()`, zero Streamlit
- `scripts/` → `main()` + funções de formatação/impressão CLI, importa tudo de `src/`
- `app/` → widgets Streamlit, importa tudo de `src/`, zero lógica de cálculo
- `app/components/` → helpers de UI (cache `@st.cache_data`, CRUD de formulários)

```python
# CERTO
from dotenv import load_dotenv
load_dotenv(r"C:\Modelos-AI\Brapi\.env")
token = os.getenv("BRAPI_API_KEY")

# CERTO — nunca hardcodar ou criar .env dentro do projeto
token = "abc123..."
```

### 8. Separação entre Estatística e Simulação Operacional

Cálculos de inferência (p-values, CAR, thinning) devem ser feitos sobre o retorno forward bruto (fixo em $H$ dias). A performance de backtest deve ser calculada em uma camada separada (`trade_simulator.py`) que gerencia caixa, rendimento CDI de capital ocioso e crédito de dividendos (D+1 proxy).

**Por quê:** O sinal estatístico mede a anomalia de preço; a simulação mede o resultado financeiro factível. Misturar CDI ou dividendos na base de teste polui a validação da hipótese pura com variáveis de custo de oportunidade e liquidez.

---

## Fontes de dados e responsabilidades

| Dado | Fonte | Observação |
|---|---|---|
| Preços históricos OHLCV | yfinance (`TICKER.SA`) | Carga inicial única |
| Data-com de dividendos | yfinance | CVM NÃO tem esta informação |
| VP por cota histórico | CVM dados abertos | Usar `Data_Entrega` para point-in-time |
| PL, cotas, DY%, rentabilidade | CVM dados abertos | Arquivos `complemento` dos ZIPs |
| Dados cadastrais (segmento, etc.) | CVM dados abertos | Arquivos `geral` dos ZIPs |
| Atualização diária de preços | brapi.dev | 15.000 req/mês gratuitos |
| Benchmark (IFIX) | brapi.dev | Verificar endpoint antes de implementar |

### URLs da CVM (confirmadas e testadas)
```
https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2023.zip
https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2024.zip
https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2025.zip
https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2026.zip
```

### Campos reais confirmados nos arquivos CVM
- `complemento`: `Valor_Patrimonial_Cotas`, `Patrimonio_Liquido`, `Cotas_Emitidas`,
  `Percentual_Dividend_Yield_Mes`, `Percentual_Rentabilidade_Efetiva_Mes`,
  `Percentual_Rentabilidade_Patrimonial_Mes`
- `geral`: `Nome_Fundo_Classe`, `Segmento_Atuacao`, `Mandato`, `Tipo_Gestao`,
  `Codigo_ISIN`, `Data_Entrega`, `Data_Funcionamento`, `CNPJ_Fundo_Classe`
- Separador: `;` | Encoding: `latin1`

---

## FIIs monitorados

**Ativos** (em `src/fii_analysis/config.py`, `TICKERS`):

| Ticker | Segmento | Histórico desde |
|---|---|---|
| KNIP11 | Papel (CRI) — **canário de validação** | 2017-10 |
| CPTS11 | Papel | 2015-09 |
| HSRE11 | Tijolo | 2020-12 |
| CPSH11 | Híbrido | 2023-07 |
| GARE11 | Tijolo | 2024-03 |
| SNEL11 | Energia | 2023-12 |

**Inativos** (preservar histórico, marcar `inativo_em` em `tickers`, excluir de panorama/radar/alertas):

| Ticker | CNPJ | Motivo |
|---|---|---|
| SNFF11 | 40.011.225/0001-68 | Liquidação/descontinuação |

KNIP11 substituiu SNFF11 como FII canário de validação cruzada (`scripts/validate_knip11.py` contra FundsExplorer). Lista pequena, escolhida a dedo — não automatizar adição.

---

## Banco de dados

- **Tecnologia:** SQLite via SQLAlchemy
- **Arquivo:** `dados/fii_data.db`
- **ORM:** SQLAlchemy 2.0+ (preparado para migrar para PostgreSQL — só trocar a connection string)
- **Não usar Parquet** — decidido manter somente SQLite para este escopo

---

## Estrutura de pastas

```
D:/analise-de-acoes-v2/
├── CLAUDE.md
├── config.yaml                ← thresholds, janelas, fontes (defaults runtime)
├── pyproject.toml
├── dados/
│   ├── cvm/raw/               ← ZIPs da CVM (.gitignored)
│   ├── alertas/               ← Markdown diário gerado por evaluation/alertas.py
│   ├── cache/                 ← cache JSON (Focus BCB, optimizer_cache, etc)
│   └── fii_data.db            ← banco SQLite (.gitignored)
├── src/fii_analysis/
│   ├── config.py              ← TICKERS, períodos treino/teste, custos, IR
│   ├── config_yaml.py         ← loader do config.yaml
│   ├── cli.py                 ← typer: panorama, fii, carteira, calendario, radar, alertas
│   ├── data/
│   │   ├── database.py        ← SQLAlchemy 2.0: ORM 15 tabelas (9 operacionais + 6 snapshot),
│   │   │                        get_session_ctx, migrations
│   │   ├── ingestion.py       ← CVM, yfinance, brapi, BCB SGS (CDI)
│   │   ├── cdi.py             ← get_cdi_acumulado_12m(t, session)
│   │   ├── focus_bcb.py       ← fetch_focus_selic() — expectativas Selic 3/6/12m
│   │   └── migrations.py      ← SQLAlchemy migrations (Alembic)
│   ├── features/
│   │   ├── dividend_window.py ← janela ±10 dias úteis (event study)
│   │   ├── indicators.py      ← P/VP, DY trailing (point-in-time)
│   │   ├── valuation.py       ← percentil rolling, DY N-meses, DY Gap
│   │   ├── portfolio.py       ← panorama, alocação, retorno vs IFIX, Herfindahl
│   │   ├── saude.py           ← tendência PL, flag destruição capital, emissões
│   │   ├── fundamentos.py     ← rentabilidade efetiva/patrimonial, alavancagem
│   │   ├── composicao.py      ← classificação Tijolo/Papel/Híbrido
│   │   ├── radar.py           ← matriz booleana
│   │   ├── risk_metrics.py    ← volatilidade, VaR, drawdown históricos
│   │   ├── score.py           ← score composto 0–100 (4 sub-scores: Valuation/Risco/Liquidez/Histórico)
│   │   └── data_loader.py     ← agregadores de dados para CLI e UI
│   ├── models/
│   │   ├── statistical.py     ← event study CAR/BHAR, t-test, Mann-Whitney
│   │   ├── walk_forward.py    ← splits temporais com gap + validação leakage
│   │   ├── walk_forward_rolling.py ← validação out-of-sample deslizante (thinned)
│   │   ├── episodes.py        ← episódios discretos de P/VP extremo (thinned)
│   │   ├── critic.py          ← CriticAgent: shuffle/placebo/estabilidade
│   │   ├── strategy.py        ← simulação dividend capture, grid search
│   │   ├── trade_simulator.py ← motor puro de backtest (caixa/CDI, dividendos, preço bruto)
│   │   ├── div_capture.py     ← estratégias captura dividendo (janela flexível, etc)
│   │   ├── threshold_optimizer_v2.py ← otimizador com métricas de robustez
│   │   ├── event_study_cvm.py ← event study CVM: CAR, NW HAC, block bootstrap
│   │   ├── cdi_sensitivity.py ← diagnóstico regressão P/VP ~ CDI 12m (V1 informativa)
│   │   ├── cdi_comparison.py  ← [PESQUISA] Fase 2 V2 CDI: resíduo vs P/VP bruto
│   │   └── cdi_oos_evaluation.py ← [PESQUISA] Teste OOS comparativo
│   ├── decision/
│   │   ├── recommender.py     ← motor de decisão: TickerDecision (Sinal/Ação/Risco separados)
│   │   ├── portfolio_advisor.py ← HoldingAdvice, cruzamento decisões × carteira
│   │   ├── abertos.py         ← detectores de oportunidades abertas (episódios/janelas)
│   │   ├── cdi_focus_explainer.py ← camada explicação CDI + Focus (informativa)
│   │   └── daily_report.py    ← geração relatório diário acionável Markdown/CSV
│   ├── evaluation/
│   │   ├── reporter.py        ← relatório técnico (somente dados de teste)
│   │   ├── panorama.py        ← rich.Table: render carteira/calendário
│   │   ├── alertas.py         ← geração alertas diários legados (4 flags)
│   │   ├── daily_snapshots.py ← geração/leitura snapshots diários (6 tabelas)
│   │   └── radar.py           ← render matriz booleana
│   └── mcp_server/server.py   ← MCP: validate_split, detect_leakage, check_window_overlap
├── app/
│   ├── streamlit_app.py       ← entry point Streamlit com st.navigation e agrupamento sidebar
│   ├── state.py               ← error boundary global (@safe_page decorator)
│   ├── components/
│   │   ├── page_content/      ← módulos reutilizáveis por Dossie/Laboratório + wrappers
│   │   │   ├── analise_fii.py ← render(ticker) — análise por FII
│   │   │   ├── fundamentos.py ← render(ticker) — DY, P/VP, PL, distribuição
│   │   │   ├── fund_eventstudy.py ← render() — eventos discretos CVM
│   │   │   ├── otimizador_v2.py ← render() — backtest com thresholds
│   │   │   ├── episodios.py   ← render() — episódios thinned
│   │   │   └── walkforward.py ← render() — validação deslizante
│   │   ├── carteira_ui.py     ← cache Streamlit + CRUD carteira
│   │   ├── charts.py          ← gráficos Plotly reutilizáveis
│   │   ├── tables.py          ← formatadores tabelas Rich/Streamlit
│   │   ├── snapshot_ui.py     ← leitura snapshots diários com cache
│   │   └── ui_shell.py        ← helpers de UI (headers, notes, sidebar)
│   └── pages/                 ← 14 páginas Streamlit (8 na sidebar + 6 legacy)
│       ├── 1_Panorama.py      ← métricas gerais (Diário)
│       ├── 3_Carteira.py      ← CRUD, sugestões operacionais, alertas estruturais (Diário)
│       ├── 4_Radar.py         ← heatmap booleano (Diário)
│       ├── 5_Event_Study.py   ← event study agregado (Investigação)
│       ├── 6_Alertas.py       ← geração alertas sob demanda (Investigação)
│       ├── 13_Hoje.py         ← cockpit operacional com snapshots (Diário)
│       ├── 14_Dossie_FII.py   ← consolidado: Análise/Fundamentos/Eventos por ticker (Investigação)
│       ├── 15_Laboratorio.py  ← auditoria: Otimizador/Episódios/WalkForward (Técnico)
│       ├── 2_Analise_FII.py   ← wrapper standalone → page_content/analise_fii.render(ticker)
│       ├── 7_Fundamentos.py   ← wrapper standalone → page_content/fundamentos.render(ticker)
│       ├── 8_Fund_EventStudy.py ← wrapper standalone → page_content/fund_eventstudy.render()
│       ├── 10_Otimizador_V2.py ← wrapper standalone → page_content/otimizador_v2.render()
│       ├── 11_Episodios.py    ← wrapper standalone → page_content/episodios.render()
│       └── 12_WalkForward.py  ← wrapper standalone → page_content/walkforward.render()
├── scripts/                   ← wrappers CLI finos: main() + impressão, sem lógica
│   ├── load_database.py       ← download ZIPs CVM + carga yfinance
│   ├── run_strategy.py        ← pipeline completo
│   ├── run_event_study.py     ← event study universo + CriticAgent
│   ├── run_event_study_car_ajustado.py ← CAR com ajuste mecânico
│   ├── plot_car.py, plot_car_adjusted.py ← gráficos CAR (PNG)
│   ├── validate_knip11.py     ← validação cruzada vs FundsExplorer
│   ├── check_prices.py        ← inspeção de preços (debug)
│   ├── analise_janela_flexivel.py, analise_janela_v2.py, analise_spread_recompra.py ← wrappers
│   ├── scrape_fundsexplorer.py ← scraping FundsExplorer
│   ├── daily_report.py        ← CLI relatório diário (decisões)
│   ├── generate_daily_snapshots.py ← CLI geração snapshots
│   ├── test_recommender.py    ← sanity check motor decisão
│   ├── compare_cvm_headers.py ← debug headers CVM
│   ├── _patch_database.py     ← patch ad-hoc banco
│   └── _aceite_v3_cdi.py      ← [PESQUISA] teste aceite V3 CDI
├── financial-advisor/         ← Multi-agent ADK (Vertex AI): data, trading, execution, risk
├── .claude/agents/            ← 9 agentes Claude Code
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
    ├── PROJETO.md
    ├── STATUS_ATUAL.md        ← estado factual (regenerar quando mudar)
    ├── UX_AUDIT.md            ← auditoria UX: 43 problemas (P0-P4)
    └── BETA_TESTER_REPORT.md  ← relatório beta trader
```

**Dois pontos de configuração** (dívida técnica conhecida):
- `config.py` (Python) — universo de tickers, períodos do event study
- `config.yaml` (runtime) — pisos, janelas, fontes — carregado por `config_yaml.py`

Reconciliar em algum momento. Por enquanto: parâmetros de **decisão** vão no YAML; constantes de **escopo** ficam no `.py`.

---

## MCPs e agentes disponíveis

### MCP Server
| Componente | Status | Ferramentas |
|---|---|---|
| MCP Estatístico (`mcp_server/server.py`) | Implementado | `validate_split`, `detect_leakage`, `check_window_overlap`, `summary_report` |

### Agentes Claude Code (`.claude/agents/`)
| Agente | Especialização | Modelo |
|---|---|---|
| `data-scientist.md` | Regras estatísticas: split temporal, leakage, testes | haiku |
| `python-pro.md` | Implementação Python: SQLAlchemy, pandas, lógica pura | haiku |
| `streamlit-developer.md` | Páginas Streamlit e componentes de visualização | haiku |
| `documentation-engineer.md` | Atualização CLAUDE.md, STATUS_ATUAL.md, docs | haiku |
| `ux-researcher.md` | Pesquisa UX: síntese de feedback em ações | sonnet |
| `beta-tester-trader.md` | Teste beta: perspectiva de trader B&H real | sonnet |
| `release-manager.md` | Coordenação de releases e versionamento | haiku |
| `qa-operator.md` | Testes de aceite e auditoria | haiku |
| `onboarding-writer.md` | Documentação para novos usuários | haiku |

### Componentes Internos
| Componente | Status | Função |
|---|---|---|
| CriticAgent (`models/critic.py`) | Implementado | Falsificação estatística: shuffle/placebo/estabilidade |

---

## Análises adicionais identificadas nos dados CVM

### Saúde financeira do fundo (arquivo complemento)
Além da janela de data-com, o arquivo `complemento` permite análises críticas:

**Destruição de capital:**
```
PL(mês t) vs PL(mês t-1) após pagamento de dividendo
→ PL crescendo: fundo gerando renda real
→ PL estável: dividendo sustentável
→ PL caindo consistentemente: fundo devolvendo capital (sinal de alerta)
```

Campos usados: `Patrimonio_Liquido`, `Cotas_Emitidas`, `Valor_Patrimonial_Cotas`,
`Percentual_Rentabilidade_Efetiva_Mes`, `Percentual_Rentabilidade_Patrimonial_Mes`

**Relação rentabilidade efetiva vs patrimonial:**
- `Rentabilidade_Efetiva` > `Rentabilidade_Patrimonial` → pode estar distribuindo mais do que ganha
- Divergência persistente = sinal de alerta de destruição de capital

### Composição do ativo (arquivo ativo_passivo)
Determina o perfil de risco e comportamento do fundo:

| Composição | Tipo de FII | Comportamento |
|---|---|---|
| > 60% imóveis físicos | Tijolo | Menos volátil, renda de aluguel |
| > 60% CRI/LCI | Papel | Mais volátil, sensível a juros |
| Misto | Híbrido | Intermediário |

Campos relevantes: `Direitos_Bens_Imoveis`, `CRI`, `LCI`, `LCI_LCA`, `Disponibilidades`

**Status**: Saúde financeira e Composição foram implementadas (Fases 1–5).
Disponíveis em `src/fii_analysis/features/saude.py` e `composicao.py`, renderizadas em páginas de análise.

---

## Estado atual e próximos passos

**Concluído** (até 2026-05-03):
- **Fases 0–5 Estatísticas + Camada de Decisão (Fases 1–4) + Score (Fase 2)**: Schema SQLite 15 tabelas (9 operacionais + 6 snapshot), ingestão CVM/yfinance/brapi/BCB CDI/Focus Selic, indicadores point-in-time, Event Study, Saúde financeira, Composição, Risk metrics, Score 0–100.
- **Refatoração Arquitetural**: Singleton engine + context manager (`get_session_ctx`), separação `src/` (lógica pura) / `scripts/` (wrappers CLI) / `app/` (UI Streamlit). Remoção de duplicatas, centralização thresholds em `config.yaml`.
- **MCP Server Estatístico** e **CriticAgent** (falsificação shuffle/placebo/estabilidade).
- **Otimizador V2** (`models/threshold_optimizer_v2.py`): sinais diários P/VP + DY Gap + meses_alerta, NW HAC df-efetivos (n/h), block bootstrap bicaudal BUY, placebo SELL, Bonferroni ×36, grid 3×3×2×2, métricas robustez (Sharpe/Sortino, diagnóstico overfitting).
- **Novos Modelos Robustos**: `episodes.py` (episódios discretos thinned), `walk_forward_rolling.py` (validação deslizante genuína OOS), `trade_simulator.py` (motor backtest puro: caixa/CDI/dividendos/preço bruto).
- **Camada de Decisão** (`src/fii_analysis/decision/`): `recommender.py` (TickerDecision separada: Sinal/Ação/Risco), `portfolio_advisor.py` (HoldingAdvice: HOLD/AUMENTAR/REDUZIR/SAIR/EVITAR), `abertos.py` (episódios/janelas abertas), `daily_report.py` (relatório Markdown/CSV acionável), `cdi_focus_explainer.py` (contexto informativo CDI+Focus, não altera decisão).
- **Snapshots Diários** (`evaluation/daily_snapshots.py`): 6 tabelas desnormalizadas (runs, metrics, radar, decisions, advices, alerts) com versionamento motor e hashing universo.
- **UI Nova**: Páginas 13_Hoje.py (cockpit operacional), 14_Dossie_FII.py (consolidado por ticker), 15_Laboratorio.py (auditoria: Otimizador/Episódios/WalkForward). Extração de conteúdo em `app/components/page_content/*.py` reutilizável.
- **Agentes Claude Code**: 9 agentes em `.claude/agents/` (data-scientist, python-pro, streamlit-developer, documentation-engineer, ux-researcher, beta-tester-trader, release-manager, qa-operator, onboarding-writer).
- **Auditoria UX**: 43 problemas identificados em `docs/UX_AUDIT.md` (P0→P4). Fixes P0 aplicados (error boundary global, consolidação sessões). Fixes P1 concluídos (gráficos valor_mercado, CAR extraído, event study desacoplado). Fixes P2/P3 parciais (st.tabs, radio horizontal, charts eixo data nativo, tabs 7_Fundamentos, footer, dead imports).
- **Auditoria Estatística**: Thinning obrigatório para independência. Anualização Sharpe corrigida `sqrt(252/n)`. Overfitting detectado como SUSPEITO. Block bootstrap validado contra degenerescência.
- **Experimento V2 CDI encerrado**: Teste OOS rejeitou hipótese de substituir sinal por resíduo CDI-ajustado. V1 CDI (informativa) permanece; V2 mantida como pesquisa interna (`cdi_comparison.py`, `cdi_oos_evaluation.py`, `_aceite_v2_cdi.py`).
- **Fase 2 — Score 0–100**: Implementado `src/fii_analysis/features/score.py` com 4 sub-scores (Valuation 35%, Risco 30%, Liquidez 20%, Histórico 15%). Campos adicionados em `SnapshotTickerMetrics` e `SnapshotDecisions`. Integração em `daily_snapshots.py` via `calcular_score_batch()`. Renderizado em UI (pages 13_Hoje, analise_fii, snapshot_ui).
- **Anomalias de Ingestão Investigadas e Corrigidas** (documentadas em `INVESTIGACAO_LOG.md`): (1) Dupla leitura `ativo_passivo` — implementado `keys_to_extract` em `load_cvm_zip()`, usado em `load_cvm_to_db()` e `load_ativo_passivo_to_db()`; (2) Duplicação logger — adicionado `logger.remove()` em `load_database.py` antes de `logger.add()`; (3) CDI 404 abortava backfill — tratamento específico de `HTTPError 404` com `continue` em `load_cdi_to_db()` (linha 380–383).

**Pendente** (em ordem de prioridade):
1. **Cache de `optimizer_params`**: salvar `best_params` por ticker em `dados/optimizer_cache/{ticker}.json` com timestamp; reotimizar semanalmente (melhora utilidade `daily_report.py` sem `--com-otimizador`).
2. **UX P2**: extrair charts inline de `7_Fundamentos.py` → componente reutilizável.
3. **UX P3**: `@st.cache_data` em queries pesadas; IFIX YTD conectar `get_benchmark_ifix()`.
4. Snapshots reprodutíveis do `fii_data.db` com SHA-256 (§5.2 do V2).
5. **Fase 6**: `fii diario` (diff), relatório mensal Markdown/HTML, log de decisões.
6. Reconciliar `config.py` ↔ `config.yaml` (conhecer dívida técnica — parâmetros de decisão vs constantes de escopo).
7. Criar `tests/` com cobertura de integração para splits temporais e leakage.

**Bugs menores conhecidos**:
- `1_Panorama.py`: métrica IFIX YTD hardcoded como `"n/d"` — `get_benchmark_ifix()` existe mas não é chamado (P3).
- Paridade CLI/web no Panorama incompleta — faltam Rent. Acum., DY 24m, Tipo na web.

**Fora do escopo até decisão explícita:**
- LightGBM ou qualquer ML enquanto event study não confirmar padrão
- Multi-usuário, autenticação, notificações push
- Adicionar novos FIIs ao universo (lista curada, não automatizar)

---

## Python — usar sempre o Anaconda

Este projeto tem 3 Pythons instalados na máquina. Usar **sempre o Anaconda**:

```bash
# CORRETO
C:/ProgramData/anaconda3/python.exe script.py

# ERRADO — não tem as dependências
python3 script.py
C:/Users/carlo/AppData/Local/Python/bin/python3.exe script.py
```

O Anaconda está em `C:/ProgramData/anaconda3/` e já tem todas as dependências instaladas.

---

## Stack obrigatória

```toml
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
```
