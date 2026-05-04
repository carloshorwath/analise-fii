# Plano Técnico: Motor de Recomendação de FIIs V2

Este documento detalha o plano técnico para reformular o motor de recomendação de Fundos Imobiliários (FIIs), resolvendo o problema atual de hiperfoco em P/VP e expandindo a lógica de otimização de *thresholds*.

---

## 1. Diagnóstico do Motor Atual

O motor de decisão atual (`decision/recommender.py`) processa os sinais em três camadas (Sinal, Risco, Ação) baseando-se em três modelos estatísticos:

1. **Otimizador (`ThresholdOptimizerV2`)**: Busca a melhor combinação de percentis de P/VP para definir os limites de Compra (*Buy*) e Venda (*Sell*).
2. **Episódios (`episodes.py`)**: Identifica momentos em que o P/VP entra em território extremo (abaixo ou acima do percentil histórico) e rastreia o retorno futuro em janelas discretas.
3. **Walk-Forward (`walk_forward_rolling.py`)**: Valida iterativamente no tempo se a estratégia baseada em percentil de P/VP se mantém consistente ao longo de diferentes cortes de tempo.

**Features Usadas:** O modelo atual depende quase exclusivamente de percentil de **P/VP** e **DY Gap**. As *flags* de risco consideram emissões, P/VP extremo e DY Gap baixo.

**Dados Disponíveis no Banco e NÃO Utilizados como Sinal:**
- `PrecoDiario`: `abertura`, `maxima`, `minima`, `volume`.
- `RelatorioMensal`: `rentab_efetiva`, `rentab_patrim`, `cotas_emitidas` e `patrimonio_liq` (tendência no tempo).
- O contexto de *CDI* e *IFIX* existe mas é apenas usado de forma passiva (diagnóstico).

**Pontos Cegos Identificados:**
- O modelo sofre de **hiperfoco em P/VP**. Ele não consegue distinguir se um ativo caiu de preço por um ajuste normal de mercado ou por um desespero (queda com volume alto).
- Falta avaliação de *Momentum* e saúde intrínseca do fluxo de dividendos.
- O grid de *thresholds* não atende investidores que preferem operações mais curtas ou com frequências de *trading* diferentes (ex.: comprar em 40, vender em 80).

---

## 2. Lacunas de Sinal Identificadas

Abaixo listamos 8 sinais críticos que estão ausentes, com justificativa para inclusão:

1. **Queda com volume alto vs queda sem volume:** Queda expressiva com volume acima da média de 21 dias sugere pressão vendedora real institucional. Queda sem volume pode ser apenas falta de liquidez momentânea. Separar estes eventos é crítico.
2. **Momentum de preço relativo ao IFIX:** FII que cai enquanto o IFIX sobe indica problema ou fundamento enfraquecido específico do ativo. Ajuda a isolar o *alpha*.
3. **Tendência de PL em janela de 3 meses consecutivos:** Se o PL está crescendo (não por reavaliação ou novas emissões isoladas, mas em valor base), o fundo gera valor. Quedas sucessivas no Patrimônio Líquido indicam distribuição de patrimônio sob o disfarce de yield.
4. **Rentabilidade efetiva vs patrimonial divergente por N meses:** Quando a *rentabilidade efetiva* descola sucessivamente da *rentabilidade patrimonial*, pode indicar que o FII está distribuindo mais do que de fato ganha, corroendo seu VP futuro.
5. **DY média móvel 3m vs DY 12m:** Divergência entre DY recente (3m) e histórico longo (12m). Um DY 3m em tendência de alta pode sinalizar um reposicionamento da carteira de CRIs ou revisionais de aluguel. Se o 3m cruza para baixo do 12m, serve de alerta.
6. **Variação do volume médio 21d vs 63d:** O volume de liquidez está diminuindo drasticamente a curto prazo (21d) comparado à média mais longa (63d). Pode preceder saídas de grandes investidores ou desinteresse do mercado.
7. **Número de meses com DY anualizado acima do CDI nos últimos 12 meses:** Métrica direta de qualidade. Em FIIs de recebíveis ou híbridos, não superar o CDI na maioria dos meses indica ineficiência na alocação de risco vs retorno livre de risco.
8. **Distância para a mínima de 52 semanas com filtro de Data-Com:** Ajuda a pegar movimentos de reversão e exaustão, calculando quão perto o ativo chegou de seu fundo histórico recente, filtrando a janela sensível pré-Data-Com (~10 dias úteis).

---

## 3. Proposta de Sinais por Categoria

Todos os cálculos de P/VP e DY utilizarão o método *point-in-time*, calculados dinamicamente via `PrecoDiario` do dia e `RelatorioMensal` filtrado restritamente por `data_entrega`.

### Sinais de Volume e Liquidez
- **Sinal:** Queda de Preço com Volume Alto
  - **Fórmula:** `Retorno Diário < -x%` E `Volume Atual > 1.5 * Média Móvel(Volume, 21d)`
  - **Banco:** `PrecoDiario` (`fechamento`, `fechamento_aj`, `volume`).
  - **Tipo:** Filtro de Risco (Veta *Buy* ou sinaliza atenção).
- **Sinal:** Razão de Liquidez 21d vs 63d
  - **Fórmula:** `Média(Volume, 21d) / Média(Volume, 63d)`
  - **Banco:** `PrecoDiario` (`volume`).
  - **Tipo:** Filtro de Risco (Se a razão cair muito, evitar).

### Sinais de Momentum e Tendência de Preço
- **Sinal:** Momentum Relativo ao IFIX
  - **Fórmula:** `Retorno FII (21d) - Retorno IFIX (21d)`
  - **Banco:** `PrecoDiario` (precisa puxar cotação do Fundo e Cotação do índice IFIX, usando `fechamento_aj`).
  - **Tipo:** Sinal Auxiliar de Entrada / Confirmação.

### Sinais de Qualidade de Dividendos
- **Sinal:** Tendência DY Curto vs Longo
  - **Fórmula:** `Soma(DY, 3m) / 3` vs `Soma(DY, 12m) / 12`
  - **Banco:** `RelatorioMensal` (`dy_mes_pct`) ou calculado via `Dividendo` e `PrecoDiario` point-in-time.
  - **Tipo:** Sinal de Entrada (Ascendente = Positivo).
- **Sinal:** DY Anualizado vs CDI Consistente
  - **Fórmula:** `Contagem de meses onde DY_anualizado > CDI_anualizado` nos últimos 12m.
  - **Banco:** `RelatorioMensal` (`dy_mes_pct` anualizado ou `rentab_efetiva` anualizada) e série histórica do CDI.
  - **Tipo:** Sinal de Entrada / Score de Qualidade.

### Sinais de Saúde Financeira do Fundo
- **Sinal:** Tendência de Patrimônio Líquido (PL)
  - **Fórmula:** Derivada do PL. `PL_mês_atual < PL_mês_anterior < PL_mês_anterior_2`.
  - **Banco:** `RelatorioMensal` (`patrimonio_liq`).
  - **Tipo:** Filtro de Risco (Veta se tendência de destruição estrutural for observada).
- **Sinal:** Divergência de Rentabilidade (Efetiva vs Patrimonial)
  - **Fórmula:** `Soma(Rentab Efetiva, 6m) - Soma(Rentab Patrimonial, 6m)` > Limite tolerado.
  - **Banco:** `RelatorioMensal` (`rentab_efetiva`, `rentab_patrim`).
  - **Tipo:** Filtro de Risco.

### Sinais de Contexto Macro
- **Sinal:** Sensibilidade Data-Com
  - **Fórmula:** Dias úteis até próxima data-com <= 10.
  - **Tipo:** Filtro Restritivo. Garante que ruídos e distorções de preço pela extração dos rendimentos sejam isolados.

---

## 4. Expansão do Grid de Thresholds

O otimizador atual foca apenas em 15/20/25% (Buy) e 65/70/75% (Sell). Será ampliado:
- **Buy Grid (P/VP Percentil):** [15, 20, 25, 30, 35, 40, 45, 50]
- **Sell Grid (P/VP Percentil):** [55, 60, 65, 70, 75, 80, 85, 90]
- **Restrição Lógica:** Só testar cenários onde `Sell - Buy >= 15` pontos percentuais.
- **Segundo Eixo Obrigatório:** DY percentil atuando em conjunto ou Momentum (só comprar se o DY percentil também estiver acima da sua média móvel longa).

**Como apresentar resultados:**
Os resultados devem ser sumarizados num *heatmap* 2D no Streamlit ou via log de output mostrando a relação "Percentil Compra x Percentil Venda", colorindo pela métrica preferida (`avg_return_buy` descontado de custos ou Sharpe Ratio independent/thinned).

**Controle de Overfitting:**
Com muitos testes numéricos, haverá aumento da taxa de falsos positivos (*Multiple Testing Problem*). Devemos:
1. Empregar correção estatística baseada na *False Discovery Rate (FDR)* ou *Bonferroni*.
2. Exigir consistência estrita (*rank consistent*) nos 3 cortes: Treino, Validação e Teste (OOS).
3. Avaliar degradação de performance entre validação e teste como limitante.

---

## 5. Arquitetura Proposta

As lógicas não podem misturar apresentação. Devem ser funções puras dentro de `src/fii_analysis/`.

**a) `features/volume_signals.py`**
- `def get_volume_profile(ticker: str, target_date: date, session: Session) -> dict:`
  Retorna métricas como `vol_ratio_21_63`, `is_high_volume_drop`.
- `def get_volume_drop_flag(ticker: str, target_date: date, session: Session, window_days: int = 21, threshold_z: float = 1.5) -> bool:`

**b) `features/momentum_signals.py`**
- `def get_relative_momentum(ticker: str, benchmark_ticker: str, target_date: date, session: Session, window: int = 21) -> float:`
- `def get_pl_trend_flag(ticker: str, target_date: date, session: Session, months: int = 3) -> bool:`
- Usa `RelatorioMensal` estritamente apontado via `data_entrega`.

**c) Modificações em `models/threshold_optimizer_v2.py`**
- Expandir nas variáveis da classe: `self.pvp_percentil_buy_grid = [15, 20, 25, 30, 35, 40, 45, 50]`.
- Modificar o `itertools.product` na rotina `optimize()` para ignorar se `sell_val - buy_val < 15`.
- Incorporar no `self._get_enriched_daily_data()` as novas features importadas de `volume_signals.py` e `momentum_signals.py`.

**d) Modificações em `decision/recommender.py`**
- Incluir na `@dataclass TickerDecision`:
  - `flag_volume_queda_forte: bool`
  - `flag_pl_destruido_recorrente: bool`
  - `momentum_ifix_21d: Optional[float]`
- Em `decidir_ticker()`, puxar essas flags e acoplar a lógica à camada de RISCO, vetando compras (*VETADA*) caso sinais de degradação forte de PL ou fuga de volume sejam alarmantes.

---

## 6. Plano de Validação

- **Prevenção de Leakage:** Todo valor contábil (VP, PL) será restrito à data em que foi publicamente conhecido (`data_entrega`), e não quando se refere (`data_referencia`).
- **Splits:** Manter `self._make_splits(df)` sem qualquer uso de `shuffle=True`. Séries temporais devem preservar autocorrelação original.
- **Thinning:** Reutilizar a função `_thin_returns` que garante intervalo mínimo `forward_days` entre observações, tornando o *N* amostral real e i.i.d.
- **Critério de Aceite:** A V2 só substituirá a V1 (Otimizador Simples de 3 grid-points) se, no *out-of-sample holdout* (Teste OOS), o retorno ajustado ao risco e a taxa de acerto (*win_rate_independent*) sofrer degradação < 30% em relação ao Treino e for superior ao Baseline V1, garantindo robustez a ruídos.

---

## 7. Priorização por Impacto x Esforço

| Iniciativa | Impacto Esperado | Esforço (Dev) | Prioridade / Ação |
| :--- | :--- | :--- | :--- |
| **Expansão do Grid do Otimizador** | Alto (Destrava negociações curtas) | Baixo (Apenas parâmetros e loop de restrição) | **#1 (Quick Win)** |
| **Sinal de Queda com Volume** | Alto (Evita falsos *Buy* de fuga de capital) | Baixo (Dados diários já em BD) | **#2 (Quick Win)** |
| **Tendência de PL e Divergência de Rentabilidade** | Médio (Avalia saúde real) | Médio (Queries SQL sobre `RelatorioMensal`) | **#3 (Fase 2)** |
| **Momentum vs IFIX** | Médio | Alto (Exige tratar base IFIX externa se ainda não estiver na DB) | **#4 (Fase 2)** |
| **DY 3m vs 12m + CDI** | Baixo a Médio | Médio (Cálculo point-in-time e matching do CDI) | **#5 (Fase 3)** |
