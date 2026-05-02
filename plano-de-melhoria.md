# Plano de Melhoria — FII Analytics

> **Baseado em:** auditoria técnica completa do código + análise do `PROJETO-completo.md`
> **Data:** 2026-05-02
> **Objetivo:** fechar o gap entre o que o projeto visiona e o que realmente está implementado.

---

## 1. Diagnóstico Honesto do Estado Atual

### O que o motor realmente faz

Os três sinais do `decision/recommender.py` são, na prática, **todos baseados em P/VP percentil**:

| Sinal | Feature principal | Feature secundária |
|---|---|---|
| Sinal Otimizador | P/VP percentil rolling (p10–p25 = BUY) | DY Gap percentil (< p25–35 = SELL) + meses_alerta |
| Sinal Episódio | P/VP percentil fixo (p10 = BUY, p90 = SELL) | — |
| Sinal Walk-Forward | P/VP percentil (p15/p85 calculado no treino) | — |

**Concordância** é uma contagem heurística (2/3 ou 3/3 concordam), não um score estatístico. O resultado final — COMPRAR / VENDER / AGUARDAR / EVITAR — é derivado dessas contagens mais um veto manual em caso de destruição de capital.

Isso é **tecnicamente sólido** (validação out-of-sample, thinning, bootstrap), mas **estatisticamente estreito**: o sistema avalia se o P/VP está no percentil baixo ou alto, pouco mais que isso.

### O que não existe

| Feature | Status |
|---|---|
| Volatilidade anualizada | ❌ Não implementada |
| Beta vs IFIX | ❌ Apenas diagnóstico CDI (não altera ação) |
| Maximum Drawdown real | ❌ Só min(fwd_ret) nos episódios |
| Liquidez 21d como input decisório | ❌ Existe no radar mas não entra no sinal |
| DY 3m anualizado | ❌ Só 12m/24m/60m |
| Retorno total 12m | ❌ Ausente |
| Yield on Cost (YoC) | ❌ Ausente |
| Spread sobre NTN-B | ❌ Ausente |
| Score numérico 0–100 | ❌ Só categorias (ALTA/MÉDIA/BAIXA/VETADA) |
| Justificativa em linguagem natural (LLM) | ❌ Ausente — diferenciador central do produto |
| Diagnóstico LLM da carteira | ❌ Ausente |
| Comparativo com pares do segmento | ❌ Ausente |
| Histórico de recomendações versionado | ❌ Ausente |
| Vacância / WAULT / LTV | ❌ Ausente (dados qualitativos) |
| Alavancagem no sinal | ❌ Calculada mas não ativa na decisão |

### O que funciona bem e não deve ser tocado

- Validação estatística dos sinais P/VP (thinning, bootstrap, placebo, Bonferroni) ✅
- Walk-forward rolling out-of-sample genuíno ✅
- Flags de saúde (destruição capital, emissões, veto BUY) ✅
- Pipeline de snapshots diários (`generate_daily_snapshots.py`) ✅
- Arquitetura limpa `src/features` → `src/decision` → `app/pages` ✅

---

## 2. Gap vs Visão do PROJETO-completo.md

O documento propõe um produto com cinco dimensões de análise por FII:

```
Output = ⟨Sinal, Convicção, Justificativa, Score Decomosto, Alertas⟩
```

Hoje temos Sinal + Convicção + Alertas. Faltam **Justificativa** e **Score Decomposto** — as peças que transformam o dado em decisão comunicável.

---

## 3. Fases de Melhoria

### Fase 1 — Métricas de Risco e Retorno
**Estimativa: 3–4 dias | Pré-requisito de todas as fases seguintes**

Criar `src/fii_analysis/features/risk_metrics.py` com funções puras, zero side-effects, zero print.

**Funções a implementar:**

```python
def volatilidade_anualizada(ticker: str, janela: int = 252, session=None) -> float | None:
    """σ_diário × √252. Mínimo 63 pregões. Usa fechamento_aj."""

def beta_vs_ifix(ticker: str, janela: int = 252, session=None) -> float | None:
    """Cov(R_FII, R_IFIX) / Var(R_IFIX). Usa benchmark_diario (já está no schema)."""

def max_drawdown(ticker: str, janela: int = 504, session=None) -> float | None:
    """MDD = max((Pt - max(P_s, s≤t)) / max(P_s, s≤t)). Retorna negativo."""

def liquidez_media_21d(ticker: str, session=None) -> float | None:
    """Média(volume × fechamento) dos últimos 21 pregões. Em R$."""

def retorno_total_12m(ticker: str, session=None) -> float | None:
    """(P_t - P_{t-12m} + Σdiv_12m) / P_{t-12m}."""

def dy_3m_anualizado(ticker: str, session=None) -> float | None:
    """Σ(dividendos_3m) × 4 / preço_atual."""

def yield_on_cost(ticker: str, preco_medio: float, session=None) -> float | None:
    """Σ(dividendos_12m) / preco_medio. Só calcula quando PM disponível."""
```

**Integração:**
- Adicionar colunas em `SnapshotTickerMetrics`: `volatilidade_anual`, `beta_ifix`, `max_drawdown`, `liquidez_21d_brl`, `retorno_total_12m`, `dy_3m_anualizado`
- Exibir nas páginas `7_Fundamentos.py` e `14_Dossie_FII.py`

**Testes mínimos esperados:** para KNIP11, volatilidade > 0, beta entre -2 e 2, liquidez > R$ 100k.

---

### Fase 2 — Score Numérico 0–100 com Decomposição Visual
**Estimativa: 3–4 dias | Depende da Fase 1**

Criar `src/fii_analysis/features/score.py`.

**Arquitetura do score:**

```
Score(FII) = 0,35 × ScoreValuation
           + 0,30 × ScoreRisco
           + 0,20 × ScoreLiquidez
           + 0,15 × ScoreHistórico
```

Pesos únicos por enquanto (sem diferenciação Tijolo/Papel — implementar depois de validar com dados reais).

**Sub-scores (0–100 cada):**

```python
# ScoreValuation: P/VP percentil invertido + DY Gap percentil
# P/VP baixo = bom → score alto
# DY Gap alto = bom → score alto
def score_valuation(pvp_percentil, dy_gap_percentil) -> int:
    pvp_score = 100 - pvp_percentil          # p10 → 90 pts; p80 → 20 pts
    gap_score = dy_gap_percentil              # p80 → 80 pts; p10 → 10 pts
    return round(0.6 * pvp_score + 0.4 * gap_score)

# ScoreRisco: volatilidade, beta, drawdown — todos penalizam quando altos
# Normalizar contra o universo dos FIIs monitorados (percentil relativo)
def score_risco(vol_percentil, beta_abs_percentil, mdd_abs_percentil) -> int:
    return round(100 - (0.4 * vol_percentil + 0.3 * beta_abs_percentil + 0.3 * mdd_abs_percentil))

# ScoreLiquidez: liquidez 21d em escala log, normalizada
# < R$ 200k = 20 pts; 200k–1M = 50 pts; > R$ 1M = 80+ pts
def score_liquidez(liquidez_21d_brl) -> int: ...

# ScoreHistórico: consistência do DY 24m — coef. variação invertido
# CV = std(DY_mensal_24m) / mean(DY_mensal_24m)
# CV baixo = DY consistente = score alto
def score_historico(ticker, session) -> int: ...
```

**Dataclass de resultado:**

```python
@dataclass
class ScoreFII:
    ticker: str
    data_referencia: date
    score_total: int           # 0–100
    score_valuation: int
    score_risco: int
    score_liquidez: int
    score_historico: int
    sinal_score: str           # "COMPRAR" (≥80), "MANTER" (65–79), etc.
    conviccao_score: str       # "ALTA" (sub-scores convergem), etc.
```

**Integração:**
- `SnapshotTickerMetrics`: nova coluna `score_total`, `score_breakdown` (JSON)
- `SnapshotDecisions`: coluna `score_fii` ligada ao score calculado
- UI em `14_Dossie_FII.py`: barras horizontais Plotly por sub-score
- UI em `13_Hoje.py`: badge colorido com o score total ao lado do badge COMPRAR/EVITAR

**Notas críticas:**
- O score **não substitui** o motor estatístico atual. É uma camada paralela de *comunicação*.
- A ação final continua sendo derivada dos 3 sinais + flags. O score serve para a UI e para a justificativa LLM.
- Documentar explicitamente que score ≥ 80 ≠ sinal COMPRAR — podem divergir quando walk-forward diz NEUTRO.

---

### Fase 3 — Justificativa em Linguagem Natural (LLM)
**Estimativa: 2–3 dias | Depende da Fase 2 | MAIOR IMPACTO para o usuário**

Criar `src/fii_analysis/decision/justifier.py`.

**Arquitetura:**

```python
from anthropic import Anthropic

def gerar_justificativa(
    decision: TickerDecision,
    score: ScoreFII | None = None,
    holding: HoldingAdvice | None = None,
    cache: dict | None = None,    # dict mutável para cache em memória
) -> str:
    """
    Gera 3–6 frases em PT-BR explicando a recomendação.
    
    Não decide o sinal — apenas comunica o que já foi decidido.
    Cache por hash(ação + concordância + pvp_percentil + dy_gap_percentil).
    Se Anthropic falhar, retorna template estático com os dados crus.
    """
```

**Prompt template** (baseado na especificação do PROJETO-completo.md):

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
2. Cite no máximo 3 indicadores, com valores numéricos reais dos dados acima.
3. Mencione 1 risco mesmo em ações positivas.
4. Linguagem clara, sem jargão sem explicação.
5. NÃO use: "garantido", "certeza", "infalível", "recomendo fortemente".
6. Tom sóbrio, sem exclamações.
7. Entre 3 e 6 frases. Não passe disso.

Devolva APENAS o texto da justificativa, sem cabeçalho.
```

**Guardrails pós-geração:**
- Comprimento: 150–600 caracteres → se fora, refazer com prompt reforçado, senão template estático
- Palavras proibidas (regex): `garanti|certez|infalív|vai subir|vai cair|lucro cert`
- Validação: deve conter pelo menos 1 número presente nos dados de input

**Cache:**
- Chave: `md5(f"{ticker}|{acao}|{nivel_concordancia}|{pvp_pct:.0f}|{dy_gap_pct:.0f}")`
- Persistência: coluna `justificativa_llm` e `justificativa_hash` em `SnapshotDecisions`
- Regenerar apenas quando hash muda (economia de ~90% de tokens)

**Integração UI:**
- `13_Hoje.py`: expandir card de cada ação para mostrar justificativa (colapsável)
- `14_Dossie_FII.py`: seção de destaque na aba "Análise"

**Modelo:** Claude Haiku 4.5 por padrão. Fallback: template estático formatado com os dados crus.

---

### Fase 4 — Diagnóstico LLM da Carteira
**Estimativa: 1–2 dias | Depende das Fases 2 e 3**

Criar `src/fii_analysis/decision/portfolio_diagnostics.py`.

**O que faz:**
- Recebe todos os `HoldingAdvice` + `AlertaEstrutural` + scores individuais
- Calcula `score_carteira`: média ponderada pelo valor de mercado dos scores individuais
- Chama LLM para gerar 1 parágrafo de diagnóstico da carteira como um todo

**Prompt:**
```
Você é um analista de FIIs resumindo o estado de uma carteira de investimentos.

Carteira: {n_holdings} FIIs
Composição: {segmentos_pct}
Score médio ponderado: {score_carteira}/100
Ações prioritárias: {n_comprar} COMPRAR, {n_reduzir} REDUZIR/SAIR, {n_manter} MANTER
Maior posição: {top_holding} ({top_peso:.1f}%)
Alertas estruturais: {alertas}

Escreva 3–5 frases descrevendo a saúde da carteira. 
Mencione 1 ponto forte e 1 ponto de atenção. 
Não cite nomes de FIIs específicos — fale de segmentos e métricas.
Tom: técnico, sóbrio, sem promessas.
```

**Integração UI:**
- `13_Hoje.py`: painel de topo, antes das ações individuais
- `3_Carteira.py`: nova seção "Diagnóstico da Carteira"

**Novo campo em `SnapshotPortfolioAdvices`:** `score_carteira`, `diagnostico_llm`, `diagnostico_hash`

---

### Fase 5 — Spread sobre NTN-B
**Estimativa: 2 dias | Independente das outras fases**

**Por que:** o DY Gap atual usa CDI como benchmark. O CDI representa risco de crédito zero.
Para FIIs (ativos reais), o benchmark mais relevante é NTN-B (IPCA+), que é o que
gestores de tijolo e papel competem contra na alocação de capital.

**Implementação:**

```python
# src/fii_analysis/data/ingestion.py — adicionar função
def get_ntnb_bcb(anos_vencimento: int = 5) -> pd.DataFrame:
    """
    BCB SGS série 12466 (NTN-B 5a) ou 12464 (NTN-B 2a).
    Retorna DataFrame com data, ytm_real_aa (yield IPCA+, em %).
    """

# Nova tabela: benchmark_ntnb (data, ytm_real_aa, fonte)
```

**Cálculo:**
```python
spread_ntnb = DY_12m - YTM_NTNB_vigente
# Positivo = FII oferece prêmio vs renda fixa real
# Negativo = renda fixa real é mais atraente
```

**Integração:**
- `SnapshotTickerMetrics`: coluna `spread_ntnb_pp` (em pontos percentuais)
- `ScoreValuation`: substituir componente CDI por NTN-B quando disponível
- `7_Fundamentos.py`: gráfico de série histórica do spread

---

### Fase 6 — Comparativo com Pares do Segmento
**Estimativa: 2–3 dias | Depende das Fases 1 e 2**

**O que faz:** tabela side-by-side de todos os FIIs ativos por segmento (Papel, Tijolo, Híbrido),
com ranking por score, mostrando as métricas principais.

**Implementação:**

```python
# src/fii_analysis/features/peer_comparison.py
def comparar_pares(tickers: list[str], session=None) -> pd.DataFrame:
    """
    Retorna DataFrame com uma linha por ticker e colunas:
    ticker, segmento, pvp_atual, pvp_percentil, dy_12m, dy_gap_percentil,
    score_total, acao, concordancia, volatilidade, liquidez_21d_brl
    Ordenado por score_total DESC.
    """
```

**Integração UI:**
- Nova aba "Comparar" em `14_Dossie_FII.py`
- `4_Radar.py`: expandir a matriz booleana para mostrar ranking por score

---

### Fase 7 — Histórico de Recomendações Versionado
**Estimativa: 2–3 dias | Depende da Fase 3**

**Por que:** permite ao usuário ver como a recomendação evoluiu no tempo, gerando confiança
e auditabilidade. O PROJETO-completo.md coloca isso como item de V1.

**Nova tabela:**

```sql
recommendation_history (
    id          INTEGER PRIMARY KEY,
    ticker      TEXT,
    data_ref    DATE,
    acao        TEXT,           -- COMPRAR / VENDER / AGUARDAR / EVITAR
    badge       TEXT,           -- AUMENTAR / REDUZIR / HOLD / SAIR
    concordancia TEXT,
    score_total  INTEGER,
    justificativa TEXT,
    pvp_snapshot REAL,
    dy_gap_snapshot REAL,
    criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Lógica:** a cada `generate_daily_snapshots.py`, gravar na tabela somente quando a ação ou badge mudou vs o registro anterior (diff-based).

**Integração UI:**
- `14_Dossie_FII.py`: nova aba "Histórico" com timeline de mudanças de ação
- `13_Hoje.py`: badge "Mudou ontem" quando ação mudou no último snapshot

---

### Fase 8 — Relatório Exportável (Markdown / HTML)
**Estimativa: 2 dias | Depende das Fases 3 e 4**

`export_daily_report_md()` já existe em `decision/daily_report.py`. Ampliar:

```python
def export_report_html(report: DailyCommandCenter, holdings: list) -> str:
    """
    Relatório HTML formatado com:
    - Diagnóstico da carteira (LLM)
    - Cards por FII com score, justificativa, indicadores
    - Alertas estruturais
    - Data de geração + disclaimer CVM
    Usando Jinja2 template (dependência já disponível via Streamlit)
    """
```

**Integração UI:**
- Botão "Exportar Relatório" em `13_Hoje.py`
- Download como `.html` (abre no browser) ou `.md`

---

### Fase 9 — Dados Qualitativos (Vacância, WAULT, LTV)
**Estimativa: 1–2 semanas | Longo prazo | Alta complexidade**

Estes dados vêm de relatórios gerenciais (PDFs das gestoras). Pipeline:

1. **Coleta manual inicial** (para os 5 FIIs monitorados): CSV com os campos-chave preenchidos manualmente, atualizado trimestralmente. Custo: ~1h/trimestre.

2. **Nova tabela `fii_qualitativo`**:
   ```sql
   (cnpj, data_referencia, vacancia_fisica_pct, vacancia_financeira_pct,
    wault_anos, ltv_pct, top_inquilino_pct, indexador_predominante, fonte)
   ```

3. **Integração no ScoreQualidade** (novo sub-score na Fase 2+):
   - Tijolo: vacância baixa + WAULT alto = qualidade alta
   - Papel: LTV < 60% + indexador IPCA+ = qualidade alta

4. **Automação futura (V2):** pipeline LLM com extração de PDF via Claude Vision.

---

## 4. Roadmap Consolidado

```
MAIO 2026
├── Fase 1: Métricas de Risco (vol, beta, drawdown, liquidez, DY3m, retorno12m, YoC)
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
└── Fase 9: Dados qualitativos (vacância, WAULT, LTV) — coleta manual → automação
```

---

## 5. Impacto Esperado por Fase

| Fase | Impacto na decisão | Impacto na UX | Esforço |
|---|---|---|---|
| 1 — Métricas de risco | Médio (enriquece contexto) | Alto (novas métricas visíveis) | Baixo |
| 2 — Score 0-100 | Médio (camada comunicacional) | Muito alto (clareza visual) | Baixo |
| 3 — Justificativa LLM | Nenhum no sinal, alto na compreensão | **Transformador** | Baixo |
| 4 — Diagnóstico carteira LLM | Nenhum no sinal | Alto | Baixo |
| 5 — Spread NTN-B | Alto (melhora ScoreValuation) | Médio | Médio |
| 6 — Comparativo pares | Nenhum no sinal | Alto | Médio |
| 7 — Histórico versionado | Nenhum no sinal | Alto (confiança) | Médio |
| 8 — Relatório exportável | Nenhum | Médio | Baixo |
| 9 — Vacância/WAULT/LTV | **Alto** (ScoreQualidade real) | Alto | Alto |

---

## 6. Decisões de Design

**O score numérico NÃO substitui o motor estatístico.**
O motor atual (P/VP percentil + walk-forward + episódios + thinning + bootstrap) é o que tem
validade estatística. O score 0–100 é uma *camada de comunicação* — torna a saída inteligível
para o usuário sem comprometer o rigor do sinal.

**A justificativa LLM NÃO decide o sinal.**
O LLM recebe o sinal já decidido e gera o texto. Guardrails impedem que o texto contradiga o
sinal ou use linguagem de certeza. Se o Anthropic falhar, fallback é template estático com dados.

**Métricas de risco entram como CONTEXTO antes de entrar como SINAL.**
Nas Fases 1 e 2, volatilidade e beta aparecem no score e na UI. Só depois de validar empiricamente
se eles predizem retornos nos 5 FIIs monitorados é que entram nos sinais do recommender.
Regra do CLAUDE.md: separar inferência estatística de comunicação operacional.

**Pesos do score são fixos por agora, ajustáveis por tipo em Fase futura.**
O PROJETO-completo.md propõe pesos diferentes por tipo (Tijolo/Papel/FoF). Com apenas 5 FIIs,
não há amostra suficiente para calibrar pesos por tipo. Implementar peso único e documentar
como dívida técnica a ser revisada quando o universo crescer.

---

## 7. Dívidas Técnicas Conhecidas

| Item | Onde está | O que falta |
|---|---|---|
| Alavancagem no sinal | `features/fundamentos.py` | Adicionar como flag suave no recommender |
| Pesos score por tipo | `features/score.py` (Fase 2) | Calibrar quando universo > 15 FIIs |
| Custos reais de transação | `models/trade_simulator.py` | Emolumentos B3 (0.03%), IR 20% |
| Slippage | `models/trade_simulator.py` | Spread bid-ask para fundos ilíquidos |
| Vacância automática | Fase 9 | Pipeline PDF → LLM → JSON |
| Config reconciliação | `config.py` + `config.yaml` | Unificar em único ponto |
| Testes automatizados | `tests/` (vazio) | Cobertura mínima das features de score |
