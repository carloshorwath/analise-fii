# Plano de Lançamento

Plano objetivo para levar o projeto de “sistema funcionando para uso interno” até “produto utilizável, estável e auditável”.

Data de referência: `2026-04-26`

---

## 1. Objetivo do lançamento

Entregar uma versão utilizável do sistema para uso diário, com:

- navegação madura e previsível
- snapshots prontos para consumo rápido
- fluxo operacional claro (`Hoje` → `Carteira` → `Panorama`)
- rotina de atualização simples
- riscos metodológicos conhecidos documentados
- regressões críticas reduzidas ao mínimo

Este lançamento **não** significa:

- plataforma multiusuário
- automação de execução
- recomendação formal de investimento
- cobertura ampla de universo sem curadoria

---

## 2. Escopo do lançamento

### Incluído

- app Streamlit com navegação por contexto
- carteira do usuário
- panorama e radar do universo curado
- cockpit `Hoje`
- snapshots diários (`curado` e `carteira`)
- relatórios/exportações operacionais
- auditoria estatística via `Otimizador V2`, `Episódios`, `WalkForward`, `Event Study`

### Fora do lançamento

- expansão automática do universo
- notificações push
- autenticação
- backtests multiusuário
- score proprietário
- machine learning

---

## 3. Definição de pronto

O lançamento só deve acontecer quando todos os itens abaixo estiverem verdadeiros:

1. O app abre sem erro e a navegação lateral está na ordem desejada.
2. `Hoje`, `Carteira`, `Panorama` e `Radar` abrem rápido usando snapshot.
3. O fluxo de atualização diária está documentado e reproduzível.
4. Há um smoke test mínimo executado antes de cada atualização maior.
5. Os bugs conhecidos de severidade alta foram zerados.
6. As limitações metodológicas principais estão visíveis para o usuário.
7. Existe um caminho simples para recuperar o sistema se o snapshot do dia falhar.

---

## 4. Macrofases até o lançamento

### Fase A — Estabilização final

Objetivo: zerar bugs críticos e medium-alto na experiência principal.

Entregas:

- revisar `Hoje`, `Carteira`, `Panorama`, `Radar`
- revisar páginas com navegação nova (`st.navigation`)
- revisar seletores/filtros que antes viviam no sidebar
- revisar cards truncados, labels longos e estados vazios
- validar que nenhuma página pesada recalcula motor sem necessidade

Critério de saída:

- nenhum erro bloqueante no fluxo diário
- navegação funcional em todas as páginas principais

---

### Fase B — Operação diária confiável

Objetivo: transformar atualização e uso diário em rotina simples.

Entregas:

- consolidar fluxo admin:
  - atualizar base
  - gerar snapshot `curado`
  - gerar snapshot `carteira`
- documentar o procedimento de início de dia
- documentar o procedimento de troubleshooting
- mostrar data/hora do snapshot de forma consistente nas páginas

Critério de saída:

- qualquer pessoa do projeto consegue atualizar o sistema seguindo um roteiro curto

---

### Fase C — QA de produto

Objetivo: validar a experiência como produto, não só como código.

Entregas:

- rodada de teste manual guiada
- checklist por página principal
- revisão de textos, disclaimers e nomenclatura
- validação da jornada:
  - `Hoje`
  - `Carteira`
  - `Panorama`
  - `Análise FII`
  - `Otimizador V2`

Critério de saída:

- a jornada principal pode ser executada sem orientação do desenvolvedor

---

### Fase D — Empacotamento de lançamento

Objetivo: deixar o projeto publicável e sustentável.

Entregas:

- documentação de uso atualizada
- documentação operacional do snapshot
- changelog ou nota de versão
- snapshot de referência do banco ou estratégia de backup
- plano de rollback

Critério de saída:

- projeto fica apresentável, operável e recuperável

---

## 5. Backlog priorizado até o lançamento

### P0 — Bloqueadores do lançamento

1. Validar o fluxo completo do app com a navegação nova.
   Arquivos mais sensíveis:
   - `app/streamlit_app.py`
   - `app/state.py`
   - `app/pages/13_Hoje.py`
   - `app/pages/3_Carteira.py`
   - `app/pages/8_Fund_EventStudy.py`

2. Garantir que o fluxo de snapshots rode sem intervenção manual além do comando.
   Comandos-alvo:
   - `C:\ProgramData\anaconda3\python.exe scripts/load_database.py`
   - `C:\ProgramData\anaconda3\python.exe scripts/generate_daily_snapshots.py --scope curado --force`
   - `C:\ProgramData\anaconda3\python.exe scripts/generate_daily_snapshots.py --scope carteira --force`

3. Confirmar que `Hoje` e `Carteira` leem o snapshot correto da carteira atual.

4. Validar que páginas operacionais continuam úteis mesmo sem snapshot do dia.
   Regra:
   - snapshot primeiro
   - fallback claro
   - sem travamento silencioso

5. Revisar o entrypoint e remover regressões visuais óbvias.
   Exemplos:
   - truncamento de metric
   - seletor escondido
   - labels inconsistentes

---

### P1 — Essenciais para chamar de produto maduro

1. Conectar `IFIX YTD` real no Panorama.
   Situação atual conhecida:
   - ainda aparece `n/d` em cenários específicos

2. Fechar a paridade principal entre CLI e web no Panorama.
   Faltas conhecidas:
   - rentabilidade acumulada
   - DY 24m
   - tipo/segmento conforme exibição desejada

3. Extrair o que ainda estiver visualmente “solto” em `7_Fundamentos.py`.

4. Padronizar mensagens de estado:
   - sem snapshot
   - snapshot antigo
   - carteira desatualizada
   - fallback ao vivo

5. Consolidar a nomenclatura final do produto.
   Exemplos:
   - `Analise FII` vs `Análise FII`
   - `WalkForward` vs `Walk-Forward`
   - `Fund EventStudy` vs `Fund Event Study`

---

### P2 — Importantes, mas não bloqueantes

1. Criar cache de `optimizer_params`.
   Benefício:
   - melhora muito o custo de `daily_report.py`
   - reduz dependência de otimização completa no dia

2. Criar snapshots reprodutíveis do banco com hash.

3. Adicionar um smoke test automatizado mínimo.

4. Criar um mini changelog de release.

5. Refinar a home e os textos para apresentação externa.

---

## 6. Teste mínimo antes do lançamento

### Teste 1 — Integridade da atualização

Executar:

```powershell
C:\ProgramData\anaconda3\python.exe scripts/load_database.py
C:\ProgramData\anaconda3\python.exe scripts/generate_daily_snapshots.py --scope curado --force
C:\ProgramData\anaconda3\python.exe scripts/generate_daily_snapshots.py --scope carteira --force
```

Esperado:

- sem exceção
- snapshot `curado` pronto
- snapshot `carteira` pronto
- advices e alertas gerados para carteira quando houver posições

### Teste 2 — Jornada do usuário

Abrir e validar:

1. `Inicio`
2. `Hoje`
3. `Carteira`
4. `Panorama`
5. `Radar`
6. `Analise FII`
7. `Otimizador V2`

Esperado:

- sem erros na tela
- sem controles ocultos pela navegação
- carregamento percebido como rápido nas páginas snapshot-first

### Teste 3 — Falha controlada

Simular ausência de snapshot ou snapshot antigo.

Esperado:

- mensagem clara
- fallback compreensível
- sem travar o app inteiro

### Teste 4 — Coerência operacional

Validar manualmente:

- `Hoje` bate com `Carteira`
- `Carteira` bate com snapshot da carteira atual
- `Panorama` e `Radar` respeitam o escopo curado
- `WalkForward`, `Episódios` e `Otimizador V2` continuam acessíveis como auditoria

---

## 7. Rotina operacional recomendada

### Antes da abertura/uso do dia

1. Atualizar base
2. Gerar snapshot `curado`
3. Gerar snapshot `carteira`
4. Abrir `Hoje`
5. Conferir timestamp do snapshot

### Durante o uso

Ordem recomendada:

1. `Hoje`
2. `Carteira`
3. `Panorama`
4. `Analise FII`
5. `Fundamentos`
6. páginas de auditoria quando necessário

### Se a carteira mudar no meio do dia

1. atualizar carteira
2. gerar snapshot `carteira` novamente
3. revisar `Hoje` e `Carteira`

---

## 8. Documentação que precisa estar pronta no lançamento

### Obrigatória

- `AGENTS.md`
- `docs/STATUS_ATUAL.md`
- `docs/PROJETO.md`
- este arquivo `LANCAMENTO.md`

### Recomendável

- nota curta de versão
- roteiro “como atualizar os dados”
- roteiro “como usar o sistema no dia a dia”

---

## 9. Riscos de lançamento

### Riscos técnicos

- regressão de navegação com `st.navigation`
- fallback ao vivo ficar lento demais
- snapshot da carteira não refletir alteração intradiária
- dependência de ambiente Python correto

### Riscos metodológicos

- usuário interpretar heurística como probabilidade
- confundir simulação operacional com promessa de performance futura
- usar sinais estatísticos fora do contexto de risco do fundo

### Mitigação

- disclaimers claros
- snapshot timestamp visível
- separação entre operar, entender e auditar
- smoke test antes de cada atualização maior

---

## 10. Plano de rollback

Se o lançamento causar regressão séria:

1. voltar o entrypoint para a navegação anterior
2. manter snapshots e backend como estão
3. preservar a ordem funcional mínima:
   - `Hoje`
   - `Carteira`
   - `Panorama`
4. registrar o problema em `docs/STATUS_ATUAL.md`

Observação:

- rollback deve priorizar restabelecer uso diário, não preservar refinamento visual

---

## 11. Sequência recomendada de execução

### Semana / ciclo 1

1. fechar P0 de navegação e snapshot
2. rodar smoke test completo
3. consolidar rotina admin

### Semana / ciclo 2

1. fechar P1 visual e de consistência
2. revisar documentação final
3. preparar nota de versão

### Semana / ciclo 3

1. rodar teste final com carteira real
2. congelar mudanças grandes
3. lançar

---

## 12. Critério final de go/no-go

### Go

- fluxo diário está estável
- snapshots estão confiáveis
- páginas principais respondem rápido
- bugs bloqueantes foram eliminados
- documentação mínima está pronta

### No-go

- `Hoje` ou `Carteira` ainda quebram com frequência
- geração de snapshot ainda depende de tentativa e erro
- o usuário precisa do desenvolvedor para operar a ferramenta
- o app ainda alterna entre estados incoerentes sem aviso

---

## 13. Próximo passo imediato

O próximo passo mais racional é:

1. executar o smoke test completo do fluxo admin + snapshots
2. revisar manualmente a jornada `Inicio` → `Hoje` → `Carteira` → `Panorama`
3. fechar os últimos P0/P1 de UI e consistência

Depois disso, o projeto entra em janela real de lançamento.
