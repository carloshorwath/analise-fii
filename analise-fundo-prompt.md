# Framework de Investigao Iterativa de FIIs (Kilo AI)

Para realizar uma anlise "definitiva e completa" de um FII, no use um prompt esttico.
Siga este processo de descoberta em camadas, que permite identificar fatos inesperados
sem pressupor o que vai encontrar.

---

## Passo 1: Busca de Reconhecimento (Sentir o "Clima")
*   **Objetivo:** Identificar qual  o assunto principal do momento para aquele fundo.
*   **Prompts Iniciais (lanar vrios em paralelo):**
    *   `[Ticker] FII anlise dividendos [Ano Atual]`
    *   `[Ticker] FII dividendos mensal [Ano Atual]`
    *   `[Ticker] P/VP valor patrimonial cota [Ano Atual]`
*   **O que observar:** Olhe os ttulos dos resultados. Se vrios mencionarem o mesmo tema, voc encontrou o seu **Gancho de Investigao**.
*   **O que NO fazer:** No presuma o problema antes de ver os resultados. Deixe a internet te contar o que est acontecendo.

## Passo 2: Mergulho Profundo (Deep Dive no Gancho)
*   **Objetivo:** Uma vez identificado o tema central no Passo 1, lanar buscas focadas na causa raiz.
*   **Prompts de Refinamento (lanar em paralelo):**
    *   `[Ticker] detalhes [GANCHO IDENTIFICADO] [Ano]`
    *   `[Ticker] riscos problemas carteira [Ano]`
    *   `[Ticker] comparao [Peer 1] [Peer 2] FII [Segmento]`
*   **Resultado esperado:** Uma narrativa clara do que aconteceu, quando, se  recorrente ou no, e o que o mercado est precificando.

## Passo 3: Leitura dos Prompts do Financial Advisor (Framework Mental)
*   **Objetivo:** Usar a estrutura multi-agente como checklist de cobertura.
*   **Arquivos a consultar:**
    *   `financial-advisor/financial_advisor/sub_agents/data_analyst/prompt.py`
    *   `financial-advisor/financial_advisor/sub_agents/trading_analyst/prompt.py`
    *   `financial-advisor/financial_advisor/sub_agents/risk_analyst/prompt.py`
    *   `financial-advisor/financial_advisor/sub_agents/execution_analyst/prompt.py`
*   **Como usar:** Garantir que a anlise cubra os 4 ngulos: Dados, Estratgia, Risco e Execuo.

## Passo 4: Auditoria Quantitativa (Banco de Dados Local)
*   **Objetivo:** Ver se os nmeros do sistema confirmam ou contradizem a notcia.
*   **Aes (executar em paralelo):**
    *   **Sinais do sistema:** Consultar `snapshot_decisions` e `snapshot_ticker_metrics` pelos 3 motores e scores.
    *   **P/VP real:** Cruzar o preo de tela com o VP do ltimo informe mensal (tabela `relatorios_mensais`).
    *   **Radar booleano:** Consultar `snapshot_radar` pelos 4 flags (P/VP baixo, DY gap alto, sade OK, liquidez OK).
    *   **Histrico de VP:** Consultar os ltimos 6 meses de `relatorios_mensais` e `ativo_passivo` para detectar tendncias e variaes no nmero de cotas.
    *   **Dividendos:** Verificar se cortes detectados pelo algoritmo so recorrentes ou eventos nicos.
*   **Cruzamento crtico:** Sempre comparar o VP mais recente do banco com o que a internet cita. Se divergirem, investigar a causa (pode ser reavaliao de ativos, emisso, ou defasagem de data_entrega).

## Passo 5: Sntese e Veredito (O "Fator Humano")
*   **Objetivo:** Decidir se o mercado "errou a mo" na punio ao fundo.
*   **Perguntas-chave:**
    1. O evento que derrubou o preo  recorrente ou j foi resolvido?
    2. O score do sistema est punindo o fundo por algo que  temporrio?
    3. O desconto patrimonial compensa o risco identificado?
*   **Raciocnio crtico:** Se o mercado puniu o fundo por algo passageiro, existe uma assimetria de compra.

## Estrutura do Relatrio Final
1.  **Veredito:** Direto ao ponto (COMPRA / VENDA / AGUARDAR) e nvel de risco.
2.  **O Gancho:** O fato principal descoberto no Passo 1 que est movendo o preo.
3.  **Dados do Sistema vs. Realidade:** Scores, P/VP, Yield Gap, e onde os indicadores esto certos ou errados.
4.  **Anlise Fundamentalista:** Qualidade dos ativos, LTV, vacncia, alavancagem.
5.  **Riscos:** Distinguir risco temporrio de risco estrutural.
6.  **Recomendao de Execuo:** Preo de entrada sugerido, horizonte, e o que monitorar.

---
*Documento genrico. No contm exemplos especficos de nenhum fundo.*
