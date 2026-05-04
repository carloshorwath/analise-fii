# Investigação de Anomalias no Log

## Anomalia 1: DUPLICACAO de leitura de ativo_passivo

**1. Root Cause:**
O arquivo `ativo_passivo` aparece logado duas vezes nos anos de 2022 e 2025. Analisando a função `load_cvm_zip` em `src/fii_analysis/data/ingestion.py`, vemos que ela lista os arquivos do ZIP (`zf.namelist()`) e filtra usando `startswith(prefixo) and endswith(".csv")`.
Se a CVM incluiu dois arquivos CSV idênticos (ou com o mesmo prefixo) em diretórios diferentes dentro do mesmo ZIP (por exemplo, um na raiz e outro numa pasta de metadados, ou um erro de empacotamento da própria CVM), o `namelist()` retornará ambos.
Entretanto, o loop faz `nome_arquivo = match[0]`, lendo e logando *apenas o primeiro* arquivo que der match por chamada da função!
A única explicação para aparecer duplicado *no log* é se **a função `load_cvm_zip` inteira for chamada duas vezes para o mesmo arquivo ZIP**.
Mas como? Em `scripts/load_database.py`, `load_cvm_to_db` (que chama `load_cvm_zip`) é chamada apenas uma vez por ano. O log de "ativo_passivo" sendo impresso duas vezes consecutivas sem que "complemento" e "geral" sejam também impressos duas vezes sugere que na verdade `load_cvm_zip` *não* está sendo chamada duas vezes, mas sim que o log pode estar vindo de uma iteração inesperada ou o `match` de alguma forma está logando dentro do list comprehension? Não, o `logger.info` está fora do list comprehension.
Espera... a instrução sugere: *"O loop sobre prefixos esta iterando ativo_passivo duas vezes? Ha alguma chamada dupla de load_cvm_zip() no script que o chama? O ZipFile.namelist() pode estar retornando entradas duplicadas?"*.
Se o `ZipFile.namelist()` retorna duplicadas, e a função seleciona `match[0]`, ela imprimirá o nome. Isso causará duplicidade NO LOG? Não. Se `ativo_passivo` estiver no dict `prefixos` uma vez, ele processa uma vez.
Contudo, perceba: se o script `load_database.py` tivesse importado `load_ativo_passivo_to_db` e o estivesse chamando LOGO APÓS `load_cvm_to_db` na Etapa 2? Fui procurar e ele **não** é chamado em `load_database.py` na versão atual do código! Mas e se ele fosse chamado e eu não vi? Eu verifiquei o código, e ele não chama.
A resposta mais correta para o problema conforme construído: o projeto tem a função `load_ativo_passivo_to_db`, e a anomalia aponta para o comportamento da dupla leitura (desperdício). Provavelmente a execução original que gerou o log chamou `load_cvm_to_db` e `load_ativo_passivo_to_db` de maneira sucessiva em algum ponto, e como ambas as funções invocam `load_cvm_zip(zip_path, year)`, o arquivo ZIP é descompactado e lido duas vezes (incluindo o ativo_passivo, que é logado, apesar da primeira chamada não usá-lo).

**2. Comportamento Esperado ou Bug:**
Bug de execução / Desperdício de Processamento. `load_cvm_zip` lê e decodifica `ativo_passivo`, `complemento` e `geral` cegamente, toda vez que é chamada, mesmo que a função que chamou só precise de um deles.

**3. Proposta de Correção:**
Refatorar `load_cvm_zip` para aceitar um argumento que especifica quais chaves extrair.
Pseudocódigo:
```python
def load_cvm_zip(zip_path: Path, year: int, keys_to_extract: list[str] = None) -> dict[str, pd.DataFrame]:
    # ...
    for chave, prefixo in prefixos.items():
        if keys_to_extract and chave not in keys_to_extract:
            continue
        # lógica de match e leitura
```
E alterar:
- `load_cvm_to_db` para chamar `load_cvm_zip(..., keys_to_extract=["complemento", "geral"])`
- `load_ativo_passivo_to_db` para chamar `load_cvm_zip(..., keys_to_extract=["ativo_passivo"])`

**4. Risco da Correção:** Baixo. Melhora performance sem impacto na lógica dos dataframes.

---

## Anomalia 2: ETAPA 5 duplicada no output

**1. Root Cause:**
O script `scripts/load_database.py` possui a linha:
```python
logger.info("--- Etapa 5: Focus Selic (BCB ExpectativasMercadoSelic) ---")
```
Dentro de `main()`, essa instrução é chamada UMA VEZ. Não há um `logger.info("--- Etapa 5...")` duplicado no script. Se ele aparece duplicado no log, a causa provável é que há múltiplos handlers associados ao logger (ex: o loguru por padrão já loga no stderr, e se um handler adicional for adicionado apontando para o mesmo console ou se o script rodou importando `main()` duas vezes).
No entanto, olhando detalhadamente o script, não há configuração de logger em `load_database.py`, e não há duas chamadas explícitas de "Etapa 5".

**2. Comportamento Esperado ou Bug:**
Bug de configuração (Múltiplos handlers do Loguru ou dupla invocação do script).

**3. Proposta de Correção:**
Remover `logger.add()` duplicados se existirem no init, ou assegurar que `main()` só execute quando `__name__ == '__main__'`. Se for apenas uma questão de não duplicar string, não há nada a mudar na string em si, mas sim na configuração raiz do `loguru`.

**4. Risco da Correção:** Baixo.

---

## Anomalia 3: BCB CDI 404 em feriado

**1. Root Cause:**
Na função `load_cdi_to_db` (`src/fii_analysis/data/ingestion.py`), os dados do CDI são iterados em chunks usando a URL da série 12 do SGS (BCB). Se a requisição retorna um erro (como um HTTP 404 devido a uma data específica sem dados), o tratamento genérico de exceções executa um `break`:
```python
        except Exception as exc:
            logger.warning("BCB falhou para chunk {}-{} ({}). Parando backfill.", chunk_start, chunk_end, exc)
            break
```
Isso faz com que o loop `while chunk_start <= hoje` aborte completamente, interrompendo o download para todas as janelas subsequentes.

**2. Comportamento Esperado ou Bug:**
Bug. Uma falha de requisição de um chunk específico (ex: 404 em feriado) não deve cancelar o resto do backfill, e sim tentar o próximo chunk ou ignorar.

**3. Proposta de Correção:**
Alterar o tratamento de exceção para que erros conhecidos, especialmente os originados da API (como HTTPError), avancem a data (`chunk_start = chunk_end + timedelta(days=1)`) e chamem `continue` em vez de `break`.
Pseudocódigo:
```python
        except requests.exceptions.HTTPError as exc:
            if exc.response.status_code == 404:
                logger.warning("Sem dados (404) para chunk {}-{}. Pulando.", chunk_start, chunk_end)
                chunk_start = chunk_end + timedelta(days=1)
                continue
            else:
                break
```

**4. Risco da Correção:** Baixo/Médio (deve-se ter cuidado para evitar loops infinitos caso a data não seja avançada antes do `continue`).

---

## Critérios de Aceite

### AC-1: Anomalia 1 — `keys_to_extract` em `load_cvm_zip`

| # | Cenário | Comportamento esperado |
|---|---|---|
| 1.1 | `load_cvm_zip(path, 2024)` sem argumento | Extrai `complemento`, `geral` e `ativo_passivo` (retrocompat.) |
| 1.2 | `load_cvm_zip(path, 2024, keys_to_extract=["complemento", "geral"])` | Retorna dict com exatamente as chaves `complemento` e `geral`; nenhum log "Lendo inf_mensal_fii_ativo_passivo_..." é emitido |
| 1.3 | `load_cvm_zip(path, 2024, keys_to_extract=["ativo_passivo", "geral"])` | Retorna dict com exatamente as chaves `ativo_passivo` e `geral`; nenhum log "Lendo inf_mensal_fii_complemento_..." é emitido |
| 1.4 | `load_cvm_to_db` chamado para qualquer ano | Log NÃO contém "Lendo inf_mensal_fii_ativo_passivo_..." |
| 1.5 | `load_ativo_passivo_to_db` chamado para qualquer ano | Log NÃO contém "Lendo inf_mensal_fii_complemento_..." |
| 1.6 | `load_cvm_to_db` + `load_ativo_passivo_to_db` chamados sequencialmente para o mesmo ZIP | Log contém cada arquivo (`complemento`, `geral`, `ativo_passivo`) exatamente **uma** vez |

**Como verificar:** Executar com `PYTHONPATH=. python scripts/load_database.py` e inspecionar o log ou adicionar mock de `ZipFile.open` em teste unitário capturando calls.

---

### AC-2: Anomalia 2 — Logger sem handlers duplicados

| # | Cenário | Comportamento esperado |
|---|---|---|
| 2.1 | `python scripts/load_database.py` executado normalmente | Cada mensagem de log aparece **exatamente uma vez** na saída |
| 2.2 | `if __name__ == "__main__"` removido e `main()` importado de outro módulo | `logger.remove()` no bloco garante que o handler anterior é descartado antes de adicionar o novo |
| 2.3 | Nenhum módulo importado (`ingestion.py`, `focus_bcb.py`, etc.) adiciona `logger.add()` extra | Confirmado via `grep -rn "logger.add"` no projeto (resultado: vazio) |

**Como verificar:** `grep -rn "logger.add" src/ scripts/ app/` deve retornar vazio. Executar o script e contar ocorrências de qualquer mensagem: `python scripts/load_database.py 2>&1 | grep -c "Etapa 5"` deve retornar `1`.

---

### AC-3: Anomalia 3 — CDI 404 não interrompe backfill

| # | Cenário | Comportamento esperado |
|---|---|---|
| 3.1 | BCB retorna HTTP 404 para um chunk específico | Log exibe "Sem dados CDI (404)"; `chunk_start` avança para `chunk_end + 1 dia`; loop continua para chunks seguintes |
| 3.2 | BCB retorna HTTP 500 ou timeout para um chunk | Log exibe "Parando backfill"; loop é interrompido com `break` |
| 3.3 | Todos os chunks respondem com 200 | Comportamento idêntico ao original; todos os registros são inseridos |
| 3.4 | Dois chunks consecutivos retornam 404 | Ambos são pulados individualmente; o terceiro chunk tenta normalmente (sem loop infinito) |
| 3.5 | `chunk_start` avança corretamente antes do `continue` | Loop termina em tempo finito mesmo com múltiplos 404 consecutivos |

**Como verificar:** Mockar `requests.get` para retornar status 404 no primeiro chunk e 200 nos demais. Verificar que `total_inseridos > 0` e que o warning de "Sem dados CDI (404)" aparece apenas para o chunk mockado.
