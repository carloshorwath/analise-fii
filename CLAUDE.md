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

---

## Estrutura de pastas

```
D:/analise-de-acoes/
├── CLAUDE.md
├── config.yaml                ← thresholds, janelas, fontes (defaults runtime)
├── pyproject.toml
├── dados/
│   ├── cvm/raw/               ← ZIPs da CVM (.gitignored)
│   ├── alertas/               ← Markdown diário gerado por evaluation/alertas.py
│   └── fii_data.db            ← banco SQLite (.gitignored)
├── src/fii_analysis/
│   ├── config.py              ← TICKERS, períodos treino/teste, custos, IR
│   ├── config_yaml.py         ← loader do config.yaml
│   ├── cli.py                 ← typer: panorama, fii, carteira, calendario, radar, alertas
│   ├── data/
│   │   ├── database.py        ← SQLAlchemy 2.0: tickers, precos_diarios, dividendos,
│   │   │                        relatorios_mensais, ativo_passivo, cdi_diario,
│   │   │                        benchmark_diario, eventos_corporativos
│   │   └── ingestion.py       ← CVM, yfinance, brapi, BCB SGS (CDI)
│   ├── features/
│   │   ├── dividend_window.py ← janela ±10 dias úteis (event study)
│   │   ├── indicators.py      ← P/VP, DY trailing (point-in-time)
│   │   ├── valuation.py       ← percentil rolling, DY N-meses, DY Gap
│   │   ├── portfolio.py       ← panorama, alocação, retorno vs IFIX, Herfindahl
│   │   ├── saude.py           ← tendência PL, flag destruição capital, emissões
│   │   ├── composicao.py      ← classificação Tijolo/Papel/Híbrido
│   │   └── radar.py           ← matriz booleana (sem score numérico)
│   ├── models/
│   │   ├── statistical.py     ← event study CAR, t-test, Mann-Whitney
│   │   ├── walk_forward.py    ← splits temporais com gap + validação leakage
│   │   ├── critic.py          ← shuffle/placebo/estabilidade (CriticAgent)
│   │   └── strategy.py        ← simulação dividend capture, otimização, risco
│   ├── evaluation/
│   │   ├── reporter.py        ← relatório técnico (somente dados de teste)
│   │   ├── panorama.py        ← rich.Table, render carteira/calendário
│   │   ├── alertas.py         ← Markdown diário + terminal
│   │   └── radar.py           ← render matriz booleana
│   └── mcp_server/server.py   ← MCP: validate_split, detect_leakage, etc
├── scripts/                   ← download_cvm, load_database, update_prices,
│                                run_strategy, plot_car, validate_knip11, etc
└── docs/
    ├── PROJETO.md
    ├── PLANO_EXPANSAO.md
    ├── PLANO_EXPANSAO_V2.md   ← especificação corrente
    └── STATUS_ATUAL.md        ← estado factual (regenerar quando mudar)
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
| Kilocode (servidor headless `:3001`) | Ativo | Implementação delegada — Claude planeja, Kilo executa |
| MCP Estatístico (`mcp_server/server.py`) | Implementado | `validate_split`, `detect_leakage`, `check_window_overlap`, `summary_report` |
| CriticAgent (`models/critic.py`) | Implementado | Falsificação: shuffle/placebo/estabilidade |

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

**Estas análises devem ser implementadas na Fase 1 junto com os indicadores básicos.**

---

## Estado atual e próximos passos

**Concluído**:
- **Refatoração Arquitetural (Fases 0, 1 e 2)**: Singleton engine e context manager (`get_session_ctx`), remoção de duplicatas de lógica, criação de `features/data_loader.py`, migração das páginas Streamlit para context manager e centralização de thresholds no `config.yaml`.
- Fases 1–5 do `docs/PLANO_EXPANSAO_V2.md`: Schema SQLite + ingestão CVM/yfinance/brapi/BCB CDI, indicadores point-in-time, Event Study, Saúde financeira e Composição.
- MCP server estatístico e CriticAgent.

**Pendente** (em ordem de prioridade):
1. Snapshots reprodutíveis do `fii_data.db` (§5.2 do V2) — protege contra recálculo retroativo do yfinance
2. Rodar event study nos 5 tickers ativos e interpretar resultados
3. Fase 6: `fii diario` (diff), relatório mensal Markdown/HTML, log de decisões
4. Reconciliar `config.py` ↔ `config.yaml`
5. Criar `tests/` (pyproject já configura pytest)
**Fora do escopo até decisão explícita:**
- Streamlit/Flask, exportação IR (Fase 7 — só se o CLI doer)
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
