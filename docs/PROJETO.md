# Projeto: Análise Estatística de FIIs

## 1. Objetivo

Identificar padrões estatísticos de comportamento de preço de FIIs (Fundos de Investimento Imobiliário) antes e depois da data-com de dividendos, com o objetivo de apoiar decisões de investimento pessoal.

**Análises previstas (em ordem de prioridade):**
1. Comportamento de preço em janelas ao redor da data-com [-10, +10 dias úteis]
2. P/VP histórico como indicador de valor (abaixo de 1,0 = potencial oportunidade)
3. Dividend Yield trailing 12 meses vs. média do segmento
4. Consistência de dividendos (estabilidade ao longo do tempo)
5. Expansão futura: outros indicadores fundamentalistas

**Saída atual:** terminal (CLI)
**Saída futura:** sistema web (Flask)

---

## 2. Escopo Inicial

- FII inicial: **SNFF11** (CNPJ: 40.011.225/0001-68)
- Lista pequena de FIIs escolhidos a dedo (a definir os demais)
- Período: 2023, 2024, 2025, 2026 (até hoje)
- Uma pessoa operando, com apoio de IA para desenvolvimento
- Expansão futura prevista (mais FIIs, mais análises, interface web)

---

## 3. Fontes de Dados

### 3.1 CVM Dados Abertos (gratuito, oficial, sem limite)
Fonte principal para dados fundamentalistas.

| Arquivo | URL | Conteúdo |
|---|---|---|
| Informe Mensal 2023 | `https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2023.zip` | VP, PL, DY%, cotas |
| Informe Mensal 2024 | `https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2024.zip` | VP, PL, DY%, cotas |
| Informe Mensal 2025 | `https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2025.zip` | VP, PL, DY%, cotas |
| Informe Mensal 2026 | `https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2026.zip` | VP, PL, DY%, cotas (atualiza mensalmente) |
| Dicionário de dados | `https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/META/meta_inf_mensal_fii.zip` | Documentação oficial |

**Arquivos dentro de cada ZIP:**
- `inf_mensal_fii_complemento_AAAA.csv` — VP por cota, PL, cotas emitidas, DY%, rentabilidade
- `inf_mensal_fii_geral_AAAA.csv` — dados cadastrais, segmento, Data_Entrega (lag de publicação)
- `inf_mensal_fii_ativo_passivo_AAAA.csv` — composição do ativo (CRI, imóveis, etc.)

**Campos críticos confirmados:**
- `Valor_Patrimonial_Cotas` — VP por cota
- `Patrimonio_Liquido`, `Cotas_Emitidas`
- `Percentual_Dividend_Yield_Mes`
- `Percentual_Rentabilidade_Efetiva_Mes`, `Percentual_Rentabilidade_Patrimonial_Mes`
- `Data_Entrega` (em geral) — data de publicação do relatório, usada para point-in-time
- `Segmento_Atuacao`, `Mandato`, `Tipo_Gestao`, `Codigo_ISIN`

**Importante:** CVM NÃO tem data-com de dividendos. Usar yfinance para isso.

### 3.2 Yahoo Finance via yfinance (gratuito)
Fonte principal para preços históricos e data-com.

- Preços OHLCV diários desde 2017+
- Dividendos históricos com data-com (ex-dividend date)
- Atenção: preço ajustado é recalculado retroativamente — salvar data da coleta
- Gaps em dividendos históricos (2018-2021 para alguns FIIs)
- Sufixo `.SA` obrigatório: `HGLG11.SA`

### 3.3 brapi.dev (gratuito — 15.000 req/mês)
Fonte para atualização diária de preços recentes.

- 1 ativo por requisição
- Últimos 3 meses de histórico
- Dados básicos de FIIs
- Uso: atualização diária após carga histórica inicial via yfinance
- Token necessário (usuário já possui)

---

## 4. Banco de Dados

**Tecnologia:** SQLite via SQLAlchemy
**Arquivo:** `dados/fii_data.db`
**Motivo SQLite:** projeto solo, sem concorrência, arquivo único, backup simples
**Migração futura:** trocar connection string do SQLAlchemy para PostgreSQL quando houver sistema web com múltiplos usuários

### Schema

```sql
-- Cadastro dos FIIs monitorados
tickers
  cnpj              TEXT PRIMARY KEY
  ticker            TEXT UNIQUE        -- ex: HGLG11
  nome              TEXT               -- Nome_Fundo_Classe
  segmento          TEXT               -- Segmento_Atuacao (Shoppings, Lajes, Papel...)
  mandato           TEXT               -- Renda / Desenvolvimento / Híbrido
  tipo_gestao       TEXT               -- Ativa / Passiva
  codigo_isin       TEXT
  data_inicio       DATE               -- Data_Funcionamento

-- Preços diários
precos_diarios
  ticker            TEXT
  data              DATE
  abertura          NUMERIC
  maxima            NUMERIC
  minima            NUMERIC
  fechamento        NUMERIC            -- preço bruto
  fechamento_aj     NUMERIC            -- ajustado (registrar data da coleta!)
  volume            BIGINT
  fonte             TEXT               -- 'yfinance' ou 'brapi'
  coletado_em       TIMESTAMP          -- quando foi salvo
  PRIMARY KEY (ticker, data)

-- Dividendos com data-com
dividendos
  ticker            TEXT
  data_com          DATE               -- ex-dividend date (fonte: yfinance)
  valor_cota        NUMERIC
  fonte             TEXT
  PRIMARY KEY (ticker, data_com)

-- Relatórios mensais CVM (point-in-time)
relatorios_mensais
  cnpj              TEXT
  data_referencia   DATE               -- mês do relatório
  data_entrega      DATE               -- quando entregue à CVM (point-in-time!)
  vp_por_cota       NUMERIC            -- Valor_Patrimonial_Cotas
  patrimonio_liq    NUMERIC            -- Patrimonio_Liquido
  cotas_emitidas    BIGINT             -- Cotas_Emitidas
  dy_mes_pct        NUMERIC            -- Percentual_Dividend_Yield_Mes
  rentab_efetiva    NUMERIC            -- Percentual_Rentabilidade_Efetiva_Mes
  rentab_patrim     NUMERIC            -- Percentual_Rentabilidade_Patrimonial_Mes
  PRIMARY KEY (cnpj, data_referencia)
```

**Regra crítica — P/VP e DY são CALCULADOS, nunca armazenados:**
```
P/VP(t) = preco(t) / VP do relatório com data_entrega mais recente <= t
DY_trailing(t) = soma dividendos 12m antes de t / preco(t)
```

---

## 5. Arquitetura de Componentes

### 5.1 DataAgent — coleta e prepara dados
Módulo Python determinístico. Não é um LLM autônomo.

**Responsabilidades:**
- Baixar ZIPs da CVM e extrair CSVs
- Coletar preços históricos via yfinance (carga inicial)
- Atualizar preços diários via brapi
- Detectar e não sobrescrever dados já existentes no banco
- Registrar fonte e data de coleta em cada registro

**Regra crítica:** verificar se dado já existe antes de baixar
```
"Já tenho HGLG11 de 2023-01-01 a 2024-12-31?"
→ Sim: não recoleta, só atualiza a partir do último registro
→ Não: coleta histórico completo
```

### 5.2 MCP Estatístico — árbitro do pipeline
Servidor MCP em Python com ferramentas determinísticas.
Impede que o pipeline avance se houver problemas estatísticos.

**Ferramentas:**
- `validate_split` — verifica separação temporal treino/validação/teste sem overlap
- `detect_leakage` — cruza metadados de features com boundaries do split
- `report_metrics` — aceita SOMENTE `split_label="test"`, rejeita treino/validação
- `describe_dividend_window` — estatísticas por subjanela ao redor da data-com
- `audit_features` — árvore de dependências temporais de cada feature
- `compute_event_study` — CAR/BHAR agregado para múltiplos FIIs e eventos

### Benchmark para Event Study
- **IFIX via brapi.dev** — índice oficial de FIIs brasileiros
- IBOVESPA como fallback se IFIX não estiver disponível na brapi
- Verificar disponibilidade antes de implementar

### 5.3 CriticAgent — tenta falsificar os resultados
Ferramentas determinísticas + LLM interpreta. Chamado após o modelo gerar resultados.

**Ataques implementados:**
- Trocar datas de corte aleatoriamente (detecta overfitting)
- Testar em períodos de mercado diferentes (2023 vs 2024 vs 2025)
- Comparar com baseline ingênuo (sempre compra X dias antes da data-com)
- Verificar survivorship bias (FIIs liquidados excluídos da amostra?)
- Calcular resultado líquido de custos de transação
- Permutation test: embaralhar labels e medir acurácia (detecta correlação espúria)

### 5.4 ModelAgent — constrói e avalia o modelo
Pipeline Python estruturado. Não é um LLM autônomo.

**Responsabilidades:**
- Walk-forward validation (sem shuffle, sem data leakage)
- Separação estrita: Treino / Validação / Teste com gap entre períodos
- Modelos estatísticos clássicos (t-test, Mann-Whitney, event study CAR/BHAR)
- ML opcional (LightGBM) para fase futura

### 5.5 ReportAgent — interpreta e narra resultados
Único agente onde o LLM protagoniza. Recebe output determinístico e gera narrativa.

**Responsabilidades:**
- Interpretar resultados do MCP Estatístico e CriticAgent
- Gerar relatório em linguagem natural para decisão de investimento
- Nunca inventar métricas — só narra o que foi calculado

---

## 6. Proteções contra Data Leakage (por design)

| Proteção | Mecanismo |
|---|---|
| Point-in-time no VP | Usar `Data_Entrega` da CVM, não `Data_Referencia` |
| Preço ajustado | Salvar `coletado_em` para rastrear versão do dado |
| Walk-forward com gap | Gap entre treino e validação absorve lookback das features |
| MCP como portão | Pipeline não avança sem aprovação do MCP Estatístico |
| CriticAgent | Tenta ativamente destruir os resultados antes de reportar |
| Reporter lacrado | Módulo de relatório não tem acesso a dados de treino |

---

## 7. Estrutura de Pastas

```
D:/analise-de-acoes/
├── .claude/
│   └── settings.json          # MCP Gemini configurado
│
├── dados/
│   ├── cvm/
│   │   ├── raw/               # ZIPs originais (.gitignore)
│   │   │   ├── inf_mensal_fii_2023.zip
│   │   │   ├── inf_mensal_fii_2024.zip
│   │   │   ├── inf_mensal_fii_2025.zip
│   │   │   └── inf_mensal_fii_2026.zip
│   │   └── processado/        # Parquet extraídos e limpos
│   │       ├── complemento.parquet
│   │       ├── geral.parquet
│   │       └── ativo_passivo.parquet
│   ├── precos/
│   │   └── precos_diarios.parquet
│   └── fii_data.db            # SQLite principal
│
├── src/
│   └── fii_analysis/
│       ├── data/
│       │   ├── ingestion.py       # DataAgent: coleta CVM, yfinance, brapi
│       │   ├── alignment.py       # Une preços com relatórios CVM (point-in-time)
│       │   └── database.py        # SQLAlchemy models e conexão
│       ├── features/
│       │   ├── dividend_window.py # Janela [-30,+30] dias da data-com
│       │   └── indicators.py      # P/VP, DY trailing, etc. (calculados, nunca salvos)
│       ├── models/
│       │   ├── statistical.py     # t-test, Mann-Whitney, event study
│       │   └── walk_forward.py    # Splits temporais com gap
│       ├── evaluation/
│       │   └── reporter.py        # ReportAgent: só acessa dados de teste
│       └── mcp_server/
│           ├── server.py          # MCP Estatístico
│           └── tools/
│               ├── validate_split.py
│               ├── detect_leakage.py
│               ├── report_metrics.py
│               ├── describe_window.py
│               └── compute_event_study.py
│
├── scripts/
│   ├── download_cvm.py        # Baixa ZIPs da CVM
│   ├── load_database.py       # Processa ZIPs e popula SQLite
│   ├── update_prices.py       # Atualização diária via brapi
│   └── serve_mcp.py           # Sobe MCP Estatístico
│
├── docs/
│   └── PROJETO.md             # Este documento
│
├── .gitignore                 # dados/cvm/raw/, dados/*.db, dados/precos/
└── pyproject.toml
```

---

## 8. Stack Tecnológica

```toml
[project.dependencies]
# Banco
sqlalchemy = ">=2.0"       # abstração de banco (SQLite agora, PostgreSQL futuro)

# Dados
pandas = ">=2.2"
pyarrow = ">=15.0"         # leitura/escrita Parquet
yfinance = ">=0.2.40"
requests = ">=2.31"        # brapi.dev

# Estatística
numpy = ">=1.26"
scipy = ">=1.12"           # t-test, Mann-Whitney
statsmodels = ">=0.14"     # event study, erros HAC

# MCP
mcp = ">=1.1"              # MCP server SDK
pydantic = ">=2.6"         # validação de schemas

# Qualidade
loguru = ">=0.7"           # logging estruturado

[project.optional-dependencies]
dev = ["pytest", "ruff", "jupyter"]
ml  = ["lightgbm>=4.3"]    # fase futura
web = ["flask>=3.0"]       # fase futura
```

---

## 9. Decisões Arquiteturais Registradas

| Decisão | Escolha | Motivo |
|---|---|---|
| Banco de dados | SQLite + SQLAlchemy | Projeto solo, migração fácil para PostgreSQL via SQLAlchemy |
| Formato intermediário | Parquet | Colunar, rápido para análise, menor que CSV |
| Fonte de VP histórico | CVM (oficial) | Gratuito, oficial, sem limite, desde 2016 |
| Fonte de data-com | yfinance | CVM não tem essa informação |
| Fonte de preços | yfinance (carga) + brapi (updates) | yfinance para histórico, brapi para atualidade |
| P/VP e DY | Calculados via view, nunca salvos | Evita inconsistência com dados históricos |
| Point-in-time | Usar Data_Entrega da CVM | Evita lookahead bias no VP |
| Período inicial | 2023-2026 (~40 eventos/FII) | Suficiente para análise inicial |
| Janela data-com | ±10 dias úteis (não ±30) | Janelas de ±30 se sobrepõem em FIIs mensais — viola independência estatística |
| Benchmark | IFIX via brapi (IBOVESPA como fallback) | IFIX não disponível no yfinance |
| Storage | SQLite apenas (sem Parquet redundante) | Parquet + SQLite era complexidade desnecessária para este escopo |
| Token brapi | `C:\Modelos-AI\Brapi\.env` → chave `BRAPI_API_KEY` | Fora do projeto por segurança. Carregar via python-dotenv com caminho absoluto |
| Agentes LLM | Só ReportAgent usa LLM como protagonista | Análise financeira exige determinismo |
| MCP Estatístico | Implementar após dados validados | Prematuro na fase de validação inicial |

---

## 10. Pendências

- [ ] Definir lista de FIIs a monitorar (tickers)
- [ ] Criar estrutura de pastas no projeto
- [ ] Criar .gitignore
- [ ] Criar pyproject.toml
- [ ] Implementar DataAgent (ingestion.py)
- [ ] Implementar schema SQLAlchemy (database.py)
- [ ] Script de carga inicial CVM (load_database.py)
- [ ] Script de carga de preços yfinance
- [ ] Implementar MCP Estatístico
- [ ] Implementar CriticAgent
- [ ] Implementar análise de janela data-com
- [ ] Implementar P/VP e DY calculados
- [ ] Implementar ReportAgent (CLI)
- [ ] Testes
