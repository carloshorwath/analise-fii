# Plano de Melhoria — FII Analytics

> **Baseado em:** auditoria técnica completa do código + análise do `PROJETO-completo.md`
> **Última atualização:** 2026-05-02
> **Objetivo:** fechar o gap entre o que o projeto visiona e o que realmente está implementado.

---

## STATUS ATUAL DAS FASES

| Fase | Descrição | Status |
|---|---|---|
| 1 | Métricas de risco e retorno (`risk_metrics.py`) | ✅ Funções criadas — ⚠️ UI/snapshot pendentes |
| 1.5 | Integrar Fase 1 no pipeline de snapshots e UI | ❌ Pendente |
| 2 | Score 0–100 com decomposição visual | ❌ Pendente |
| 3 | Justificativa LLM por ticker | ❌ Pendente |
| 4 | Diagnóstico LLM da carteira | ❌ Pendente |
| 5 | Spread sobre NTN-B | ❌ Pendente |
| 6 | Comparativo com pares do segmento | ❌ Pendente |
| 7 | Histórico de recomendações versionado | ❌ Pendente |
| 8 | Relatório exportável HTML | ❌ Pendente |
| 9 | Dados qualitativos (vacância, WAULT, LTV) | ❌ Longo prazo |

---

## WORKFLOW JULES — COMO ENVIAR MISSÕES

**SEMPRE usar Bash tool + Python subprocess + SEM timeout + SEM run_in_background:**

```bash
python3 -c "
import subprocess
task = '''descrição da tarefa'''
result = subprocess.run(
    ['node', 'C:/Users/carlo/AppData/Roaming/npm/node_modules/@google/jules/run.cjs',
     'new', '--repo', 'carloshorwath/analise-fii', task],
    capture_output=True, text=True
)
print(result.stdout)
print(result.stderr)
"
```

**Verificar diff após merge:**
```bash
node "C:/Users/carlo/AppData/Roaming/npm/node_modules/@google/jules/run.cjs" remote pull --session SESSION_ID
```

---

## 1. Diagnóstico Honesto do Estado Atual

### O que o motor realmente faz

Os três sinais do `decision/recommender.py` são, na prática, **todos baseados em P/VP percentil**:

| Sinal | Feature principal | Feature secundária |
|---|---|---|
| Sinal Otimizador | P/VP percentil rolling (p10–p25 = BUY) | DY Gap percentil (< p25–35 = SELL) + meses_alerta |
| Sinal Episódio | P/VP percentil fixo (p10 = BUY, p90 = SELL) | — |
| Sinal Walk-Forward | P/VP percentil (p15/p85 calculado no treino) | — |

### O que não existe (estado original, antes das melhorias)

| Feature | Status original | Depois da Fase 1 |
|---|---|---|
| Volatilidade anualizada | ❌ | ✅ `risk_metrics.volatilidade_anualizada()` |
| Beta vs IFIX | ❌ | ✅ `risk_metrics.beta_vs_ifix()` — retorna None sem dados IFIX |
| Maximum Drawdown real | ❌ | ✅ `risk_metrics.max_drawdown()` |
| Liquidez 21d (R$) | ❌ no motor | ✅ `risk_metrics.liquidez_media_21d()` |
| DY 3m anualizado | ❌ | ✅ `risk_metrics.dy_3m_anualizado()` |
| Retorno total 12m | ❌ | ✅ `risk_metrics.retorno_total_12m()` |
| Yield on Cost (YoC) | ❌ | ✅ `risk_metrics.yield_on_cost()` |
| Score numérico 0–100 | ❌ | ❌ (Fase 2) |
| Justificativa LLM | ❌ | ❌ (Fase 3) |
| Diagnóstico LLM da carteira | ❌ | ❌ (Fase 4) |
| Spread sobre NTN-B | ❌ | ❌ (Fase 5) |
| Comparativo com pares | ❌ | ❌ (Fase 6) |
| Histórico recomendações | ❌ | ❌ (Fase 7) |
| Vacância / WAULT / LTV | ❌ | ❌ (Fase 9) |

### O que funciona bem e não deve ser tocado

- Validação estatística dos sinais P/VP (thinning, bootstrap, placebo, Bonferroni) ✅
- Walk-forward rolling out-of-sample genuíno ✅
- Flags de saúde (destruição capital, emissões, veto BUY) ✅
- Pipeline de snapshots diários (`generate_daily_snapshots.py`) ✅
- Arquitetura limpa `src/features` → `src/decision` → `app/pages` ✅

---

## 2. Arquitetura do Banco — Tabelas de Snapshot

> **Contexto crítico para Jules:** o projeto usa um pipeline de snapshots diários pré-calculados.
> Não calcule nada on-demand na UI — tudo entra via `generate_daily_snapshots.py` → tabelas de snapshot.

### `snapshot_runs` — envelope de metadados
```python
id, data_referencia, criado_em, status,  # running | ready | failed
engine_version_global, universe_scope,   # curado | carteira | db_ativos
universe_hash, carteira_hash,
base_preco_ate, base_dividendo_ate, base_cdi_ate,
mensagem_erro, tickers_falhos            # JSON list
```

### `snapshot_ticker_metrics` — métricas por ticker (ONDE ADICIONAR COLUNAS DA FASE 1.5)
```python
# COLUNAS ATUAIS:
id, run_id, ticker,
preco, vp, pvp, pvp_percentil,
dy_12m, dy_24m, rent_12m, rent_24m,
dy_gap, dy_gap_percentil,
volume_21d,          # <-- já existe, mas é diferente de liquidez_media_21d
cvm_defasada, segmento

# COLUNAS A ADICIONAR (Fase 1.5):
volatilidade_anual,  # float, ex: 0.11
beta_ifix,           # float, ex: 0.82 — None se IFIX sem dados
max_drawdown,        # float negativo, ex: -0.09
liquidez_21d_brl,    # float R$, ex: 8148647.0
retorno_total_12m,   # float, ex: 0.279
dy_3m_anualizado,    # float, ex: 0.101
```

### `snapshot_decisions` — ações derivadas por ticker
```python
id, run_id, ticker, data_referencia,
sinal_otimizador, sinal_episodio, sinal_walkforward,
acao, nivel_concordancia, n_concordam_buy, n_concordam_sell,
flag_destruicao_capital, motivo_destruicao, flag_emissao_recente,
flag_pvp_caro, flag_dy_gap_baixo,
pvp_atual, pvp_percentil, dy_gap_percentil, preco_referencia,
# (campos CDI sensitivity também presentes — não modificar)
# COLUNAS A ADICIONAR (Fase 2+):
# score_total, score_valuation, score_risco, score_liquidez, score_historico
# justificativa_llm, justificativa_hash  (Fase 3)
```

### `snapshot_portfolio_advices` — conselhos por posição da carteira
```python
id, run_id, carteira_hash,
ticker, quantidade, preco_medio, preco_atual, valor_mercado, peso_carteira,
badge,      # HOLD | AUMENTAR | REDUZIR | SAIR | EVITAR_NOVOS_APORTES
racional, prioridade,
acao_recomendada, nivel_concordancia, flags_resumo, valida_ate
```

### Como adicionar colunas (padrão do projeto)
O projeto usa `src/fii_analysis/data/migrations.py` para ALTER TABLE em SQLite.
Padrão: `ADD COLUMN IF NOT EXISTS` via `text()` do SQLAlchemy.
Ver `migrations.py` para exemplos existentes antes de criar nova migration.

---

## 3. Pipeline de Snapshots — Onde Integrar

Arquivo: `src/fii_analysis/evaluation/daily_snapshots.py`

Função principal: `gerar_snapshot(run_id, tickers, session)` — chamada por `scripts/generate_daily_snapshots.py`.

Trecho relevante onde `SnapshotTickerMetrics` é populado (linha ~240):
```python
session.add(SnapshotTickerMetrics(
    run_id=run_id,
    ticker=ticker,
    preco=...,
    pvp=...,
    pvp_percentil=...,
    dy_12m=...,
    dy_gap=...,
    dy_gap_percentil=...,
    volume_21d=vol_21d,
    ...
))
```

**Para Fase 1.5:** adicionar chamadas a `risk_metrics.*` neste bloco e persistir nas novas colunas.

---

## 4. Fases de Melhoria

### Fase 1.5 — Integrar risk_metrics no Pipeline e na UI
**PRÓXIMA MISSÃO PARA JULES**
**Estimativa: 2–3 dias | Depende da Fase 1 (já concluída)**

**O que fazer:**

**Parte A — Migration (nova coluna no banco):**
Adicionar em `src/fii_analysis/data/migrations.py` as colunas:
```sql
ALTER TABLE snapshot_ticker_metrics ADD COLUMN IF NOT EXISTS volatilidade_anual REAL;
ALTER TABLE snapshot_ticker_metrics ADD COLUMN IF NOT EXISTS beta_ifix REAL;
ALTER TABLE snapshot_ticker_metrics ADD COLUMN IF NOT EXISTS max_drawdown REAL;
ALTER TABLE snapshot_ticker_metrics ADD COLUMN IF NOT EXISTS liquidez_21d_brl REAL;
ALTER TABLE snapshot_ticker_metrics ADD COLUMN IF NOT EXISTS retorno_total_12m REAL;
ALTER TABLE snapshot_ticker_metrics ADD COLUMN IF NOT EXISTS dy_3m_anualizado REAL;
```

**Parte B — ORM (adicionar campos ao modelo):**
Em `src/fii_analysis/data/database.py`, na classe `SnapshotTickerMetrics`, adicionar:
```python
volatilidade_anual: Mapped[float | None] = mapped_column(Numeric)
beta_ifix: Mapped[float | None] = mapped_column(Numeric)
max_drawdown: Mapped[float | None] = mapped_column(Numeric)
liquidez_21d_brl: Mapped[float | None] = mapped_column(Numeric)
retorno_total_12m: Mapped[float | None] = mapped_column(Numeric)
dy_3m_anualizado: Mapped[float | None] = mapped_column(Numeric)
```

**Parte C — Pipeline de snapshot:**
Em `src/fii_analysis/evaluation/daily_snapshots.py`, no bloco que cria `SnapshotTickerMetrics`,
importar `from src.fii_analysis.features.risk_metrics import *` e popular os novos campos.
Usar try/except por campo — falha em uma métrica não deve derrubar o snapshot inteiro.

**Parte D — UI em `7_Fundamentos.py`:**
Na aba "Fundamentos", adicionar nova seção "Risco e Retorno" com métricas em `st.metric()`:
- Volatilidade anual (ex: "11,1%")
- Beta vs IFIX (ex: "0,82" ou "n/d" se None)
- Max Drawdown (ex: "-9,1%")
- Liquidez 21d (ex: "R$ 8,1 mi")
- Retorno Total 12m (ex: "+27,9%")
- DY 3m anualizado (ex: "10,1%")
Ler do snapshot atual (via `load_snapshot_ticker_metrics()` que já existe).

**Parte E — UI em `14_Dossie_FII.py`:**
Na aba "Análise", adicionar linha de métricas de risco após a seção de valuation.
Mesmo conjunto de métricas do item D, mais compacto (inline `st.metric()`).

---

### Fase 2 — Score Numérico 0–100 com Decomposição Visual
**Estimativa: 3–4 dias | Depende da Fase 1.5**

Criar `src/fii_analysis/features/score.py`.

**Arquitetura do score:**

```
Score(FII) = 0,35 × ScoreValuation
           + 0,30 × ScoreRisco
           + 0,20 × ScoreLiquidez
           + 0,15 × ScoreHistórico
```

**Sub-scores (0–100 cada):**

```python
# ScoreValuation: P/VP percentil invertido + DY Gap percentil
# P/VP baixo = bom → score alto; DY Gap alto = bom → score alto
def score_valuation(pvp_percentil: float, dy_gap_percentil: float) -> int:
    pvp_score = 100 - pvp_percentil   # p10 → 90 pts; p80 → 20 pts
    gap_score = dy_gap_percentil       # p80 → 80 pts; p10 → 10 pts
    return round(0.6 * pvp_score + 0.4 * gap_score)

# ScoreRisco: volatilidade, beta, drawdown — penalizam quando altos
# Normalizar contra universo dos FIIs monitorados (percentil relativo entre os 5–6 tickers)
def score_risco(vol: float | None, beta: float | None, mdd: float | None,
                vol_universe: list, beta_universe: list, mdd_universe: list) -> int:
    # Calcular percentil de cada métrica dentro do universo
    # vol alto = risco alto = score baixo
    # |beta| alto = risco alto = score baixo
    # |mdd| alto = risco alto = score baixo
    ...

# ScoreLiquidez: faixas fixas (não relativas ao universo)
# < R$ 200k/dia = 20 pts | 200k–1M = 50 pts | 1M–5M = 75 pts | > 5M = 90 pts
def score_liquidez(liquidez_21d_brl: float | None) -> int: ...

# ScoreHistórico: consistência do DY 24m (coef. variação invertido)
# CV = std(DY_mensal) / mean(DY_mensal) sobre 24 meses
# CV baixo (DY consistente) = score alto
def score_historico(ticker: str, session=None) -> int:
    # Buscar dy_mes_pct dos últimos 24 meses de RelatorioMensal
    # Calcular CV; inverter e normalizar para 0-100
    ...
```

**Dataclass de resultado:**

```python
@dataclass
class ScoreFII:
    ticker: str
    data_referencia: date
    score_total: int           # 0–100
    score_valuation: int       # 0–100
    score_risco: int           # 0–100
    score_liquidez: int        # 0–100
    score_historico: int       # 0–100
    # Campos auxiliares para debug/UI
    pvp_percentil: float | None
    dy_gap_percentil: float | None
    volatilidade: float | None
    liquidez_21d_brl: float | None
```

**Função pública:**
```python
def calcular_score(ticker: str, session=None,
                   todos_tickers: list[str] | None = None) -> ScoreFII | None:
    """
    todos_tickers: lista de todos os FIIs ativos (para normalização de risco relativo).
    Se None, usa apenas os dados absolutos (score_risco usa faixas fixas).
    """
```

**Integração no banco:**
- `SnapshotTickerMetrics`: adicionar `score_total`, `score_breakdown` (JSON com sub-scores)
- `SnapshotDecisions`: adicionar `score_total` (redundância intencional para queries simples)

**Integração UI:**
- `14_Dossie_FII.py`: barras horizontais Plotly mostrando cada sub-score
- `13_Hoje.py`: badge colorido com score ao lado do badge COMPRAR/EVITAR
  - Score ≥ 80: verde escuro
  - Score 65–79: verde médio
  - Score 50–64: amarelo
  - Score < 50: vermelho

**Nota crítica:** score ≥ 80 ≠ sinal COMPRAR (podem divergir). Exibir os dois separadamente.

---

### Fase 3 — Justificativa em Linguagem Natural (LLM)
**Estimativa: 2–3 dias | Depende da Fase 2 | MAIOR IMPACTO para o usuário**

Criar `src/fii_analysis/decision/justifier.py`.

**Dependências:**
- `anthropic` (já instalado: `pip show anthropic` para verificar versão)
- API key: variável de ambiente `ANTHROPIC_API_KEY` (no `.env` do projeto ou variável do sistema)

**Assinatura:**
```python
def gerar_justificativa(
    decision: TickerDecision,          # de src.fii_analysis.decision.recommender
    score: ScoreFII | None = None,     # de src.fii_analysis.features.score
    holding: HoldingAdvice | None = None,  # de src.fii_analysis.decision.portfolio_advisor
    cache: dict | None = None,
) -> str:
    """
    Retorna 3–6 frases em PT-BR explicando a recomendação.
    Nunca decide o sinal — apenas o comunica.
    Em caso de falha da API, retorna template estático com dados crus.
    """
```

**Prompt template:**
```
Você é um analista de FIIs comunicando uma recomendação a um investidor pessoa física brasileiro.

Dados calculados pelo sistema:
- Ticker: {ticker} ({classificacao})
- Ação: {acao} (concordância: {nivel_concordancia})
- P/VP percentil: {pvp_percentil:.0f}/100 (atual: {pvp_atual:.2f})
- DY Gap percentil: {dy_gap_percentil:.0f}/100
- Score total: {score_total}/100 (valuation: {score_valuation}, risco: {score_risco})
- Flags ativas: {flags}
- Posição na carteira: {peso_carteira:.1f}% | PM: R${preco_medio:.2f} | Atual: R${preco_atual:.2f}

Regras obrigatórias:
1. NUNCA prometa retorno futuro. NUNCA diga "vai subir/cair".
2. Cite no máximo 3 indicadores com valores numéricos reais dos dados acima.
3. Mencione 1 risco mesmo em ações positivas.
4. Linguagem clara, sem jargão sem explicação.
5. NÃO use: "garantido", "certeza", "infalível", "recomendo fortemente".
6. Tom sóbrio, sem exclamações.
7. Entre 3 e 6 frases. Não passe disso.

Devolva APENAS o texto da justificativa, sem cabeçalho.
```

**Modelo:** `claude-haiku-4-5` por padrão. Fallback: template estático com dados crus.

**Guardrails pós-geração:**
- Comprimento: 150–600 caracteres → se fora do range, refazer 1 vez com prompt reforçado, senão template
- Palavras proibidas (regex): `garanti|certez|infalív|vai subir|vai cair|lucro cert`
- Validação: o texto deve conter pelo menos 1 número que aparece nos dados de input

**Cache:**
- Chave: `md5(f"{ticker}|{acao}|{nivel_concordancia}|{pvp_pct:.0f}|{dy_gap_pct:.0f}")`
- Persistência: colunas `justificativa_llm` e `justificativa_hash` em `SnapshotDecisions`
- Regenerar SOMENTE quando hash muda

**Integração UI:**
- `13_Hoje.py`: expandir card de cada ação para mostrar justificativa (colapsável via `st.expander`)
- `14_Dossie_FII.py`: seção destacada na aba "Análise"

---

### Fase 4 — Diagnóstico LLM da Carteira
**Estimativa: 1–2 dias | Depende das Fases 2 e 3**

Criar `src/fii_analysis/decision/portfolio_diagnostics.py`.

**Função:**
```python
def gerar_diagnostico_carteira(
    advices: list[HoldingAdvice],
    alertas: list[AlertaEstrutural],
    scores: dict[str, ScoreFII],  # ticker → ScoreFII
    cache: dict | None = None,
) -> tuple[str, float]:
    """
    Retorna (diagnostico_texto, score_carteira_ponderado).
    score_carteira = média ponderada por valor_mercado dos score_total individuais.
    """
```

**Prompt:**
```
Você é um analista de FIIs resumindo o estado de uma carteira de investimentos.

Carteira: {n_holdings} FIIs | Score médio ponderado: {score_carteira}/100
Composição por segmento: {segmentos_pct}
Ações prioritárias: {n_comprar} COMPRAR, {n_reduzir} REDUZIR/SAIR, {n_manter} MANTER
Maior posição: {top_peso:.1f}% | Alertas estruturais: {alertas}

Escreva 3–5 frases descrevendo a saúde da carteira.
Mencione 1 ponto forte e 1 ponto de atenção.
Não cite nomes de FIIs específicos — fale de segmentos e métricas.
Tom: técnico, sóbrio, sem promessas.
```

**Integração UI:**
- `13_Hoje.py`: painel de topo antes das ações individuais
- `3_Carteira.py`: nova seção "Diagnóstico da Carteira"

**Novos campos em `SnapshotPortfolioAdvices`:** `score_carteira`, `diagnostico_llm`, `diagnostico_hash`

---

### Fase 5 — Spread sobre NTN-B
**Estimativa: 2 dias | Independente das outras fases**

**Por que:** o DY Gap atual usa CDI como benchmark. Para FIIs, o benchmark mais relevante
é NTN-B (IPCA+) — é o que gestores de tijolo e papel competem na alocação de capital.

**Implementação:**
```python
# src/fii_analysis/data/ingestion.py — adicionar função
def get_ntnb_bcb(serie_bcb: int = 12466) -> pd.DataFrame:
    """
    Série BCB SGS 12466 = NTN-B 5a (taxa IPCA+ % a.a.).
    Retorna DataFrame com colunas: data, ytm_real_aa.
    Endpoint: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json
    """

# Nova tabela no database.py:
class BenchmarkNtnb(Base):
    __tablename__ = "benchmark_ntnb"
    data: date (PK)
    ytm_real_aa: float  # yield IPCA+ % a.a.
    serie_bcb: int
    coletado_em: datetime
```

**Cálculo:**
```python
spread_ntnb = DY_12m - ytm_ntnb_vigente_em_t  # em pontos percentuais
# > 0: FII oferece prêmio vs renda fixa real
# < 0: renda fixa real é mais atraente
```

**Integração:**
- `SnapshotTickerMetrics`: coluna `spread_ntnb_pp`
- `ScoreValuation` (Fase 2+): usar spread NTN-B como substituto do DY Gap CDI quando disponível
- `7_Fundamentos.py`: gráfico de série histórica do spread

---

### Fase 6 — Comparativo com Pares do Segmento
**Estimativa: 2–3 dias | Depende das Fases 1 e 2**

```python
# src/fii_analysis/features/peer_comparison.py
def comparar_pares(tickers: list[str], session=None) -> pd.DataFrame:
    """
    Uma linha por ticker. Colunas:
    ticker, segmento, pvp_atual, pvp_percentil, dy_12m, dy_gap_percentil,
    score_total, acao, concordancia, volatilidade_anual, liquidez_21d_brl
    Ordenado por score_total DESC.
    Fonte: snapshot_ticker_metrics + snapshot_decisions mais recentes.
    """
```

**Integração UI:**
- Nova aba "Comparar" em `14_Dossie_FII.py`
- `4_Radar.py`: expandir matriz booleana para mostrar ranking por score ao lado

---

### Fase 7 — Histórico de Recomendações Versionado
**Estimativa: 2–3 dias | Depende da Fase 3**

**Nova tabela:**
```sql
recommendation_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT NOT NULL,
    data_ref     DATE NOT NULL,
    acao         TEXT,   -- COMPRAR | VENDER | AGUARDAR | EVITAR
    badge        TEXT,   -- AUMENTAR | REDUZIR | HOLD | SAIR | EVITAR_NOVOS_APORTES
    concordancia TEXT,
    score_total  INTEGER,
    justificativa TEXT,
    pvp_snapshot REAL,
    dy_gap_snapshot REAL,
    criado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Lógica:** em `generate_daily_snapshots.py`, após calcular decisões, gravar SOMENTE quando
`acao` ou `badge` mudou vs o registro mais recente na tabela (diff-based — evita duplicatas diárias).

**Integração UI:**
- `14_Dossie_FII.py`: aba "Histórico" com timeline de mudanças de ação
- `13_Hoje.py`: badge visual "↑ Mudou hoje" quando ação mudou no último snapshot vs o anterior

---

### Fase 8 — Relatório Exportável (Markdown / HTML)
**Estimativa: 2 dias | Depende das Fases 3 e 4**

`export_daily_report_md()` já existe em `decision/daily_report.py`. Ampliar:

```python
def export_report_html(report: DailyCommandCenter, holdings: list) -> str:
    """
    HTML formatado com:
    - Diagnóstico da carteira (LLM)
    - Cards por FII com score, justificativa, indicadores
    - Alertas estruturais
    - Data de geração + disclaimer CVM
    Usar Jinja2 (disponível via Streamlit já instalado).
    """
```

**Integração UI:**
- Botão "Exportar Relatório" em `13_Hoje.py` → `st.download_button` com MIME `text/html`

---

### Fase 9 — Dados Qualitativos (Vacância, WAULT, LTV)
**Estimativa: 1–2 semanas | Longo prazo | Alta complexidade**

1. **Coleta manual inicial:** CSV atualizado trimestralmente para os 6 FIIs monitorados.

2. **Nova tabela `fii_qualitativo`:**
   ```sql
   cnpj, data_referencia, vacancia_fisica_pct, vacancia_financeira_pct,
   wault_anos, ltv_pct, top_inquilino_pct, indexador_predominante, fonte
   ```

3. **Integração no ScoreQualidade** (sub-score extra na Fase 2+):
   - Tijolo: vacância baixa + WAULT alto = qualidade alta
   - Papel: LTV < 60% + indexador IPCA+ = qualidade alta

4. **Automação futura (V2):** pipeline LLM com extração de PDF via Claude Vision.

---

## 5. Roadmap Consolidado

```
MAIO 2026
├── Fase 1.5: Integrar risk_metrics no snapshot + UI (7_Fundamentos, 14_Dossie_FII)
├── Fase 2: Score 0-100 com barras de decomposição na UI
│
JUNHO 2026
├── Fase 3: Justificativa LLM — o maior diferenciador do produto
├── Fase 4: Diagnóstico LLM da carteira
│
JULHO 2026
├── Fase 5: Spread NTN-B (nova fonte BCB SGS)
├── Fase 6: Comparativo com pares
│
AGOSTO 2026
├── Fase 7: Histórico de recomendações versionado
├── Fase 8: Relatório exportável HTML
│
SETEMBRO 2026+
└── Fase 9: Dados qualitativos (vacância, WAULT, LTV)
```

---

## 6. Decisões de Design

**O score numérico NÃO substitui o motor estatístico.**
O motor atual (P/VP percentil + walk-forward + episódios + thinning + bootstrap) é o que tem
validade estatística. O score 0–100 é uma *camada de comunicação* — torna a saída inteligível
para o usuário sem comprometer o rigor do sinal.

**A justificativa LLM NÃO decide o sinal.**
O LLM recebe o sinal já decidido e gera o texto. Guardrails impedem linguagem de certeza.
Se o Anthropic falhar, fallback é template estático com os dados crus.

**Métricas de risco entram como CONTEXTO antes de entrar como SINAL.**
Nas Fases 1–2, volatilidade e beta aparecem na UI e no score. Só depois de validar empiricamente
se eles predizem retornos nos FIIs monitorados é que entram nos sinais do recommender.
Regra do CLAUDE.md: separar inferência estatística de comunicação operacional.

**beta_vs_ifix retorna None enquanto benchmark_diario não tiver dados do IFIX.**
O IFIX precisa ser coletado via brapi separadamente. A função está correta — é o banco que precisa
ser populado com dados IFIX antes que o beta funcione.

---

## 7. Dívidas Técnicas Conhecidas

| Item | Onde está | O que falta |
|---|---|---|
| IFIX no banco | `benchmark_diario` vazio para IFIX | Coletar via brapi (`ingestion.py`) |
| Alavancagem no sinal | `features/fundamentos.py` | Adicionar como flag suave no recommender |
| Pesos score por tipo | `features/score.py` (Fase 2) | Calibrar quando universo > 15 FIIs |
| Custos reais de transação | `models/trade_simulator.py` | Emolumentos B3 (0.03%), IR 20% |
| Vacância automática | Fase 9 | Pipeline PDF → LLM → JSON |
| Config reconciliação | `config.py` + `config.yaml` | Unificar em único ponto |
| Testes automatizados | `tests/` (vazio) | Cobertura mínima das features de score |
