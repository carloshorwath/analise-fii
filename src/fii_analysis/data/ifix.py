from __future__ import annotations

import base64
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import Ticker, Universo

urllib3.disable_warnings()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
IFIX_CSV_PATH = PROJECT_ROOT / "dados" / "ifix_composicao.csv"


def get_ifix_composition(session: Session) -> list[dict[str, Any]]:
    """Obtém a composição teórica do IFIX, resolvendo CNPJs.
    
    1. Tenta API da B3. Em falha, usa ifix_composicao.csv.
    2. Resolve CNPJ via DB > CSV > StatusInvest.
    3. Persiste na tabela Universo e faz self-healing no CSV.
    """
    api_url_base = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/"
    params = {
        "language": "pt-br",
        "pageNumber": 1,
        "pageSize": 200,
        "index": "IFIX",
        "segment": "1"
    }
    
    results = []
    fonte = "b3_api"
    try:
        json_str = json.dumps(params)
        b64_str = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
        resp = requests.get(api_url_base + b64_str, verify=False, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for row in data.get("results", []):
            if ticker := row.get("cod"):
                # Clean up peso from string like "1,040"
                part_str = str(row.get("part", "0")).replace(".", "").replace(",", ".")
                peso = float(part_str)
                results.append({"ticker": ticker, "peso_ifix": peso})
    except Exception as e:
        logger.warning("Falha na API B3 ({}), usando fallback do CSV...", e)
        fonte = "csv_fallback"
        if not IFIX_CSV_PATH.exists():
            logger.error("Fallback CSV não existe!")
            return []
        with open(IFIX_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                peso = float(row.get("peso_ifix", "0"))
                results.append({"ticker": row["ticker"], "peso_ifix": peso, "cnpj_csv": row.get("cnpj")})
                
    # Lê mapeamento CSV atual
    csv_mapping = {}
    if IFIX_CSV_PATH.exists():
        with open(IFIX_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("cnpj"):
                    csv_mapping[r["ticker"]] = r["cnpj"]
                    
    # Resolve CNPJs
    now = datetime.now(timezone.utc)
    hoje = datetime.now().date()  # data local: a referencia e o dia do operador, nao o dia UTC
    novos_cnpjs = False
    
    out_list = []
    
    for item in results:
        ticker = item["ticker"]
        peso = item["peso_ifix"]
        cnpj = None
        
        # 1. DB: Ticker
        if not cnpj:
            cnpj = session.execute(select(Ticker.cnpj).where(Ticker.ticker == ticker)).scalar_one_or_none()
            
        # 2. DB: Universo
        if not cnpj:
            cnpj = session.execute(
                select(Universo.cnpj)
                .where(Universo.ticker == ticker)
                .order_by(Universo.atualizado_em.desc())
                .limit(1)
            ).scalar_one_or_none()
            
        # 3. CSV
        if not cnpj:
            cnpj = csv_mapping.get(ticker)
            
        # 4. StatusInvest (crawler)
        if not cnpj:
            logger.info("Resolvendo CNPJ para {} via StatusInvest...", ticker)
            url = f"https://statusinvest.com.br/fundos-imobiliarios/{ticker.lower()}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            try:
                r_si = requests.get(url, headers=headers, timeout=10)
                if r_si.status_code == 200:
                    match = re.search(r'CNPJ</h3>\s*<strong[^>]*>([\d\.\/\-]+)</strong>', r_si.text)
                    if match:
                        cnpj = match.group(1)
                        logger.info("Encontrado: {}", cnpj)
                        csv_mapping[ticker] = cnpj
                        novos_cnpjs = True
            except Exception as e:
                logger.error("Falha ao raspar StatusInvest para {}: {}", ticker, e)
                
        if cnpj:
            out_list.append({"ticker": ticker, "cnpj": cnpj, "peso_ifix": peso})
            
            # Persiste no DB (Universo)
            universo = Universo(
                ticker=ticker,
                cnpj=cnpj,
                em_ifix=True,
                peso_ifix=peso,
                data_referencia=hoje,
                fonte=fonte,
                atualizado_em=now
            )
            session.merge(universo)
        else:
            logger.warning("Ticker {} sem CNPJ resolvido, pulando.", ticker)
            
    session.commit()
    
    # Self-healing do CSV — preserva mapeamentos antigos (ticker→cnpj) que não
    # vieram neste pull: o CSV é o fallback de resolução de CNPJ e perder
    # entradas tornaria falhas futuras da B3/StatusInvest mais custosas.
    if novos_cnpjs or fonte == "b3_api":
        finais = {r["ticker"]: dict(r) for r in out_list}
        for tkr, cnpj_antigo in csv_mapping.items():
            if tkr not in finais:
                finais[tkr] = {"ticker": tkr, "cnpj": cnpj_antigo, "peso_ifix": 0.0}
        with open(IFIX_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ticker", "cnpj", "peso_ifix"])
            writer.writeheader()
            for r in sorted(finais.values(), key=lambda x: x["ticker"]):
                writer.writerow({"ticker": r["ticker"], "cnpj": r["cnpj"], "peso_ifix": r["peso_ifix"]})

    return out_list
