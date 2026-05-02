# AGENTS.md — Regras do Projeto FII

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

# ERRADO — nunca hardcodar ou criar .env dentro do projeto
token = "abc123..."
```

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
- **15 tabelas**: 9 operacionais + 6 de snapshot diário (desnormalizadas para cache)

---

## Estrutura de pastas

```
D:/analise-de-acoes/
├── AGENTS.md
├── config.yaml                ← thresholds, janelas, fontes (defaults runtime)
├── pyproject.toml
├── dados/
│   ├── cvm/raw/               ← ZIPs da CVM (.gitignored)
│   ├── alertas/               ← Markdown diário gerado por evaluation/alertas.py
│   └── fii_data.db            ← banco SQLite (.gitignored)
├── src/fii_analysis/
│   ├── config.py              ← TICKERS, períodos treino/teste, custos, IR
│   ├── config_yaml.py         ← loader do config.yaml
│   ├── cli.py                 ← typer: panorama, fii, carteira, calendario, radar, alertas, consulta
│   ├── __main__.py            ← entry point para `python -m fii_analysis`
│   ├── data/
│   │   ├── database.py        ← SQLAlchemy 2.0: 15 tabelas (9 operacionais + 6 snapshot)
│   │   │                        Operacionais: tickers, precos_diarios, dividendos,
│   │   │                        relatorios_mensais, ativo_passivo, cdi_diario,
│   │   │                        benchmark_diario, eventos_corporativos, carteira
│   │   │                        Snapshots: snapshot_runs, snapshot_ticker_metrics,
│   │   │                        snapshot_radar, snapshot_decisions,
│   │   │                        snapshot_portfolio_advices, snapshot_structural_alerts
│   │   └── ingestion.py       ← CVM, yfinance, brapi, BCB SGS (CDI)
│   ├── decision/              ← camada de decisão (sinais → recomendações)
│   │   ├── abertos.py          ← detecção de oportunidades abertas
│   │   ├── daily_report.py     ← orquestração de relatório diário
│   │   ├── portfolio_advisor.py ← conselho de carteira
│   │   └── recommender.py      ← motor de decisão central
│   ├── features/
│   │   ├── dividend_window.py ← janela ±10 dias úteis (event study)
│   │   ├── indicators.py      ← P/VP, DY trailing (point-in-time)
│   │   ├── valuation.py       ← percentil rolling, DY N-meses, DY Gap
│   │   ├── portfolio.py       ← panorama, alocação, retorno vs IFIX, Herfindahl
│   │   ├── saude.py           ← tendência PL, flag destruição capital, emissões
│   │   ├── fundamentos.py     ← rentabilidade efetiva/patrimonial, alavancagem, payout
│   │   ├── composicao.py      ← classificação Tijolo/Papel/Híbrido
│   │   ├── data_loader.py     ← agregadores de dados para CLI e páginas Streamlit
│   │   └── radar.py           ← matriz booleana (sem score numérico)
│   ├── models/
│   │   ├── statistical.py     ← event study CAR, t-test, Mann-Whitney
│   │   ├── walk_forward.py    ← splits temporais com gap + validação leakage
│   │   ├── walk_forward_rolling.py ← validação out-of-sample deslizante genuína
│   │   ├── episodes.py        ← episódios discretos de P/VP extremo (thinned)
│   │   ├── critic.py          ← shuffle/placebo/estabilidade (CriticAgent)
│   │   ├── strategy.py        ← simulação dividend capture, otimização, risco
│   │   ├── trade_simulator.py ← motor puro de simulação (caixa/CDI, dividendos, preço bruto)
│   │   ├── div_capture.py     ← estratégias de captura de dividendo (janela flexível,
│   │   │                        compra fixa, vende-recompra, spread-recompra)
│   │   ├── threshold_optimizer.py ← otimizador v1
│   │   ├── threshold_optimizer_v2.py ← otimizador v2 com métricas de robustez
│   │   └── event_study_cvm.py ← event study CVM: CAR, NW HAC, block bootstrap placebo
│   ├── evaluation/
│   │   ├── reporter.py        ← relatório técnico (somente dados de teste)
│   │   ├── panorama.py        ← rich.Table, render carteira/calendário
│   │   ├── alertas.py         ← Markdown diário + terminal
│   │   ├── daily_report.py    ← relatório diário acionável (MD+CSV)
│   │   ├── daily_snapshots.py ← geração/leitura de snapshots diários (6 tabelas)
│   │   └── radar.py           ← render matriz booleana
│   └── mcp_server/server.py   ← MCP: validate_split, detect_leakage, etc
├── app/
│   ├── streamlit_app.py       ← entry point Streamlit
│   ├── state.py               ← session state initializer + @safe_page error boundary
│   ├── components/
│   │   ├── carteira_ui.py     ← cache Streamlit + CRUD carteira (load/save/delete)
│   │   ├── charts.py          ← gráficos Plotly reutilizáveis
│   │   ├── tables.py          ← tabelas Rich/Streamlit reutilizáveis
│   │   └── snapshot_ui.py     ← helpers de UI para leitura de snapshots diários
│   └── pages/                 ← 13 páginas Streamlit (só UI, importam de src/)
├── scripts/                   ← wrappers CLI finos: main() + impressão, sem lógica
│                                download_cvm, load_database, update_prices,
│                                run_strategy, plot_car, validate_knip11,
│                                analise_janela_flexivel, analise_janela_v2,
│                                analise_spread_recompra, generate_daily_snapshots,
│                                daily_report, compare_cvm_headers
└── docs/
    ├── PROJETO.md             ← documentação técnica unificada
    ├── STATUS_ATUAL.md        ← estado factual (regenerar quando mudar)
    ├── UX_AUDIT.md            ← auditoria UX (43 problemas, P0→P4)
    └── BETA_TESTER_REPORT.md  ← relatório de teste beta (persona trader)
```

**Dois pontos de configuração** (dívida técnica conhecida):
- `config.py` (Python) — universo de tickers, períodos do event study
- `config.yaml` (runtime) — pisos, janelas, fontes — carregado por `config_yaml.py`

Reconciliar em algum momento. Por enquanto: parâmetros de **decisão** vão no YAML; constantes de **escopo** ficam no `.py`.

---

## MCPs e agentes disponíveis

| Componente | Status | Uso |
|---|---|---|
| Gemini CLI | Ativo | Revisão de código, pesquisa, segunda opinião |
| Kilocode (servidor headless `:3001`) | Ativo | Implementação delegada — Codex planeja, Kilo executa |
| MCP Estatístico (`mcp_server/server.py`) | Implementado | `validate_split`, `detect_leakage`, `check_window_overlap`, `summary_report` |
| CriticAgent (`models/critic.py`) | Implementado | Falsificação: shuffle/placebo/estabilidade |

### Agentes `.claude/agents/`

| Agente | Arquivo | Modelo | Especialização |
|---|---|---|---|
| `data-scientist` | `data-scientist.md` | haiku | Regras estatísticas: split temporal, leakage, testes |
| `python-pro` | `python-pro.md` | haiku | Implementação Python: SQLAlchemy, pandas, lógica pura |
| `streamlit-developer` | `streamlit-developer.md` | haiku | Páginas Streamlit e componentes de visualização |
| `documentation-engineer` | `documentation-engineer.md` | haiku | Atualização de PROJETO.md e STATUS_ATUAL.md |
| `ux-researcher` | `ux-researcher.md` | sonnet | Pesquisa UX: síntese de feedback em ações implementáveis |
| `beta-tester-trader` | `beta-tester-trader.md` | sonnet | Teste beta: perspectiva de trader B&H real |

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

**Estas análises já foram implementadas** na Fase 1 em `features/saude.py`, `features/fundamentos.py` e `features/composicao.py`.

---

## Estado atual e próximos passos

**Concluído**:
- **Refatoração Arquitetural (Fases 0, 1 e 2)**: Singleton engine e context manager (`get_session_ctx`), remoção de duplicatas de lógica, criação de `features/data_loader.py`, migração das páginas Streamlit para context manager e centralização de thresholds no `config.yaml`.
- Fases 1–5: Schema SQLite + ingestão CVM/yfinance/brapi/BCB CDI, indicadores point-in-time, Event Study, Saúde financeira e Composição.
- MCP server estatístico e CriticAgent.
- **Otimizador de Thresholds** (`models/threshold_optimizer.py` + `10_Otimizador_V2.py`): sinais diários P/VP + DY Gap + meses_alerta, NW HAC com df efetivos (n/h), block bootstrap bicaudal para BUY, placebo SELL unicaudal esquerda vs mercado, Bonferroni ×36, grid 3×3×2×2. (`9_Otimizador.py` v1 foi removido; substituído por V2.)
- **Consolidação de páginas**: `8_Sinais.py` e `features/sinais.py` deletados; `6_Fund_EventStudy.py` refatorado para eventos discretos CVM e renomeado `8_Fund_EventStudy.py`; bugs críticos corrigidos (preço médio ponderado em Carteira, Herfindahl a mercado, guard Wilcoxon, filtro tickers ativos).
- **Agente data-scientist** em `.claude/agents/data-scientist.md` (modelo haiku).
- **Reorganização arquitetural**: lógica de negócio extraída dos scripts para `src/fii_analysis/models/div_capture.py`; `app/components/data_loader.py` (nome ambíguo) renomeado para `app/components/carteira_ui.py`; scripts reduzidos a wrappers CLI finos.
- **Agentes Codex**: 6 agentes em `.claude/agents/` — `data-scientist`, `python-pro`, `streamlit-developer`, `documentation-engineer`, `ux-researcher` (sonnet) e `beta-tester-trader` (sonnet).
- **Auditoria UX**: 43 problemas identificados em `docs/UX_AUDIT.md` (8 críticos, 11 altos). Ranking P0→P4 com estimativa de 12h total.
- **Fixes P0 aplicados**: `carteira_ui.py` migrado para `get_session_ctx()` (zero leaks); `2_Analise_FII.py` consolidado de 19→2 sessões por render.
- **Fixes P1 concluídos**: gráficos `carteira_alocacao_pie` e `carteira_segmento_pie` corrigidos para usar `valor_mercado`; lógica estatística (CAR, NW HAC, block bootstrap placebo) extraída de `8_Fund_EventStudy.py` → `src/fii_analysis/models/event_study_cvm.py` com `info_callback` para desacoplar de `st.info`.
- **Fixes P1/P2 UX concluídos**: error boundary global via `app/state.py` (`@safe_page` decorator com `functools.wraps` + `logging`) aplicado a todas as 9 páginas; `st.tabs()` em páginas 2, 5, 7, 8; `st.radio(horizontal=True)` substituiu 7 botões em `2_Analise_FII.py`; resultados de event study persistidos em `st.session_state` (páginas 5 e 8); gráficos de séries temporais em `charts.py` migrados para eixos de data nativos Plotly (`type="date"`, `tickformat`) em vez de strings `strftime`; `7_Fundamentos.py` dividido em 4 sessões por tab; dead imports e emojis removidos; `render_footer()` garantido antes de `st.stop()`.
- **Novos Modelos Robustos (Episódios e Walk-Forward Rolling)**: implementados `episodes.py` (detecção de episódios thinned), `walk_forward_rolling.py` (validação deslizante real) e `threshold_optimizer_v2.py` (métricas de risco e robustez).
- **Auditoria Estatística e Fixes Críticos**: aplicação de **Thinning** para garantir independência estatística em janelas sobrepostas; correção da anualização do Sharpe para `sqrt(252/n)`; classificação de overfitting como `SUSPEITO` se OOS for artificialmente superior ao treino; validação de bootstrap com detecção de degenerescência.
- **Expansão UI**: Adicionadas páginas `10_Otimizador_V2.py`, `11_Episodios.py`, `12_WalkForward.py` e `13_Hoje.py` (total 13 páginas).
- **Camada de Decisão (Fases 1–4)**: `decision/recommender.py` (motor central com dataclass `TickerDecision`), `decision/abertos.py` (oportunidades abertas), `decision/portfolio_advisor.py` (conselhos de carteira com badge HOLD/AUMENTAR/REDUZIR/SAIR/EVITAR_NOVOS_APORTES), `decision/daily_report.py` (relatório MD+CSV acionável).
- **Snapshots Diários**: Sistema completo de snapshots desnormalizados em 6 tabelas (`evaluation/daily_snapshots.py`), com geração via CLI (`scripts/generate_daily_snapshots.py`) e leitura na UI (`app/components/snapshot_ui.py`). Versionamento por motor, hash de universo/carteira, suporte a scopes `curado`/`carteira`/`db_ativos`, com consumo por padrão nas páginas `1_Panorama.py`, `3_Carteira.py`, `4_Radar.py` e `13_Hoje.py`.
- **Beta Tester Report**: Relatório de teste beta com persona trader (`docs/BETA_TESTER_REPORT.md`), identificando 15 dores ordenadas por severidade.
- **CLI `consulta`**: Comando `fii consulta TICKER` que integra indicadores locais com Gemini + Google Search para análise qualitativa em 4 seções.

**Pendente** (em ordem de prioridade):
1. **Cache de `optimizer_params`**: sem isso, `daily_report.py` precisa rodar com `--com-otimizador` (lento) ou aceitar `sinal_otimizador = INDISPONIVEL`. Plano: salvar `best_params` por ticker em `dados/optimizer_cache/{ticker}.json` com timestamp; reotimizar semanalmente.
2. **UX P2**: extrair charts inline de `7_Fundamentos.py`
3. **UX P3**: `@st.cache_data` em queries pesadas; IFIX YTD conectar `get_benchmark_ifix()`
4. Snapshots reprodutíveis do `fii_data.db` com hash SHA-256
5. Fase 6: `fii diario` (diff), relatório mensal Markdown/HTML, log de decisões
6. Reconciliar `config.py` ↔ `config.yaml`
7. Criar `tests/` (pyproject já configura pytest)

**Bugs menores conhecidos**:
- `1_Panorama.py`: métrica IFIX YTD hardcoded como `"n/d"` (P3)
- Paridade CLI/web no Panorama incompleta (faltam Rent. Acum, DY 24m, Tipo)

**Fora do escopo até decisão explícita:**
- LightGBM ou qualquer ML enquanto event study não confirmar padrão
- Score numérico ponderado no radar (substituído por matriz booleana)
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
