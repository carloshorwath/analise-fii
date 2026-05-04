# PLANO DE IMPLEMENTAÇÃO — Motor de Recomendação V2

**Versão:** 1.0  
**Data:** 2026-05-04  
**Status:** Aprovado para execução  
**Responsável:** Carlos Horwath  

---

## Resumo Executivo

O motor de recomendação atual foi auditado com base em três documentos de pesquisa
produzidos por análise do código existente, práticas da indústria brasileira de FIIs
e metodologias consolidadas de análise de REITs internacionais. A auditoria confirmou
o diagnóstico dos investidores: o modelo tem **hiperfoco em P/VP** e um **grid de
thresholds subamostrado** que nunca testou cenários básicos como comprar em percentil 40
e vender em 80.

Este plano organiza a evolução em três fases sequenciais com critérios de aceite
mensuráveis e verificáveis. Cada fase entrega valor independente — a Fase 1 pode ser
demonstrada aos investidores em até duas semanas sem esperar as fases seguintes.

**Premissa inegociável:** nenhuma mudança viola as regras de separação treino/validação/teste
nem introduz data leakage. O ganho estatístico de cada novo sinal deve ser validado
fora do conjunto de treino.

---

## 1. Diagnóstico do Estado Atual

### 1.1 O que o motor usa hoje

| Modo | Lógica Central | Features de Entrada |
|------|---------------|---------------------|
| Otimizador (`ThresholdOptimizerV2`) | Grid search de percentil P/VP | P/VP percentil, DY Gap percentil, meses_alerta |
| Episódios (`episodes.py`) | P/VP em zona extrema por N dias | P/VP percentil histórico |
| Walk-Forward (`walk_forward_rolling.py`) | Consistência do sinal P/VP ao longo do tempo | P/VP percentil, retorno forward 20 dias |
| Score (`score.py`) | Comunicação 0–100 | P/VP percentil, DY Gap, volatilidade, liquidez |

**Grid atual do otimizador:**
```python
pvp_percentil_buy_grid  = [15, 20, 25]       # 3 pontos
pvp_percentil_sell_grid = [65, 70, 75]       # 3 pontos
# = 9 combinações testadas (das quais ~6 passam no filtro spread≥15)
```

### 1.2 Dados disponíveis no banco que NÃO são usados

| Tabela | Colunas ignoradas | Sinal potencial |
|--------|-------------------|-----------------|
| `PrecoDiario` | `volume`, `abertura`, `maxima`, `minima` | Queda com volume alto, volatilidade intraday |
| `RelatorioMensal` | `pl`, `cotas_emitidas`, `rentab_efetiva`, `rentab_patrim`, `dy_mes` | PL trend, divergência rentabilidade, momentum DY |
| `AtivoPassivo` | `total_passivo`, `total_ativo`, `cri_cra`, `disponibilidades` | LTV, alavancagem oculta, composição |

### 1.3 Consequências do hiperfoco atual

1. **Falsos sinais de compra em sell-off:** Uma queda de P/VP por pressão vendedora
   institucional (volume 3× acima da média) é tratada igual a uma queda em dia sem
   liquidez. São situações opostas; o modelo não as distingue.

2. **Armadilhas de dividendo não detectadas:** Fundos com rentabilidade efetiva
   sistematicamente acima da patrimonial estão distribuindo capital — não renda. O
   motor não penaliza isso hoje.

3. **Grid de thresholds cego:** Com apenas 9 combinações, o modelo nunca testou se
   estratégias de rotação mais frequente (comprar em percentil 40, vender em 65)
   seriam mais ou menos rentáveis. Isso é exatamente o que os investidores perguntam.

---

## 2. Arquitetura do Motor V2

O Motor V2 preserva a separação em camadas existente e adiciona dois novos módulos
de features puras em `src/fii_analysis/features/`.

```
Motor V2 — fluxo de dados

PrecoDiario (volume, OHLCV)
RelatorioMensal (PL, rentab, DY)         ┐
AtivoPassivo (passivo, CRI, caixa)        ├─► features/volume_signals.py
CdiDiario (CDI diário)                    │   features/momentum_signals.py
IFIX (benchmark diário — Fase 3)          ┘   features/valuation.py (P/VP Z-score)
                                               features/score.py (atualizado)
                                                        │
                                                        ▼
                                     models/threshold_optimizer_v2.py
                                     (grid expandido + novos eixos)
                                                        │
                                                        ▼
                                     decision/recommender.py
                                     (novos campos em TickerDecision)
                                                        │
                                                        ▼
                                     evaluation/daily_snapshots.py
                                     app/pages/ (UI heatmap — Fase 3)
```

**Regra de ouro:** qualquer função nova que calcule um sinal vive em `src/fii_analysis/features/`
ou `src/fii_analysis/models/`. Zero `print()`, zero Streamlit, retorna dado estruturado.

---

## 3. Fases de Implementação

---

### FASE 1 — Quick Wins
**Prazo:** 1–2 semanas  
**Objetivo:** Corrigir os dois problemas mais visíveis aos investidores com o mínimo de risco.

---

#### F1.1 — Expansão do Grid de Thresholds

**Arquivo:** `src/fii_analysis/models/threshold_optimizer_v2.py`, linhas 38–43

**O que muda:**
```python
# ANTES
pvp_percentil_buy_grid  = [15, 20, 25]
pvp_percentil_sell_grid = [65, 70, 75]

# DEPOIS
pvp_percentil_buy_grid  = [15, 20, 25, 30, 35, 40, 45, 50]
pvp_percentil_sell_grid = [55, 60, 65, 70, 75, 80, 85, 90]
```

Adicionar filtro de spread mínimo no loop de grid search:
```python
# No itertools.product — ignorar combinações sem spread suficiente
if sell_pct - buy_pct < 15:
    continue
```

Isso expande de 9 para **~36 combinações válidas** (8×8 = 64 menos as que têm spread < 15).

**Critérios de aceite — F1.1:**
- [ ] `ThresholdOptimizerV2.__init__` contém os 8 valores de buy e os 8 de sell
- [ ] Loop de otimização executa sem erro para todos os tickers ativos
- [ ] Número de combinações testadas por ticker ≥ 30 (verificável em log)
- [ ] `best_params` retornado contém `pvp_buy_pct` e `pvp_sell_pct` sem valores duplicados
- [ ] Tempo de execução por ticker < 120 segundos (benchmark atual de referência)
- [ ] Resultados incluem pelo menos 1 combinação com `buy_pct ≥ 35` nos melhores 5 do ranking

---

#### F1.2 — Sinal de Queda com Volume Qualificado

**Novo arquivo:** `src/fii_analysis/features/volume_signals.py`

**Funções a implementar:**

```python
def get_volume_drop_flag(
    ticker: str,
    target_date: date,
    session: Session,
    queda_min_pct: float = -0.02,   # queda ≥ 2% no dia
    volume_multiplier: float = 1.5,  # volume ≥ 1.5× média 21d
    window_days: int = 21
) -> bool:
    """
    Retorna True se na data houver queda de preço significativa
    associada a volume acima da média — sinal de pressão vendedora real.
    Usa PrecoDiario.fechamento_aj e PrecoDiario.volume.
    """

def get_vol_ratio_21_63(
    ticker: str,
    target_date: date,
    session: Session
) -> float | None:
    """
    Razão entre volume médio dos últimos 21 pregões e dos últimos 63.
    Razão < 0.7 indica perda de liquidez recente.
    """

def get_volume_profile(
    ticker: str,
    target_date: date,
    session: Session
) -> dict:
    """
    Retorna dict com: is_high_volume_drop, vol_ratio_21_63,
    adtv_21d_brl, adtv_63d_brl.
    """
```

**Integração em `recommender.py`:**
- Adicionar `flag_volume_queda_forte: bool` em `TickerDecision`
- Adicionar `vol_ratio_21_63: float | None` em `TickerDecision`
- Em `decidir_ticker()`: se `flag_volume_queda_forte=True`, upgrade de risco para VETADA quando sinal for BUY

**Critérios de aceite — F1.2:**
- [ ] `get_volume_drop_flag` retorna `False` em dias com volume abaixo da média (verificar com dados reais de KNIP11)
- [ ] `get_volume_drop_flag` retorna `True` em pelo menos 1 dia de sell-off conhecido no histórico (verificar manualmente no banco)
- [ ] `get_volume_profile` retorna dict completo sem `KeyError` para qualquer ticker ativo
- [ ] `TickerDecision` tem campos `flag_volume_queda_forte` e `vol_ratio_21_63`
- [ ] Relatório diário (`scripts/daily_report.py`) imprime os novos campos sem stack trace
- [ ] Zero chamadas a `print()` ou `st.*` dentro de `volume_signals.py`

---

#### F1.3 — Flag de LTV (Alavancagem)

**Arquivo:** `src/fii_analysis/features/saude.py` (adicionar função)

```python
def get_ltv_flag(
    ticker: str,
    target_date: date,
    session: Session,
    limite_ltv: float = 0.20   # passivo/ativo > 20% = alavancado para FII
) -> tuple[bool, float | None]:
    """
    Retorna (flag_alavancado, ltv_atual).
    Usa AtivoPassivo.total_passivo e RelatorioMensal para PL.
    LTV = total_passivo / (total_passivo + pl)
    """
```

**Critérios de aceite — F1.3:**
- [ ] Função retorna `(False, ltv)` para FIIs de papel sem dívida significativa
- [ ] Integrada em `TickerDecision` como `flag_ltv_alto: bool` e `ltv_atual: float | None`
- [ ] `flag_ltv_alto=True` eleva nivel de risco para qualquer sinal BUY
- [ ] Cobertura mínima: calcula para ≥ 4 dos 6 tickers ativos (SNFF11 inativo excluído)

---

#### Critérios de Aceite — FASE 1 (gate para Fase 2)

| Critério | Métrica | Mínimo |
|----------|---------|--------|
| Grid expandido funcional | Combinações válidas testadas | ≥ 30 por ticker |
| Sem regressão de sinais | Saída de `decidir_universo()` sem erro | 6/6 tickers |
| Novos campos em snapshot | Colunas em `snapshot_decisions` | +3 campos novos |
| Cobertura de dados volume | Tickers com `vol_ratio_21_63` calculado | ≥ 4/6 |
| Testes sem leakage | MCP `detect_leakage` | Zero violações |
| Performance do otimizador | Tempo por ticker full grid | < 180s |

---

### FASE 2 — Sinais Fundamentalistas
**Prazo:** 3–5 semanas após Fase 1  
**Objetivo:** Incorporar informações do balanço mensal CVM que o modelo ignora completamente.

---

#### F2.1 — Módulo de Momentum Fundamentalista

**Novo arquivo:** `src/fii_analysis/features/momentum_signals.py`

```python
def get_pl_trend(
    ticker: str,
    target_date: date,
    session: Session,
    months: int = 3
) -> str:
    """
    Avalia tendência do Patrimônio Líquido nos últimos N meses.
    Retorna: 'CRESCENDO' | 'ESTAVEL' | 'CAINDO'
    Usa RelatorioMensal.pl filtrado por data_entrega <= target_date.
    'CAINDO' = 3 meses consecutivos de queda do PL/cota.
    """

def get_rentab_divergencia(
    ticker: str,
    target_date: date,
    session: Session,
    meses: int = 6,
    tolerancia: float = 0.01   # 1% de diferença mensal acumulada
) -> tuple[bool, float | None]:
    """
    Detecta divergência sistemática entre rentabilidade efetiva e patrimonial.
    Retorna (flag_divergencia, media_divergencia_6m).
    Divergência positiva acumulada > tolerancia*meses indica
    distribuição acima do ganho real — armadilha de dividendo.
    """

def get_dy_momentum(
    ticker: str,
    target_date: date,
    session: Session
) -> float | None:
    """
    Retorna DY médio 3m - DY médio 12m (em pontos percentuais).
    Positivo = DY acelerando (sinal favorável).
    Negativo = DY desacelerando (alerta).
    Usa RelatorioMensal.dy_mes filtrado por data_entrega.
    """

def get_meses_dy_acima_cdi(
    ticker: str,
    target_date: date,
    session: Session,
    janela_meses: int = 12
) -> int:
    """
    Conta meses nos últimos 12 em que o DY anualizado superou o CDI.
    Retorna inteiro 0–12. Fonte: RelatorioMensal.dy_mes × 12 vs CdiDiario.
    """
```

**Critérios de aceite — F2.1:**
- [ ] `get_pl_trend('KNIP11', date(2024,6,1), session)` retorna valor válido (verificar manualmente)
- [ ] `get_rentab_divergencia` retorna `(False, valor)` para fundo saudável e `(True, valor)` para fundo em destruição patrimonial (validar com dados históricos reais)
- [ ] `get_dy_momentum` retorna `None` quando há menos de 12 relatórios disponíveis (graceful degradation)
- [ ] `get_meses_dy_acima_cdi` retorna valor coerente com CDI histórico (cruzar com `CdiDiario`)
- [ ] Todas as funções respeitam point-in-time via `data_entrega <= target_date`

---

#### F2.2 — P/VP Z-Score (Reversão à Média do Próprio Fundo)

**Arquivo:** `src/fii_analysis/features/valuation.py` (adicionar função)

```python
def get_pvp_zscore(
    ticker: str,
    target_date: date,
    session: Session,
    janela: int = 756   # 3 anos de pregões
) -> float | None:
    """
    Z-score do P/VP atual contra a série histórica do próprio fundo.
    z = (pvp_atual - média_histórica) / desvio_padrão_histórico
    Z-score < -1.5 indica desconto atípico — potencial zona de reversão.
    Z-score > +1.5 indica prêmio atípico — zona de venda.
    Retorna None se histórico < 252 pregões.
    """
```

**Critérios de aceite — F2.2:**
- [ ] Z-score de KNIP11 em períodos de P/VP historicamente baixo é negativo
- [ ] Z-score de KNIP11 em períodos de P/VP historicamente alto é positivo
- [ ] Retorna `None` para tickers com histórico < 252 pregões (GARE11, SNEL11 podem cair aqui)
- [ ] Adicionado como `pvp_zscore: float | None` em `TickerDecision`

---

#### F2.3 — Integração no Otimizador e Score

**Arquivo:** `models/threshold_optimizer_v2.py`

Expandir `_get_enriched_daily_data` para incluir:
- `volume` (PrecoDiario)
- `pl` mensal (via join point-in-time com RelatorioMensal)
- `rentab_efetiva`, `rentab_patrim` (já no query — **garantir que chegam ao DataFrame**)
- `dy_mes` (RelatorioMensal)

Adicionar coluna `volume_drop_flag` e `pl_trend_flag` como features binárias no DataFrame enriquecido.
Estas features são usadas como **filtros de exclusão** — dias com `volume_drop_flag=True`
são removidos dos candidatos a BUY antes do grid search.

**Arquivo:** `features/score.py`

Atualizar `score_valuation` para incluir P/VP Z-score (novo eixo, peso 20% do sub-score valuation):
```
ScoreValuation = 0.50 × (100 - pvp_percentil) + 0.30 × dy_gap_percentil + 0.20 × pvp_zscore_score
```
onde `pvp_zscore_score = max(0, min(100, 50 - pvp_zscore * 20))`.

**Critérios de aceite — F2.3:**
- [ ] DataFrame enriquecido contém colunas: `volume`, `volume_drop_flag`, `pl_trend`, `rentab_div`
- [ ] Grid search exclui corretamente dias com `volume_drop_flag=True` dos candidatos BUY
- [ ] Score de valuation muda quando P/VP Z-score é extremo (delta > 5 pontos no score)
- [ ] Sem alteração no significado estatístico de `p_value_buy` — é calculado sobre amostra filtrada, não bruta

---

#### Critérios de Aceite — FASE 2 (gate para Fase 3)

| Critério | Métrica | Mínimo |
|----------|---------|--------|
| Cobertura de novos sinais | Tickers com `get_pl_trend` calculado | ≥ 5/6 |
| Cobertura de novos sinais | Tickers com `get_rentab_divergencia` calculado | ≥ 5/6 |
| Qualidade estatística | Correlação `pl_trend_flag` × retorno 20d no set de teste | p < 0.15 (sinal fraco aceito) |
| Qualidade estatística | Correlação `volume_drop_flag` × retorno 20d no set de teste | p < 0.15 |
| Anti-leakage | MCP `validate_split` e `detect_leakage` | Zero violações |
| Retrocompatibilidade | `decidir_universo()` retorna `TickerDecision` para todos tickers | 6/6 sem erro |
| Score atualizado | `ScoreFII.score_valuation` muda entre tickers com Z-scores distintos | Delta visível ≥ 3 pts |
| Snapshots | `generate_daily_snapshots.py` executa sem erro com novos campos | Execução limpa |

---

### FASE 3 — Qualidade Avançada e UI
**Prazo:** 6–9 semanas após Fase 1  
**Objetivo:** Adicionar os sinais mais sofisticados e tornar os resultados transparentes para os investidores na interface.

---

#### F3.1 — Momentum Relativo ao IFIX

**Pré-requisito:** Dados diários do IFIX carregados em `PrecoDiario` com `ticker='IFIX11'`
(verificar disponibilidade via brapi.dev antes de implementar).

**Arquivo:** `src/fii_analysis/features/momentum_signals.py` (adicionar função)

```python
def get_momentum_relativo_ifix(
    ticker: str,
    target_date: date,
    session: Session,
    window: int = 21   # pregões
) -> float | None:
    """
    Retorna retorno_fundo_21d - retorno_ifix_21d.
    Positivo = fundo superou benchmark (força relativa).
    Negativo = fundo perdeu para o mercado (fraqueza idiossincrática).
    Usa PrecoDiario.fechamento_aj para ambos.
    Retorna None se IFIX não estiver no banco.
    """
```

**Critérios de aceite — F3.1:**
- [ ] Função retorna `None` graciosamente se IFIX não estiver no banco (sem exception)
- [ ] Valor calculado é coerente com inspeção manual (se KNIP11 caiu 3% e IFIX subiu 1%, retorna -0.04)
- [ ] Campo `momentum_ifix_21d: float | None` adicionado em `TickerDecision`
- [ ] Momentum negativo persistente (`< -5%` em 21d) eleva flag de risco em `recommender.py`

---

#### F3.2 — Cap Rate Implícito vs NTN-B

**Arquivo:** `src/fii_analysis/features/valuation.py` (adicionar função)

```python
def get_cap_rate_spread(
    ticker: str,
    target_date: date,
    session: Session
) -> tuple[float | None, float | None]:
    """
    Retorna (cap_rate_implicito, spread_vs_ntnb).
    cap_rate_implicito = (rentab_efetiva_anualizada) / pvp
    Proxy: usa rentab_efetiva × 12 como NOI estimado e P/VP como inverso do Cap Rate.
    spread_vs_ntnb = cap_rate_implicito - yield_ntnb_longa (5 anos, obtido via BCB Focus)
    Retorna (None, None) se dados insuficientes.
    Aplicável principalmente a FIIs de Tijolo.
    """
```

**Critérios de aceite — F3.2:**
- [ ] Cap rate positivo para todos os FIIs com `rentab_efetiva > 0`
- [ ] Spread vs NTN-B é calculado usando dado de Focus BCB com ponto-no-tempo correto
- [ ] Campo `cap_rate_spread_ntnb: float | None` em `TickerDecision`
- [ ] Para FIIs de Papel (`classificacao == 'Papel'`): campo é `None` (não aplicável)

---

#### F3.3 — Dividend Safety Score

**Arquivo:** `src/fii_analysis/features/momentum_signals.py` (adicionar)

```python
def get_dividend_safety(
    ticker: str,
    target_date: date,
    session: Session,
    meses: int = 6
) -> dict:
    """
    Retorna dict com:
    - payout_vs_caixa: float | None  (dividendo / rentab_efetiva, média 6m)
    - cortes_24m: int  (número de meses com DY < DY_mes_anterior em 24 meses)
    - flag_insustentavel: bool  (payout_vs_caixa > 1.10 por 3+ meses consecutivos)
    Usa RelatorioMensal.dy_mes e rentab_efetiva com point-in-time via data_entrega.
    """
```

**Critérios de aceite — F3.3:**
- [ ] `flag_insustentavel=True` detectado em pelo menos 1 ticker histórico com corte de dividendo conhecido
- [ ] `cortes_24m` é inteiro ≥ 0 para todos os tickers ativos
- [ ] Campos adicionados em `TickerDecision`: `dividend_safety_flag`, `payout_vs_caixa`, `cortes_24m`

---

#### F3.4 — Heatmap de Thresholds na UI

**Arquivo:** `app/pages/15_Laboratorio.py` e `app/components/page_content/otimizador_v2.py`

Adicionar visualização que mostre o grid completo de combinações buy×sell como heatmap,
colorido por métrica selecionável (Sharpe OOS, win_rate, avg_return).

```python
# Estrutura da saída esperada do otimizador
{
  "grid_results": [
    {"buy_pct": 15, "sell_pct": 65, "sharpe": 0.82, "win_rate": 0.61, "n_trades": 14},
    {"buy_pct": 20, "sell_pct": 70, "sharpe": 0.75, "win_rate": 0.58, "n_trades": 18},
    ...
  ]
}
```

**Critérios de aceite — F3.4:**
- [ ] Heatmap renderiza sem erro para todos os 6 tickers ativos
- [ ] Combinação ótima (`best_params`) destacada visualmente no heatmap
- [ ] Tooltip exibe `sharpe`, `win_rate`, `n_trades` para cada célula
- [ ] Métrica selecionável via `st.selectbox` (Sharpe / Win Rate / Retorno Médio)

---

#### Critérios de Aceite — FASE 3 (gate para release V2)

| Critério | Métrica | Mínimo |
|----------|---------|--------|
| Melhoria vs baseline | Sharpe OOS Motor V2 vs Motor V1 (mesmo conjunto de teste) | V2 ≥ V1 − 0.05 (não pode regredir) |
| Win rate OOS | Win rate no conjunto de teste (fora do treino) | ≥ 0.50 |
| Degradação treino→teste | (Win rate treino − Win rate teste) / Win rate treino | < 35% |
| Cobertura de sinais | Tickers com todos os novos campos preenchidos | ≥ 5/6 |
| UI funcional | Heatmap renderizado sem erro | 6/6 tickers |
| Anti-leakage final | MCP `validate_split`, `detect_leakage`, `check_window_overlap` | Zero violações |
| Estabilidade | `generate_daily_snapshots.py` executado 3 dias consecutivos sem erro | 3/3 |

---

## 4. Plano de Validação Estatística

### 4.1 Protocolo anti-leakage (obrigatório em cada fase)

Antes de qualquer merge de Fase, executar:
```bash
# MCP server local
python -m src.fii_analysis.mcp_server.server validate_split
python -m src.fii_analysis.mcp_server.server detect_leakage
python -m src.fii_analysis.mcp_server.server check_window_overlap
```

Critério: saída `"leakage_detected": false` e `"overlap_detected": false` para todos os tickers.

### 4.2 Separação temporal obrigatória

```
|─────── Treino ───────|── gap 10d ──|── Validação ──|── gap 10d ──|── Teste (OOS) ──|
        ~60%                                ~20%                          ~20%
```

- Sem shuffle em nenhuma etapa
- Gap mínimo de 10 dias úteis entre conjuntos
- Métricas finais reportadas **exclusivamente** do conjunto de Teste

### 4.3 Thinning obrigatório

Observações candidatas a BUY devem ter intervalo mínimo de `forward_days` (20 pregões)
entre si. Isso garante independência estatística e evita n amostral inflado.

### 4.4 Correção por múltiplos testes

Com 36 combinações no grid, a probabilidade de falso positivo por chance aumenta.
Aplicar correção **Bonferroni** (divisão do α por número de testes) ao reportar
significância estatística das combinações:

```
α_corrigido = 0.05 / 36 ≈ 0.0014
```

Combinações com `p_value > 0.05` (sem correção) são **descartadas** mesmo se
o retorno médio for positivo.

### 4.5 Teste de Estabilidade (CriticAgent)

Após Fase 2 e após Fase 3, executar o `CriticAgent` (`models/critic.py`) com:
- **Shuffle test:** p-value do modelo shuffled deve ser > 0.30 (sinal real não é aleatório)
- **Placebo test:** placebo SELL deve ter retorno negativo no treino
- **Stability test:** top-3 combinações do treino devem aparecer no top-10 da validação

---

## 5. Priorização e Sequência de Entrega

```
Semana 1–2:   [F1.1] Grid expandido
              [F1.2] Volume signals
              [F1.3] LTV flag
              → Demo para investidores: "Testamos 36 cenários, antes eram 9"

Semana 3–4:   [F2.1] PL trend + Rentab divergência + DY momentum
              [F2.2] P/VP Z-score
              → Demo: "Detectamos fundos distribuindo capital como se fosse renda"

Semana 5:     [F2.3] Integração no otimizador e score
              → Demo: "Motor V2 filtra automaticamente sell-offs de pressão institucional"

Semana 6–7:   [F3.1] Momentum vs IFIX
              [F3.2] Cap Rate vs NTN-B
              [F3.3] Dividend safety
              → Demo: "Usamos os mesmos critérios de analistas de REITs internacionais"

Semana 8–9:   [F3.4] Heatmap UI
              → Demo final: "Visualize qualquer combinação de threshold e compare com benchmark"
```

---

## 6. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| IFIX não disponível via brapi | Alta | Baixo | F3.1 implementa `None` gracioso; IFIX pode ser carregado via yfinance `^IFIX` como fallback |
| Poucos eventos após thinning | Média | Alto | Reportar `n_trades` explicitamente; não reportar p-value quando n < 10 |
| Overfitting no grid expandido | Média | Alto | Bonferroni obrigatório; reporting de degradação treino→teste |
| Dados CVM atrasados | Baixa | Médio | Point-in-time via `data_entrega` já resolve; documentado no CLAUDE.md |
| Regressão em funcionalidades existentes | Baixa | Alto | `decidir_universo()` executado como smoke test em cada fase |

---

## 7. Definição de "Done" por Feature

Cada feature está "Done" quando satisfaz **todos** os critérios abaixo:

1. **Código:** Função em `src/fii_analysis/`, sem `print()`, sem Streamlit, com type hints
2. **Point-in-time:** Qualquer dado mensal usa `data_entrega <= target_date` (não `data_referencia`)
3. **Graceful degradation:** Retorna `None` ou valor padrão quando dados insuficientes (nunca levanta exception não tratada)
4. **Campo em TickerDecision:** Feature surfaceia em `TickerDecision` e é escrita no snapshot diário
5. **Critério de aceite específico:** Todos os critérios da seção correspondente acima estão verificados
6. **Anti-leakage:** MCP confirma zero violações após a integração

---

## 8. Glossário

| Termo | Definição no contexto deste projeto |
|-------|-------------------------------------|
| **Thinning** | Espaçamento mínimo de `forward_days` entre observações para garantir independência estatística |
| **Point-in-time** | Uso exclusivo de dados disponíveis publicamente na data t, nunca de dados futuros |
| **Grid Search** | Busca exaustiva de combinações de parâmetros (buy_pct × sell_pct) com avaliação de performance |
| **OOS** | Out-of-sample — conjunto de Teste, nunca visto durante treino ou seleção de parâmetros |
| **Data Leakage** | Uso inadvertido de informação futura no treino ou sinal — invalida qualquer resultado |
| **P/VP Z-Score** | Distância do P/VP atual em desvios padrão da média histórica do próprio fundo |
| **Armadilha de dividendo** | Fundo com DY atrativo mas que está distribuindo patrimônio, não renda operacional |
| **Volume qualificado** | Queda de preço associada a volume ≥ 1.5× a média de 21 dias — pressão vendedora real |
| **Cap Rate implícito** | NOI anualizado estimado / valor de mercado — retorno operacional imobiliário bruto |
| **LTV** | Loan-to-Value — passivo oneroso / ativo total, mede alavancagem do fundo |
| **NTN-B** | Tesouro Direto IPCA+ — benchmark de risco zero para ativos reais no Brasil |

---

*Documento gerado com base em: `docs/PLANO_MOTOR_RECOMENDACAO_V2.md`,
`docs/VARIAVEIS_ANALISE_FII_BRASIL.md`, `docs/VARIAVEIS_ANALISE_REITS_ADAPTACAO_FII.md`
e análise direta do código em `src/fii_analysis/`.*
