# Plano de Expansão — FII Analytics (v2)

> Revisão do `PLANO_EXPANSAO.md` após análise crítica.
> Mudanças principais: Fase 5 (event study) promovida para antes do Radar; score composto substituído por ranking descritivo até existir backtest; especificações ambíguas fechadas; política explícita de dados faltantes, reprodutibilidade e eventos corporativos.
> Usuário único: Carlos. Multi-usuário fora de escopo.

---

## 1. Visão do produto

O sistema hoje **coleta** (yfinance, CVM, brapi) e **testa** hipóteses estatísticas sobre a data-com. O objetivo desta expansão é transformar esse núcleo em uma **ferramenta de decisão pessoal**, respondendo:

- *Minha carteira está saudável?*
- *Algum dos meus FIIs está devolvendo capital em vez de gerar renda?*
- *Qual FII está descontado agora, em relação ao seu próprio histórico?*
- *Existe padrão estatisticamente significativo na data-com deste FII?*

O plano é organizado em camadas **independentes**, cada uma entregando valor sozinha, e **sem usar hipóteses não validadas como input de decisão**.

---

## 2. Pilares

| # | Pilar | Pergunta | Fonte |
|---|---|---|---|
| 1 | Panorama da carteira | *Como estou?* | preço diário + CVM |
| 2 | Valuation histórico | *Está caro ou barato vs si mesmo?* | P/VP e DY point-in-time |
| 3 | Saúde financeira | *É sustentável?* | PL, rentabilidades, composição, emissões |
| 4 | Event study | *Há padrão na data-com?* | janela ±10 dias úteis |
| 5 | Radar descritivo | *Onde olhar primeiro?* | filtros booleanos, não score numérico |
| 6 | Relatórios & histórico | *O que mudou? Minhas decisões bateram o IFIX?* | diff + log de decisões |

---

## 3. Métricas e indicadores (calculados, nunca armazenados)

Tudo abaixo é **derivado on the fly** com VP e preço point-in-time, seguindo o `CLAUDE.md`.

### 3.1 Valuation

- **P/VP em t** = `preco_em_t / vp_vigente(data_entrega <= t)`
- **Série histórica de P/VP** — diária desde o início do histórico do FII.
- **Percentil P/VP rolling** (janelas 252d, 504d, 756d):
  - Percentil calculado sobre a janela **até t−1**, comparando com o P/VP de t.
  - Isto elimina contaminação trivial do próprio dia na sua distribuição de referência.
- **DY N-meses** (N ∈ {12, 24, 36}):
  - Numerador: soma dos dividendos com **data-com** dentro de `[t − N meses, t]`.
  - Denominador: **preço de fechamento médio aritmético** no mesmo intervalo, usando apenas pregões.
  - Definição congelada neste documento para evitar divergência entre módulos.
- **DY Gap** = `DY 12m − taxa livre de risco em t` (default: CDI acumulado 12m; configurável).
- **Percentil do DY Gap** — mesma regra rolling até t−1.

### 3.2 Panorama da carteira

- Lista: ticker, preço, VP, P/VP, DY 12m/24m/mês, rentabilidade acumulada.
- Alocação por **segmento** e por **classificação de composição** (Tijolo / Papel / Híbrido, definida em §3.4).
- Proventos recebidos: mês / YTD / 12m.
- Retorno total (preço + proventos reinvestidos a preço de fechamento da data-pgto) vs **IFIX** no mesmo intervalo.
- Concentração: **Herfindahl simples** e **peso do maior FII**.
- **Calendário de datas-com** dos próximos 30 dias (trivial, já entra na Fase 2).

### 3.3 Saúde financeira (arquivo CVM `complemento`)

- **Tendência do PL por cota** — regressão linear dos últimos 6 e 12 meses; reportar coeficiente angular e R².
- **Flag de destruição de capital** (todas as condições obrigatórias):
  1. `Rentabilidade_Efetiva_Mes > Rentabilidade_Patrimonial_Mes` por **≥ 3 meses consecutivos**, E
  2. `Cotas_Emitidas` **não cresceu** no período (crescimento > 1% invalida a leitura — emissão distorce as duas rentabilidades), E
  3. `PL / Cotas_Emitidas` (VP por cota) com tendência **não-positiva** no mesmo período.
- **Emissões recentes** — detectar salto em `Cotas_Emitidas` mês a mês (> 1%) e exibir como evento.

### 3.4 Composição (arquivo CVM `ativo_passivo`)

- % imóveis físicos (`Direitos_Bens_Imoveis` / Ativo Total).
- % recebíveis (`CRI` + `LCI` + `LCI_LCA`).
- % caixa (`Disponibilidades`).
- Classificação:
  - **Tijolo**: imóveis ≥ 60%
  - **Papel**: recebíveis ≥ 60%
  - **Híbrido**: caso contrário

### 3.5 Radar descritivo (substitui o score composto da v1)

**Não há score numérico ponderado até existir backtest walk-forward validando a fórmula.**

Em vez disso, o radar é um **conjunto de filtros booleanos** exibidos como matriz:

| FII | P/VP pct < 30 | DY Gap pct > 70 | Saúde OK | Liquidez OK |
|---|---|---|---|---|
| AAAA11 | ✓ | ✓ | ✓ | ✓ |
| BBBB11 | ✓ | ✗ | ✓ | ✓ |

- **P/VP pct < 30** — P/VP atual abaixo do percentil 30 da sua janela rolling 504d.
- **DY Gap pct > 70** — DY Gap atual acima do percentil 70 da sua janela rolling 504d.
- **Saúde OK** — sem flag de destruição de capital (§3.3).
- **Liquidez OK** — volume financeiro médio 21d ≥ piso configurável em YAML.

FIIs com todos os ✓ aparecem no topo. Ordenação por número de ✓. **Nenhum peso arbitrário.**

**Proximidade da data-com NÃO entra no radar** enquanto a Fase 4 (event study) não validar padrão estatisticamente significativo. Se validar, entra como filtro adicional **apenas para os FIIs em que o padrão foi confirmado individualmente**.

---

## 4. Roadmap por fases

### Fase 1 — Dados e validação *(em andamento)*

Conforme `CLAUDE.md`. Conclusão: SNFF11 no banco, validado contra fonte.

### Fase 2 — Panorama e valuation *(prioridade 1)*

Entrega imediata de valor. Comandos CLI:

- `fii panorama` — tabela de todos os FIIs monitorados
- `fii fii SNFF11` — detalhe
- `fii carteira` — alocação e rentabilidade consolidada vs IFIX
- `fii calendario` — datas-com próximas (30d)

Módulos:

- `features/valuation.py` — P/VP e DY point-in-time (§3.1)
- `features/portfolio.py` — agregações da carteira (§3.2)
- `evaluation/panorama.py` — renderização CLI (rich/tabulate)

### Fase 3 — Saúde financeira e alertas *(prioridade 2)*

Proteger contra perda vem antes de buscar ganho.

- `features/saude.py` — flag de destruição (§3.3), tendência PL, emissões
- `features/composicao.py` — classificação Tijolo/Papel/Híbrido (§3.4)
- `evaluation/alertas.py` — alertas diários em Markdown + terminal

### Fase 4 — Event study *(prioridade 3, promovida da v1)*

**Promovida para antes do radar** porque o radar depende de saber se existe padrão na data-com.

- Walk-forward com gap obrigatório (CLAUDE.md §1)
- CAR/BHAR, t-test, Mann-Whitney
- Resultado por FII: existe padrão? magnitude? significância após correção de múltiplas comparações (Benjamini-Hochberg)?
- Output: lista de FIIs com padrão estatisticamente significativo → insumo para Fase 5

### Fase 5 — Radar descritivo *(prioridade 4)*

- `features/radar.py` — filtros booleanos (§3.5)
- `evaluation/radar.py` — `fii radar` lista top N
- Se Fase 4 confirmou padrão para algum FII, adicionar coluna "data-com próxima" **apenas para esses FIIs**

### Fase 6 — Relatórios e histórico de decisões

- Relatório mensal Markdown: panorama + alertas + event study + radar + proventos
- `fii diario` — diff desde a última execução
- **Log de decisões**: quando Carlos comprar/vender, registrar em tabela `decisoes` (ticker, data, lado, preço, motivo texto-livre)
- Futuro backtest: "minhas escolhas vs IFIX" — possível porque o log existe desde o início

### Fase 7 — Interface *(futuro, possivelmente descartado)*

Streamlit/Flask e MCP server **só se o CLI doer**. Sai do documento se após 6 meses não houver dor real.

---

## 5. Políticas transversais (novas na v2)

### 5.1 Dados faltantes / atrasados

- **CVM atrasada**: se o relatório mais recente disponível em t tem `data_entrega` há mais de 45 dias, exibir no panorama com aviso `[CVM defasada]`. Não preencher com valor futuro.
- **FII novo sem histórico suficiente**: percentis rolling exigem ≥ 252 pregões; abaixo disso, exibir `n/d` em vez de calcular com janela curta enganosa.
- **Dividendo sem data-com confiável**: yfinance é a única fonte de data-com; se faltar, o FII é excluído da análise de event study mas permanece no panorama.
- **NaN nunca vira zero silenciosamente** em cálculo de médias/percentis.

### 5.2 Reprodutibilidade

- `coletado_em` (timestamp) já exigido pelo CLAUDE.md para preços.
- **Snapshot diário do banco**: cópia comprimida de `fii_data.db` em `dados/snapshots/YYYY-MM-DD.db.gz`, retenção de 90 dias.
- Todo relatório gerado grava, no cabeçalho, o hash SHA-256 do snapshot usado. Análises passadas ficam reproduzíveis exatamente.

### 5.3 Eventos corporativos

- **Split/grupamento**: yfinance ajusta preço automaticamente. Guardar também preço **não-ajustado** para auditoria (`Close` vs `Adj Close`).
- **Mudança de CNPJ / fusão**: manter tabela `eventos_corporativos` (ticker, data, tipo, cnpj_antigo, cnpj_novo, observação). Ingestão CVM segue pelo CNPJ vigente em t.
- **Liquidação / fechamento**: marcar o FII como `inativo_em` (data); excluir de panorama e radar após essa data, preservar histórico.

### 5.4 Sobreposição de janelas de event study

FIIs pagam mensalmente, então janelas ±10 podem se sobrepor entre dois dividendos consecutivos.

- **Regra**: quando duas datas-com distam < 21 dias úteis, **o evento seguinte é descartado** daquela rodada de event study. Não truncar janela — isso introduz viés de seleção.
- Log explícito de quantos eventos foram descartados por sobreposição.

---

## 6. Princípios não negociáveis (mantidos)

- **Point-in-time sempre** — nenhum cálculo usa `data_entrega > t`.
- **P/VP e DY nunca armazenados** — sempre recalculados.
- **Ingestão isolada** — `ingestion.py` é a única porta para dados externos.
- **Thresholds em YAML** — nada hardcoded em lógica de decisão.
- **Testes de leakage obrigatórios** antes de qualquer decisão baseada em modelo.
- **Sem recomendação automática de compra/venda** — o sistema informa, Carlos decide.
- **SQLite até doer.**

---

## 7. Fora de escopo

- ML / LightGBM enquanto event study não validar padrão.
- Score numérico ponderado para ranking (substituído por filtros booleanos).
- Multi-usuário, login, autenticação.
- Notificações push / e-mail / Telegram.
- Adicionar FIIs além da lista curada antes da validação com SNFF11.

---

## 8. Próximos passos

1. Validar esta v2 com o usuário.
2. Concluir Fase 1 (SNFF11 validado).
3. Iniciar Fase 2: `valuation.py` + `fii panorama`.
4. Implementar `snapshots` (§5.2) junto com Fase 2 — barato agora, caro depois.
5. Reavaliar ordem Fase 3 vs Fase 4 após Fase 2, conforme quantos FIIs forem adicionados.
