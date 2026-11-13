# PRE-REGISTRO (escrito em 2026-11-12 ANTES de qualquer analise preditor x retorno)
Escrito apos: ler o codigo dos indicadores e fazer o censo de dados (so contagens/cobertura, nenhuma relacao preditor-retorno).

## Achado de dados que condiciona o desenho (censo, verificado)
- `dividendos` (fonte yfinance) so tem cobertura plena a partir de 2022-03/04 (fundos com dividendo por mes: 9 em 2022-02, 43 em 2022-03, 69 em 2022-04, ~100+ depois).
  Antes disso `fechamento_aj` (retorno total) == retorno de PRECO. Logo:
  * Amostra primaria: datas de formacao (ultimo pregao do mes) >= 2022-04-29. Qualquer retorno futuro que comece antes e fosse "total" seria preco puro.
  * DY12m so valido se (t - 12m) >= 2022-03-31 e fundo listado ha >= 12 meses => DY/DY gap em nivel a partir de ~2023-03-31;
    percentil temporal do DY gap (janela 252, minimo 50 obs como no codigo) a partir de ~2023-06.
  * Momentum (sobre retorno total) so valido se a janela comecar >= 2022-04-01.
- Horizontes 1/3/6/12 meses => ~54/52/49/43 datas de formacao, ~54/17/8/3.6 periodos NAO sobrepostos. 12m tem poder praticamente nulo.

## Unidade / alvo
- Painel ticker x data de formacao mensal (ultimo pregao do mes, exige preco nesse dia). Retorno futuro = fechamento_aj(T)/fechamento_aj(t)-1, T = ultimo pregao do mes t+h (ffill ate 5 pregoes).
- Alvo PRIMARIO (a): excesso sobre media equal-weight cross-section da mesma janela (so fundos com retorno valido). (b) XFIX11 (preco; ETF nao tem dividendos no banco), (c) CDI, (d) bruto: o intercepto por data
  absorve qualquer constante por data, logo a INCLINACAO Fama-MacBeth e o spread Q1-Q5 sao identicos em (a),(b),(c),(d); (b)(c) so mudam niveis (usados na traducao economica). Verificarei numericamente.
- Segmento (Tijolo/Papel/Hibrido): classificar_fii replicado com ultimo informe (ativo_passivo), fixo no tempo (declarado).

## Preditores (calculados por mim, point-in-time; informe so se data_entrega <= t)
Continuos (16), cada um transformado em rank cross-sectional por data em [0,1]:
 C1 pvp_pct   percentil do P/VP na historia propria (janela 504 pregoes ate t-1, estritamente abaixo, exige >=252 obs previas [codigo aceita 63; escolho 252, robustez com 63])
 C2 pvp_cs    P/VP (ordem do nivel) vs cross-section da data [ordenacao do nivel == rank]
 C3 pvp_seg   rank do P/VP dentro do segmento
 C4 dy12      DY 12m (== DY gap em nivel == rank cross-sectional do DY gap: ordenacao identica dentro da data; declaro equivalencia)
 C5 dygap_pct percentil temporal (252) do DY gap
 C6 dvp3, C7 dvp6   variacao % VP/cota (vp_aj) vs informe 3 e 6 meses antes (por data_referencia)
 C8-C11 mom1, mom3, mom6, mom12  retorno total passado
 C12 liq      log volume financeiro medio 21d
 C13 lev      ativo_total/PL
 C14 vol      volatilidade anualizada 252d (retorno log de fechamento_aj)
 C15 score    score_total do sistema (replica PIT: 0.35 val + 0.30 risco + 0.20 liq + 0.15 hist; beta vs XFIX11 252d, MDD 504d; replica APROXIMADA, sem z-score do P/VP)
 C16 saude    score_saude (0-100) de flag_destruicao_capital(t) (funcao do proprio projeto chamada com t)
Discretos (9), coeficiente = diferenca de excesso medio (flag=1 menos 0):
 D1 buy_ep  pvp_pct <= 10 (estado no dia de formacao; NAO e a entrada de episodio com thinning do codigo - declaro a diferenca)
 D2 sell_ep pvp_pct >= 90
 D3 destr   flag_destruicao_capital.destruicao  (saude_ok = not destr: mesmo teste, nao duplico)
 D4 pvp_baixo pvp_pct < 30 (radar)
 D5 dygap_alto dygap_pct > 70 (radar)
 D6 liq_ok  volume 21d >= 500.000 (radar)
 D7 vistos  contagem 0-4 do radar (regressao linear)
 D8 pvp_lt05 P/VP < 0.5
 D9 vistos4 vistos == 4
Familia pre-registrada: (16 + 9) x 4 horizontes = 100 testes, alvo (a). BH 5% e Bonferroni sobre os 100.

## Inferencia
- PRIMARIA: Fama-MacBeth univariado. Por data, OLS do excesso sobre o preditor (rank [0,1] ou dummy), exige n>=20 fundos (discreto: >=5 em cada grupo). Media temporal dos coeficientes.
  SE Newey-West (Bartlett) com lag = h (lag 1 para h=1). P-valor PRIMARIO (para BH/Bonferroni) = t de Student com gl = N_eff-1, N_eff = floor(T/h) periodos nao sobrepostos (conservador de proposito).
  Tambem reporto p com NW normal (nao entra na decisao; usado como sensibilidade "leniente").
- Portfolios ordenados (continuos): quintis por rank na data (tercis se n<25), igual-peso. Spread = Q1(menor valor) - Q5 (maior). t NW lag h, hit rate, pior sequencia negativa, N_eff.
- Direcao hipotetica do sistema (apenas rotulo; testes bicaudais): favorece P/VP baixo, pct P/VP baixo, DY alto, DY gap pct alto, saude alta, liquidez alta, alavancagem baixa, vol baixa, score alto, momentum NAO definido (bicaudal).
- SOBREVIVE = p BH(primario) < 0.05 E spread Q1-Q5 com mesmo sinal do coeficiente FM. Bonferroni reportado ao lado.
- N minimo: n_periodos_efetivos < 30 sinalizado em toda linha (sera quase sempre, nos horizontes longos).

## Robustez (apenas para sobreviventes; se nao houver, sobre os 3 de menor p marcada "exploratoria")
(i) metade inicial x final; por ano; (ii) por segmento; (iii) excluindo liq < 500k e < 1.000.000; (iv) excluindo CACR11,MFII11,HCTR11,DEVA11,TGAR11,URPR11 e fundos com queda>40% em 1 dia;
(v) entrada em t+1 pregao; (vi) custos 0,10% e 0,30% ida-e-volta x giro das carteiras (h-espacadas) ; (vii) vies de sobrevivencia: restringir a fundos listados >= 2 anos antes de t, + direcao do vies;
(viii) placebo: >=500 (uso 2000) permutacoes do preditor entre fundos dentro de cada data + placebo adicional por deslocamento circular temporal do preditor dentro de cada ticker.

## Pergunta 8 (pre-registradas como estas comparacoes)
 Q-A destr (D3) -> coeficiente e retorno medio dos grupos; Q-B dygap_alto (D5) discrimina? (D5 + Q5 vs Q1 de dygap_pct); Q-C BUY episodio (D1) vs "barato vs pares" (Q1 de pvp_cs): diferenca pareada por data;
 Q-D P/VP<0.5 (D8) e tabela por faixas de P/VP (descritiva, exploratoria). Retorno de grupos sempre em excesso (a) com t NW; contagens de obs e de fundos distintos.

## Exploratorio (rotulado como tal, fora da familia)
Tudo mais: regressoes multivariadas, FM com nivel bruto, percentil com minimo 63, tabelas por faixa, interacoes, subperiodos de nao-sobreviventes, DY via informe CVM, retorno bruto etc.
