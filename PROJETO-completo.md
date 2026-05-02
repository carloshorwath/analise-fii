# PROJETO.md — Sistema de Análise e Recomendação de FIIs

> **Documento técnico-estratégico — Blueprint definitivo**
> **Versão:** 1.0
> **Contexto:** Desenvolvimento solo alavancado por IA generativa
> **Filtro mestre:** *“Isso é gerenciável e mantível por uma pessoa usando IA como copiloto?”*

---

## Sumário

1. [Visão Geral e Proposta de Valor](#1-visão-geral-e-proposta-de-valor)
2. [Público-Alvo e Personas](#2-público-alvo-e-personas)
3. [Filosofia de Desenvolvimento Solo + IA](#3-filosofia-de-desenvolvimento-solo--ia)
4. [Escopo Funcional Completo](#4-escopo-funcional-completo)
5. [Indicadores e Métricas — Especificação Matemática](#5-indicadores-e-métricas--especificação-matemática)
6. [Motor de Recomendação — Coração do Produto](#6-motor-de-recomendação--coração-do-produto)
7. [Fontes de Dados](#7-fontes-de-dados)
8. [Arquitetura Técnica](#8-arquitetura-técnica)
9. [Stack Tecnológico Recomendado](#9-stack-tecnológico-recomendado)
10. [Modelo de Dados](#10-modelo-de-dados)
11. [UX/UI e Design](#11-uxui-e-design)
12. [Segurança Técnica](#12-segurança-técnica)
13. [Monetização](#13-monetização)
14. [Roadmap e Faseamento](#14-roadmap-e-faseamento)
15. [Riscos e Mitigações](#15-riscos-e-mitigações)
16. [Custos Estimados](#16-custos-estimados)
17. [Métricas de Sucesso](#17-métricas-de-sucesso)
18. [Glossário](#18-glossário)
19. [Anexos e Próximos Passos](#19-anexos-e-próximos-passos)
20. [Autocrítica do Documento](#20-autocrítica-do-documento)

---

## 1. Visão Geral e Proposta de Valor

### Resumo executivo

Sistema SaaS web (PWA mobile-first) que avalia, fundo a fundo, os FIIs em carteira do investidor pessoa física brasileiro e devolve, em segundos, uma recomendação acionável (**Comprar / Aumentar / Manter / Reduzir / Vender / Evitar**) com convicção (**baixa / média / alta**), justificativa em linguagem natural e indicadores fundamentalistas pertinentes. Não é homebroker, não toca em dinheiro, não trata IR. É uma camada de inteligência analítica que substitui o “achismo de WhatsApp” por critério auditável e personalizado para a carteira real do usuário.

### Problema que o sistema resolve

O investidor de FIIs brasileiro hoje tem três dores conjugadas:

1. **Paralisia de decisão.** Quando o fundo cai 8 %, ele não sabe se aporta, segura ou vende. Pergunta no Twitter, lê analista A e analista B com opiniões opostas, e congela.
2. **Falta de critério próprio.** A maioria não consegue olhar para uma DRE de FII de papel ou um relatório gerencial de FII de tijolo e dizer “aqui tem problema de inadimplência” ou “a vacância está estruturalmente alta”.
3. **Viés emocional.** Vende ganhador cedo, segura perdedor por anos, ancorado em preço médio. A “marcação a mercado” da B3 dói quando devia ser ignorada — e dá euforia quando devia acender alerta.

Os concorrentes (Status Invest, Investidor10, Funds Explorer, Clube FII, Suno) entregam **dados**. O usuário ainda precisa interpretar. Este produto entrega **decisão fundamentada**, calibrada pela carteira que ele de fato tem.

### Proposta única de valor (UVP)

> **“Cole sua carteira. Receba, em 30 segundos, o que fazer com cada FII e porquê — em português claro, com indicadores que você entende, sem precisar abrir 12 sites.”**

### O que o sistema é e não é

| É | Não é |
|---|---|
| Conselheiro analítico de FIIs | Homebroker / corretora |
| Camada de decisão sobre carteira já existente | Custodiante |
| Recomendação fundamentalista + qualitativa | Robô de execução de ordens |
| Justificativa em linguagem natural | Cálculo de IR / DARF / DIRPF |
| Dashboard de “o que fazer hoje” | Conciliação de notas de corretagem |
| Alertas de mudança de cenário | Plataforma de educação genérica |

> A regra é dura: **não tocamos em dinheiro nem em obrigações fiscais**. Isso reduz brutalmente a superfície regulatória, jurídica e operacional. Solo dev não tem condição de operar sob escrutínio de Banco Central ou Receita Federal.

### Diferenciais frente a concorrentes

| Concorrente | Foco principal | Onde falha | Onde nós ganhamos |
|---|---|---|---|
| **Status Invest** | Screener e dados crus | Não personaliza, não decide | Decisão por carteira, justificativa em LN |
| **Investidor10** | Indicadores e ranking | Mesmo problema, paywall confuso | Recomendação acionável, UX focada em decisão |
| **Funds Explorer** | Dados e gráficos detalhados | UX densa, sem opinião | Opinião auditável, mobile-first |
| **Clube FII** | Comunidade e curadoria | Curadoria genérica, não vê *sua* carteira | Personalização real |
| **Suno** | Research humano + carteira modelo | Caro, lento, opinião monolítica | Algorítmico, instantâneo, transparente |

**Nosso posicionamento:** *“O analista que olha sua carteira de verdade — em vez de te vender uma carteira recomendada genérica.”*

### Posicionamento de mercado

- **Categoria:** PropTech / WealthTech analítica.
- **Tier de preço:** entre o gratuito (Status Invest) e o caro (Suno R$ 50–80/mês). Sweet spot **R$ 19–39/mês**.
- **Tom de marca:** técnico, sóbrio, “você no controle”. Sem hype, sem promessa de retorno, sem influencer-speak.
- **Compliance-aware:** todo conteúdo é **análise**, não recomendação personalizada no sentido CVM 20 — isso precisa estar martelado no rodapé, T&C e em cada tela de recomendação. Vê seção 15 (riscos).

---

## 2. Público-Alvo e Personas

### Persona 1 — Rafael, 32, “O Acumulador Metódico”

- **Perfil:** dev de software, R$ 12k/mês, R$ 180k em FIIs, 18 fundos, aporta R$ 3k/mês.
- **Comportamento:** já leu “Pai Rico, Pai Pobre”, segue 3 canais de YouTube, tem planilha. Aporta no FII que “está mais barato” no dia 5.
- **Dor:** “Será que estou diversificado de verdade? Esses 18 fundos têm sobreposição? Se um cair 10 %, devo aumentar ou é sinal?”
- **Jornada-chave:** dia 5 do mês, recebe proventos. Abre o app, vê dashboard *“o que fazer com o dinheiro que entrou”*: 3 sugestões de aporte ranqueadas por convicção, 1 alerta de FII problemático.

### Persona 2 — Mariana, 45, “A Investidora de Renda”

- **Perfil:** dentista autônoma, R$ 25k/mês, R$ 800k em FIIs, busca substituir parte da renda ativa por passiva.
- **Comportamento:** odeia volatilidade. Não entende muito de balanço, segue indicação de assessor.
- **Dor:** “Esse FII de papel rende 1,2 % ao mês mas o assessor parou de comentar. Está tudo bem? E aquele de shopping que não voltou pós-pandemia?”
- **Jornada-chave:** recebe alerta no celular: *“XPLG11: queda de 6 % em 5 dias + redução de DY anunciada. Recomendação mudou de Manter para Reduzir.”* Abre o app, lê justificativa de 3 parágrafos, decide com base em algo concreto.

### Persona 3 — Eduardo, 28, “O Novato Ambicioso”

- **Perfil:** primeiro emprego CLT, R$ 6k/mês, R$ 15k em 5 FIIs comprados pela dica do amigo.
- **Comportamento:** ainda confunde DY com Cap Rate. Quer aprender mas não tem tempo nem paciência para curso.
- **Dor:** “Comprei MXRF11, KNRI11, HGLG11, BTLG11, IRDM11. Tá certo? Tô concentrado em alguma coisa?”
- **Jornada-chave:** primeira vez no app, faz onboarding, cola a carteira via CSV exportado da corretora. Recebe diagnóstico: *“Você está 60 % em FIIs de papel, 40 % em tijolo. Concentração baixa em logística. Eis o que isso significa…”* — clica nas explicações inline e aprende lendo sobre **a sua** carteira.

### Casos de uso prioritários (top 5)

1. **Onboarding rápido + diagnóstico inicial** (≤ 5 minutos para o primeiro “aha”).
2. **“Recebi proventos, onde aportar?”** (recorrência mensal, gatilho de hábito).
3. **“Caiu 8 %, e agora?”** (gatilho de evento, alerta).
4. **“Esse fundo ainda faz sentido?”** (revisão trimestral).
5. **“Minha carteira está saudável como um todo?”** (análise consolidada, gatilho semestral).

---

## 3. Filosofia de Desenvolvimento Solo + IA

> **Esta seção define todas as decisões subsequentes. Lê com atenção; o resto do documento é coerente com ela.**

### Princípios de arquitetura para dev solo com IA

1. **Simplicidade radical.** Cada peça que entra no sistema é uma peça que precisa ser mantida por uma pessoa. Default: *não adicionar*. Quando adicionar, escolher o mais boring possível.
2. **Convenção sobre configuração.** Frameworks opinativos (Next.js, Prisma) > frameworks flexíveis (Express + 12 plugins). A IA conhece a convenção; ela alucina menos.
3. **Monolito modular > microsserviços.** Um repositório, um deploy, módulos bem separados internamente. Sem Kafka, sem service mesh, sem Kubernetes. Solo + microsserviços = morte.
4. **Type-safety end-to-end.** TypeScript em tudo. tRPC ou similar entre front e back. Erros em compile-time > erros em produção, porque dev solo não tem QA.
5. **Managed > self-hosted, sempre.** Postgres gerenciado, auth gerenciada, deploy gerenciado, fila gerenciada. O tempo do founder vale R$ X/h; o SaaS custa R$ X/mês. Comparação fácil.
6. **Boring tech wins.** PostgreSQL > MongoDB. Next.js > framework do mês. Stripe > construir billing. A IA tem 10x mais dados de treino sobre tecnologias maduras.
7. **Convenção de pastas e nomes que a IA decora.** `app/`, `components/`, `lib/`, `server/`, `db/`. Nomes de arquivo descritivos (`recommendationEngine.ts`, não `engine.ts`).

### O que a IA faz bem (delegar agressivamente)

| Tarefa | Nível IA | Observação |
|---|---|---|
| CRUD completo (rotas + UI + validação) | Alto | Especialmente Next.js + Prisma + shadcn |
| Parsing de CSV / extração de PDF estruturada | Alto | Inclusive com bibliotecas como `papaparse`, `pdf-parse` |
| Transformações de dados (mapear, agrupar, séries temporais) | Alto | TypeScript + lodash/date-fns |
| Componentes de UI a partir de wireframe textual | Alto | shadcn/ui é o sweet spot |
| Prompt engineering inicial (rascunho + iteração) | Médio-alto | Humano valida saídas em casos reais |
| Testes unitários (geração) | Alto | Humano revisa testes críticos |
| Documentação técnica e READMEs | Alto | |
| Migrations SQL simples | Alto | |
| Configuração de Vercel/Supabase | Médio | IA conhece bem mas detalhes mudam |
| Mensagens de commit, changelogs | Alto | |
| Refactoring guiado (renomear, extrair função) | Alto | Ferramentas tipo Cursor com agente |

### O que ainda exige humano (**não delegar cegamente**)

| Tarefa | Por quê |
|---|---|
| Decisões de produto e priorização | Trade-offs de negócio, não técnicos |
| Validação de recomendações financeiras | Risco regulatório e reputacional |
| Design do motor de scoring (pesos, regras) | Conhecimento de domínio + responsabilidade |
| Seleção de fontes de dados confiáveis | IA pode sugerir fonte morta ou ilegal de scraping |
| Escolha de copy de marketing e tom de marca | Voz de marca é humana |
| Revisão final de qualquer texto que vai para usuário sobre dinheiro | Hallucination risk |
| Decisões de compliance (T&C, disclaimers, LGPD) | Exige interpretação jurídica |

### Workflow recomendado

```
Ideia ──► Spec curta em Markdown (humano + IA brainstorm)
       └► Quebrar em tickets pequenos (≤ 1 dia cada)
              │
              ▼
       Cursor / Claude Code gera implementação inicial
              │
              ▼
       Humano revisa, ajusta, testa manualmente
              │
              ▼
       IA gera testes + documentação
              │
              ▼
       Humano abre PR pra si mesmo, revê com IA atuando como reviewer
              │
              ▼
       Merge → deploy automático (Vercel)
              │
              ▼
       Sentry + análise de uso reais → próximo ticket
```

**Cadência sustentável solo:** 4–6 horas de “fluxo de código” por dia útil. Acima disso, qualidade despenca e bugs sutis acumulam — especialmente perigoso em produto financeiro.

### Como dividir “IA executa” vs “humano valida”

| Situação | IA executa | Humano valida |
|---|---|---|
| Componente visual padrão (botão, card, form) | ✅ | Acessibilidade e edge cases |
| Endpoint CRUD | ✅ | Autorização e regras de negócio |
| Cálculo de indicador (DY, P/VP) | ✅ rascunho | **Sempre** com testes manuais sobre dados reais |
| Geração de justificativa por LLM | ✅ produção | **Sempre** com guardrails + amostragem manual semanal |
| Migration de schema | ✅ | Sempre revisar antes de aplicar em prod |
| Lógica de recomendação (regras) | Parcialmente | Humano define os pesos e thresholds |

### Padrões de código que maximizam IA

- **Módulos pequenos** (≤ 300 linhas/arquivo). Contexto curto = IA mais precisa.
- **Funções puras quando possível.** Mais fácil de testar, mais fácil de IA gerar.
- **Comentários como contexto pra IA, não pra humano.** Ex.: `// Calcula DY 12m: soma proventos dos últimos 12 meses sobre preço atual. Fonte: B3.`
- **Convenção de pastas estável.** A IA aprende o seu repo; mudar layout custa contexto.
- **Monorepo com `pnpm workspaces`** para frontend/backend/scripts. Tudo num só lugar acelera IA contextual (Cursor/Claude Code indexam melhor).
- **Tipos exportados em `types/`** centrais. IA referencia.
- **Nada de mágica.** Sem decorators exóticos, sem AOP, sem metaprogramação. IA escorrega nessas coisas.

### Estratégia de testes com IA

- **MVP:** testes manuais + smoke tests em rotas críticas. Não vale a pena cobertura alta cedo.
- **V1:** testes unitários gerados por IA para o **motor de recomendação** (essa parte exige), revisados linha a linha.
- **V2:** snapshot tests para UI, integration tests para fluxos principais.
- **Sempre:** testes para qualquer função que faça cálculo financeiro. Bug aqui = perda de confiança = morte do produto.

### Trade-offs aceitos conscientemente

- **Performance hiperotimizada:** abrimos mão. Se uma página carrega em 800 ms em vez de 200 ms, ok. Otimizamos quando o uso justificar.
- **Customização visual exótica:** abrimos mão. shadcn/ui pronto, ajustes mínimos.
- **Features de borda (i18n para 5 idiomas, modo offline complexo):** abrimos mão até prova de demanda.
- **Disponibilidade 99,99 %:** abrimos mão. 99,5 % é aceitável; é Vercel + Supabase com SLA de plataforma.
- **Time zone exótico, calendários alternativos:** ignoramos. Mercado brasileiro, BRT, dia útil B3.

---

## 4. Escopo Funcional Completo

> Legenda: **Prioridade** = MVP / V1 / V2. **Complexidade** = Baixa / Média / Alta. **Viabilidade IA** = Alta / Média / Baixa.

### 4.1. Cadastro simplificado da carteira

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Input manual ticker + qtd + PM (opcional) | MVP | Baixa | Alta |
| Validação de ticker contra base interna de FIIs | MVP | Baixa | Alta |
| Importação via CSV (template fornecido) | MVP | Baixa | Alta |
| Importação por colagem de texto (parser inteligente via LLM) | V1 | Média | Alta |
| Edição rápida (inline) | MVP | Baixa | Alta |
| Múltiplas carteiras por usuário | V1 | Baixa | Alta |
| Histórico de aportes (opcional, sem fins fiscais) | V1 | Média | Alta |

### 4.2. Análise individual por FII (motor de recomendação)

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Sinal: Comprar / Aumentar / Manter / Reduzir / Vender / Evitar | MVP | Alta | Média (humano define regras) |
| Convicção: Baixa / Média / Alta | MVP | Média | Média |
| Justificativa em linguagem natural (3–6 frases) | MVP | Alta | Alta (LLM) |
| Painel de indicadores fundamentalistas | MVP | Média | Alta |
| Alertas de risco ativos (vacância > X, LTV > Y) | V1 | Média | Alta |
| Histórico de recomendações (versionado) | V1 | Média | Alta |
| Comparativo com pares do mesmo segmento | V1 | Média | Média |

### 4.3. Análise consolidada da carteira

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Diagnóstico geral em LN (1 parágrafo) | V1 | Alta | Alta |
| Concentração por segmento, gestora, tipo (papel/tijolo/FoF) | MVP | Média | Alta |
| Detecção de sobreposição (FoF que detém os mesmos FIIs já em carteira) | V1 | Alta | Média |
| Lista de FIIs problemáticos da carteira | MVP | Média | Alta |
| Sugestões de rebalanceamento direcional (não “compre X”, mas “reduza concentração em logística”) | V1 | Alta | Média |
| Score de saúde da carteira (0–100) | V1 | Alta | Média |

### 4.4. Indicadores fundamentalistas

Detalhe na seção 5. Categorias: rentabilidade, valuation, qualidade, risco, liquidez.

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Cálculo de 8 indicadores principais | MVP | Média | Alta |
| Painel completo (15+ indicadores) | V1 | Média | Alta |
| Comparativo com mediana do segmento | V1 | Média | Alta |
| Séries históricas em gráfico | V1 | Média | Alta |

### 4.5. Sistema de scoring proprietário

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Score numérico 0–100 por FII | MVP | Alta | Baixa (design humano) |
| Decomposição do score (quanto vem de valuation, qualidade, risco) | V1 | Alta | Média |
| Ajuste de pesos por tipo (papel vs tijolo vs FoF) | MVP | Alta | Baixa |
| Página de transparência: “como calculamos” | MVP | Baixa | Alta |

### 4.6. Análise qualitativa

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Extração estruturada de relatórios gerenciais (PDF) via LLM | V1 | Alta | Alta |
| Tracking de fato relevante via FNET / RSS CVM | V1 | Alta | Média |
| Sumarização automática de fato relevante (LLM) | V1 | Média | Alta |
| Tags qualitativas (gestão experiente, vacância controlada, etc.) | V1 | Média | Média |
| Concentração de inquilinos / devedores (top 5) | V1 | Média | Média |

### 4.7. Comparadores

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| FII vs pares (mesmo segmento, top 5 por liquidez) | V1 | Média | Alta |
| FII vs IFIX (rentabilidade, beta, drawdown) | V1 | Média | Alta |
| Sugestão de alternativas ao FII problemático | V2 | Alta | Média |

### 4.8. Alertas

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Mudança de status de recomendação (ex.: Manter → Reduzir) | V1 | Média | Alta |
| Queda de preço > X % em N dias | V1 | Baixa | Alta |
| Mudança relevante de DY (queda > 20 % vs média 12m) | V1 | Média | Alta |
| Fato relevante publicado | V1 | Alta | Média |
| Canal: e-mail (Resend) + push (PWA) | V1 | Média | Alta |

### 4.9. Educação contextual

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Tooltips inline em cada indicador | MVP | Baixa | Alta |
| Glossário pesquisável | MVP | Baixa | Alta |
| Mini-explicações “o que isso significa para você” | MVP | Média | Alta |

### 4.10. Dashboard de decisão

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Tela única “o que devo fazer hoje?” | MVP | Média | Alta |
| Top 3 ações sugeridas (aportar X, reduzir Y, atenção em Z) | MVP | Alta | Média |
| Resumo de alertas do dia | V1 | Baixa | Alta |

### 4.11. Relatórios exportáveis

| Funcionalidade | Prioridade | Complexidade | Viab. IA |
|---|---|---|---|
| Relatório PDF mensal da carteira | V1 | Média | Alta |
| Snapshot da carteira em PDF | MVP | Baixa | Alta |
| Compartilhamento por link (read-only) | V2 | Média | Alta |

---

## 5. Indicadores e Métricas — Especificação Matemática

> Cada fórmula está em forma fechada. Frequência indica a cadência de recálculo no sistema.

### 5.1. Rentabilidade

**Dividend Yield 12 meses (DY12m)**
$$DY_{12m} = \frac{\sum_{i=1}^{12} P_i}{\text{Preço atual}}$$
- $P_i$ = provento mensal do mês $i$ (anúncio).
- **Fontes:** B3 / brapi / Status Invest.
- **Frequência:** diária (preço muda).
- **Interpretação:** “quanto seu investimento renderia em proventos no último ano se você comprasse hoje”.
- **Faixas (referência):** Tijolo logístico 7–10 %, lajes corporativas 7–9 %, shoppings 6–9 %, papel high-grade 11–14 %, papel high-yield 13–18 %, FoF 8–11 %.

**DY 3 meses anualizado**
$$DY_{3m,anual} = \frac{\sum_{i=1}^{3} P_i \cdot 4}{\text{Preço atual}}$$
- **Frequência:** diária.
- **Interpretação:** projeta o ritmo recente. Útil para detectar mudança de regime.

**Yield on Cost (YoC)**
$$YoC = \frac{\sum_{i=1}^{12} P_i}{\text{Preço médio do investidor}}$$
- **Interpretação:** rendimento real da posição em si, ignorando MTM.

**Retorno total 12m**
$$R_{12m} = \frac{P_t - P_{t-12m} + \sum_{i=1}^{12} \text{Prov}_i}{P_{t-12m}}$$

### 5.2. Valuation

**P/VP**
$$P/VP = \frac{\text{Preço da cota}}{\text{Valor patrimonial por cota}}$$
- **Fontes:** informe trimestral / mensal (CVM, Funds Explorer).
- **Frequência:** mensal (atualiza quando o FII publica).
- **Interpretação:** > 1 negocia acima do patrimônio; < 1 abaixo.
- **Faixas:** depende do tipo. Papel ~1,00 ± 0,05 é típico; tijolo varia 0,80–1,10 conforme ciclo de juros.

**Cap Rate**
$$\text{CapRate} = \frac{\text{NOI anualizado}}{\text{Valor de mercado dos imóveis}}$$
- **Fonte:** relatório gerencial (extração via LLM).
- **Frequência:** trimestral.
- **Interpretação:** rentabilidade dos ativos imobiliários sem alavancagem.

**Spread sobre NTN-B**
$$\text{Spread} = DY_{12m} - YTM_{NTNB,IPCA+}$$
- **Interpretação:** prêmio sobre renda fixa real.

### 5.3. Qualidade (FIIs de Tijolo)

**Vacância física**
$$V_{fis} = \frac{\text{m}^2 \text{ vagos}}{\text{m}^2 \text{ totais (ABL)}}$$

**Vacância financeira**
$$V_{fin} = \frac{\text{Receita potencial perdida}}{\text{Receita potencial total}}$$
- **Faixas:** logística < 5 % saudável, lajes < 10 % aceitável, shoppings < 5 % saudável.

**Prazo médio dos contratos (WAULT)**
$$WAULT = \frac{\sum_i (\text{Receita}_i \cdot \text{Prazo restante}_i)}{\sum_i \text{Receita}_i}$$

**Concentração de inquilinos**
$$C_{inq} = \frac{\text{Receita do maior inquilino}}{\text{Receita total}}$$
- **Faixa:** > 25 % em único inquilino é alerta.

### 5.4. Qualidade (FIIs de Papel)

**LTV ponderado**
$$LTV_w = \frac{\sum_i (\text{Saldo CRI}_i \cdot LTV_i)}{\sum_i \text{Saldo CRI}_i}$$
- **Faixa:** < 60 % conservador; 60–75 % padrão; > 75 % alerta.

**Rating médio ponderado** (escala numérica AAA=1 ... D=21)
$$\text{Rating}_w = \frac{\sum_i (\text{PL}_i \cdot \text{RatingNum}_i)}{\sum_i PL_i}$$

**Concentração por devedor**
$$C_{dev} = \frac{\text{Maior posição em um devedor}}{PL}$$

**Indexador médio** — % do portfólio em IPCA+ vs CDI vs IGP-M.
- **Frequência:** mensal.

### 5.5. Risco e Liquidez

**Volatilidade anualizada**
$$\sigma_{anual} = \sigma_{diária} \cdot \sqrt{252}$$
- **Janela:** 252 dias úteis.

**Beta vs IFIX**
$$\beta = \frac{\text{Cov}(R_{FII}, R_{IFIX})}{\text{Var}(R_{IFIX})}$$
- **Janela:** 252 dias úteis.

**Maximum Drawdown**
$$MDD = \max_{t \in T}\left(\frac{P_t - \max_{s \leq t} P_s}{\max_{s \leq t} P_s}\right)$$

**Liquidez média 21d**
$$L = \frac{1}{21} \sum_{i=1}^{21} (\text{Volume}_i \cdot \text{Preço}_i)$$
- **Faixas:** < R$ 200 mil/dia = ilíquido; 200k–1M = baixa; > R$ 1 mi = adequada.

### 5.6. Distribuição

**Payout ratio**
$$\text{Payout} = \frac{\text{Distribuição}}{\text{Resultado contábil}}$$
- **Faixa:** 95 % é o mínimo legal. Acima de 100 % consistentemente = consumo de reservas, alerta.

**Resultado distribuído por cota / Distribuição** — proxy de sustentabilidade.

### Tabela-resumo de frequência de atualização

| Indicador | Frequência | Origem |
|---|---|---|
| Preço, volume, liquidez | Diária (EOD) | brapi / B3 |
| DY 12m, DY 3m | Diária | calculado a partir de proventos + preço |
| P/VP | Mensal | informe mensal CVM |
| Vacância, WAULT, LTV | Trimestral | relatório gerencial |
| Rating, concentração | Trimestral / quando publicar | relatório gerencial |
| Beta, volatilidade, drawdown | Diária (rolling) | calculado |
| Fato relevante | Real-time (polling) | FNET / CVM |

---

## 6. Motor de Recomendação — Coração do Produto

> **Esta é a peça de maior risco e maior valor do produto. É também onde IA generativa ajuda *gerando código*, mas onde **decisões humanas determinam tudo**: pesos, thresholds, regras, copy, guardrails.**

### 6.1. Princípio fundador

O motor produz, para cada FII em carteira, uma tupla:

$$\text{Output} = \langle \text{Sinal}, \text{Convicção}, \text{Justificativa}, \text{Indicadores}, \text{Alertas} \rangle$$

Onde:
- **Sinal** ∈ {Comprar, Aumentar, Manter, Reduzir, Vender, Evitar}
- **Convicção** ∈ {Baixa, Média, Alta}
- **Justificativa** ∈ texto de 3–6 frases em PT-BR
- **Indicadores** = subset relevante para a justificativa
- **Alertas** = lista de flags ativos

### 6.2. Algoritmo em fases

**Fase 1 — Motor de Regras Puras (MVP)**

Regras determinísticas, transparentes, testáveis. Sem LLM no caminho crítico do score.

```
Score(FII) = w_v · ScoreValuation
           + w_q · ScoreQualidade
           + w_r · ScoreRisco
           + w_l · ScoreLiquidez
           + w_h · ScoreHistorico

Onde Σ w_i = 1.
```

**Pesos por tipo de FII (definidos pelo humano, ajustáveis):**

| Tipo | $w_v$ | $w_q$ | $w_r$ | $w_l$ | $w_h$ |
|---|---|---|---|---|---|
| Tijolo (logístico, lajes, shoppings) | 0,30 | 0,35 | 0,15 | 0,10 | 0,10 |
| Papel | 0,25 | 0,40 | 0,20 | 0,10 | 0,05 |
| FoF | 0,30 | 0,25 | 0,15 | 0,15 | 0,15 |
| Híbrido / Desenvolvimento | 0,25 | 0,30 | 0,25 | 0,10 | 0,10 |

**Sub-scores (cada um 0–100):**

- **ScoreValuation:** função de P/VP normalizado pelo segmento + spread sobre NTN-B.
- **ScoreQualidade:** vacância, WAULT, concentração, LTV, rating médio (papel).
- **ScoreRisco:** volatilidade, beta, drawdown, liquidez.
- **ScoreLiquidez:** liquidez 21d em faixas (50 mil < L < 5 mi, escala log).
- **ScoreHistorico:** consistência de DY 24m (coeficiente de variação invertido).

**Mapeamento Score → Sinal (calibração inicial):**

| Score | Sinal default |
|---|---|
| 80–100 | Comprar / Aumentar |
| 65–79 | Manter (com viés positivo) |
| 50–64 | Manter |
| 35–49 | Reduzir |
| 0–34 | Vender / Evitar |

**Modificadores baseados na posição do usuário:**

- Se preço atual < preço médio em mais de 15 % e Score ≥ 65 → **Aumentar** (em vez de Comprar).
- Se Score ≥ 80 e usuário não possui → **Comprar** (sugestão de aporte).
- Se Score ≤ 35 e LTV > 80 % (papel) ou vacância > 25 % (tijolo) → **Vender** (não “Reduzir”).
- Se concentração da carteira no FII > 15 % → **Reduzir** mesmo com Score 60+ (controle de risco da carteira).

**Convicção:**

- **Alta:** indicadores convergem (4+ sub-scores na mesma direção) **e** dados estão atualizados (≤ 30 dias) **e** liquidez adequada.
- **Média:** maioria converge mas há sinais mistos.
- **Baixa:** divergência significativa entre sub-scores ou dados defasados ou liquidez baixa.

> A convicção é o que diferencia o produto. Ninguém comunica incerteza honestamente — todo mundo é “certo” no Twitter. **Esta é parte da nossa marca.**

**Fase 2 — Justificativa via LLM (MVP)**

A justificativa é gerada por LLM (Claude Haiku/Sonnet ou GPT-4o-mini), **mas não decide o sinal**. O LLM recebe:

```
Input: {
  ticker, tipo, sinal, convicção,
  score_total, sub_scores,
  indicadores principais (numéricos),
  alertas ativos,
  contexto da carteira (posição %, preço médio vs atual)
}

Saída: 3–6 frases em PT-BR, tom técnico-acessível,
sem prometer retorno, com disclaimer implícito,
citando 2–3 indicadores que mais explicam o sinal.
```

**Prompt template (versão inicial — refinar com testes):**

```
Você é um analista de FIIs comunicando uma recomendação a um investidor pessoa física brasileiro.

Dados:
- Ticker: {ticker}
- Tipo: {tipo}
- Sinal calculado: {sinal} (convicção: {conviccao})
- Score total: {score}/100
- Indicadores principais: {indicadores_json}
- Alertas: {alertas_lista}
- Posição do usuário: {percentual_carteira}% da carteira, preço médio R${pm}, atual R${pa}

Regras:
1. NUNCA prometa retorno futuro.
2. NUNCA diga "vai subir/cair".
3. Use linguagem clara, evite jargão sem explicar.
4. Cite no máximo 3 indicadores na justificativa.
5. Mencione 1 risco mesmo em sinais positivos.
6. NÃO use a palavra "garantido", "certeza", "infalível".
7. Tom: sóbrio, profissional, sem exclamações.
8. 3 a 6 frases. Não passe disso.

Devolva APENAS o texto da justificativa, sem cabeçalho.
```

**Guardrails:**
- Lista de palavras proibidas (regex pós-geração) → se aparecer, refazer com prompt reforçado ou cair em template estático.
- Validação: a justificativa **deve** mencionar pelo menos um número que está no input (regex/inclusão).
- Comprimento: 200–600 caracteres. Fora disso, refazer.
- Cache: gerar justificativa só quando sinal **muda** ou indicadores se alteram materialmente. Caso contrário, reutilizar (economiza 90 %+ de tokens).

**Fase 3 — Sofisticação (V1+)**

- **Calibração de pesos** com base em backtest (ver 6.4).
- **Score qualitativo via LLM extraindo relatório gerencial** (gestão proativa? guidance positivo? mudança de estratégia?).
- **Detecção de anomalias** (DY caiu 30 % vs média móvel — investigar se é evento pontual ou estrutural).

### 6.3. Tratamento do preço médio

Quando o usuário informa PM:
- Calcula-se **YoC** real.
- Calcula-se ganho/perda relativo ($\Delta = (P_{atual} - PM)/PM$).
- **Não influencia o sinal de qualidade do FII** (recomendação fundamental é a mesma para todos).
- **Influencia o copy da justificativa** (“apesar da queda de 12 % no preço, os fundamentos seguem saudáveis…”).
- **Influencia o sinal “Aumentar” vs “Comprar”** (já tem posição vs não tem).

> **Regra de ouro:** o passado do investidor não muda o futuro do fundo. Bom analista ignora preço médio na *avaliação*; usa preço médio só na *comunicação* e no *gerenciamento de exposição*.

### 6.4. Backtesting

**O que validamos:** se um portfólio formado pelo top X FIIs com Score ≥ 80 e rebalanceado mensalmente teria gerado retorno comparável ou superior ao IFIX em janela 5y.

**Como construir (V2):**

1. Snapshot mensal histórico de indicadores (precisamos de dados que existem retroativamente).
2. Aplicar motor de regras com pesos congelados em cada snapshot.
3. Construir portfólio simulado, rebalanceamento mensal.
4. Comparar com IFIX (retorno total, vol, drawdown, Sharpe).

**Limitações honestas:** dados históricos de relatórios gerenciais são frágeis no Brasil; vamos backtestar com indicadores que **temos** retroativamente (preço, DY, P/VP, liquidez). Backtest é honesto sobre essas limitações.

> **Decisão solo + IA:** não construir backtest completo no MVP. Apenas validações pontuais manuais (tipo: “se eu tivesse evitado MXRF11 quando vacância subiu, teria ganho?”). Backtest sistemático fica para V2 — exige infraestrutura de dados históricos que toma 4–6 semanas só pra montar.

### 6.5. Explicabilidade

Toda recomendação tem uma página “Como chegamos aqui”:
- Sub-scores numéricos com barra visual.
- Top 3 indicadores que mais empurraram.
- Top 3 fatores de risco.
- Link para metodologia (página estática).
- “O que mudou desde a última recomendação” (diff).

> Confiança vem de transparência. Caixa preta financeira é morte.

---

## 7. Fontes de Dados

### 7.1. Inventário

| Fonte | Tipo | Custo | SLA percebido | Limite | Observações |
|---|---|---|---|---|---|
| **brapi.dev** | Cotações, dividendos, info básica | Free / Pro R$ ~30/mês | Bom | Rate limit no free | Cobre FIIs. Boa para MVP. |
| **HG Brasil Finance** | Cotações | Free / Premium | Médio | Rate limit | Backup |
| **B3** | Dados oficiais (preço, volume) | Free (delay 15 min) | Alto | Acesso por arquivos | Para EOD oficial |
| **CVM (dados abertos)** | Informes mensais, formulários | Free | Alto | CSVs grandes | Fonte canônica de PL, P/VP, distribuições |
| **FNET** | Fato relevante | Free (RSS / scraping leve) | Médio | — | Crítico para alertas |
| **Status Invest / Funds Explorer / Fundamentus** | Indicadores agregados | Scraping (zona cinza) | Variável | Quebram | **Risco alto.** Evitar dependência. |
| **ComDinheiro / MaisRetorno / Trading Economics** | Dados consolidados | Pago (R$ 200–2000/mês) | Alto | Conforme plano | Considerar quando MRR justificar |
| **OpenAI / Anthropic** | LLM para extração de relatório | Per-token | Alto | API limits | Para extrair relatório gerencial |
| **Tesouro Direto** | NTN-B (referência de spread) | Free | Alto | — | Site / API pública |

### 7.2. Estratégia de cache e atualização

| Dado | Cache | Atualização |
|---|---|---|
| Preço EOD | 24h | Job às 19h dia útil |
| Dividendos | 7d | Job semanal + em FR |
| Informe mensal CVM | 30d | Job mensal (dia 20) |
| Relatório gerencial (extração) | 90d | Job mensal + on demand |
| Cotação intraday | Não cachear (ou 5 min) | Quando usuário olhar |
| Justificativa LLM | Persistente | Refazer só em mudança de sinal |

### 7.3. Plano de contingência

- Cada fonte primária tem **fallback**.
- brapi cair → HG Brasil + cache do dia anterior.
- Status Invest quebrar (e ele quebra) → não dependemos dele para dados oficiais; só para enriquecimento.
- LLM provider cair → fallback de provider (OpenAI ↔ Anthropic) + template estático de justificativa.
- CVM lenta → continuar com último valor + flag “dados defasados há X dias”.

### 7.4. Extração de relatório gerencial via LLM

**Pipeline (V1):**

1. Job mensal lista FIIs em alguma carteira ativa.
2. Para cada FII, busca o relatório gerencial mais recente (FNET / site da gestora).
3. Faz download do PDF.
4. Extrai texto via `pdf-parse` (ou OCR via Mistral OCR / Claude / GPT-4o vision se for PDF imagem).
5. Envia para LLM com prompt estruturado de extração:

```
Extraia do relatório os seguintes campos em JSON estrito:
{
  "vacancia_fisica": float | null,
  "vacancia_financeira": float | null,
  "wault_anos": float | null,
  "ltv": float | null,
  "top5_inquilinos": [{nome, percentual_receita}, ...],
  "indexador_predominante": "IPCA+" | "CDI" | "IGP-M" | "MIXED",
  "destaques_qualitativos": [string, ...],
  "alertas_qualitativos": [string, ...]
}

Se um campo não estiver no documento, retorne null.
NÃO invente valores.
NÃO infira.
```

6. Validação por schema (Zod). Se falhar, log + retry com prompt reforçado, depois fallback humano (eu reviso manualmente os top 30 FIIs por liquidez).

> **Decisão solo + IA:** extração 100 % automática para os ~80 FIIs de maior liquidez. Calda longa fica em demanda. Custo estimado: ~R$ 0,02–0,05 por extração com Claude Haiku ou GPT-4o-mini.

### 7.5. Trade-off custo vs tempo

| Cenário | Custo direto | Custo de tempo solo | Decisão |
|---|---|---|---|
| Scraping de 5 sites | R$ 0 | 8h/semana corrigindo | ❌ |
| brapi Pro | R$ 30/mês | 0 | ✅ |
| Status Invest scraping | R$ 0 | 4h/mês | ⚠️ usar só para campos não cobertos pela CVM |
| Mistral OCR / Claude vision | R$ ~0,03/página | 0 | ✅ |
| Pacote pago tipo ComDinheiro | R$ 200–500 | 0 | ⏳ adiar até MRR > R$ 5k |

**Princípio:** se custa menos que 2 horas do meu tempo por mês, contrato.

---

## 8. Arquitetura Técnica

### 8.1. Diagrama lógico

```
                   ┌──────────────────────────────────────────┐
                   │         USUÁRIO (PWA / Mobile)           │
                   └─────────────────────┬────────────────────┘
                                         │ HTTPS
                                         ▼
                   ┌──────────────────────────────────────────┐
                   │              VERCEL EDGE                 │
                   │  ┌────────────────────────────────────┐  │
                   │  │   Next.js App (App Router)         │  │
                   │  │   ─ React Server Components        │  │
                   │  │   ─ Route Handlers (REST/tRPC)     │  │
                   │  │   ─ Server Actions                 │  │
                   │  └────────────────────────────────────┘  │
                   │  ┌────────────────────────────────────┐  │
                   │  │   Vercel Cron (jobs leves)         │  │
                   │  └────────────────────────────────────┘  │
                   └─────┬───────────────┬────────────────────┘
                         │               │
            ┌────────────▼─────┐    ┌────▼──────────────┐
            │   SUPABASE       │    │   INNGEST /       │
            │   ─ Postgres     │    │   TRIGGER.DEV     │
            │   ─ Auth         │    │   (jobs longos,   │
            │   ─ Storage      │    │    fila, retry)   │
            │   ─ Realtime     │    └────┬──────────────┘
            └────────┬─────────┘         │
                     │                   │
                     ▼                   ▼
         ┌──────────────────────────────────────────────┐
         │         APIS EXTERNAS                        │
         │   brapi · CVM · FNET · Anthropic · OpenAI    │
         │   Stripe / Hotmart · Resend                  │
         └──────────────────────────────────────────────┘

         ┌──────────────────────────────────────────────┐
         │         OBSERVABILIDADE                      │
         │   Sentry · Vercel Analytics · Logflare/Axiom │
         └──────────────────────────────────────────────┘
```

### 8.2. Padrão arquitetural — defesa do monolito modular

**Decisão:** **monolito modular em Next.js (App Router) + tRPC**, deployado em Vercel.

**Por quê:**

| Aspecto | Monolito Next.js | Microsserviços |
|---|---|---|
| Latência inter-serviço | 0 (mesmo processo) | 50–200 ms |
| Deploy | 1 pipeline | N pipelines |
| Observabilidade | Tudo em 1 lugar | Distributed tracing necessário |
| Onboarding (eu mesmo, daqui a 6 meses) | Trivial | Pesadelo |
| Coordenação de versão API | Não existe (tipos compartilhados) | Tarefa ingrata |
| Custo | 1 plano Vercel | Vários servidores |
| **Aderência solo + IA** | **Altíssima** | **Anti-padrão** |

**Quando reavaliar:** quando um módulo específico tiver carga radicalmente diferente (ex.: o motor de extração de PDFs precisar de máquinas com mais memória) — aí extrai-se **um** worker para Trigger.dev/Inngest, mantendo o monolito. **Nunca** faremos microsserviços só por elegância.

### 8.3. Decomposição em módulos

```
src/
├── app/                    # Next.js App Router
│   ├── (marketing)/        # landing, pricing, blog
│   ├── (auth)/             # login, signup
│   ├── app/                # área logada
│   │   ├── carteira/
│   │   ├── fii/[ticker]/
│   │   ├── dashboard/
│   │   └── alertas/
│   ├── api/                # webhooks (Stripe, etc.)
│   └── trpc/[trpc]/route.ts
├── server/
│   ├── routers/            # tRPC routers por domínio
│   ├── services/           # lógica de negócio
│   │   ├── portfolio/
│   │   ├── recommendation/   ◄─ MOTOR
│   │   ├── data-fetcher/
│   │   ├── llm/
│   │   ├── alerts/
│   │   └── billing/
│   ├── jobs/               # handlers de jobs Inngest
│   └── db/                 # Drizzle schema, queries
├── lib/                    # utilitários puros
│   ├── indicators/         # cálculo de DY, P/VP, etc.
│   ├── dates/
│   └── formatting/
├── components/             # UI (shadcn-based)
└── types/                  # tipos compartilhados
```

> **Regra:** nada de `services/` chama `app/`. UI nunca importa de `db/`. Importações fluem de baixo (lib) para cima (app). IA respeita isso porque está documentado em `CLAUDE.md` na raiz do repo.

### 8.4. Fluxos críticos

**(a) Cadastro de carteira → cálculo de recomendação**

```
1. Usuário cola CSV (ou digita manualmente).
2. Frontend valida tickers contra catálogo local de FIIs (cache).
3. tRPC mutation cria/atualiza Portfolio + Positions.
4. Server dispara recálculo: para cada Position:
   a. Carrega FII + indicadores mais recentes do DB (cache).
   b. Se cache > TTL, refresca em background (não bloqueia UX).
   c. Calcula sub-scores → score → sinal → convicção.
   d. Verifica se justificativa LLM precisa ser regerada (mudança de sinal ou diff > 5 % nos sub-scores).
   e. Se sim: chama LLM (Anthropic Claude Haiku) com prompt template + guardrails.
   f. Persiste Recommendation versionada.
5. Frontend recebe via tRPC subscription (ou refetch) e renderiza dashboard.
```

**Latência alvo:** primeira render do dashboard < 1,5 s; recomendações completas < 4 s para carteira de 20 FIIs.

**(b) Job diário de atualização (D+1)**

```
Diariamente às 19h00 BRT (após fechamento B3):
1. Vercel Cron dispara handler `daily-update`.
2. Handler enfileira em Inngest: `update-quotes`, `check-fato-relevante`.
3. update-quotes: busca preços EOD do dia (brapi), atualiza tabela Quote.
4. check-fato-relevante: lê RSS do FNET, identifica novos FRs, salva.
5. Para cada portfólio com posição em FII afetado:
   a. Recalcula score (regras puras, rápido).
   b. Compara com sinal anterior persistido.
   c. Se mudança: regera justificativa (LLM), enfileira alerta.
6. Job de alertas envia e-mails (Resend) e push (Web Push API).
```

**(c) Detecção de fato relevante → alerta**

```
A cada 15 minutos em horário comercial:
1. Job `poll-fnet` (Inngest) busca novos FRs publicados.
2. Para cada FR novo:
   a. Persiste FatoRelevante.
   b. Identifica FIIs afetados (ticker).
   c. Sumariza via LLM (1–2 frases): "Gestor anuncia X". Cache.
   d. Se LLM detecta categoria crítica (mudança de gestão, default de devedor, distribuição reduzida) → trigger imediato de recálculo + alerta.
   e. Caso contrário, entra na fila de "novidades" para o próximo digest.
3. Notifica usuários afetados (push + e-mail).
```

**(d) Recálculo de score (manual ou automático)**

```
Triggers:
- Cron diário (todos os FIIs com posição ativa).
- Mudança em qualquer indicador material (preço > 3 % move, novo informe CVM, novo FR).
- Usuário clica "atualizar" (rate limit 1x/min).

Pipeline:
1. Buscar últimos indicadores (DB).
2. Aplicar pesos por tipo.
3. Calcular sub-scores.
4. Aplicar modificadores (PM, concentração).
5. Mapear para sinal + convicção.
6. Se sinal mudou → gerar justificativa nova.
7. Persistir Recommendation com versão = anterior + 1.
8. Disparar evento (alerta) se mudança material.
```

### 8.5. Estratégia de jobs

| Tipo | Ferramenta | Justificativa |
|---|---|---|
| Cron leve (< 10 s, < 5 min) | Vercel Cron | Já incluso no Vercel, zero infra |
| Job longo (> 10 s, fila, retry) | **Inngest** ou Trigger.dev | Gerenciados, type-safe TS, IA conhece bem |
| Webhook → ação | Route Handler + Inngest event | |
| Job paralelo grande (50+ FIIs) | Inngest fan-out | |

> **Decisão:** **Inngest no MVP**. Grátis até volume razoável. Type-safe. Excelente DX. Fan-out trivial. Trigger.dev é alternativa equivalente — escolher um e ficar.

---

## 9. Stack Tecnológico Recomendado

### 9.1. Linguagem única: **TypeScript em tudo**

**Justificativa solo + IA:**
- Um único contexto mental. IA mantém um único contexto também.
- Tipos compartilhados entre front e back via tRPC = elimina classe inteira de bugs.
- Ecossistema gigantesco. IA tem dados de treino abundantes.
- Substitui Python para a maioria de scripts auxiliares.
- **Exceção justificada:** se algum cálculo pesado de séries temporais demandar (não é o caso aqui), considera-se Python isolado em script.

### 9.2. Frontend (web): **Next.js 15 (App Router)**

| Critério | Avaliação |
|---|---|
| Domínio da IA | **Altíssimo** (Cursor, Claude Code, Copilot dominam) |
| Maturidade | Alta |
| Comunidade | Enorme |
| Documentação | Excelente |
| Deploy | Trivial (Vercel) |
| Renderização híbrida | Sim (SSR/SSG/RSC/ISR) |

**Alternativas consideradas:**
- **Remix:** ótimo, mas menos exemplos para IA do que Next.
- **SvelteKit:** mais enxuto, mas IA tem 1/5 do treino.
- **Nuxt/Vue:** descartado por mesma razão.

### 9.3. Mobile: **PWA primeiro, React Native (Expo) na V2**

**Justificativa:**
- PWA com Next.js cobre 90 % das necessidades de mobile (instalável, push notifications via Web Push).
- Manter um app nativo dobra a superfície de manutenção. Solo + IA não dá.
- React Native via **Expo** é a única opção viável para nativo solo, e mesmo assim só na V2 quando MRR justificar.
- Swift/Kotlin nativo: **descartado**. Complexidade incompatível.

### 9.4. Backend: **Next.js API Routes + tRPC + Server Actions**

**Justificativa:**
- Zero context switch (mesmo repo, mesmos tipos).
- tRPC dá type-safety end-to-end sem precisar de OpenAPI/codegen.
- Server Actions cobrem mutations triviais de UI.
- IA gera tRPC routers com altíssima precisão.

**Alternativas consideradas:**
- **NestJS:** muito enterprise, boilerplate alto. Solo não precisa.
- **Hono:** delicioso mas pequeno; perderíamos integração nativa com Next.
- **Express:** boring no sentido bom, mas falta type-safety nativa.
- **Backend separado em outra linguagem:** veto explícito.

### 9.5. Banco de dados: **Postgres gerenciado — Supabase**

**Por que Supabase (vs Neon, Railway, RDS):**

| Aspecto | Supabase | Neon | Railway |
|---|---|---|---|
| Postgres gerenciado | ✅ | ✅ | ✅ |
| Auth incluído | ✅ | ❌ | ❌ |
| Storage de arquivos | ✅ | ❌ | ❌ |
| Realtime | ✅ | ❌ | ❌ |
| Edge functions | ✅ | ❌ | ❌ |
| Free tier viável | ✅ | ✅ | ⚠️ |
| Curva de aprendizado | Suave | Suave | Suave |
| **IA conhece** | **Muito bem** | Bem | Bem |

**Decisão:** **Supabase** pelo combo Postgres + Auth + Storage + Realtime num só lugar. Reduz vendor sprawl (menos contas, menos faturas, menos surface area).

### 9.6. ORM: **Drizzle**

**Drizzle vs Prisma:**

| Critério | Drizzle | Prisma |
|---|---|---|
| Performance | Melhor | Boa |
| SQL transparente | ✅ | ⚠️ (Prisma esconde) |
| Schema em TS | ✅ | DSL próprio |
| Edge runtime | ✅ | Recente |
| Build size | Pequeno | Maior |
| **IA conhece** | **Médio-alto** | **Altíssimo** |
| Docs | Boas | Excelentes |

**Decisão:** Drizzle para projetos novos pela performance e por trabalhar nativo no edge. Prisma seria escolha igualmente defensável e talvez mais segura para IA gerar — vai do gosto. **Recomendação principal: Drizzle.** Backup: Prisma.

### 9.7. Autenticação: **Supabase Auth**

- Já incluso no Supabase.
- Suporta e-mail/senha, magic link, OAuth (Google, Apple).
- LGPD-compliant.
- **Nunca** codar auth do zero. Delegar é não-negociável.

**Alternativa:** Clerk (UX excelente, mais caro). Auth.js (mais flexível mas você cuida da sessão).

### 9.8. Pagamentos: **Stripe + alternativa BR**

**Para mercado brasileiro:**
- **Stripe:** suporta cartão BR, mas não tem PIX boleto fácil. Bom para internacional eventual.
- **Hotmart / Kiwify / Braip:** cobrem PIX/boleto/cartão BR, mas cobram mais (até 12 % por transação). Têm “produtor digital” enraizado, com afiliados, que pode ser vetor de aquisição.
- **Pagar.me / Mercado Pago:** PIX/boleto, fee menor, mas integração mais densa.
- **Lemon Squeezy:** Merchant of Record, ótimo para SaaS internacional, mas BR é fraco.

**Recomendação:**
- **MVP:** Hotmart ou Kiwify (lança rápido, suporta PIX, tem checkout pronto, integra via webhook).
- **V1:** migrar para Stripe + Pagar.me se escalar (fee menor a longo prazo).
- **Carlos**, dado seu canal de YouTube de finanças: Hotmart/Kiwify potencialmente abre porta para programa de afiliados — vale considerar isso na decisão.

### 9.9. E-mails transacionais: **Resend**

- DX excelente em TS.
- Templates em React (`react-email`).
- IA gera templates muito bem.
- Free tier 3000 e-mails/mês.
- Alternativas: Postmark, SendGrid (mais antigos; Resend é o moderno).

### 9.10. Hospedagem: **Vercel**

| Critério | Vercel | Railway | Fly.io |
|---|---|---|---|
| Otimizado pra Next.js | ✅✅✅ | ✅ | ✅ |
| Edge global | ✅ | ⚠️ | ✅ |
| Preview deploys por PR | ✅ | ⚠️ | ⚠️ |
| Cron incluso | ✅ | ⚠️ | ⚠️ |
| Pricing previsível | Médio (pode escalar) | Bom | Bom |
| **IA conhece** | **Altíssimo** | Alto | Médio |

**Decisão:** Vercel. Caveat: monitorar custo de bandwidth e function invocations conforme cresce. Plano Pro a US$ 20/mês cobre confortavelmente até várias dezenas de milhares de usuários ativos no nosso perfil de uso.

### 9.11. Filas e jobs: **Inngest** (ou Trigger.dev)

**Por quê:**
- Type-safe nativo (TypeScript).
- Step functions com retry, delay, fan-out.
- Free tier generoso.
- Substitui pilha Redis + BullMQ + worker (que solo dev não tem cabeça pra manter).
- **IA conhece bem** (boa documentação).

**Anti-padrão evitado:** subir Redis no Railway, BullMQ, worker process próprio. Solo + isso = horas perdidas em produção.

### 9.12. Observabilidade: **Sentry + Vercel Analytics + Axiom (logs)**

| Camada | Ferramenta | Justificativa |
|---|---|---|
| Erros | Sentry | Padrão de mercado, IA gera config |
| Performance frontend | Vercel Analytics | Já incluso |
| Logs estruturados | Axiom (free tier) ou Logflare | Pesquisa em logs grandes |
| Uptime | UptimeRobot ou Better Stack (free) | Ping simples |

**Anti-padrão evitado:** ELK stack, Grafana self-hosted, Prometheus. Tudo isso é fantástico — e tudo isso mata projeto solo.

### 9.13. IaC: **NÃO** no início

- **MVP e V1:** configuração via dashboard. Documentar em `INFRA.md` quais serviços, quais variáveis, quais cron schedules existem.
- **V2 ou se time crescer:** considerar Terraform Cloud para Vercel/Supabase. Não antes.

### 9.14. LLM provider: **Anthropic Claude (primário) + OpenAI (fallback)**

**Por quê Anthropic primário:**
- Claude é particularmente forte em justificativas em PT-BR e em seguir guardrails.
- API simples.
- **Custo controlado:** Haiku (≈US$ 0,80/Mtok input, US$ 4/Mtok output) cobre 95 % das justificativas; Sonnet só para extrações de relatório complexas.

**Estratégia de custo:**
- **Cache agressivo:** justificativa só regera quando sinal muda. Estimativa: < 0,1 chamada por usuário ativo por dia.
- **Prompt curto:** input em formato denso (JSON, não prosa).
- **Modelo certo pro trabalho:** Haiku para justificativas, Sonnet para extração de relatório, Opus só em pesquisa pontual (não em produção crítica).
- **Fallback automático:** se Anthropic 5xx por 30 s, troca para OpenAI (gpt-4o-mini ou o equivalente vigente) sem mudar prompt (com pequeno adapter).
- **Batching** para extrações em massa (Anthropic Message Batches API tem 50 % de desconto).
- **Limite duro por usuário/mês:** mesmo no plano premium, cap de N gerações para evitar abuso/runaway.

### 9.15. Tabela-resumo da stack

| Camada | Recomendação | Domínio IA |
|---|---|---|
| Linguagem | TypeScript | Alto |
| Framework full-stack | Next.js 15 (App Router) | Alto |
| RPC tipado | tRPC | Alto |
| ORM | Drizzle (alt: Prisma) | Médio-alto |
| Banco | Supabase Postgres | Alto |
| Auth | Supabase Auth | Alto |
| UI | Tailwind + shadcn/ui | Alto |
| Charts | Recharts | Alto |
| Validação | Zod | Alto |
| Forms | react-hook-form + Zod | Alto |
| Mobile | PWA → Expo (V2) | Alto / Médio |
| Pagamentos | Hotmart/Kiwify (BR) → Stripe | Médio |
| E-mail | Resend | Alto |
| Hosting | Vercel | Alto |
| Jobs/Filas | Inngest | Médio-alto |
| Observabilidade | Sentry + Axiom | Alto |
| LLM | Anthropic + OpenAI fallback | Alto |
| Testes | Vitest + Playwright | Alto |
| Monorepo | pnpm workspaces (mesmo se for um só pacote) | Alto |

### 9.16. Tecnologias descartadas (e por quê)

| Descartado | Motivo |
|---|---|
| Kubernetes | Complexidade incompatível com solo |
| Microsserviços | Overhead operacional inviável |
| MongoDB | Postgres é melhor para dados relacionais (carteira é relacional) |
| GraphQL (Apollo) | tRPC dá benefícios similares com 10 % do overhead |
| Redux / MobX | Server Components + React Query/SWR resolvem |
| Webpack manual | Next.js abstrai |
| Custom CI/CD | Vercel CI/CD é suficiente |
| Self-hosted DB | Sem motivo para sofrer |
| Python para backend | Quebra type-safety end-to-end |
| Redis self-hosted | Inngest cobre fila gerenciada |
| Frontend separado (SPA) | Next.js full-stack mata isso |

---

## 10. Modelo de Dados

### 10.1. Entidades

```ts
// User (delegado ao Supabase Auth, mas perfil estendido)
profiles {
  id: uuid (FK auth.users)
  email: string
  display_name: string | null
  plan: 'free' | 'pro' | 'premium'
  stripe_customer_id: string | null
  hotmart_subscriber_id: string | null
  created_at: timestamp
  updated_at: timestamp
}

portfolios {
  id: uuid
  user_id: uuid (FK profiles.id)
  name: string  -- "Principal", "Renda", etc.
  is_default: boolean
  created_at: timestamp
  updated_at: timestamp
  deleted_at: timestamp | null  -- soft delete
}

positions {
  id: uuid
  portfolio_id: uuid (FK portfolios.id)
  ticker: string  -- ex: "MXRF11"
  quantity: numeric(18,6)
  avg_price: numeric(18,4) | null
  notes: text | null
  created_at: timestamp
  updated_at: timestamp
}

fiis {  -- catálogo mestre
  ticker: string (PK)  -- ex: "MXRF11"
  cnpj: string
  name: string
  type: 'tijolo' | 'papel' | 'fof' | 'hibrido' | 'desenvolvimento' | 'outros'
  segment: string  -- "logística", "lajes corporativas", "shoppings", "high-grade", etc.
  manager: string
  inception_date: date
  is_active: boolean
  metadata: jsonb  -- campos extras
  updated_at: timestamp
}

quotes {  -- séries temporais
  ticker: string (FK fiis.ticker)
  date: date
  close: numeric(18,4)
  volume: numeric(18,2)
  source: string
  PK (ticker, date)
}

dividends {
  id: uuid
  ticker: string (FK fiis.ticker)
  ex_date: date
  payment_date: date
  amount: numeric(18,6)  -- por cota
  type: 'rendimento' | 'amortizacao'
}

fii_indicators {  -- snapshot mensal/trimestral
  id: uuid
  ticker: string (FK fiis.ticker)
  reference_date: date
  pvp: numeric | null
  vacancia_fisica: numeric | null
  vacancia_financeira: numeric | null
  wault_anos: numeric | null
  ltv: numeric | null
  payout: numeric | null
  num_cotistas: int | null
  pl: numeric | null
  raw_data: jsonb  -- payload bruto da extração
  source: string
  created_at: timestamp
}

recommendations {
  id: uuid
  portfolio_id: uuid (FK)
  ticker: string (FK fiis.ticker)
  signal: 'buy' | 'add' | 'hold' | 'reduce' | 'sell' | 'avoid'
  conviction: 'low' | 'medium' | 'high'
  score: int  -- 0..100
  sub_scores: jsonb  -- {valuation: 70, qualidade: 65, ...}
  justification: text  -- gerado por LLM
  justification_model: string  -- ex: "claude-haiku-3.5"
  alerts: jsonb  -- [{type, severity, message}]
  context_snapshot: jsonb  -- preço, indicadores no momento
  version: int
  created_at: timestamp
  superseded_at: timestamp | null
}

alerts {
  id: uuid
  user_id: uuid
  portfolio_id: uuid | null
  ticker: string | null
  type: 'signal_change' | 'price_drop' | 'dy_drop' | 'fato_relevante' | 'data_stale'
  severity: 'info' | 'warning' | 'critical'
  payload: jsonb
  read_at: timestamp | null
  created_at: timestamp
}

fato_relevante {
  id: uuid
  ticker: string (FK fiis.ticker)
  published_at: timestamp
  title: string
  url: string
  raw_text: text | null
  llm_summary: text | null
  category: string | null  -- "distribuicao", "aquisicao", "default", "gestao", etc.
  created_at: timestamp
}

recommendation_methodology_versions {
  id: uuid
  version: int
  weights: jsonb  -- pesos por tipo
  thresholds: jsonb
  notes: text
  effective_from: timestamp
}

llm_invocations {  -- audit trail
  id: uuid
  user_id: uuid | null
  recommendation_id: uuid | null
  provider: string
  model: string
  input_tokens: int
  output_tokens: int
  cost_estimate_usd: numeric
  prompt_version: string
  status: 'success' | 'fallback' | 'error'
  created_at: timestamp
}
```

### 10.2. Diretrizes

- **Soft delete** em `portfolios` e `positions` (`deleted_at`). Hard delete via job mensal só em registros muito antigos.
- **Recomendações são versionadas** (immutable history). Para “a recomendação atual”, query `WHERE superseded_at IS NULL`. Auditável e didático para usuário (“mudei de Manter para Reduzir em 15/03 porque…”).
- **`raw_data` jsonb** em `fii_indicators` para guardar tudo que veio da fonte; campos top-level são cache do que mais se usa.
- **Migrations** versionadas em `db/migrations/`, executadas via Drizzle Kit. Toda PR que mexe em schema entra com migration.
- **Sem premature partitioning.** Postgres aguenta dezenas de milhões de linhas tranquilamente. Quando `quotes` passar de 50M, considera-se partition by year.
- **Índices essenciais:**
  - `quotes (ticker, date DESC)`
  - `recommendations (portfolio_id, ticker, superseded_at)`
  - `alerts (user_id, read_at, created_at DESC)`
  - `fii_indicators (ticker, reference_date DESC)`

---

## 11. UX/UI e Design

### 11.1. Princípios

1. **Decisão em segundos.** O dashboard tem que responder “o que faço hoje?” em uma rolada de tela.
2. **Mobile-first.** O usuário olha no celular, no metrô, no intervalo. Desktop é bônus.
3. **Convicção visível.** Convicção (alta/média/baixa) tem peso visual. Recomendação alta convicção em verde forte; baixa em verde acinzentado.
4. **Honestidade radical.** “Dados desatualizados há 3 dias” aparece. Não escondemos limitação.
5. **Progressive disclosure.** Tela inicial: resumo. Toque: detalhe. Toque novamente: metodologia. Nada empurrado goela abaixo.
6. **Sem dark patterns.** Cancelamento de assinatura tem 2 cliques. Sempre.

### 11.2. Sistema de design: **shadcn/ui + Tailwind**

**Por quê:**
- Não é biblioteca instalada — é código copiado. Você é dono.
- Acessibilidade nativa (Radix UI por baixo).
- IA gera componentes com altíssima precisão.
- Tema customizável via CSS variables.
- Comunidade gigantesca.

**Alternativas consideradas:**
- **Mantine:** ótimo, mais opinativo. Boa segunda escolha.
- **Chakra:** maduro mas perdeu momentum.
- **Material UI:** pesado, “cheira Google” — ruim para marca financeira sóbria.
- **Design system custom:** ❌ no MVP. ❌ no V1. Talvez V3.

### 11.3. Wireframes textuais

**Onboarding (5 passos)**

```
[Passo 1] Boas-vindas
  "Seu analista de FIIs. Cole sua carteira, receba o que fazer."
  CTA: Começar (sem cadastro inicial — friction reduzida)

[Passo 2] Sua carteira
  "Como prefere informar?"
  Opções: [Colar texto] [CSV da corretora] [Digitar fundo a fundo]
  Exemplo de cada uma.

[Passo 3] Validação
  Lista de FIIs detectados. Editar quantidades / preço médio.
  Validação inline (ticker existe? quantidade > 0?).

[Passo 4] Análise rodando
  "Estamos analisando seus 12 FIIs..."
  Skeleton loader, ~3-5 segundos.

[Passo 5] Resultado
  Dashboard "o que fazer hoje". Top 3 ações.
  CTA: Criar conta para salvar e receber alertas
  (cadastro postergado para reduzir friction inicial)
```

**Dashboard "O que fazer hoje"**

```
┌─────────────────────────────────────────────┐
│ Olá, Rafael — 15 de março                   │
│                                             │
│ Sua carteira: R$ 187.420 | DY 12m: 9,8%     │
│ Score de saúde: 72/100  ●●●○○                │
│                                             │
├─ AÇÕES PRIORITÁRIAS ──────────────────────  │
│                                             │
│  ⬆ AUMENTAR  HGLG11    Convicção: ALTA      │
│    "Score 84. Vacância em 2,1%, P/VP em     │
│     0,94, abaixo da média do segmento..."   │
│    [Ver análise completa →]                 │
│                                             │
│  ⬇ REDUZIR   MXRF11    Convicção: MÉDIA     │
│    "Concentração em high-yield aumentou..." │
│    [Ver análise completa →]                 │
│                                             │
│  ⚠ ATENÇÃO   XPLG11   Fato relevante novo  │
│    [Ler resumo →]                           │
│                                             │
├─ DEMAIS POSIÇÕES ───────────────────────── │
│   12 fundos • 9 manter • 3 outros           │
│   [Ver todas →]                             │
└─────────────────────────────────────────────┘
```

**Detalhe do FII**

```
┌─────────────────────────────────────────────┐
│ ← Voltar       HGLG11 — CSHG Logística      │
│                                             │
│ Sinal: ⬆ AUMENTAR    Convicção: ●●● ALTA    │
│                                             │
│ Justificativa                               │
│ ┌───────────────────────────────────────┐  │
│ │ O fundo apresenta vacância em 2,1%,    │  │
│ │ abaixo da mediana de 4,5% para        │  │
│ │ logística. P/VP de 0,94 indica         │  │
│ │ desconto vs valor patrimonial...       │  │
│ │ [...]                                  │  │
│ └───────────────────────────────────────┘  │
│                                             │
│ Score: 84/100                               │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░                       │
│                                             │
│ Decomposição:                               │
│ Valuation     ▓▓▓▓▓▓▓▓░░ 82                 │
│ Qualidade     ▓▓▓▓▓▓▓▓▓░ 88                 │
│ Risco         ▓▓▓▓▓▓▓░░░ 75                 │
│ Liquidez      ▓▓▓▓▓▓▓▓▓▓ 95                 │
│                                             │
│ Indicadores principais                      │
│ DY 12m: 8,9%       P/VP: 0,94               │
│ Vacância: 2,1%     WAULT: 5,8 anos          │
│ [Ver todos os 18 indicadores →]             │
│                                             │
│ Sua posição                                 │
│ 120 cotas · PM R$ 142,30 · YoC 9,2%         │
│ Hoje: R$ 152,10 (+6,9%)                     │
│                                             │
│ [Como chegamos a essa recomendação →]      │
│ [Histórico de recomendações →]              │
└─────────────────────────────────────────────┘
```

**Análise consolidada da carteira**

```
┌─────────────────────────────────────────────┐
│ Diagnóstico (em LN, gerado por LLM)         │
│ "Sua carteira tem viés ao high-yield em     │
│  papel (45%) com WAULT médio curto..."      │
│                                             │
│ Composição                                  │
│ Tipo:    ▓▓▓▓ Tijolo 35%                    │
│          ▓▓▓▓▓▓ Papel 50%                   │
│          ▓ FoF 15%                           │
│                                             │
│ Por segmento (top 5)                        │
│ High-yield papel  ▓▓▓▓▓▓▓ 32%               │
│ Logística         ▓▓▓▓▓ 18%                 │
│ ...                                         │
│                                             │
│ Concentração                                │
│ Maior posição: 18% (alerta > 15%)          │
│ Top 3 posições: 41%                         │
│ HHI segmento: 0,21                          │
│                                             │
│ Sobreposição                                │
│ HGFF11 detém posições que você já tem em    │
│ HGLG11 e KNRI11 (overlap ~22%)              │
│                                             │
│ Sugestões direcionais                       │
│ • Reduzir exposição a high-yield papel     │
│ • Considerar adicionar lajes corporativas   │
│ • Atenção: 3 FIIs com score < 50            │
└─────────────────────────────────────────────┘
```

**Configurações (mínimas)**

```
- Conta: nome, e-mail, plano
- Notificações: e-mail, push, frequência
- Carteira: padrão, exportar, deletar
- Sobre: metodologia, T&C, disclaimers, suporte
- Faturamento: assinatura, histórico, cancelar
```

### 11.4. Comunicação visual de incerteza

| Convicção | Cor | Bullets |
|---|---|---|
| Alta | Verde forte (positivo) / Vermelho forte (negativo) | ●●● |
| Média | Verde médio / Amarelo / Laranja | ●●○ |
| Baixa | Cinza-azulado | ●○○ |

Texto sempre explicita: “Convicção alta: 4 dos 5 sub-scores convergem.”

### 11.5. Considerações para baixa literacia financeira

- Tooltips em **todo** termo técnico, sempre.
- Modo “explicar como se eu tivesse 12 anos” em cada justificativa (toggle).
- Glossário linkado inline.
- Nenhuma sigla introduzida sem definição na primeira ocorrência por sessão.
- Evitar percentuais em isolado: sempre comparar com mediana ou faixa do segmento.

---

## 12. Segurança Técnica

### 12.1. Camadas

| Risco | Mitigação |
|---|---|
| **TLS** | HTTPS por padrão na Vercel. HSTS via header. |
| **Auth** | Supabase Auth (delegado), MFA opcional, sessões via cookie httpOnly secure |
| **Senhas** | Não armazenamos (Supabase Auth cuida) |
| **OAuth** | Google / Apple (reduz superfície de senhas próprias) |
| **Authorization (RLS)** | Row Level Security no Postgres garantido por Supabase. Toda tabela com `user_id` tem policy. |
| **Criptografia em repouso** | Supabase usa storage criptografado por padrão |
| **Segredos** | Variáveis de ambiente (Vercel + Supabase). Zero segredo em repo. `.env.example` versionado, `.env.local` no `.gitignore`. |
| **Rate limiting** | Middleware Next.js + Upstash Ratelimit. 60 req/min para usuários autenticados, 20/min para públicos. |
| **CSRF** | Server Actions e tRPC com origin check |
| **XSS** | React auto-escape; nunca `dangerouslySetInnerHTML` em conteúdo de usuário |
| **SQL injection** | Drizzle parametriza tudo |
| **OWASP A1–A10** | Coberto por defaults: auth, validation (Zod), config, etc. |
| **Backups** | Supabase faz daily backups (Pro plan). Configurar retenção 7+ dias. |
| **PII / LGPD** | Mínimo de dados coletados. Consentimento explícito no signup. Direito a exportar/deletar via endpoint. Página de privacidade revisada por advogado quando MRR > X. |
| **Logs** | Não logar valores monetários sensíveis em texto plano. Não logar payloads de pagamento. |
| **Dependências** | `pnpm audit` no CI. Renovate ou Dependabot configurado. |
| **Webhooks (Stripe/Hotmart)** | Validação de assinatura HMAC obrigatória. |

### 12.2. Compliance regulatório (CVM)

**Atenção:** O sistema NÃO emite recomendação personalizada no sentido da Resolução CVM 20 (analista de valores mobiliários). Para se manter dentro da raia:

- Linguagem em **todas** as páginas: “análise informativa baseada em metodologia algorítmica e dados públicos. Não constitui recomendação personalizada de investimento.”
- Disclaimer em rodapé de toda página de recomendação.
- T&C com cláusula expressa.
- Se em algum momento contratarmos analista CVM e quisermos virar “recomendação”, viramos a chave consciente.
- **Não publicar “carteira modelo recomendada”** — isso pisa na linha.
- Não usar termos como “garantia”, “alta probabilidade de retorno”, “dica certa”.

> **Conversa com advogado especializado em mercado de capitais é obrigatória antes do lançamento.** Não é negociável. Mais barato ouvir “não pode” cedo do que receber notificação CVM depois.

---

## 13. Monetização

### 13.1. Modelos avaliados

| Modelo | Prós | Contras | Adequação solo |
|---|---|---|---|
| Freemium SaaS | Recorrência, escala, sem suporte intensivo | Leva tempo pra escalar | ⭐⭐⭐⭐⭐ |
| Vitalício (one-shot R$ 297) | Caixa rápido | Sem recorrência, churn invisível | ⭐⭐⭐ |
| White-label para corretoras | Ticket alto | Ciclo de venda B2B exige time | ⭐⭐ |
| Parceria com corretora (rev share) | Aquisição grátis | Dependência | ⭐⭐⭐ |
| Conteúdo + afiliado de corretora | Você já faz isso (canal) | Alinhamento perigoso | ⭐⭐⭐⭐ (sinergia com canal) |
| Curso + ferramenta combo | Aproveita audiência | Esforço de produzir curso | ⭐⭐⭐⭐ |

### 13.2. Recomendação principal: Freemium SaaS com tiers

| Tier | Preço/mês | Limites |
|---|---|---|
| **Free** | R$ 0 | 1 carteira, até 5 FIIs, recomendação sem justificativa LLM (só template), sem alertas |
| **Pro** | R$ 24,90 | 3 carteiras, FIIs ilimitados, justificativa LLM completa, alertas por e-mail |
| **Premium** | R$ 49,90 | Pro + relatórios PDF mensais, comparadores avançados, alertas push em real-time, prioridade no suporte |

**Recomendação secundária:** **plano anual com desconto** (Pro R$ 199, Premium R$ 399 — equivalente a 2 meses grátis). Reduz churn.

**Cap por usuário Premium:** ~50 FIIs ativos para evitar abuso de API LLM. Acima disso, plano “Family” futuro.

### 13.3. Estratégias específicas para Carlos (criador de conteúdo)

> Dado o perfil do founder, há sinergias específicas que valem ser exploradas:

- **Lançamento exclusivo para audiência do canal** com early-bird (50 % off no primeiro ano).
- **Programa de afiliados** integrado (comissão recorrente de 30 % por X meses).
- **Cupons em vídeos** de YouTube com tracking via UTM.
- **Conteúdo educacional gratuito que vira funil** (vídeo “como avaliar um FII” → CTA para o app).
- **Parcerias com outros criadores** (rev share).

### 13.4. Princípios de monetização solo

- **Self-service total.** Cancela com 2 cliques. Suporte por e-mail/Discord, não chat ao vivo.
- **Atendimento manual = veneno.** Toda dúvida vira FAQ na hora.
- **Cobrar cedo, mas com plano free real.** Free tem que dar valor genuíno (1 carteira de 5 FIIs analisada bem) — caso contrário, vira “demo” e pessoas saem.
- **Trial vs Free:** ambos. Free permanente para 1 carteira pequena; trial de 14 dias do Pro para qualquer um que quiser provar.

---

## 14. Roadmap e Faseamento

### 14.1. MVP — 8 a 12 semanas (solo + IA)

**Objetivo:** lançar no ar uma versão capaz de demonstrar valor único: cole carteira → receba recomendações com justificativa.

**Semanas 1–2: Fundação**
- Setup repo, Vercel, Supabase, schema inicial.
- Auth com Supabase.
- Landing page estática.
- Catálogo de FIIs populado (top 100 por liquidez).

**Semanas 3–4: Cadastro de carteira**
- CRUD de carteira/posições.
- Importação CSV.
- Validação de tickers.
- Cálculo de indicadores básicos (DY, P/VP, liquidez) com brapi.

**Semanas 5–7: Motor de recomendação Fase 1**
- Sub-scores numéricos.
- Regras de mapeamento score → sinal.
- Convicção.
- Persistência versionada.
- Templates de justificativa estática para validar fluxo.

**Semanas 7–8: Justificativa LLM**
- Integração Anthropic.
- Prompt engineering inicial + guardrails.
- Cache de justificativas.

**Semanas 9–10: Dashboard + UI**
- Tela “o que fazer hoje”.
- Detalhe do FII.
- Onboarding fluido.

**Semanas 11–12: Polimento + cobrança**
- Integração Hotmart/Kiwify.
- Tier free / pro.
- T&C, disclaimers, política de privacidade.
- Soft launch para 20–50 usuários do canal.

**KPIs MVP:**
- 100 usuários cadastrados.
- 30 % de ativação (concluem cadastro de carteira).
- 5–10 % de conversão para Pro nos primeiros 30 dias.
- NPS inicial ≥ 40.

### 14.2. V1 — 3 a 6 meses pós-MVP

**Objetivos:** consolidar valor recorrente, reduzir churn, expandir motor.

- Análise consolidada da carteira (diagnóstico LLM).
- Alertas por e-mail (mudança de sinal, queda de preço, FR).
- Extração de relatórios gerenciais via LLM (top 50 FIIs).
- Comparadores básicos (FII vs pares, vs IFIX).
- Histórico de recomendações.
- Múltiplas carteiras.
- Plano Premium ativo.

**KPIs V1:**
- 500 usuários ativos mensais.
- 8–12 % conversão para pago.
- Churn mensal < 8 %.
- MRR R$ 5–10k.

### 14.3. V2 — 6 a 12 meses pós-V1

- Backtesting visual da metodologia.
- IA conversacional sobre a carteira (chat “me explica essa recomendação”).
- App mobile (Expo) — push real, melhor UX em mobile.
- Programa de afiliados.
- Relatórios mensais automáticos por e-mail.
- API pública para usuários Premium.
- Comparador “vs Suno carteira modelo” (controverso, mas marketing).

**KPIs V2:**
- 3000 usuários ativos.
- MRR R$ 30–60k.
- Churn < 6 %.

### 14.4. Riscos de prazo (honestidade brutal)

- Solo + IA acelera 2–3x, **não** 10x. Quem promete 10x vende curso.
- Bug em produto financeiro derruba 1 dia inteiro.
- Conteúdo regulatório/jurídico pode atrasar 2 semanas.
- Mercado pode esfriar (período eleitoral, taxa Selic alta) reduzindo apetite por SaaS de FIIs.

**Multiplicador de prazo realista:** o que parece 8 semanas vira 12. O que parece 12 vira 16. Planeje colchão.

---

## 15. Riscos e Mitigações

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| 1 | **Bus factor 1** — founder doente, machucado, sem fôlego | Média | Crítico | Documentação obsessiva (`README`, `CLAUDE.md`, `INFRA.md`). Repo num GitHub privado com herdeiro. Disable de cobrança automatizada com pause de 90 dias se falhar deploy de saúde. Considerar pessoa de confiança com acesso de emergência (cônjuge, parceiro). |
| 2 | **Burnout do solo founder** | Alta | Crítico | Cadência sustentável de 4–6h/dia. Domingo off. Sprint de duas semanas com retrospectiva consigo mesmo. Não enxergar o produto como única fonte de identidade. Exercício e sono como infra crítica. |
| 3 | **Recomendação errada destrói confiança** | Média | Crítico | Disclaimers claros, convicção honesta, backtesting (V2), revisão humana semanal de amostras. Política pública: “erramos, aqui está o aprendizado”. Nunca prometer retorno. |
| 4 | **Qualidade de dados / scraping quebra** | Alta | Alto | Múltiplas fontes com fallback. Monitoring automatizado de “staleness”. Telegram bot que avisa o founder. Comprar fonte paga quando MRR cobrir. Página de status pública. |
| 5 | **Custo de LLM cresce desproporcional** | Média | Médio | Cache agressivo. Modelo certo pro trabalho (Haiku default). Cap por usuário/mês. Alertas de custo no dashboard Anthropic. Batch API quando aplicável. |
| 6 | **Concorrente grande copia a UVP** | Média | Alto | Velocidade de iteração (vantagem solo: zero comitê). Marca pessoal forte (canal de YouTube). Comunidade. Foco no nicho “investidor pessoa física brasileiro” onde gigantes não calçam o sapato. |
| 7 | **Mudança de pricing de SaaS dependente (Vercel, Supabase, OpenAI)** | Média | Médio | Abstrair LLM provider (interface comum). Postgres é portável. Vercel→Railway é factível em ~2 dias. Não casar com features exóticas e proprietárias. |
| 8 | **CVM ou Receita interpreta como recomendação personalizada** | Média | Crítico | Linguagem cuidadosa. Análise vs recomendação. Disclaimers. Conversa com advogado especialista antes do lançamento. Documentação interna do que foi consultado. Não usar termos proibidos. |
| 9 | **LGPD: vazamento ou pedido massivo de exclusão** | Baixa-Média | Alto | Coleta mínima. Endpoint de exportação/exclusão. Política clara. Backup criptografado. Postura de incident response documentada. |
| 10 | **Mercado de FIIs entra em bear longo, demanda cai** | Média | Alto | Posicionar produto como ainda mais útil em bear (“te ajuda a não vender no fundo”). Diversificar para ações brasileiras (V3). Não criar dependência de TAM crescente. |
| 11 | **Hallucination da LLM gera justificativa errada** | Alta no início | Alto | Guardrails: validação regex, comprimento, palavras proibidas. Justificativa **nunca** decide o sinal — só comunica. Amostragem manual semanal de 20 justificativas. Telemetria das que falham guardrail. |
| 12 | **Onboarding com fricção: usuário desiste no CSV** | Alta | Médio | Importação por colagem com parser LLM (V1). Vídeo de 60s no onboarding. Templates por corretora (Rico, XP, Clear, Inter, Nubank). |
| 13 | **Custo de aquisição alto, audiência do canal não converte** | Média | Alto | Free tier real e generoso. Onboarding de 2 minutos. Conteúdo dirigido (“fizemos um app, eis um exemplo da minha carteira”). |
| 14 | **Suporte cresce e devora tempo** | Alta após N usuários | Alto | FAQ exaustivo. Loom de 2 minutos respondendo dúvidas comuns. Chatbot com Claude no app (V2). Discord/comunidade resolve usuário a usuário. |

---

## 16. Custos Estimados

### 16.1. Custos mensais de infraestrutura (estimativa em BRL)

| Item | MVP (0–500 users) | V1 (500–3k) | V2 (3k–10k) |
|---|---|---|---|
| Vercel Pro | R$ 100 | R$ 100 | R$ 250 (function invocations) |
| Supabase Pro | R$ 125 | R$ 125 | R$ 250 |
| Inngest | R$ 0 (free) | R$ 0–100 | R$ 200 |
| Sentry | R$ 0 (free) | R$ 130 | R$ 130 |
| Resend | R$ 0 | R$ 100 | R$ 250 |
| Axiom (logs) | R$ 0 | R$ 0 | R$ 100 |
| Domínio + e-mail | R$ 50 | R$ 50 | R$ 50 |
| **Subtotal infra** | **~R$ 275** | **~R$ 605** | **~R$ 1.230** |

### 16.2. Fontes de dados

| Item | MVP | V1 | V2 |
|---|---|---|---|
| brapi Pro | R$ 30 | R$ 30 | R$ 30 |
| (V2) ComDinheiro / MaisRetorno | – | – | R$ 500–2.000 |
| **Subtotal dados** | **~R$ 30** | **~R$ 30** | **~R$ 530–2.030** |

### 16.3. LLM — estimativa por usuário ativo

**Premissas:**
- Justificativa: 800 tokens input, 250 tokens output, Claude Haiku.
  - Custo: ~US$ 0,001 por chamada.
- Justificativa só regera quando sinal muda (média 1–2x/mês por FII).
- Carteira média: 12 FIIs.
- Logo: ~15–25 chamadas/usuário/mês = ~US$ 0,02 (R$ 0,11) por usuário ativo.

**Extração de relatório gerencial:**
- Trimestral, 80 FIIs cobertos. Sonnet ou GPT-4o-mini (depende complexidade).
- Custo: ~US$ 0,10 por extração.
- 80 FIIs × 4x/ano = 320 extrações/ano = US$ 32/ano = R$ 14/mês.

**Total LLM:**
- 500 users: ~R$ 80/mês.
- 3.000 users: ~R$ 350/mês.
- 10.000 users: ~R$ 1.150/mês.

### 16.4. Custos diversos

| Item | Mensal |
|---|---|
| Advogado (consulta inicial regulatória) | R$ 2.000–5.000 (one-shot) |
| Contador (PJ ou MEI) | R$ 100–300 |
| Logo / identidade visual | R$ 500–2.000 (one-shot, ou IA + ajustes) |
| Marketing / ADS | Variável (recomendação: começar com R$ 0, usar canal próprio) |

### 16.5. Investimento total estimado para o MVP

| Categoria | Estimativa |
|---|---|
| Tempo do founder | 8–12 semanas × ~30 h/semana = 240–360 h |
| SaaS no MVP | R$ 275/mês × 3 meses = ~R$ 825 |
| Dados | R$ 30/mês × 3 meses = ~R$ 90 |
| LLM em desenvolvimento | ~R$ 200 (testes intensos) |
| Advogado | R$ 3.000 (one-shot) |
| Domínio + branding mínimo | R$ 500 |
| **Total caixa MVP** | **~R$ 4.600** |

**Custo de oportunidade de tempo:** se Carlos cobra R$ X/h em consultoria, é Carlos que sabe. Em geral solo founders costumam aceitar 6–12 meses de “pagamento adiado” como investimento.

### 16.6. Custo unitário (LTV / payback)

- Custo médio por usuário Pro: ~R$ 0,20/mês de LLM + alocação de infra (~R$ 0,30) = ~R$ 0,50.
- Receita Pro: R$ 24,90/mês.
- Margem bruta por usuário pago: ~98 %.
- Payback de aquisição cabe em 1 mês mesmo com CAC de R$ 25.

---

## 17. Métricas de Sucesso

### 17.1. North Star Metric

> **Recomendações acionadas com sucesso por mês** = recomendações em que o usuário confirmou ter “seguido” via tela in-app (botão simples “já fiz isso”) ou marcou como lida com timestamp + ação subsequente na carteira.

Alternativa secundária: **carteiras analisadas com pelo menos 1 alerta lido** por mês.

### 17.2. AARRR

| Stage | Métrica | Alvo MVP |
|---|---|---|
| Acquisition | Visitas únicas/mês, CAC | 1.000 / R$ 0–25 |
| Activation | % completam onboarding (carteira + 1 análise) | ≥ 40 % |
| Retention | DAU/MAU; usuários ativos mês N+1 | DAU/MAU ≥ 0,15; W4 ≥ 30 % |
| Revenue | MRR, ARPU, conversão free→pro | MRR R$ 5k em 6 meses; conv ≥ 8 % |
| Referral | NPS, % usuários convidando | NPS ≥ 40; 5 % convidando |

### 17.3. Qualidade do motor

- **Acerto direcional em backtest** (V2): % de recomendações “Comprar/Aumentar” que outperformam IFIX em 6 meses; % “Vender/Reduzir” que underperformam.
- **NPS** segmentado por usuários que tomaram ação.
- **Taxa de “discordo da recomendação”** (botão de feedback inline).
- **Tempo até primeira ação** após onboarding (mediana).

### 17.4. Produtividade do solo dev

- **Features entregues por semana** (issues fechadas).
- **% do código gerado por IA** (heurística: linhas de PR atribuídas ao Cursor/Claude vs digitadas manualmente — métrica grosseira mas indicativa).
- **Tempo médio de bug fix** (lead time issue → deploy).
- **% de testes verdes em CI** (baseline > 95 %).
- **Frequência de deploy** (alvo: 5+ deploys/semana).

---

## 18. Glossário

| Termo | Definição |
|---|---|
| **FII** | Fundo de Investimento Imobiliário. Patrimônio coletivo investido em ativos imobiliários (imóveis, CRIs, cotas de outros fundos). |
| **IFIX** | Índice de Fundos Imobiliários da B3. Benchmark do segmento. |
| **DY (Dividend Yield)** | Razão entre proventos pagos no período e preço da cota. |
| **P/VP** | Preço da cota dividido pelo valor patrimonial por cota. |
| **Cap Rate** | Net Operating Income anualizado dividido pelo valor de mercado dos imóveis. |
| **NOI** | Net Operating Income. Receita operacional menos despesas operacionais (sem juros e impostos). |
| **Vacância física** | % de área construída sem locação. |
| **Vacância financeira** | % de receita potencial perdida por área vaga ou descontos. |
| **WAULT** | Weighted Average Unexpired Lease Term. Prazo médio ponderado dos contratos de locação. |
| **LTV** | Loan-to-Value. Saldo da dívida sobre valor do ativo. |
| **CRI** | Certificado de Recebíveis Imobiliários. Ativo de renda fixa lastreado em fluxos imobiliários. |
| **LCI** | Letra de Crédito Imobiliário. (Não compõe FII; só citamos por contexto.) |
| **FoF** | Fund of Funds. FII que investe em cotas de outros FIIs. |
| **Yield on Cost** | Proventos de 12 meses divididos pelo preço médio do investidor. |
| **Beta** | Sensibilidade do retorno do FII ao retorno do índice. |
| **Drawdown** | Queda do pico até o vale subsequente. |
| **Payout** | Razão entre distribuição e resultado contábil/caixa. |
| **Indexador** | Índice ao qual o CRI é atrelado (IPCA+, CDI, IGP-M). |
| **Fato relevante** | Comunicado obrigatório à CVM/B3 sobre evento material. |
| **High-grade / High-yield** | Classificação informal de FIIs de papel pelo perfil de risco/rating dos CRIs. |
| **B3** | Bolsa do Brasil. |
| **CVM** | Comissão de Valores Mobiliários. |
| **FNET** | Sistema da B3 onde fundos publicam comunicados. |
| **PWA** | Progressive Web App. App web instalável. |
| **RSC** | React Server Components. |
| **tRPC** | Type-safe Remote Procedure Call para TypeScript. |
| **Drizzle** | ORM TypeScript-first. |
| **Inngest** | Plataforma de jobs/workflows gerenciada. |
| **MTM** | Marcação a mercado. |

---

## 19. Anexos e Próximos Passos

### 19.1. Decisões em aberto

- **Naming do produto:** ainda não definido. Sugestões: “FIIscope”, “Bússola FII”, “Norte FII”, “Carteira Lúcida”. Validar disponibilidade de domínio + Instagram + LinkedIn.
- **Cor primária / identidade visual:** definir paleta — sugestão: azul-naval + verde-financeiro discreto, evitando vermelhão de “gritar”.
- **Tom de voz da marca:** “sóbrio + acessível” (vs “influencer hypado” ou “institucional engessado”). Documentar em guia de estilo.
- **Política de devolução:** 7 dias (Código de Defesa do Consumidor cobre).
- **Decisão final entre Drizzle e Prisma:** prototipar 1 dia em cada, escolher.

### 19.2. Pesquisas adicionais recomendadas

1. Análise de UX dos concorrentes (especialmente Status Invest e Investidor10).
2. Levantamento de 30 perguntas mais frequentes em fóruns brasileiros de FIIs (Reddit r/investimentos, X, Comunidade Rico, Suno).
3. Conversar com 10 investidores reais (do canal de YouTube) sobre processo atual de decisão.
4. Estudo regulatório com advogado: linguagem permitida × proibida. Documento interno “Glossário regulatório”.
5. Mapear corretoras brasileiras e formato de exportação de extrato de cada uma (para parsers do importador CSV).

### 19.3. Concorrentes a estudar a fundo

- **Status Invest** (gratuito + premium): UX, fontes, monetização, comunidade.
- **Investidor10** (premium): paywall, qualidade dos dados, motor de score (eles têm um “score”).
- **Funds Explorer** (gratuito): completude de dados, atualização.
- **Suno**: research humano, carteiras modelo, cobrança.
- **Clube FII**: comunidade, conteúdo.
- **Variável Investimentos** (newsletter paga): formato de conteúdo, retenção.

### 19.4. Próximas 5 ações práticas para iniciar

1. **Validar nome e domínio** (24 h). Registrar `.com.br` e `.com`. Reservar Instagram/X/LinkedIn handles.
2. **Configurar repo monorepo** (1 dia). `pnpm init`, Next.js 15 + TS + Tailwind + shadcn + Drizzle + Supabase. CI no GitHub Actions trivial.
3. **Modelar schema inicial** (1 dia). Tabelas profiles, portfolios, positions, fiis, quotes, recommendations. Migrations versionadas. Popular com top 50 FIIs.
4. **Prototipar motor de regras com 3 FIIs reais** (3 dias). MXRF11, HGLG11, KNRI11. Calcular sub-scores manualmente, comparar com expectativa intuitiva, calibrar. Mostrar resultado em tela tosca.
5. **Testar prompt de geração de justificativa** (1 dia). Anthropic API. 20 iterações com FII real, ler outputs, refinar. Documentar prompt versionado em `prompts/justification-v1.md`.

### 19.5. Documentos auxiliares a criar no repo

- `README.md` — visão geral.
- `CLAUDE.md` — contexto para Claude Code/Cursor (regras de código, arquitetura, comandos).
- `INFRA.md` — registro vivo de SaaS, env vars, cron schedules.
- `METHODOLOGY.md` — pesos, thresholds, fórmulas (versão pública para usuário).
- `prompts/` — diretório de prompts versionados.
- `decisions/` — ADRs (Architectural Decision Records) — uma por decisão grande.

---

## 20. Autocrítica do Documento

> Por dever de honestidade, o que este documento ainda não cobre bem ou pode estar errado:

1. **Pesos do motor são chutes calibrados, não validados.** Os valores sugeridos para $w_v, w_q, w_r, w_l, w_h$ saíram de intuição de domínio, não de backtest. **Antes de lançar para usuários pagantes, é obrigatório validar manualmente em pelo menos 30 FIIs de tipos diferentes.** Provavelmente os pesos vão se mover.

2. **Risco regulatório CVM 20 está sub-explorado.** Cobrimos em alto nível, mas não substitui parecer jurídico. Se o advogado disser que o produto descrito **é** recomendação personalizada de investimento, parte do escopo precisa mudar (linguagem, tiers, ou caminho para credenciamento).

3. **Estimativas de prazo do MVP são otimistas.** 8–12 semanas é viável para alguém em fluxo total, mas burnout, vida pessoal, bug crítico ou pivot pequeno facilmente extendem para 16. Considere o limite superior como o realista.

4. **Custos LLM podem explodir em casos de uso não previstos.** Se um usuário Premium quiser “converse com sua carteira” (V2), custo por sessão pode ser 10–50x o estimado. Modelo de cobrança e cap por uso precisarão evoluir.

5. **Backtest é tratado com leveza.** Construir backtest histórico fiel é trabalho de 4–8 semanas só dele. Ficou só no V2 — talvez devesse estar no V1, porque é o argumento mais forte de credibilidade técnica.

6. **Importação de CSV é mais difícil do que parece.** Cada corretora exporta diferente. Vai exigir parser robusto + tratamento de edge cases. Pode consumir 1–2 semanas extras no MVP.

7. **Foco no *brasileiro* às vezes vai além — alguns FIIs brasileiros têm edge cases (fundos em desenvolvimento, FIIs com baixíssima liquidez, gestoras com práticas heterodoxas) que o motor de regras simples vai marcar erroneamente como bom ou ruim. Precisa lista de exceções manuais.

8. **Nada foi dito sobre acessibilidade real (WCAG).** Mencionei tooltips e linguagem clara, mas WCAG AA exige mais (contraste, navegação por teclado, screen reader). Vale incluir desde o MVP — Radix UI ajuda muito, mas não é grátis.

9. **Plano para quando o founder ficar 100 % no projeto vs continuar com canal** não foi tratado. Carlos pode ter cliente conflito de tempo entre produzir conteúdo (gera audiência → users) e codar (gera produto). Não se resolve no documento, mas precisa de decisão consciente.

10. **A análise consolidada da carteira é a feature mais difícil de fazer bem** e está categorizada como “V1, complexidade alta, viab IA alta” — provavelmente subestimei a parte de detecção de sobreposição em FoFs (exige composição interna do FoF, dado que nem sempre é público em alta resolução). Pode ficar feature “best effort” em vez de definitiva.

> O documento deve ser tratado como **versão 1.0 viva**. Cada decisão tomada na execução deve voltar e atualizar a seção correspondente. Manter `PROJETO.md` sincronizado com a realidade é responsabilidade contínua — porque é a única documentação estratégica que você vai ler de novo daqui a 6 meses, num dia em que esquecer por que escolheu Drizzle em vez de Prisma.

---

*Fim do documento.*
