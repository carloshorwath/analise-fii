# PLANO V4 — Camada Estratégica do FII Analysis

> **Status:** PROPOSTA — aguardando aprovação do Carlos para execução.
> **Data:** 2026-06-11
> **Para a IA implementadora:** antes de qualquer código, leia `docs/PROJETO.md` na íntegra
> (regra de governança §12.2). Este plano NÃO substitui o SSOT — ele descreve o trabalho
> futuro. Ao executar cada fase, atualize `docs/PROJETO.md` (ADRs, arquitetura) e
> `docs/STATUS_ATUAL.md` conforme o checklist §12.3.

---

## 1. Diagnóstico — por que o sistema "se repete e não é estratégico"

O sistema atual (Fases 0–5 + Decisão + Motor V2 + V3) é **estatisticamente honesto e
operacionalmente sólido**, mas tem cinco limitações estruturais que explicam a sensação
de repetição:

| # | Causa raiz | Evidência no código |
|---|---|---|
| 1 | **Universo de 6 tickers.** Não existe "mercado" para comparar. Sem cross-section, não há como dizer "FII X está caro *em relação a* Y" — só "X está caro vs seu próprio histórico". | `docs/PROJETO.md` §7 (lista curada); `config.py` TICKERS |
| 2 | **Nenhum motor de oportunidade relativa.** O sistema responde "como está cada FII?" mas nunca "o que eu deveria trocar por o quê?". A pergunta central do Carlos — *vender um FII que valorizou e comprar outro* — não tem módulo correspondente. | `decision/` tem recommender, advisor e abertos — todos por-ticker, nenhum par/rotação |
| 3 | **Relatório diário sem memória.** O `fii diario` e a página Hoje recalculam e exibem o mesmo painel todos os dias. Sem diff vs ontem, 95% do conteúdo é idêntico → sensação de repetição. | Pendente conhecido #3 em `STATUS_ATUAL.md`; `snapshot_runs` já guarda histórico mas ninguém compara N vs N-1 |
| 4 | **Sem síntese qualitativa integrada.** O único ponto de LLM é `fii consulta` (subprocess `gemini` CLI, `cli.py:83`) — desacoplado dos números locais, não versionado, sem fallback. | `cli.py:50-83` |
| 5 | **Sem ciclo de aprendizado.** Recomendações nunca são confrontadas ex-post ("a sugestão de 60 dias atrás teria batido o IFIX?"). Sem isso o sistema não acumula credibilidade nem evolui. | Roadmap P2 "Log de decisões" nunca implementado |

**Conclusão:** não é preciso reescrever nada. As fundações (point-in-time, snapshots,
walk-forward, CriticAgent, camada de decisão) são exatamente o que um motor estratégico
precisa por baixo. O que falta é construir **4 camadas em cima**: universo amplo,
oportunidades relativas, síntese LLM e memória de decisões.

---

## 2. Decisões de produto (responder antes de codar)

### 2.1 Streamlit vs "Python puro"

**Decisão: manter Streamlit como está e investir todo o esforço novo em pipeline headless.**

Racional:
- O valor estratégico novo (oportunidades, prompts, briefings) nasce em **artefatos**
  (Markdown, JSON, tabelas de snapshot) gerados por pipeline batch — não em widgets.
  Artefatos headless servem terminal, Streamlit, n8n, WhatsApp/Telegram e ChatGPT
  ao mesmo tempo.
- O Streamlit já existe, está estável (error boundary, snapshots com cache) e custa
  quase zero de manutenção. Reescrever UI agora é gastar energia onde não há dor.
- Regra para todo código novo deste plano: **lógica em `src/fii_analysis/`, UI é
  consumidor fino**. Nenhuma fase abaixo depende de Streamlit para entregar valor;
  as páginas novas são a última tarefa de cada fase, nunca a primeira.

Confirma ADR-14; não criar Flask/FastAPI/TUI adicionais.

### 2.2 LLM via n8n (gateway), com fallback de prompt manual

**Decisão: todo acesso a LLM passa por um gateway único que chama o webhook n8n do
Carlos.** Racional: troca de modelo sem tocar no projeto, chave fica no n8n (consistente
com ADR-10 — secrets fora do repo). Quando o n8n estiver fora do ar ou o Carlos preferir,
o mesmo gateway **gera um arquivo `.md` de prompt pronto para colar no ChatGPT** — o
prompt pack é o fallback de primeira classe, não um extra.

**Guardrail inegociável:** a saída do LLM **nunca altera** Sinal/Ação/badge — apenas
enriquece o racional, sempre rotulada `[OPINIÃO LLM — não validada estatisticamente]`.
Coerente com o princípio "o sistema informa, o investidor decide" (PROJETO.md §1).

### 2.3 Expansão do universo para o IFIX

**Decisão: universo dual.**
- **Carteira curada** (6 tickers) continua sendo o único universo de *decisão operacional*
  (badges HOLD/AUMENTAR/REDUZIR/SAIR) — a regra "lista curada, não automatizar" de
  PROJETO.md §7 permanece para a carteira.
- **Universo IFIX (~110 FIIs)** entra como universo de *observação e comparação*:
  radar, percentis cross-section, candidatos a rotação. FIIs do IFIX só viram posição
  se o Carlos decidir manualmente.

Isto exige novo ADR (ADR-23) atualizando PROJETO.md §7 — a regra atual proíbe a
expansão e precisa ser formalmente revisada, não silenciosamente ignorada.

---

## 3. Princípios herdados (inegociáveis — valem para todas as fases)

1. Point-in-time sempre (`Data_Entrega`, nunca `Data_Referencia`) — PROJETO.md §4.3.
2. P/VP e DY calculados, nunca persistidos (exceto snapshots como cache) — §4.4.
3. Split temporal com gap, sem shuffle; métricas finais só do teste — §4.1.
4. CriticAgent como gate de qualquer padrão novo reportado — §5.8.
5. NaN nunca vira zero; `n/d` explícito — ADR-13.
6. Sem ML (LightGBM etc.) enquanto o event study não validar padrão — ADR-08.
7. Secrets fora do repositório — ADR-10.
8. Concordância de sinais é heurística, nunca intervalo de confiança — ADR-18.

---

## 4. Arquitetura alvo

```
                       ┌──────────────────────────────────────────┐
                       │  PIPELINE DIÁRIO (headless, ~5 min)      │
                       │  fii update-prices                       │
                       │   ├─ preços brapi (carteira + IFIX)      │
                       │   ├─ CVM / CDI / XFIX11 / Focus          │
                       │   ├─ snapshot universo (scope=ifix)      │
                       │   ├─ motor de oportunidades  ◄── F2      │
                       │   ├─ diff vs snapshot anterior ◄── F4    │
                       │   └─ briefing MD + prompt packs ◄── F3   │
                       └───────────────┬──────────────────────────┘
                                       │ artefatos: snapshot_*, MD, JSON
              ┌────────────────┬───────┴────────┬─────────────────┐
              ▼                ▼                ▼                 ▼
        fii diario       Streamlit        n8n webhook       prompt .md
        (terminal)      (páginas Hoje/   (LLM automático,  (colar no
                         Oportunidades)   journal)          ChatGPT)
```

Módulos novos (todos com lógica pura, sem UI):

```
src/fii_analysis/
├── data/ifix.py                  # F1 — composição IFIX (B3 + fallback CSV)
├── decision/opportunities.py     # F2 — motor de rotação relativa
├── decision/decision_journal.py  # F4 — log de decisões + ex-post
├── evaluation/daily_diff.py      # F4 — diff snapshot N vs N-1
└── llm/                          # F3
    ├── context_builder.py        # dossiê JSON/MD por ticker e oportunidade
    ├── prompts.py                # templates versionados
    ├── gateway.py                # POST n8n + fallback prompt pack
    └── journal.py                # persistência de respostas com proveniência
```

---

## 5. Fases de implementação

> Ordem obrigatória: **F0 → F1 → F2 → {F3 ∥ F4} → F5**. F3 e F4 são independentes
> entre si. Cada fase = um PR com testes, docs atualizadas e critérios de aceite
> verificados. Não iniciar fase seguinte com a anterior reprovada.

---

### F0 — Fundação de testes (pré-requisito de tudo)

**Por quê primeiro:** as fases F1–F4 mexem em ingestão, snapshots e decisão. Sem rede
de testes, cada fase arrisca quebrar silenciosamente as garantias estatísticas que são
o diferencial do projeto. Já é a Prioridade 1 do roadmap (PROJETO.md §10).

**Tarefas:**

| # | Tarefa | Detalhe |
|---|---|---|
| F0.1 | Criar `tests/` com `conftest.py` | Fixture de banco SQLite **em memória** populado com dados sintéticos mínimos (2 tickers fictícios, ~600 pregões, 24 dividendos, 24 relatórios mensais com `data_entrega` ≠ `data_referencia`) |
| F0.2 | Testes de point-in-time | `features/indicators.py`: VP vigente respeita `data_entrega <= t`; caso armadilha: relatório entregue *depois* de t não pode aparecer |
| F0.3 | Testes de leakage e split | `models/walk_forward.py::validate_no_leakage` — casos com gap correto, sobreposição de 1 dia (deve falhar), janelas de event study < 21 dias úteis (descarte do evento seguinte, §4.5) |
| F0.4 | Testes de cálculo | P/VP, DY 12m, DY Gap, percentil rolling (janela mínima 252 → `n/d` abaixo), z-score; NaN propaga (nunca zero) |
| F0.5 | Testes da camada de decisão | `decision/recommender.py`: veto absoluto (BUY + `flag_destruicao_capital` → EVITAR/VETADA); concordância 3/3, 2/3, 1/3 |
| F0.6 | Testes de snapshot | `evaluation/daily_snapshots.py`: idempotência (rodar 2× no mesmo dia não duplica), status `failed` quando faltam dados |
| F0.7 | Smoke test do CLI | `python -m fii_analysis diario` contra snapshot da fixture, sem exceção |
| F0.8 | Runner local | `scripts/run_tests.ps1` (ou alvo no pyproject) executando `pytest -q` + cobertura; documentar comando em STATUS_ATUAL.md |

**Critérios de aceite:**
- `pytest` verde no Anaconda (`C:/ProgramData/anaconda3/python.exe -m pytest`).
- Cobertura ≥ 70% em `features/indicators.py`, `features/valuation.py`,
  `models/walk_forward.py`, `decision/recommender.py`.
- Nenhum teste depende de rede ou de `dados/fii_data.db` real.

---

### F1 — Universo IFIX (dados)

**Objetivo:** o sistema enxerga ~110 FIIs do IFIX com as mesmas garantias de qualidade
dos 6 curados, sem degradar o pipeline diário.

**Tarefas:**

| # | Tarefa | Detalhe |
|---|---|---|
| F1.1 | Migração 005: tabela `universo` | Colunas: `ticker`, `cnpj`, `em_ifix` (bool), `peso_ifix` (nullable), `data_referencia`, `fonte`, `atualizado_em`. PK (`ticker`, `data_referencia`). A carteira curada NÃO muda de mecanismo |
| F1.2 | `data/ifix.py` — composição IFIX | Fonte primária: carteira teórica do IFIX no site da B3 (download CSV/scraping). Fallback obrigatório: `dados/ifix_composicao.csv` mantido manualmente (atualização trimestral na revisão do índice). A função retorna a fonte usada; nunca falha silenciosamente |
| F1.3 | Ampliar ingestão CVM | Os ZIPs CVM **já contêm todos os FIIs** — ajustar o filtro de carga em `data/ingestion.py` para persistir `relatorios_mensais`/`ativo_passivo`/cadastro de todo ticker presente em `universo` (não só TICKERS). Cuidado com mapeamento CNPJ↔ticker (arquivo `geral` + `codigo_isin`) |
| F1.4 | Carga inicial de preços yfinance | Script idempotente para ~110 tickers com throttle (sleep entre chamadas, retry com backoff); tickers que falharem entram em lista de exclusão com motivo, nunca quebram a carga |
| F1.5 | Atualização diária via brapi | 110 tickers/dia ≈ 2.400 req/mês — confortável nos 15.000/mês. Usar endpoint de quote em lote se o plano brapi permitir; senão sequencial com throttle |
| F1.6 | Snapshot scope `ifix` | `evaluation/daily_snapshots.py` + `scripts/generate_daily_snapshots.py --scope ifix`. **Orçamento de performance: ≤ 10 min** para o universo completo — exige reescrever as consultas por-ticker mais quentes em batch (uma query por tabela, agregação em pandas), não 10+ queries × 110 tickers |
| F1.7 | Gates de qualidade por ticker | Percentis exigem ≥ 252 pregões (regra §4.8) → tickers novos exibem `n/d` e ficam fora do ranking; flag `cvm_defasada` (> 45 dias) exclui do motor de oportunidades; liquidez < piso exclui de candidato a compra |
| F1.8 | Corrigir falso positivo de destruição de capital | Pendência ALTA conhecida (`flag_destruicao_capital` dispara quando FII vende ativo e distribui ganho pontual). Com 110 FIIs o ruído escala — **resolver antes de F2**. Abordagem sugerida: marcar mês como "evento de capital" quando `rentab_efetiva` >> mediana 12m E `vp_por_cota` não cai proporcionalmente; exigir 2 meses não-saudáveis *excluindo* meses de evento. Validar contra casos reais nos 6 curados |

**Critérios de aceite:**
- `fii update-prices` completo (carteira + IFIX) em ≤ 10 min na máquina do Carlos.
- ≥ 90% dos tickers IFIX com preço D-1 e relatório CVM ≤ 45 dias; relatório de
  qualidade lista os excluídos e o motivo.
- Radar e Panorama continuam funcionando inalterados para os 6 curados (testes F0 verdes).
- ADR-23 escrito em PROJETO.md §11; §7 atualizado com o conceito de universo dual.

---

### F2 — Motor de Oportunidades (rotação relativa)

**Objetivo:** responder diretamente "o que vender e o que comprar no lugar?" com
honestidade estatística — o coração estratégico que falta.

**Design (`decision/opportunities.py`):**

```python
@dataclass
class RotationOpportunity:
    vender: str               # ticker da carteira
    comprar: str              # candidato do universo IFIX
    segmento: str             # rotação intra-segmento por padrão
    spread_pvp_pct: float     # pvp_percentil(vender) - pvp_percentil(comprar)
    spread_dy_gap: float
    delta_score: float        # score(comprar) - score(vender)
    custo_estimado_pct: float # corretagem B3 + IR 20% sobre ganho da venda
    spread_liquido_pct: float # spread bruto - custos
    dias_persistencia: int    # há quantos dias o par está acima do limiar
    racional: list[str]       # frases prontas para relatório/LLM
    flags_veto: list[str]     # qualquer veto → oportunidade suprimida
```

**Regras do motor (thresholds em `config.yaml`, nova seção `oportunidades`):**

1. **Lado VENDER:** posição da carteira com `pvp_percentil ≥ 80` (rico vs próprio
   histórico) OU badge REDUZIR/SAIR do portfolio_advisor.
2. **Lado COMPRAR:** FII do universo IFIX, mesmo segmento, com radar ≥ 3/4 vistos
   (obrigatórios: saúde OK e liquidez OK), `pvp_percentil ≤ 30`, sem `cvm_defasada`.
3. **Anti-ruído (essencial para não voltar a "se repetir"):**
   - spread líquido mínimo após custos (default: 25 pontos de percentil P/VP);
   - **persistência**: o par só é exibido após N dias consecutivos acima do limiar
     (default 3) — elimina oscilação diária;
   - **cooldown**: par exibido e não acionado entra em silêncio por 21 dias úteis;
   - máximo de 3 oportunidades por dia (as de maior spread líquido).
4. **Vetos absolutos:** destruição de capital no lado comprar; alavancagem >
   limite; dividend safety insustentável; IR + custos > spread.

**Validação obrigatória antes de exibir ao usuário (gate estatístico):**

| # | Tarefa | Detalhe |
|---|---|---|
| F2.1 | Implementar motor + thresholds YAML | Lógica pura, testável sem DB real |
| F2.2 | Backtest walk-forward da regra de rotação | Reusar `trade_simulator.py`: simular a regra nos últimos ~3 anos sobre o universo com dados suficientes, com gap temporal, custos e IR. Comparar vs (a) buy-and-hold da carteira, (b) XFIX11. Sem otimizar thresholds no mesmo período em que se mede o resultado (se otimizar, split treino/teste com gap) |
| F2.3 | CriticAgent sobre o backtest | Placebo: pares aleatórios do mesmo segmento; estabilidade: 1ª vs 2ª metade. Se reprovar → o motor é exibido como **descritivo** ("par estatisticamente não validado") com o mesmo padrão visual honesto do resto do sistema |
| F2.4 | Persistir em snapshot | Nova tabela `snapshot_opportunities` (migração 006) com versionamento de motor, espelhando o padrão de `snapshot_decisions` |
| F2.5 | Integração no pipeline | `update-prices` gera oportunidades após o snapshot; `fii oportunidades` no CLI lê do snapshot |
| F2.6 | Testes | Casos: par válido; veto por saúde; supressão por persistência < N; cooldown; custo engole spread; segmento diferente não pareia |

**Critérios de aceite:**
- Backtest reportado com Sharpe, retorno vs XFIX11, nº de rotações/ano, turnover —
  números **somente do período de teste**.
- Veredito do CriticAgent gravado junto da versão do motor no snapshot.
- Em dias sem oportunidade acima do limiar, a saída é literalmente
  **"Nenhuma oportunidade acionável hoje"** — silêncio é um resultado válido.

---

### F3 — Camada LLM: prompt packs + gateway n8n

**Objetivo:** transformar os números locais em análise qualitativa — automaticamente
(n8n) ou via prompt pronto para o ChatGPT — sem nunca contaminar a camada de decisão.

**Tarefas:**

| # | Tarefa | Detalhe |
|---|---|---|
| F3.1 | `llm/context_builder.py` | `build_ticker_context(ticker, session) -> dict` e `build_opportunity_context(opp, session) -> dict`. Conteúdo: métricas do snapshot (P/VP, percentis, DY, score, flags, CDI/Focus), resumo da série (52 semanas: máx/mín/atual), últimos 6 meses de saúde, composição, racional do motor. Tudo que o LLM precisa **vai no contexto** — o LLM não deve "saber" nada sozinho sobre números do fundo |
| F3.2 | `llm/prompts.py` | Templates versionados (`PROMPT_VERSION` por template): `analise_ticker`, `oportunidade_rotacao`, `revisao_carteira`, `briefing_semanal`. Estrutura fixa de resposta pedida ao LLM (seções: contexto de mercado, riscos não capturados pelos números, o que checar no último relatório gerencial, veredito qualitativo). Instrução explícita no template: "os números fornecidos são a verdade; não invente valores" |
| F3.3 | `llm/gateway.py` | `ask_llm(payload: dict, timeout=120) -> LlmResult`. POST no webhook n8n; URL e token via env (`N8N_FII_WEBHOOK_URL`, `N8N_FII_TOKEN`) carregados de `.env` **fora do repo** (mesmo padrão ADR-10 do brapi). Retry 2× com backoff. Status `OK`/`TIMEOUT`/`ERRO`/`SEM_CONFIG`. Em qualquer falha → degrada para prompt pack |
| F3.4 | Prompt pack (fallback de 1ª classe) | `export_prompt_pack(context, template) -> Path`: grava `dados/prompts/YYYY-MM-DD_<template>_<ticker>.md` com prompt completo + contexto embutido, pronto para colar no ChatGPT. Sempre disponível mesmo sem n8n |
| F3.5 | CLI | `fii prompt TICKER` e `fii prompt --oportunidades` (gera packs); `fii analise TICKER --via-n8n` (gateway, imprime resposta e salva no journal). Migrar `fii consulta` para o gateway mantendo o comando como alias (depreciação documentada) |
| F3.6 | `llm/journal.py` | Migração 007: tabela `llm_journal` (`data`, `template`, `prompt_version`, `modelo` informado pelo n8n, `ticker/par`, `snapshot_run_id`, `resposta_md`, `latencia_ms`). Toda resposta automática é persistida com proveniência — auditável e comparável entre modelos |
| F3.7 | Workflow n8n (lado do Carlos) | Documentar contrato do webhook em `docs/N8N_CONTRACT.md`: request `{template, prompt_version, contexto, pergunta}` → response `{resposta_md, modelo, tokens}`. A criação do workflow em si é tarefa do Carlos (ou via skill n8n-mcp), não deste repo |
| F3.8 | Testes | Gateway com mock HTTP (sem rede): OK, timeout, sem config → fallback; context_builder com fixture F0: nenhum NaN vira número, campos `n/d` preservados; templates renderizam sem placeholders órfãos |

**Critérios de aceite:**
- Com n8n fora do ar, `fii prompt KNIP11` ainda entrega um `.md` completo e colável.
- Nenhuma chave/URL no repositório (verificar com grep antes do PR).
- Resposta LLM aparece nos relatórios sempre sob o rótulo
  `[OPINIÃO LLM — não validada estatisticamente]` e nunca altera Ação/badge (teste F0.5 continua verde).
- ADR-24 escrito (gateway n8n + fallback prompt pack).

---

### F4 — Memória estratégica: diff diário + diário de decisões

**Objetivo:** matar a repetição (só mostrar o que mudou) e criar o ciclo de
aprendizado (medir ex-post o que o sistema recomendou).

**Tarefas:**

| # | Tarefa | Detalhe |
|---|---|---|
| F4.1 | `evaluation/daily_diff.py` | Comparar snapshot ready N vs N-1: mudanças de Ação/badge, radar (filtros que viraram ✓/✗), score (Δ ≥ limiar), oportunidades novas/expiradas, datas-com próximas (≤ 5 dias úteis), alertas estruturais novos. Saída: `DailyDiff` dataclass + render MD |
| F4.2 | `fii diario --diff` (tornar default) | Estrutura do relatório: **(1) O que mudou desde ontem** (vazio = "Nada mudou"), **(2) Oportunidades acionáveis hoje**, **(3) Painel completo** (colapsado/no fim). A informação repetida sai da frente do usuário, não do sistema |
| F4.3 | Migração 008: tabela `decisoes_log` | `data`, `tipo` (COMPRA/VENDA/ROTACAO/IGNORADA), `ticker_vendido`, `ticker_comprado`, `quantidade`, `preco`, `opportunity_id` (nullable — qual sugestão originou), `racional_usuario` |
| F4.4 | Registro via CLI e Streamlit | `fii registrar-decisao ...` + formulário simples na página Carteira. Registrar "IGNORADA" é tão importante quanto registrar execução (mede falsos positivos do motor) |
| F4.5 | Review ex-post | `fii review [--periodo 90]`: para cada oportunidade exibida nos últimos N dias — executada ou não — calcular retorno realizado do par vs XFIX11 desde a sinalização. Métricas: hit-rate, retorno médio por rotação, custo de oportunidade das ignoradas. Render MD mensal em `dados/alertas/` |
| F4.6 | Testes | Diff com snapshots sintéticos (nada mudou / badge mudou / oportunidade nova); review com decisões fictícias e preços da fixture |

**Critérios de aceite:**
- Dois dias seguidos sem mudança de dados ⇒ relatório diário abre com "Nada mudou
  desde ontem" em ≤ 5 linhas.
- `fii review` produz tabela de hit-rate das oportunidades com ≥ 1 ciclo completo.
- Log de decisões alimentável em < 30 segundos por operação.

---

### F5 — Interfaces (última camada, esforço mínimo)

| # | Tarefa | Detalhe |
|---|---|---|
| F5.1 | Página `16_Oportunidades.py` (grupo Diário) | Lê `snapshot_opportunities` via `snapshot_ui.py` (cache 5 min). Cards: vender X → comprar Y, spread líquido, persistência, racional, botões "Gerar prompt" e "Registrar decisão" |
| F5.2 | Página Hoje | Seção "Oportunidades de rotação" (top 3) + bloco "O que mudou desde ontem" (F4.1) |
| F5.3 | Página Carteira | Formulário de registro de decisão (F4.4) |
| F5.4 | CLI | `fii oportunidades`, `fii review`, `fii registrar-decisao`, `fii prompt` — todos já implementados nas fases anteriores; aqui só consolidar `--help` e docs |
| F5.5 | Docs finais | Atualizar PROJETO.md (§2 pilares: adicionar pilar 8 "Oportunidades de rotação" e pilar 9 "Síntese LLM"; §3.4 estrutura; §6 interfaces) e STATUS_ATUAL.md completo |

---

## 6. KPIs do programa (medem se "realmente ajuda")

| KPI | Alvo | Como medir |
|---|---|---|
| Tempo da rotina diária do Carlos | ≤ 5 min | `update-prices` + leitura do diff |
| Sinal/ruído do relatório diário | Dias sem mudança ⇒ relatório ≤ 5 linhas | F4.2 |
| Oportunidades acionáveis | 1–6 por mês (não zero, não dezenas) | contagem em `snapshot_opportunities` |
| Hit-rate das rotações sinalizadas | > 50% vs XFIX11 em 90 dias (medido, não prometido) | `fii review` |
| Cobertura do universo IFIX | ≥ 90% com dados completos D-1 | relatório de qualidade F1 |
| Cobertura de testes (módulos críticos) | ≥ 70% | pytest --cov |
| Latência do pipeline diário completo | ≤ 10 min | log do `update-prices` |

---

## 7. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Scraping da composição IFIX na B3 quebra | F1 para | Fallback CSV manual trimestral (F1.2) é obrigatório, não opcional |
| yfinance rate-limit na carga inicial de 110 tickers | Carga falha no meio | Throttle + retry + idempotência (retomar de onde parou) |
| Snapshot de 110 tickers estoura o orçamento de 10 min | Pipeline diário inviável | Reescrita batch das queries (F1.6); medir antes/depois |
| Falso positivo de destruição de capital escala com o universo | Motor de rotação veta bons candidatos | F1.8 resolve **antes** de F2 |
| Backtest da rotação reprova no CriticAgent | Motor sem validação estatística | Exibir como descritivo com rótulo honesto — o sistema já tem esse padrão; não suprimir o recurso, suprimir a falsa confiança |
| LLM inventa números | Decisão baseada em alucinação | Contexto completo no prompt + instrução "números fornecidos são a verdade" + rótulo de opinião + journal auditável |
| Escopo crescer (ML, multi-usuário, novos índices) | Plano nunca termina | Fora de escopo permanece: ML antes de validação (ADR-08), autenticação, IR, apps móveis |

---

## 8. Governança — ADRs a registrar durante a execução

| ADR | Decisão | Fase |
|---|---|---|
| ADR-23 | Universo dual: carteira curada (decisão) + IFIX (observação/comparação) | F1 |
| ADR-24 | LLM via gateway n8n com fallback prompt pack; LLM nunca altera Ação | F3 |
| ADR-25 | Motor de rotação com gate CriticAgent; silêncio é resultado válido | F2 |
| ADR-26 | Relatório diário diff-first (mostrar mudança, não estado) | F4 |

Checklist §12.3 do PROJETO.md ao final de **cada** fase. STATUS_ATUAL.md regenerado
ao final de F1, F2, F3, F4 e F5 (todas são mudanças estruturais).

---

## 9. Resumo executivo para a IA implementadora

1. Leia `docs/PROJETO.md` inteiro. Depois este plano. Depois comece por **F0 (testes)**.
2. Nunca quebre os princípios da seção 3 — eles são o motivo de este projeto valer
   mais que os sites grandes.
3. Toda lógica nova em `src/fii_analysis/` (pura, testável); UI e CLI são consumidores.
4. Cada fase: PR isolado, testes verdes, critérios de aceite verificados, docs
   atualizadas, ADR registrado.
5. O objetivo final, em uma frase: **todo dia útil, em 5 minutos, o Carlos sabe o que
   mudou, se existe alguma troca que vale a pena, e tem um dossiê pronto para
   aprofundar com LLM — e o sistema mede a posteriori se os próprios conselhos
   funcionaram.**
