# Framework de Investigao Iterativa de FIIs (Kilo AI)

Para realizar uma anlise "definitiva e completa", no use um prompt esttico. Siga este processo de descoberta em camadas, que permite identificar fatos inesperados (como mudanas de gesto ou erros operacionais).

---

## Passo 1: Busca de Reconhecimento (Sentir o "Clima")
*   **Objetivo:** Identificar qual  o assunto principal do momento para aquele fundo, sem pressupor o que vai encontrar.
*   **Prompts Iniciais (lanar vrios em paralelo):**
    *   `[Ticker] FII fundo imobilirio [Ano Atual] anlise dividendos`
    *   `[Ticker] FII dividendos mensal [Ano Atual]`
    *   `[Ticker] P/VP valor patrimonial cota [Ano Atual]`
*   **O que observar:** Olhe os ttulos dos resultados. Se vrios mencionarem o mesmo tema (ex: "venda", "calote", "vacncia", "nova gesto"), voc encontrou o seu **Gancho de Investigao**.
*   **O que NO fazer:** No presuma o problema. No RBRR11, a mudana de gesto apareceu naturalmente no primeiro resultado. Em outro fundo, pode ser vacncia, inadimplncia ou emisso dilutiva.

## Passo 2: Mergulho Profundo (Deep Dive no Gancho)
*   **Objetivo:** Uma vez identificado o tema central no Passo 1, lanar mltiplas buscas focadas para entender causa raiz, impactos e cronologia.
*   **Prompts de Refinamento (lanar em paralelo):**
    *   Se o gancho for gesto: `[Ticker] consolidao [Nome da Gestora] fundos [Ano]` E `[Ticker] riscos problemas [Nome do ativo problemtico] gesto [Ano]`
    *   Se o gancho for queda de dividendo: `[Ticker] motivo queda rendimento [Ms/Ano] fato relevante` E `[Ticker] resultado [Ms/Ano] prejuzo`
    *   Se o gancho for crdito: `[Ticker] inadimplncia CRI [Nome do devedor] impacto` E `[Ticker] watchlist riscos carteira [Ano]`
    *   **SemPRE incluir:** `[Ticker] comparao [Peer 1] [Peer 2] FII [Segmento]` para ter referncia relativa.
*   **Resultado esperado:** Ter uma narrativa clara do que aconteceu, quando aconteceu, se  recorrente ou no, e o que o mercado est precificando.

## Passo 3: Leitura dos Prompts do Financial Advisor (Framework Mental)
*   **Objetivo:** Usar a estrutura multi-agente do projeto como checklist de anlise.
*   **Arquivos a consultar:**
    *   `financial-advisor/financial_advisor/sub_agents/data_analyst/prompt.py` - Estrutura do relatrio de dados.
    *   `financial-advisor/financial_advisor/sub_agents/trading_analyst/prompt.py` - Estrutura de estratgias.
    *   `financial-advisor/financial_advisor/sub_agents/risk_analyst/prompt.py` - Estrutura de riscos.
    *   `financial-advisor/financial_advisor/sub_agents/execution_analyst/prompt.py` - Estrutura de execuo.
*   **Como usar:** No  para seguir literalmente (so prompts para outro contexto), mas para garantir que a anlise cobre os 4 ngulos: Dados, Estratgia, Risco e Execuo.

## Passo 4: Auditoria Quantitativa (Banco de Dados Local)
*   **Objetivo:** Ver se os nmeros do sistema confirmam ou contradizem a notcia. Cruzar mltiplas fontes.
*   **Aes (executar em paralelo):**
    *   **Sinais do sistema:** Consultar `snapshot_decisions` e `snapshot_ticker_metrics` para ver o que os 3 motores (Otimizador V2, Episdios, Walk-Forward) esto sinalizando e os scores atuais.
    *   **P/VP real:** Cruzar o preo de tela com o VP do ltimo informe mensal (tabela `relatorios_mensais`). **Ateno:** verificar se houve emisso recente que mudou o nmero de cotas e o VP/cota.
    *   **Radar booleano:** Consultar `snapshot_radar` para ver os 4 flags (P/VP baixo, DY gap alto, sade OK, liquidez OK).
    *   **Histrico de VP:** Consultar os ltimos 6 meses de `relatorios_mensais` e `ativo_passivo` para detectar tendncia de PL, emisses, e concentrao de ativos.
    *   **Dividendos:** Verificar se o "corte de DY" detectado pelo algoritmo  recorrente ou se foi um evento nico j resolvido.
*   **Cruzamento crtico:** No RBRR11, o banco mostrava VP/cota de R$ 97,47 (mar/2026), mas a internet mostrava R$ 93,33 (fev/2026). A diferena era uma **emisso recente** que alterou o clculo. Sem esse cruzamento, a anlise estaria errada.

## Passo 5: Sntese e Veredito (O "Fator Humano")
*   **Objetivo:** Decidir se o mercado "errou a mo" na punio ao fundo.
*   **Perguntas-chave:**
    1. O evento que derrubou o preo  recorrente ou j foi resolvido?
    2. O score do sistema est punindo o fundo por algo que  temporrio?
    3. O desconto patrimonial compensa o risco identificado?
*   **Raciocnio crtico:** "O mercado caiu 15% por causa de um prejuzo de 1% que j foi resolvido?". Se a resposta for sim, voc encontrou uma **Assimetria de Compra**.

## Estrutura do Relatrio Final
1.  **Veredito:** Direto ao ponto (COMPRA / VENDA / AGUARDAR) e nvel de risco.
2.  **O Gancho:** O fato principal descoberto no Passo 1 que est movendo o preo hoje.
3.  **Dados do Sistema vs. Realidade:** Scores, P/VP, Yield Gap, e onde os indicadores esto certos ou errados.
4.  **Anlise Fundamentalista:** Qualidade dos ativos, LTV, vacncia, alavancagem.
5.  **Riscos:** O que pode piorar. Distinguir risco temporrio de risco estrutural.
6.  **Recomendao de Execuo:** Preo de entrada sugerido, horizonte, e o que monitorar.

---
*Atualizado em 08/05/2026 aps reviso de coerncia com o processo real aplicado ao RBRR11.*
