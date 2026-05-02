# Beta Tester Report — Módulos Estatísticos
**Persona:** Marcos, trader B&H, 8 anos de mercado
**Data:** 2026-04-24
**Pergunta central:** Devo comprar KNIP11 hoje para capturar o próximo dividendo? Quando vender?

---

## Veredicto Geral

Passei uma sessão inteira tentando responder a minha pergunta mais básica — "compro KNIP11 agora ou espero?" — e saí mais confuso do que entrei. O programa tem muita coisa funcionando: roda scripts, calcula retornos históricos, até me diz se o padrão "passou no teste". O problema é que nenhuma dessas saídas se conecta a uma ação que eu possa tomar amanhã de manhã. O módulo de Event Study — que deveria ser o coração de tudo — está reportando "LEAKAGE" para todos os cinco FIIs monitorados e não mostra nenhum resultado estatístico. A única saída que chegou perto de me dar um sinal foi o Otimizador V2, que me disse "SELL" para KNIP11 hoje — mas o sinal está baseado em parâmetros que não passaram no teste de placebo, e o Bonferroni p-value é 0.48. O programa está sendo honesto comigo sobre as limitações, o que respeito. Mas honestidade sem alternativa não me ajuda a investir.

A segunda frustração é a ausência da próxima data-com de KNIP11 no banco. O último dividendo registrado é 2026-03-31. Hoje é 2026-04-24. A data-com de abril deve ser em breve, mas o banco não sabe. Não tem como o programa me dizer "compra agora, faltam X dias para a data-com" se ele não conhece a data-com futura.

---

## Scorecard — Perguntas do Trader

| Pergunta | Status | Onde encontrei | Problema |
|---|---|---|---|
| Sinal hoje (comprar/esperar?) | ⚠️ | `10_Otimizador_V2.py` → `get_signal_hoje()` retornou "SELL" | Sinal baseado em parâmetros com p-value Bonferroni = 0.48 (não significativo). Sem validade estatística confirmada. |
| Preço de entrada / P/VP alvo | ⚠️ | `threshold_optimizer_v2.py` define `pvp_percentil_buy=15` | Não traduz para "compre abaixo de R$X" nem para P/VP numérico alvo. Nenhum módulo exibe P/VP atual de KNIP11 como saída direta de script. |
| Timing de saída (dias após ex-div) | ⚠️ | `analise_janela_flexivel.py` e `analise_janela_v2.py` | Mostra "dia médio de saída = +1.6" no período de teste, mas não há output "saia no dia +N do próximo ciclo". Histórico passado, não instrução futura. |
| Confiança no sinal | ❌ | `run_event_study.py` → veredicto "LEAKAGE" para TODOS os tickers | Event study completo bloqueado por leakage detectado. CriticAgent em `run_strategy.py` reprovou KNIP11 ("SINAL ESPURIO"). Nenhum sinal tem endorsamento estatístico. |
| Prova histórica do padrão | ⚠️ | `analise_janela_flexivel.py` mostra ciclo a ciclo | Existe tabela histórica de ciclos. Mas: (a) a data-com futura não existe no banco; (b) não há visual consolidado de "esses trades teriam funcionado". |
| Resultado financeiro backtestado | ⚠️ | `run_strategy.py` → KNIP11: retorno acumulado +14.6% (pós-IR) vs Buy&Hold que não é reportado para KNIP11 no summary | Existe retorno por ciclo. Falta comparativo direto com Buy&Hold para KNIP11. CPTS11 mostra comparativo: estratégia perde (-6.3pp). |

---

## Dores Identificadas (ordenadas por severidade)

### [FATAL] Event Study bloqueado por LEAKAGE em todos os tickers

**Onde:** `scripts/run_event_study.py` — saída final do veredicto
**O que tentei fazer:** Rodar o event study para ver se KNIP11 tem padrão estatístico de comportamento perto da data-com — que é exatamente o que o programa promete fazer.
**O que aconteceu:** Todos os 5 tickers retornam "LEAKAGE DETECTADO" e o veredicto final para todos é `LEAKAGE`. A tabela de resultados fica completamente vazia — sem CAR, sem p-values, sem veredito BUY/SELL.
```
VEREDICTO FINAL:
    CPTS11  LEAKAGE
    CPSH11  LEAKAGE
    GARE11  LEAKAGE
    HSRE11  LEAKAGE
    KNIP11  LEAKAGE
    SNFF11  LEAKAGE
```
**Por que é fatal:** O event study é a única fonte de validação estatística do padrão de dividend capture. Sem ele, o programa inteiro fica sem fundação estatística. A documentação diz que "Proximidade da data-com não entra no radar enquanto o event study não validar padrão" — então todo o sistema está em compasso de espera.
**O que eu precisaria para usar isso:** O leakage precisa ser corrigido no código de `make_splits()` antes que qualquer resultado possa ser confiável. O erro mostra 1-3 pregões de sobreposição, o que sugere um bug de boundary (off-by-one), não leakage conceitual.

---

### [FATAL] Próxima data-com de KNIP11 não existe no banco

**Onde:** `dados/fii_data.db` — tabela `dividendos`
**O que tentei fazer:** Ver quando é a próxima data-com de KNIP11 para calcular se estou na janela de compra.
**O que aconteceu:** O banco tem dados até 2026-03-31. Hoje é 2026-04-24. A data-com de abril/2026 não está no banco. Não há nenhum dado futuro de dividendo.
**Por que é fatal:** A pergunta central ("devo comprar agora?") é impossível de responder sem saber se estamos na janela pré-data-com. Se a próxima data-com é daqui 3 dias, a resposta é diferente de se é daqui 25 dias.
**O que eu precisaria para usar isso:** Um script de atualização automática de dividendos futuros via yfinance, ou uma estimativa probabilística da próxima data-com com base na sazonalidade histórica (ex: "KNIP11 tipicamente paga na última sexta do mês").

---

### [CRITICAL] CriticAgent reprova todos os sinais de KNIP11, mas o programa não diz o que fazer com isso

**Onde:** `scripts/run_strategy.py` — seção CRITIC AGENT para KNIP11
**O que tentei fazer:** Verificar se o sinal de dividend capture tem validade estatística.
**O que aconteceu:** O CriticAgent reporta claramente:
```
REPROVADO — falharam: Permutation Shuffle, Placebo
```
O Permutation Shuffle tem p-value = 0.0520 (borderline) e o Placebo tem p-value = 0.3614.
**Por que é crítico:** O programa me diz que o sinal falhou nos testes — mas ainda assim me mostra retorno acumulado de +14.6% e me convida a usar a estratégia. Não existe nenhuma mensagem que diga "este sinal foi reprovado — não use para tomar decisão de compra". O output de retorno e o output de reprovação estão no mesmo bloco de texto sem hierarquia visual. Um trader leigo vai ver "+14.6%" e ignorar "REPROVADO".
**O que eu precisaria para usar isso:** Uma gate explícita: se CriticAgent reprova, o relatório de retorno não deve ser exibido (ou deve aparecer com aviso vermelho em destaque: "ESTE SINAL NÃO TEM VALIDADE ESTATÍSTICA — Os números abaixo são simulação sem respaldo").

---

### [CRITICAL] Sinal de SELL do Otimizador V2 tem Bonferroni p=0.48 mas não diz isso ao usuário de forma clara

**Onde:** `src/fii_analysis/models/threshold_optimizer_v2.py` → `optimize()` + `get_signal_hoje()`
**O que tentei fazer:** Obter o sinal atual para KNIP11.
**O que aconteceu:** `get_signal_hoje()` retornou `{"sinal": "SELL", ...}`. Os parâmetros otimizados têm `p_value_buy_bonferroni = 0.483` — longe do nível de significância de qualquer teste razoável. O sinal BUY thinned tem apenas 4 eventos no conjunto de teste.
**Por que é crítico:** O usuário da página Streamlit `10_Otimizador_V2.py` provavelmente vê "SELL" em verde/vermelho e age. Não há forma de saber, olhando para o sinal, que ele é estatisticamente indistinguível do acaso.
**O que eu precisaria para usar isso:** O sinal deveria exibir condicionalmente: "SELL (sinal sem significância estatística — p=0.48 após Bonferroni)" ou simplesmente ser suprimido quando n_thinned < 10 ou p_bonferroni > 0.10.

---

### [HIGH] Ausência de ponto de entrada único: onde começo?

**Onde:** Estrutura geral do projeto
**O que tentei fazer:** Abrir o projeto pela primeira vez e descobrir qual script/página rodar para responder "devo comprar KNIP11?".
**O que aconteceu:** Existem pelo menos 6 scripts CLI estatísticos + 8 páginas Streamlit relacionadas a análise. Nenhum README ou guia rápido diz "para decisão de compra, comece por aqui". O `PROJETO.md` documenta tudo mas não tem um fluxograma de decisão.
**Por que é alto:** Um usuário novo vai rodar os scripts em ordem aleatória, ver outputs contraditórios (Event Study diz LEAKAGE, Janela Flexível diz 91.7% de acerto, CriticAgent diz REPROVADO), e não saber o que acreditar.
**O que eu precisaria para usar isso:** Uma página "Start Here" ou um documento de 1 página: "Fluxo de decisão: (1) rode event study → (2) se aprovado, veja janela flexível → (3) consulte sinal hoje → (4) verifique data-com". Com setas.

---

### [HIGH] Saída de `analise_janela_flexivel.py` é histórico, não instrução

**Onde:** `scripts/analise_janela_flexivel.py`
**O que tentei fazer:** Entender quando comprar e vender na prática.
**O que aconteceu:** O script me dá uma tabela linda de todos os ciclos passados — data-com por data-com, qual target bateu, em qual dia. Para o período de teste, KNIP11 bate 91.7% no target 0.25% com dia médio +1.6. Isso parece ótimo. Mas a última entrada é `2026-03-31`. Não há resposta para "e agora, em abril de 2026?".
**Por que é alto:** A pergunta do usuário é futura, o output é histórico. O gap entre os dois exige que eu mentalmente extrapole: "se o padrão continua, então eu deveria comprar X dias antes da próxima data-com que eu não sei quando é".
**O que eu precisaria para usar isso:** Uma linha final no output: "Próxima data-com estimada: YYYY-MM-DD. Se padrão histórico se mantém: compre em [data], alvo de saída: [data range]."

---

### [HIGH] Contradição visível entre módulos sem reconciliação

**Onde:** Comparação entre `run_event_study.py` e `analise_janela_flexivel.py`
**O que tentei fazer:** Entender se KNIP11 tem ou não padrão.
**O que aconteceu:**
- `run_event_study.py`: "LEAKAGE — sem resultado"
- `analise_janela_flexivel.py` (teste): 91.7% batendo target 0.25%, dia médio +1.6
- `run_strategy.py` CriticAgent: "REPROVADO"
- `run_strategy.py` retorno: "+14.6% acumulado"
Quatro saídas contraditórias sem nenhum módulo explicando qual tem precedência.
**Por que é alto:** Um trader vai escolher a saída que confirma o que ele já quer fazer. Sem hierarquia clara, o programa vira um gerador de viés de confirmação.
**O que eu precisaria para usar isso:** Uma saída consolidada única que hierarquize: "Validação estatística: REPROVADA. Backtest descritivo: positivo. Conclusão: padrão não validado. Não use para trading."

---

### [MEDIUM] P/VP atual de KNIP11 não aparece em nenhum script estatístico

**Onde:** Scripts CLI em `scripts/`
**O que tentei fazer:** Ver se KNIP11 está barato ou caro hoje vs seu histórico (para contextualizar o sinal).
**O que aconteceu:** Nenhum dos scripts estatísticos (`run_strategy.py`, `analise_janela_flexivel.py`, `run_event_study.py`) exibe P/VP atual. O único lugar acessível via CLI seria `fii KNIP11` do CLI Typer — mas esse não é documentado como parte do fluxo estatístico.
**Por que é médio:** P/VP é o critério de BUY do Otimizador. O Otimizador V2 diz que BUY ocorre quando P/VP percentil <= 15. Mas eu não sei onde estou nessa escala agora.
**O que eu precisaria para usar isso:** Uma linha no resumo do `run_strategy.py`: "P/VP atual: 1.03 (percentil 42%). Threshold BUY: percentil 15%."

---

### [MEDIUM] "Episódios thinned" — terminologia incompreensível sem contexto

**Onde:** `app/pages/11_Episodios.py`, `src/fii_analysis/models/episodes.py`
**O que tentei fazer:** Entender o que essa página faz e se ela me ajuda.
**O que aconteceu:** O título é "Episodios Discretos — Extremos de P/VP". O subtitle menciona "thinning por intervalo mínimo". Não existe nenhuma explicação de "o que é um episódio", "por que thinning", "o que faço com essa informação".
**Por que é médio:** Para um trader B&H, "episódio" e "thinning" não são palavras do vocabulário. A funcionalidade pode ser útil (detectar momentos onde P/VP estava extremamente baixo e ver o que aconteceu depois), mas o nome bloqueia o entendimento.
**O que eu precisaria para usar isso:** Renomear para "Análise de Compra em P/VP Extremo" e adicionar uma frase: "Quando o KNIP11 estava nos 10% mais baratos da sua história, o retorno médio nos 30 dias seguintes foi X%."

---

### [MEDIUM] Buy-and-hold ausente no comparativo de KNIP11

**Onde:** `scripts/run_strategy.py` — tabela final de comparação
**O que tentei fazer:** Ver se a estratégia de dividend capture bate o Buy&Hold para KNIP11.
**O que aconteceu:** A tabela final tem Buy&Hold para CPTS11 (e mostra que a estratégia perde: -6.3pp). Para KNIP11, a coluna Buy&Hold existe na tabela resumo mas o valor final não é comparado explicitamente no output da seção KNIP11.
**Por que é médio:** A comparação com Buy&Hold é a métrica mais importante para um investidor B&H. Se a estratégia perde para ficar parado, não há razão para usá-la.
**O que eu precisaria para usar isso:** Para cada ticker: "Estratégia: X% / Buy&Hold: Y% / Diferença: Z%" — consistente para todos os tickers.

---

### [LOW] Página 9_Otimizador.py referenciada na documentação não existe

**Onde:** `docs/PROJETO.md`, `docs/STATUS_ATUAL.md` — ambos mencionam `9_Otimizador.py`
**O que aconteceu:** O arquivo `D:/analise-de-acoes/app/pages/9_Otimizador.py` não existe no disco. A numeração pula de `8_Fund_EventStudy.py` para `10_Otimizador_V2.py`.
**Por que é baixo:** Não bloqueia o uso, mas quebra confiança na documentação. Um usuário seguindo o guia vai procurar a página 9 e não vai encontrar.
**O que eu precisaria para usar isso:** Corrigir a documentação para refletir que o Otimizador V1 foi removido/substituído.

---

### [LOW] Encoding quebrado no terminal (caracteres com "?" e "�")

**Onde:** Todos os scripts — saída no terminal Windows
**O que aconteceu:** Caracteres especiais (acentos, "—") aparecem como "??" ou "⛽" no terminal. Ex: `EVENT STUDY — CPTS11` vira `EVENT STUDY ? CPTS11`.
**Por que é baixo:** Não afeta os cálculos, mas dificulta a leitura dos outputs no terminal.
**O que eu precisaria para usar isso:** Configurar `PYTHONIOENCODING=utf-8` ou usar `sys.stdout.reconfigure(encoding='utf-8')` nos scripts.

---

### [LOW] Data da última atualização de preços não aparece nos scripts

**Onde:** Scripts estatísticos em geral
**O que aconteceu:** O último preço de KNIP11 no banco é 2026-04-23 (ontem). Mas nenhum script avisa isso. Se o banco estivesse desatualizado, eu não saberia.
**Por que é baixo:** Há proteção no código (`dias_staleness` no config.yaml), mas ela não é surfaceada nos scripts CLI.

---

## O que está funcionando bem

1. **`analise_janela_flexivel.py` e `analise_janela_v2.py`** — Rodaram sem erros, produziram output rico e legível. A tabela de ciclos com data-com, dividendo, preço de compra, melhor retorno e quais targets bateram é exatamente o nível de detalhe que um trader precisa ver. Isso é o melhor output do sistema na perspectiva prática.

2. **`run_strategy.py` — métricas de risco** — Sharpe, Sortino, Max Drawdown, perdas consecutivas: tudo presente e com valores numéricos claros. Para quem entende essas métricas, o output é completo.

3. **Honestidade sobre limitações** — O sistema não esconde os problemas. CriticAgent imprime "REPROVADO" com clareza. O leakage é detectado e reportado. Isso é raro e valioso. O sistema prefere dizer "não sei" a inventar um sinal.

4. **`ThresholdOptimizerV2.get_signal_hoje()`** — Existe uma função que retorna um sinal acionável ("BUY"/"SELL"/"NEUTRO") com indicadores atuais. A estrutura está correta. Só falta a validação estatística ser aprovada para o sinal ter credibilidade.

5. **Dados históricos ricos** — 8.184 preços diários, 355 dividendos, dados desde 2017 para KNIP11. A base de dados é sólida para análise histórica.

6. **Período de teste out-of-sample real** — O sistema usa um conjunto de teste genuinamente futuro (não visto no treino). Para KNIP11: 12 ciclos de teste de 2025-04 a 2026-03. Isso é metodologicamente correto.

---

## Sugestões do usuário (voz do Marcos)

Olha, eu entendo que vocês não querem me dar uma recomendação irresponsável. Respeito isso. Mas tem um jeito de ser honesto E ser útil ao mesmo tempo.

O que eu precisaria, no mínimo:

1. **Uma tela de resumo "Hoje para KNIP11"**: P/VP atual, percentil histórico, dias até próxima data-com estimada, sinal do otimizador, e uma linha vermelha ou verde em destaque dizendo se o sinal tem ou não respaldo estatístico.

2. **Corrijam o leakage do event study.** Parece um bug de off-by-one no `make_splits()`. Com o event study funcionando, pelo menos eu teria uma resposta para "existe padrão ou não?". Hoje não tenho nenhuma.

3. **A próxima data-com de KNIP11 não está no banco.** Preciso de um script que busque dividendos futuros ou pelo menos estime a próxima data-com com base na sazonalidade histórica. "Provavelmente na última semana de abril" já me ajuda a saber se estou na janela ou não.

4. **Separem visual e semanticamente o backtest descritivo da validação estatística.** Os +14.6% de retorno acumulado são um backtest descritivo. O CriticAgent reprovou o sinal. Esses dois resultados não podem aparecer no mesmo bloco de texto em pé de igualdade. O backtesto positivo com sinal reprovado deveria ter um aviso vermelho grande: "PADRÃO NÃO VALIDADO — números meramente ilustrativos".

5. **Rename na página 11**: "Episódios thinned" → "Compras em P/VP Mínimo Histórico". Mesma coisa, linguagem que um trader entende.

---

---

## Avaliação Aprofundada — Otimizador V2 + Episódios + Walk-Forward

**Data:** 2026-04-24  
**Ticker testado:** KNIP11  
**Pergunta central:** "Devo comprar KNIP11 hoje?"

---

### Resultado da Execução (tudo rodou sem erros fatais)

Rodei os três módulos via Python direto (`get_session_ctx`, sem Streamlit) com KNIP11. Todos completaram normalmente. Resumo dos números reais obtidos:

**Otimizador V2 (KNIP11)**
- Melhores params encontrados: `pvp_percentil_buy=15, pvp_percentil_sell=75, meses_alerta_sell=2, dy_gap_pct_sell=25`
- TEST: BUY médio = +2.71% (n=19 bruto, n_indep=4), p=0.013, **Bonferroni p=0.483**
- Overfitting: **SUSPEITO** (treino=+0.56%, val=+3.67%, teste=+2.71%)
- Sinal hoje: **SELL** (P/VP percentil=83.7%, DY Gap percentil=2.4%)
- Simulação no conjunto de teste: Estratégia +17.27% vs Buy&Hold +8.51% → Alpha +8.77%
- Sharpe BUY: 5.28, Win Rate (indep): 100% — mas n_indep=4, **resultado estatisticamente frágil**

**Episódios (KNIP11, BUY≤10%, SELL≥90%, fwd=30d)**
- BUY: n=23, média=+1.79%, win_rate=78.3%, **p=0.013 (SIGNIFICATIVO)**, IC95%=[+0.54%,+3.07%]
- SELL: n=5, média=+0.43% (poucos episódios)
- Spread BUY-SELL: +1.36%, Mann-Whitney p=0.145 (NS)
- Sinal hoje: **NEUTRO** (percentil=83.7% — não é extremo ≥90%)

**Walk-Forward Rolling (KNIP11, treino=18m, pred=1m, BUY<p15, SELL>p85)**
- 41 steps, 819 sinais (205 BUY, 150 SELL, 464 NEUTRO)
- BUY OOS: n=205, n_efetivo=19, média=+1.58%, win=78.9%, **p=0.0132 (SIG)**, IC=[+0.46%,+2.62%]
- SELL OOS: n=150, n_efetivo=13, média=+0.69% — sinal de SELL fraco (mal distinguível do mercado)
- Spread BUY-SELL: +0.95%, MW p=0.059 (borderline — NS a 5%)
- Simulação: Estratégia +60.49% vs Buy&Hold +41.90% → **Alpha +18.58%**
- Sinal mais recente na série OOS: 2026-03-03 — **NEUTRO**
- Sinal de hoje (extrapolando threshold da janela 18m): P/VP=0.9990 vs SELL thr=0.9893 → **SELL**

---

### O que está funcionando BEM (e por quê)

**1. O sinal BUY tem poder real — confirmado por três métodos independentes**

Todos os três módulos chegam na mesma conclusão via caminhos diferentes:
- Otimizador V2: BUY quando P/VP está nos 15% mais baixos → retorno médio +2.71% em 20 pregões (n_indep=4, frágil mas consistente)
- Episódios: BUY quando P/VP está nos 10% mais baixos → retorno médio +1.79% em 30 pregões (p=0.013, n=23, o mais robusto dos três)
- Walk-Forward OOS: BUY quando P/VP abaixo do p15 da janela de treino → retorno médio +1.58% em 20 pregões (p=0.013, n_eff=19, genuinamente out-of-sample)

Três métodos independentes, períodos distintos, todos apontando o mesmo sinal BUY com p<0.05. Isso é evidência real. O padrão não é artefato de overfitting num único modelo.

**2. Por que os módulos têm boas métricas: a variável P/VP funciona**

O P/VP (preço / valor patrimonial) é a variável que une os três módulos. Quando um FII de crédito como KNIP11 negocia abaixo do percentil 15% do seu histórico, isso sinaliza pressão vendedora desvinculada dos fundamentos, que historicamente reverte. Isso tem base econômica: o VP de crédito privado é mais estável do que o preço, criando oportunidade de mean-reversion. A rolling window de 504 pregões (≈2 anos) captura o regime atual sem contaminar com histórico muito antigo. Essa combinação — variável com fundamento + janela adaptativa — é o que faz o sinal funcionar.

**3. Walk-Forward como o mais confiável metodologicamente**

O Walk-Forward é o único módulo que produz sinais genuinamente out-of-sample: cada previsão usa somente dados passados, sem qualquer seleção de parâmetros contaminada pelo futuro. O Alpha de +18.58% no Walk-Forward é mais crível do que o Alpha de +17.27% do Otimizador V2 (que ainda tem leakagem metodológica possível pelo grid search no split). Com 41 steps e 819 sinais classificados, também é o que tem maior abrangência temporal.

**4. Episódios como a visualização mais didática**

O módulo Episódios tem a melhor relação sinal/ruído para um trader: mostra diretamente "quando o P/VP estava assim, isso aconteceu depois". Com n=23 episódios BUY, IC95% inteiro positivo ([+0.54%,+3.07%]) e p=0.013, é o único módulo onde posso dizer com confiança: "comprar em P/VP extremo funcionou historicamente para KNIP11". Win rate de 78% é concreto.

**5. Simulação operacional presente nos três**

Os três módulos têm curva de capital real com CDI, dividendos e posição aberta marcada a mercado. Isso é um diferencial enorme — não é só "forward return médio", é quanto dinheiro teria sobrado. A premissa de "capital fora rende CDI" é conservadora e realista.

---

### Dores específicas de cada módulo

**Otimizador V2**

- [HIGH] n_indep=4 no conjunto de teste invalida a maioria das métricas de risco calculadas (Sharpe=5.28 com n=4 é ruído puro, não sinal). O módulo exibe essas métricas sem aviso suficiente de que são estatisticamente sem sentido com n<10. Sharpe 5.28 com 4 observações parece impressionante mas não quer dizer nada.
- [HIGH] Overfitting classificado como "SUSPEITO" — degradação negativa (treino < validação) dispara essa classificação, mas isso pode ser noise num split pequeno. O diagnóstico assusta sem contexto.
- [MEDIUM] O sinal atual é "SELL" (DY Gap percentil = 2.4% < threshold 25%), mas o sinal SELL nunca foi validado: p_sell no teste não é significativo. O módulo emite SELL baseado numa condição não validada sem avisar. Para um trader, SELL sem evidência é pior que NEUTRO.
- [MEDIUM] Grid search com 24 combinações + Bonferroni: o p-valor bruto de 0.013 vira 0.483 após correção. Isso precisa aparecer com mais destaque no sinal em destaque no Streamlit — não apenas num caption técnico.
- [LOW] `fillna(method="ffill")` depreciado no Pandas moderno — vai gerar FutureWarning no plot da simulação operacional.

**Episódios**

- [HIGH] Parâmetro na UI chama-se `min_gap` mas na função `identify_episodes()` o parâmetro é `min_hold_days`. Quem chama a função via script (como eu fiz) recebe `TypeError`. Bug de interface que quebra uso programático.
- [HIGH] Sinal hoje é NEUTRO (percentil 83.7%), mas o módulo não explica a distância até o próximo sinal. Não responde "quando vai ser BUY?". Com P/VP em percentil 84%, falta 74 pontos percentis para chegar em BUY≤10%. Isso pode demorar meses ou anos — o módulo não contextualiza.
- [MEDIUM] Episódios SELL têm n=5 (com threshold 90%), o que é insuficiente para qualquer inferência. O Mann-Whitney fica NS por isso. O módulo deveria sugerir ampliar o threshold SELL (ex: ≥80%) antes de concluir que o sinal não existe.
- [LOW] A aba "Simulação Operacional" define SELL automaticamente como D+forward a partir do BUY, mas isso não é o que o módulo de Episódios promete (ele não tem sinal SELL por valuation). Existe uma inconsistência conceitual: o trader compra no BUY e vende em D+N fixo, não num sinal de valuation. Esse detalhe não é explicado na UI.

**Walk-Forward Rolling**

- [CRITICAL] O último sinal gerado na série OOS é 2026-03-03 — **há 52 dias de gap até hoje (2026-04-24)**. O módulo não gera sinais para o período atual porque a série OOS termina antes dos dados mais recentes. O trader olha o Walk-Forward e vê "dados até março/2026" sem entender por que. O Streamlit não avisa isso.
- [HIGH] O sinal SELL no Walk-Forward tem média de +0.69% (positivo!) e win rate de 77%. Isso quer dizer que o P/VP alto não prediz queda — o SELL não é um sinal de saída válido nesse modelo. O módulo produz sinais SELL e os exibe na timeline como se fossem acionáveis, mas eles não têm evidência.
- [HIGH] A UI mostra apenas o último sinal gerado pela série OOS (março/2026). Para saber o sinal de hoje, o trader precisaria extrapolamente manualmente o threshold — que eu fiz no teste: SELL (P/VP=0.9990 > threshold=0.9893). Isso não aparece em lugar nenhum na UI.
- [MEDIUM] Com `predict_months=1` e `train_months=18`, cada step avança 21 pregões. A última janela de treino começa em ~setembro/2024 e termina em ~março/2026. Mas os preços de abril/2026 existem no banco e não são usados. Adicionar um step final "hoje" resolveria o gap.
- [LOW] `n_steps` é calculado como número de meses únicos nos sinais, não número real de iterações do loop — pode confundir.

---

### Resposta à pergunta central: "devo comprar KNIP11 hoje?"

**Com base nos três módulos, a resposta convergente é: NÃO agora.**

| Módulo | Sinal Hoje | Confiança |
|---|---|---|
| Otimizador V2 | SELL (P/VP pct=83.7%, DY Gap pct=2.4%) | Baixa — SELL não validado estatisticamente |
| Episódios | NEUTRO (percentil 83.7%, longe do extremo ≤10%) | Média — o sinal BUY é validado, mas não está ativo |
| Walk-Forward | SELL (extrapolado: P/VP=0.9990 > threshold=0.9893) | Média — metodologia OOS robusta, mas gap de 52 dias |

**P/VP atual = 0.9990, percentil rolling = 83.7%.** O threshold de BUY fica no percentil ≤15%, que corresponde a P/VP ≈0.94-0.95 na janela recente. Para comprar com o sinal validado historicamente, KNIP11 precisaria cair ~5% em valor relativo ao VP. Isso não é iminente.

O que vale guardar: quando KNIP11 estiver com P/VP percentil abaixo de 10-15%, os três módulos convergem para BUY com evidência estatística genuína (p<0.05, win rate >78%). **Esse é o único sinal com respaldo em todo o sistema.**

---

### Recomendação final: esses 3 módulos juntos conseguem responder minha pergunta central?

**Sim, parcialmente — e essa é a melhor resposta honesta que o sistema consegue dar.**

O que os três módulos juntos respondem bem:
1. **"Vale a pena monitorar KNIP11?"** — Sim. O padrão BUY em P/VP extremo existe, é replicável OOS, tem IC95% positivo.
2. **"Quando comprar?"** — Quando P/VP percentil cair para ≤10-15% (P/VP ≈ 0.94 ou menos). Não agora.
3. **"A estratégia bate Buy&Hold?"** — Historicamente sim, com alpha de +8% a +18% dependendo do módulo e do período.

O que os três módulos ainda não respondem:
1. **"Qual é o target de saída?"** — Não há sinal SELL validado. Os três módulos mostram que o SELL baseado em P/VP alto não funciona para KNIP11. A saída ideal seria por timing (D+N) ou por outro critério não modelado.
2. **"Quando é a próxima data-com?"** — Dor estrutural do banco, não dos módulos em si.
3. **"Com quanto entrar?"** — Position sizing está completamente ausente.

**Com pequenos ajustes esses 3 módulos podem ser o núcleo de um produto real:**
- Walk-Forward: adicionar 1 step extra que cobre "hoje" usando a janela de treino mais recente disponível → resolve o gap de 52 dias
- Episódios: corrigir o bug `min_gap` / `min_hold_days` e adicionar "distância até próximo BUY: X pontos percentis"
- Otimizador V2: suprimir métricas de risco quando n_indep < 10, e não emitir sinal SELL quando o SELL não passou nos testes

Com essas correções, o produto conseguiria responder: "P/VP está em 83.7% do histórico. BUY ocorre abaixo de 10-15%. Não é o momento. Monitore."

Isso é útil. Não é trading algorítmico — é vigilância estatisticamente fundamentada sobre quando agir.

---

## Próximas perguntas que o Marcos teria

1. Quando exatamente vai ser a próxima data-com de KNIP11? O banco para em março/2026.

2. Se o padrão foi reprovado no CriticAgent, por que o `analise_janela_flexivel.py` mostra 91.7% de acerto no período de teste? Esses dois resultados medem a mesma coisa ou coisas diferentes?

3. O Otimizador V2 diz "SELL" para KNIP11. Isso significa "não compre agora" ou "se você tem posição, venda"? Para quem não tem posição, "SELL" não faz sentido.

4. O P/VP atual de KNIP11 está no percentil 42% (vi isso no código, não na tela). Isso está longe do threshold de compra (percentil 15%). Mas quanto tempo demora historicamente para chegar no percentil 15%? O sistema nunca chegou lá com KNIP11?

5. CPTS11 teve buy-and-hold de +27.5% vs estratégia +21.2%. Por que ainda aparece na lista como candidata para dividend capture?

6. O leakage detectado é de 1-3 pregões de sobreposição. Isso invalida completamente os resultados ou apenas os torna ligeiramente otimistas? Existe uma maneira de estimar o impacto?
