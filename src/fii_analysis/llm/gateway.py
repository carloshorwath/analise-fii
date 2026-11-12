from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional
import requests
from loguru import logger
from dotenv import load_dotenv

from src.fii_analysis.llm.prompts import render_prompt

# Carrega chaves locais e globais
load_dotenv()
load_dotenv(r"C:\Modelos-AI\Brapi\.env")


@dataclass
class LlmResult:
    status: str       # "OK" | "TIMEOUT" | "ERRO" | "SEM_CONFIG"
    resposta_md: Optional[str] = None
    modelo: Optional[str] = None
    prompt_pack_path: Optional[str] = None
    erro_mensagem: Optional[str] = None
    latencia_ms: Optional[int] = None


PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "dados", "prompts",
)


def export_prompt_pack(
    system_prompt: str,
    user_prompt: str,
    template_name: str,
    ticker: str
) -> str:
    """Grava o prompt completo renderizado em Markdown para colagem manual.

    Sempre grava em <raiz do projeto>/dados/prompts, independente do CWD.
    """
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    dt_str = date.today().isoformat()
    # Limpa caracteres especiais do ticker/par para o nome do arquivo
    clean_ticker = str(ticker).replace("/", "_").replace("\\", "_")
    filename = f"{dt_str}_{template_name}_{clean_ticker}.md"
    filepath = os.path.join(PROMPTS_DIR, filename)

    content = (
        f"# PROMPT PACK: {template_name.upper()} - {ticker}\n"
        f"Gerado em: {dt_str}\n\n"
        f"--- SYSTEM PROMPT ---\n"
        f"```text\n"
        f"{system_prompt}\n"
        f"```\n\n"
        f"--- USER PROMPT ---\n\n"
        f"{user_prompt}\n"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def ask_llm(
    template_name: str,
    context: dict,
    pergunta: Optional[str] = None,
    timeout: int = 120
) -> LlmResult:
    """Envia o prompt renderizado para o webhook n8n ou gera o fallback prompt pack em caso de falha."""
    # 1. Renderizar prompt localmente
    try:
        sys_prompt, user_prompt, version = render_prompt(template_name, context, pergunta)
    except Exception as e:
        logger.error(f"Erro ao renderizar prompt: {e}")
        return LlmResult(
            status="ERRO",
            erro_mensagem=f"Erro de renderizacao: {e}"
        )

    ticker = context.get("ticker") or f"{context.get('vender_ticker', 'N/D')}_{context.get('comprar_ticker', 'N/D')}"

    # 2. Verificar configurações
    webhook_url = os.getenv("N8N_FII_WEBHOOK_URL")
    token = os.getenv("N8N_FII_TOKEN")

    if not webhook_url:
        logger.warning("N8N_FII_WEBHOOK_URL não configurado. Degradando para Prompt Pack.")
        pack_path = export_prompt_pack(sys_prompt, user_prompt, template_name, ticker)
        return LlmResult(
            status="SEM_CONFIG",
            prompt_pack_path=pack_path,
            erro_mensagem="N8N_FII_WEBHOOK_URL não configurado."
        )

    # 3. Enviar HTTP POST com Retry
    headers = {
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "template": template_name,
        "prompt_version": version,
        "contexto": context,
        "pergunta": pergunta or "",
        "system_prompt": sys_prompt,
        "user_prompt": user_prompt
    }

    retries = 2
    backoff = 2.0
    start_time = time.time()

    for attempt in range(retries + 1):
        try:
            logger.info(f"Enviando requisicao LLM (Tentativa {attempt+1}/{retries+1}) para {webhook_url}")
            r = requests.post(webhook_url, json=payload, headers=headers, timeout=timeout)
            r.raise_for_status()

            latencia = int((time.time() - start_time) * 1000)

            # Interpreta resposta
            resposta_md = None
            modelo = None
            try:
                res_json = r.json()
                if isinstance(res_json, dict):
                    resposta_md = res_json.get("resposta_md") or res_json.get("response") or res_json.get("text")
                    modelo = res_json.get("modelo") or res_json.get("model")
            except Exception:
                pass

            if not resposta_md:
                # Se não for JSON estruturado, consome texto bruto da resposta
                resposta_md = r.text

            return LlmResult(
                status="OK",
                resposta_md=resposta_md,
                modelo=modelo or "n8n-model",
                latencia_ms=latencia
            )

        except requests.Timeout as e:
            logger.warning(f"Timeout na tentativa {attempt+1}: {e}")
            if attempt == retries:
                pack_path = export_prompt_pack(sys_prompt, user_prompt, template_name, ticker)
                return LlmResult(
                    status="TIMEOUT",
                    prompt_pack_path=pack_path,
                    erro_mensagem=f"Timeout apos {retries+1} tentativas: {e}"
                )
        except Exception as e:
            logger.warning(f"Falha na tentativa {attempt+1}: {e}")
            if attempt == retries:
                pack_path = export_prompt_pack(sys_prompt, user_prompt, template_name, ticker)
                return LlmResult(
                    status="ERRO",
                    prompt_pack_path=pack_path,
                    erro_mensagem=f"Erro HTTP apos {retries+1} tentativas: {e}"
                )
        # Backoff
        time.sleep(backoff)
        backoff *= 2.0

    # Fallback genérico
    pack_path = export_prompt_pack(sys_prompt, user_prompt, template_name, ticker)
    return LlmResult(
        status="ERRO",
        prompt_pack_path=pack_path,
        erro_mensagem="Falha inesperada no gateway."
    )
