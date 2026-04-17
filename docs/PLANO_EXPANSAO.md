# Plano de Expansão — FII Analytics

> Documento vivo. Objetivo: transformar o coletor de dados atual em uma **ferramenta de decisão de investimento**, onde dados brutos viram **informação acionável**.
> Usuário único nesta fase: Carlos. Multi-usuário não é prioridade.

---

## 1. Visão do produto

Hoje o sistema **coleta** (yfinance, CVM, brapi) e **testa** hipóteses estatísticas sobre a data-com. Isso é um núcleo acadêmico sólido, mas não responde às perguntas que o investidor faz no dia a dia:

- *Minha carteira está saudável?*
- *Qual FII está descontado agora?*
- *Algum dos meus FIIs está devolvendo capital em vez de gerar renda?*
- *Vale comprar antes da próxima data-com?*

O plano abaixo organiza a evolução em camadas independentes, cada uma entregando valor sozinha.

---

## 2. Pilares da ferramenta

| # | Pilar | Responde a pergunta | Fonte de dados |
|---|---|---|---|
| 1 | Panorama da carteira | *Como estou?* | preço diário + CVM |
| 2 | Valuation | *Está caro ou barato?* | P/VP e DY histórico |
| 3 | Radar de oportunidades | *Onde alocar agora?* | ranking multi-critério |
| 4 | Saúde financeira | *Este fundo é sustentável?* | PL, rentabilidades, composição |
| 5 | Event study (núcleo original) | *Há padrão na data-com?* | janela ±10 dias úteis |
| 6 | Relatórios & alertas | *O que mudou desde ontem?* | diff + resumo periódico |

---

## 3. Métricas e indicadores (calculados, nunca armazenados)

Seguindo a regra do `CLAUDE.md`, tudo abaixo é **derivado on the fly** com VP e preço point-in-time.

### 3.1 Valuation

- **P/VP atual** = `preco_hoje / vp_vigente(data_entrega <= hoje)`
- **P/VP histórico** — série diária desde o início do histórico
- **Percentil P/VP (252d, 504d, 756d)** — posição do P/VP atual na sua própria distribuição histórica
- **DY 12m / 24m / 36m** = soma de dividendos nos últimos N meses / preço médio do período
- **DY atual vs médio** — diferença absoluta e percentual
- **DY Gap** = DY 12m − CDI atual (ou IPCA+prêmio; configurável)
- **DY Spread percentil** — posição do DY gap atual no próprio histórico

### 3.2 Panorama da carteira

- Lista consolidada: ticker, preço, VP, P/VP, DY 12m, DY 24m, DY mês, rentabilidade acumulada
- Alocação por **segmento** e por **tipo de ativo** (Tijolo / Papel / Híbrido)
- Proventos recebidos no mês / YTD / 12m
- Retorno total (preço + proventos) vs **IFIX** no mesmo período
- Concentração (Herfindahl simples): quanto da carteira está em 1 FII

### 3.3 Saúde financeira (arquivo CVM `complemento`)

- **Tendência do PL** — regressão linear últimos 6/12 meses
- **Destruição de capital (flag)** — `Rentabilidade_Efetiva > Rentabilidade_Patrimonial` por ≥ 3 meses consecutivos
- **PL por cota** estável ou crescente ao longo dos meses
- **Cotas Emitidas** — detecta emissões que diluem o investidor

### 3.4 Composição (arquivo CVM `ativo_passivo`)

- % imóveis físicos (`Direitos_Bens_Imoveis`)
- % recebíveis (`CRI`, `LCI`, `LCI_LCA`)
- % caixa (`Disponibilidades`)
- Classificação automática: **Tijolo** (>60% imóveis), **Papel** (>60% recebíveis), **Híbrido** (intermediário)

### 3.5 Radar de oportunidades — score composto

Cada FII recebe um score 0–100 combinando:

| Componente | Peso sugerido | Sinal |
|---|---|---|
| P/VP abaixo da média histórica | 25% | percentil < 30 |
| DY gap acima da média histórica | 25% | percentil > 70 |
| Saúde financeira OK | 25% | sem flag de destruição, PL estável/crescente |
| Liquidez mínima | 15% | volume 21d > piso configurável |
| Proximidade da data-com | 10% | dentro de −10 a +10 dias úteis |

Pesos **configuráveis** em arquivo YAML — não hardcoded.

---

## 4. Roadmap por fases

### Fase 1 — Dados e validação *(em andamento, definida no CLAUDE.md)*
- Coleta CVM + yfinance + brapi funcionando
- Validação dos dados com SNFF11
- Indicadores básicos implementados

### Fase 2 — Painel da carteira (**prioridade 1**)
Entrega de valor imediato. CLI com:
- `fii panorama` — tabela formatada de todos os FIIs monitorados
- `fii fii SNFF11` — detalhe de um FII
- `fii carteira` — alocação e rentabilidade consolidada

Módulos novos:
- `features/valuation.py` — P/VP e DY point-in-time
- `features/portfolio.py` — agregações da carteira
- `evaluation/panorama.py` — renderização CLI (rich/tabulate)

### Fase 3 — Saúde financeira e alertas (**prioridade 2**)
Protege contra perda. Antes de oportunidades, evitar armadilhas.
- `features/saude.py` — flags de destruição de capital, tendência do PL
- `features/composicao.py` — classificação Tijolo/Papel/Híbrido
- `evaluation/alertas.py` — gera alertas diários (arquivo Markdown + terminal)

### Fase 4 — Radar de oportunidades (**prioridade 3**)
- `features/score.py` — score composto com pesos YAML
- `evaluation/radar.py` — `fii radar` lista top N oportunidades
- Calendário de datas-com próximas

### Fase 5 — Event study (núcleo original, **prioridade 4**)
Manter como originalmente planejado no `CLAUDE.md`:
- Walk-forward com gap
- CAR/BHAR, t-test, Mann-Whitney
- Resultado: existe padrão estatisticamente significativo? Em quais FIIs?

### Fase 6 — Relatórios e histórico de decisões
- Relatório mensal Markdown/HTML: panorama + alertas + radar + proventos
- `fii diario` — diff desde a última execução (o que mudou)
- Persistir decisões tomadas → futuro backtest "minhas escolhas vs IFIX"

### Fase 7 — Interface e integração (futuro)
- Streamlit ou Flask mínimo
- MCP server para Claude consultar o banco em tempo real
- Exportação para planilha (imposto de renda, etc.)

---

## 5. Princípios de implementação (não negociáveis)

- **Point-in-time sempre** — nenhum cálculo usa dado com `data_entrega > t`
- **P/VP e DY nunca armazenados** — sempre recalculados
- **Ingestão isolada** — `ingestion.py` é a única porta para dados externos
- **Pesos e thresholds em YAML** — nada hardcoded em lógica de decisão
- **Testes de leakage** obrigatórios antes de qualquer decisão baseada em modelo
- **SQLite por enquanto** — migração Postgres só se houver dor real

---

## 6. O que **não** entra no plano

- Machine learning / LightGBM enquanto event study não estiver validado
- Multi-usuário, login, autenticação
- Adicionar novos FIIs além da lista curada antes da validação com SNFF11
- Recomendação automática de compra/venda (o sistema **informa**, Carlos **decide**)
- Notificações push / e-mail / Telegram (Fase 7+ se necessário)

---

## 7. Próximos passos concretos

1. Validar este plano com o usuário (ajustar pesos, prioridades, escopo)
2. Concluir Fase 1 (dados de SNFF11 no banco, validados)
3. Começar Fase 2 — `valuation.py` e comando `fii panorama`
4. Avaliar após Fase 2 se Fase 3 ou Fase 4 vem primeiro (depende de quantos FIIs forem adicionados)
