# Variáveis para Análise Quantitativa de FIIs no Brasil

Este documento apresenta um levantamento fundamentado das variáveis essenciais para a modelagem quantitativa de Fundos de Investimento Imobiliário (FIIs) no mercado brasileiro. A estrutura foi construída com base em literatura acadêmica, regulamentação da CVM, metodologias de gestoras locais e plataformas de análise de mercado.

## 1. Variáveis de Valuation

Estas variáveis compõem a fundação para precificação de FIIs e determinação de valor relativo.

| Variável | Definição / Cálculo | Por que é usada | Limitações |
| :--- | :--- | :--- | :--- |
| **P/VP (Preço / Valor Patrimonial)** | Preço da cota na bolsa dividido pelo Valor Patrimonial por Cota (VPA). | Métrica clássica de precificação. Em FIIs de **Papel**, P/VP > 1 indica ágio sobre o PL (costuma não fazer sentido pois os CRIs são marcados a mercado). Em FIIs de **Tijolo**, P/VP < 1 indica que o fundo negocia abaixo do valor de avaliação dos imóveis. Em **Híbridos**, a interpretação é mista. | Em FIIs de Tijolo, depende da qualidade e tempestividade dos laudos de avaliação anuais (frequentemente defasados ou otimistas). |
| **DY (Dividend Yield) 12m** | (Soma dos dividendos pagos nos últimos 12 meses) / Preço atual. | Reflete o retorno de caixa gerado para o investidor. | É um indicador de passado ("backward-looking"). Pode estar inflado por distribuições não-recorrentes (ex: venda de ativo) ou repasse inflacionário (FII de papel). |
| **DY Projetado (Forward Yield)** | (Estimativa de dividendos próximos 12m) / Preço atual. | Tenta antecipar a rentabilidade futura com base em guidance da gestão ou modelagem de contratos/CRIs. | Difícil padronização em modelos quantitativos; depende de projeções de IPCA/CDI. |
| **DY vs CDI (Spread)** | DY Anualizado - CDI Anualizado. | O CDI é a taxa livre de risco brasileira. O spread mede o prêmio de risco exigido pelo investidor para deter o FII ao invés de renda fixa pós-fixada. | Ignora a valorização patrimonial do FII; compara uma renda nominal (CDI) com uma renda frequentemente isenta de IR e ajustada pela inflação (FIIs de tijolo). |
| **Cap Rate Implícito (Tijolo)** | NOI (Net Operating Income) Anualizado / Valor de Mercado da parcela imobiliária do fundo. | Mostra o retorno operacional imobiliário gerado *aos preços de tela*, removendo distorções de alavancagem ou caixa. | Requer extração detalhada de demonstrativos de resultados operacionais que a CVM não consolida com perfeição. |
| **Desconto/Prêmio sobre NAV** | (Valor de Mercado - NAV) / NAV. NAV = Valor dos ativos menos passivos. | Pode ser estimado via modelagem quando o P/VP é falho (ex: ajustando laudos com base em inflação não repassada). | Exige premissas subjetivas para reavaliar os imóveis sem laudo formal. |
| **Preço por m² (Tijolo)** | Valor de mercado da fatia do FII no imóvel / Área Bruta Locável (ABL) detida. | Permite comparar se o fundo está sendo negociado a custos de reposição razoáveis ou abaixo do mercado imobiliário físico local. | Não se aplica a FIIs de papel. Difícil automação em massa sem bases de dados proprietárias. |

## 2. Variáveis de Qualidade dos Ativos (específicas para Tijolo)

Essenciais para avaliar o risco imobiliário fundamental do fundo.

| Variável | Definição | Por que é usada |
| :--- | :--- | :--- |
| **Taxa de Vacância Física** | (Área não alugada) / (ABL Total do Fundo). | Mede a desocupação espacial. Altos níveis indicam dificuldade de locação ou má localização. |
| **Taxa de Vacância Financeira** | (Receita potencial de espaços vagos) / (Receita potencial total). | Mais relevante que a física, pois pondera espaços vazios pelo seu valor financeiro (ex: espaço vazio em SP pesa mais que no interior). |
| **WALE (Weighted Average Lease Expiry)** | Prazo médio remanescente dos contratos, ponderado pela receita. | Mede o risco de renovação/vacância no curto prazo. Maior WALE = maior previsibilidade. |
| **Tipo de Contrato** | Proporção de contratos Atípicos (Built-to-Suit, Sale&Leaseback, penalidades severas) vs Típicos (3-5 anos, sem multa de saldo devedor). | Contratos atípicos oferecem renda quase garantida, reduzindo risco de vacância durante a vigência. |
| **Qualidade dos Inquilinos** | Concentração da receita no principal inquilino; Setor econômico; Rating de crédito. | Evita FIIs monoproduto/monoinquilino que podem sofrer calote catastrófico. |
| **Qualificação do Ativo** | Classificação (Triple-A, A, B, C); Localização (ex: Faria Lima vs Região Metropolitana distante). | Imóveis prime têm maior resiliência em crises, menor vacância e melhor poder de repasse de preços. |
| **Índice de Reajuste** | % de contratos indexados a IPCA vs IGP-M. | No Brasil, o IGP-M tornou-se volátil e frequentemente negativo/muito alto. IPCA é considerado mais "saudável" para locatários no longo prazo. |

## 3. Variáveis de Qualidade para FIIs de Papel (CRI/CRA/LCI/LCA)

FIIs de papel demandam análise de risco de crédito e sensibilidade a indexadores.

| Variável | Definição | Por que é usada |
| :--- | :--- | :--- |
| **Duration da Carteira** | Prazo médio ponderado de recebimento dos fluxos de caixa da carteira de dívida. | Indica a sensibilidade da cota às variações da curva de juros futuros. |
| **Spread Médio** | Taxa média da carteira acima do indexador (ex: IPCA + 7%, CDI + 3%). | Mede o risco intrínseco. Spreads muito altos (High Yield) indicam maior risco de calote. |
| **Concentração de Devedores** | % do PL alocado no maior devedor ou nos Top 5. | Risco de cauda. Um evento de crédito em um devedor relevante destrói o rendimento. |
| **LTV (Loan-to-Value) Médio** | (Saldo Devedor do CRI) / (Valor da Garantia). | Quanto menor o LTV, maior a segurança na execução das garantias em caso de calote. |
| **Índice de Inadimplência** | % da carteira em atraso ou default. | Métrica direta de qualidade de crédito ("non-performing loans"). |
| **Tipo de Garantia** | % com alienação fiduciária de imóvel (forte) vs fiduciária de cotas/recebíveis (mais fraca). | Determina a capacidade de recuperação de capital em cenários de stress. |

## 4. Variáveis de Saúde Financeira do Fundo

Ajudam a identificar fundos que estão corroendo valor no longo prazo, mesmo pagando dividendos atraentes.

| Variável | Definição / Avaliação | Por que é usada |
| :--- | :--- | :--- |
| **Tendência do PL** | Variação do PL total e por cota em 3, 6 e 12 meses. | Queda constante do PL/Cota indica destruição de patrimônio (frequentemente por inflação não reinvestida em FIIs de papel ou amortizações mal feitas). |
| **Rentabilidade Efetiva vs Patrimonial** | Comparação entre o retorno gerado de fato e a variação do patrimônio. | Divergência sistemática é um "red flag" de distribuições que corroem o principal. |
| **Histórico de Cortes de Dividendo** | Contagem e magnitude de reduções de proventos em 24 meses. | Reduções frequentes afastam investidores institucionais e sinalizam deterioração estrutural. |
| **Índice de Distribuição** | Dividendos Pagos / Lucro Caixa. | FIIs que distribuem exatamente 100% (ou mais, via reservas) consistentemente não constroem reservas, ficando frágeis. |
| **Emissões Recentes** | Análise se as emissões de cotas foram feitas abaixo ou acima do VPA. | Emissões abaixo do VPA ("dilutivas") prejudicam o cotista atual e indicam gestão focada no crescimento do PL para aumentar taxa de administração. |
| **Alavancagem (LTV do Fundo)** | Passivo Oneroso / Total de Ativos. | Relevante para fundos que tomam dívida (CRIs na ponta passiva) para comprar imóveis. Alta alavancagem com juros altos é perigoso. |

## 5. Variáveis de Liquidez e Mercado

Fatores cruciails para modelos sistemáticos devido aos custos de transação.

| Variável | Definição | Por que é usada |
| :--- | :--- | :--- |
| **ADTV 21d e 63d** | Volume financeiro médio diário de negociação. | Fundamental para dimensionar posições e evitar "slippage" (impacto no preço ao operar). |
| **Free Float Efetivo** | % de cotas em circulação não travadas. | Maior free float = melhor formação de preços e menor risco de manipulação. |
| **Bid-Ask Spread** | Diferença percentual média entre a melhor oferta de compra e de venda. | Mede o custo implícito da transação para o modelo quantitativo. |
| **Correlação com o IFIX (Beta)** | Sensibilidade do fundo aos movimentos do mercado geral de FIIs. | Importante para otimização de portfólio e gestão de risco (hedge). |
| **Impacto Preço x Volume** | Análise de quedas associadas a pico de volume ("sell-off" real) vs quedas em baixo volume (ineficiência). | Captura sinais microestruturais relevantes para timing. |
| **Captação Líquida** | Fluxo de caixa de subscrições menos amortizações. | Fundos com forte fluxo de entrada tendem a ter suporte de preços temporário. |

## 6. Variáveis de Contexto Macro (específicas do Brasil)

Modelos no Brasil não funcionam ignorando o cenário juros/inflação altamente volátil.

| Variável | Definição | Por que é usada |
| :--- | :--- | :--- |
| **Selic e CDI** | Taxas básicas de juros de curto prazo. | Custo de oportunidade direto ("gravidade" que puxa P/VP e preços para baixo quando sobe). |
| **IPCA e IGP-M** | Índices de inflação. | Indexam os contratos de locação e os FIIs de Papel. Impactam a distribuição nominal de curto prazo. |
| **Curva de Juros (DI1)** | Expectativa futura do CDI a 1, 2, 5 anos. | O vencimento DI1F29 (por exemplo) precifica ativos de duração longa. "Yield Curve" é vital para valuation de FIIs. |
| **IFIX** | Índice de referência do mercado. | Usado para medir a força relativa e o prêmio de risco sistemático. |
| **Ciclo de Crédito** | Disponibilidade e custo do financiamento imobiliário. | Afeta a liquidez dos imóveis físicos e o risco de crédito dos CRIs. |

## 7. Variáveis Comportamentais e de Momentum

Úteis para modelos preditivos e algoritmos de "trading".

| Variável | Definição | Por que é usada |
| :--- | :--- | :--- |
| **Momentum Relativo** | Retorno do FII menos o retorno do IFIX no período. | Permite diferenciar correções de mercado (todos caem) de problemas idiossincráticos (só o fundo cai). |
| **Reversão à Média do P/VP** | Z-Score do P/VP atual contra a média histórica do próprio fundo. | Muitos FIIs respeitam ranges históricos de prêmio/desconto. Comprar nos "fundo do canal" gera alfa. |
| **Spread DY TTM vs Forward** | DY 12m passados - DY Projetado. | Quando o passado é alto mas a expectativa cai (ex: IPCA desabou), o preço cai antecipadamente. |
| **Cobertura de Analistas** | Número de relatórios e recomendações buy/sell. | "Crowded trades" sofrem mais em reversões; fundos ignorados podem ser pechinchas. |

---

## 8. Variáveis Disponíveis nos Dados CVM do Projeto

Muitas variáveis fundamentais já estão sendo ingeridas nos bancos de dados locais do projeto, via tabelas `inf_mensal_fii_geral`, `inf_mensal_fii_complemento` e `inf_mensal_fii_ativo_passivo`.

Abaixo o mapeamento exato dos campos CVM:

| Variável Teórica | Fonte CVM Exata (Tabela / Coluna) |
| :--- | :--- |
| **Patrimônio Líquido (PL)** | `complemento` / `Patrimonio_Liquido` |
| **Valor Patrimonial por Cota (VPA)** | `complemento` / `Valor_Patrimonial_Cotas` |
| **Dividend Yield (Mensal)** | `complemento` / `Percentual_Dividend_Yield_Mes` |
| **Rentabilidade Efetiva** | `complemento` / `Percentual_Rentabilidade_Efetiva_Mes` |
| **Rentabilidade Patrimonial** | `complemento` / `Percentual_Rentabilidade_Patrimonial_Mes` |
| **Volume de Ativo Total** | `ativo_passivo` / `Total_Investido` ou soma de ativos |
| **Participação em Imóveis Diretos** | `ativo_passivo` / `Direitos_Bens_Imoveis` |
| **Exposição a Dívida / Papel (CRI)** | `ativo_passivo` / `CRI_CRA` e `CRI` |
| **Exposição LCI** | `ativo_passivo` / `LCI_LCA` e `LCI` |
| **Caixa e Disponibilidades** | `ativo_passivo` / `Disponibilidades` |
| **Passivo Total (Alavancagem)** | `ativo_passivo` / `Total_Passivo` |
| **Número de Cotistas** | `complemento` / `Total_Numero_Cotistas` |
| **Quantidade de Cotas** | `complemento` / `Cotas_Emitidas` |
| **Taxas de Adm/Gestão a Pagar** | `ativo_passivo` / `Taxa_Administracao_Pagar` |
| **Segmento de Atuação** | `geral` / `Segmento_Atuacao` |
| **Tipo de Gestão (Ativa/Passiva)** | `geral` / `Tipo_Gestao` |
| **Mandato** | `geral` / `Mandato` |

*Nota técnica: O banco de dados SQLite do projeto extrai e consolida essas colunas nas classes `RelatorioMensal` e `AtivoPassivo`.*

## 9. Variáveis NÃO Disponíveis na CVM (Requerem Outras Fontes)

Alguns dados essenciais não trafegam de forma estruturada nos informes mensais padronizados da CVM:

*   **Taxa de Vacância, WALE e Reajustes:** Só disponíveis nos relatórios gerenciais em PDF ou em agregadores pagos (SiiLA Brasil, Buildings). *Viabilidade: Difícil escala grauita. Pode exigir scraping em sites como FundsExplorer ou StatusInvest.*
*   **Duration e Spread da Carteira de CRIs:** Gestores publicam em PDFs. *Viabilidade: Alta complexidade técnica. Alternativa é o web-scraping dos agregadores abertos.*
*   **P/VP Real-time e Preços Diários:** CVM só traz fechamentos mensais defasados. *Viabilidade: O projeto já usa `yfinance` e B3, cobrindo perfeitamente as métricas diárias, volume e spread vs CDI.*
*   **Emissões Recentes (Acretiva/Dilutiva):** Necessita acompanhamento de Fatos Relevantes e Prospectos CVM 400/476. *Viabilidade: Viável via APIs de Fatos Relevantes da B3, mas requer parser textual avançado.*

## 10. Recomendação de Implementação

Para o motor de recomendação quantitativo atual do projeto, sugere-se a adição imediata das 5 variáveis a seguir. A seleção pondera **alto impacto na predição** e **dados já estruturados ou fáceis de obter** com a stack local.

1.  **Spread P/VP vs Média Histórica (Z-Score):**
    *   *Por que:* FIIs tendem fortemente à reversão à média. Fácil cálculo a partir dos dados locais.
2.  **Rentabilidade Patrimonial vs Rentabilidade Efetiva:**
    *   *Por que:* Filtro de sanidade crítico. Usando as colunas CVM `Percentual_Rentabilidade_Patrimonial_Mes` e `Percentual_Rentabilidade_Efetiva_Mes`, o motor descartará "value traps" (fundo derretendo PL para pagar yield alto).
3.  **Proporção de CRI/CRA no Ativo:**
    *   *Por que:* O mercado exige yields diferentes para Tijolo e Papel. A coluna CVM `CRI_CRA` dividida pelo Ativo Total classifica automaticamente as "caixas-pretas" que mudaram de mandato para FII de Papel mascarado.
4.  **Alavancagem Sistêmica LTV:**
    *   *Por que:* Com SELIC alta, fundos alavancados quebram silenciosamente. Uso imediato: `Total_Passivo` / `Patrimonio_Liquido` (dados CVM).
5.  **Beta CDI Diário (CDI Sensitivity V2):**
    *   *Por que:* O projeto já tem `cdi_beta` na tabela `snapshot_decisions`, mas usá-lo ativamente como penalização no escore quantitativo (FIIs muito dependentes do juro pós vs FIIs de tijolo puro) refinará o valuation.
