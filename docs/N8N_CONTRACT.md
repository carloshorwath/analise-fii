# Contrato do Webhook n8n — Camada LLM

Este documento define a especificação da requisição HTTP POST e o formato da resposta esperada entre o gateway do FII Analysis e o workflow do n8n.

---

## 1. Endereço e Autenticação

- **Endpoint**: Configurado na variável `N8N_FII_WEBHOOK_URL` do arquivo `.env`
- **Método**: `POST`
- **Autenticação**: Envia o cabeçalho `Authorization: Bearer <TOKEN>` usando o valor da variável `N8N_FII_TOKEN`.

---

## 2. Payload da Requisição (JSON)

O gateway do FII Analysis enviará o seguinte JSON estruturado:

```json
{
  "template": "analise_ticker",
  "prompt_version": "1.0",
  "contexto": {
    "ticker": "KNIP11",
    "data_contexto": "2026-06-11",
    "score_total": 85,
    "score_breakdown": {
      "valuation": 90,
      "risco": 80,
      "liquidez": 90,
      "historico": 80
    },
    "indicadores": {
      "preco": 98.5,
      "vp": 100.0,
      "pvp": 0.985,
      "pvp_percentil": 24.5,
      "dy_12m": 0.105,
      "dy_24m": 0.21,
      "dy_gap": 0.005,
      "dy_gap_percentil": 72.1,
      "volume_21d": 1200000.0,
      "segmento": "Papel",
      "cvm_defasada": false
    },
    "decisao": {
      "acao": "COMPRAR",
      "nivel_concordancia": "ALTA",
      "sinal_otimizador": "BUY",
      "sinal_episodio": "BUY",
      "sinal_walkforward": "BUY",
      "rationale": [
        "Preço atrativo",
        "Concordância 3/3"
      ]
    },
    "flags_risco": {
      "destruicao_capital": false,
      "motivo_destruicao": null,
      "emissao_recente": false,
      "pvp_caro": false,
      "dy_gap_baixo": false,
      "volume_queda_forte": false,
      "ltv_alto": false,
      "pl_trend": "ESTAVEL",
      "rentab_divergencia": false
    }
  },
  "pergunta": "Pergunta extra opcional do usuário",
  "system_prompt": "Você é um analista sênior de Fundos Imobiliários...",
  "user_prompt": "Análise detalhada do ticker: KNIP11..."
}
```

### Campos do Payload

| Campo | Tipo | Descrição |
|---|---|---|
| `template` | `string` | Nome do template do prompt (`analise_ticker` \| `oportunidade_rotacao` \| `revisao_carteira` \| `briefing_semanal`) |
| `prompt_version` | `string` | Versão do template (`1.0`) |
| `contexto` | `object` | Dicionário contendo dados estruturados do snapshot do ticker ou da oportunidade |
| `pergunta` | `string` | Pergunta livre opcional inserida pelo usuário via CLI ou UI |
| `system_prompt` | `string` | Prompt de sistema pré-renderizado |
| `user_prompt` | `string` | Prompt de usuário completo pré-renderizado |

---

## 3. Resposta Esperada (JSON)

O workflow do n8n deve retornar a resposta no formato abaixo:

```json
{
  "resposta_md": "## Análise Qualitativa de KNIP11\n\n1. **Sumário Executivo**:\nKNIP11 apresenta indicadores sólidos de...",
  "modelo": "gpt-4o",
  "tokens": 1420
}
```

### Campos da Resposta

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `resposta_md` | `string` | Sim | O texto completo da análise gerado pelo LLM em formato Markdown. |
| `modelo` | `string` | Não | O nome/ID do modelo de linguagem utilizado para gerar a resposta (ex: `gpt-4o`, `claude-3-5-sonnet`). |
| `tokens` | `integer` | Não | Total de tokens consumidos na requisição (opcional, estatístico). |

> [!TIP]
> **Fallback**: Se o n8n retornar um conteúdo que não seja um objeto JSON válido (por exemplo, retornar apenas texto Markdown puro como string), o gateway tratará o texto bruto retornado como o valor de `resposta_md` e definirá o `modelo` como `"n8n-model"` por padrão.
