import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from loguru import logger

TICKERS = ["HSRE11", "GARE11", "CPSH11", "CPTS11", "KNIP11"]
BASE_URL = "https://www.fundsexplorer.com.br/funds/{ticker}"
OUTPUT = Path(__file__).resolve().parents[1] / "dados" / "validacao_fundsexplorer.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def parse_br_float(val: str) -> float | None:
    if not val or val.strip() in ("-", "", "N/A"):
        return None
    cleaned = val.strip().replace("R$", "").replace("%", "").replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_br_date(val: str) -> str | None:
    if not val or val.strip() in ("-", "", "N/A"):
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_json_dividends(text: str, ticker: str) -> list[dict]:
    pattern = re.compile(
        r'"(earnings|dividends|dividendsHistory|rendimentos)"\s*:\s*(\[.*?\])',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        try:
            import json

            data = json.loads(match.group(2))
            if isinstance(data, list) and len(data) > 0:
                logger.info("{}: achou JSON com {} registros em '{}'", ticker, len(data), match.group(1))
                return data
        except (json.JSONDecodeError, ValueError):
            continue
    return []


def parse_json_records(records: list[dict], ticker: str) -> list[dict]:
    rows = []
    for rec in records:
        row = {
            "ticker": ticker,
            "data_com": None,
            "data_pagamento": None,
            "cotacao_base": None,
            "rendimento": None,
            "dy_pct": None,
        }
        for k, v in rec.items():
            k_lower = k.lower()
            if "com" in k_lower and "data" in k_lower:
                row["data_com"] = parse_br_date(str(v))
            elif "pag" in k_lower and "data" in k_lower:
                row["data_pagamento"] = parse_br_date(str(v))
            elif "cotacao" in k_lower or "base" in k_lower or "price" in k_lower:
                row["cotacao_base"] = parse_br_float(str(v))
            elif "rendimento" in k_lower or "dividend" in k_lower or "value" in k_lower:
                if "percent" in k_lower or "yield" in k_lower or "%" in str(v):
                    row["dy_pct"] = parse_br_float(str(v))
                else:
                    row["rendimento"] = parse_br_float(str(v))
            elif "yield" in k_lower or "dy" in k_lower:
                row["dy_pct"] = parse_br_float(str(v))
        rows.append(row)
    return rows


def extract_table_dividends(soup: BeautifulSoup, ticker: str) -> list[dict]:
    table = None
    for selector in [
        ("id", "dividends-table"),
        ("id", "earnings-table"),
        ("id", "table-dividends"),
        ("class", "dividends"),
        ("class", "earnings"),
        ("class", "table-rendimentos"),
    ]:
        attr, val = selector
        if attr == "id":
            table = soup.find("table", {"id": val})
        else:
            table = soup.find("table", class_=val)
        if table:
            break

    if not table:
        tables = soup.find_all("table")
        for t in tables:
            header_text = t.get_text(separator=" ").lower()
            if any(kw in header_text for kw in ["rendimento", "dividendo", "data com", "data base"]):
                table = t
                break

    if not table:
        return []

    header_row = table.find("tr")
    if not header_row:
        return []
    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    col_map = {}
    for i, h in enumerate(headers):
        if "com" in h or "base" in h:
            col_map["data_com"] = i
        elif "pag" in h or "receb" in h:
            col_map["data_pagamento"] = i
        elif "cot" in h or "pre" in h or "cota" in h:
            col_map["cotacao_base"] = i
        elif "rendimento" in h and "yield" not in h and "%" not in h:
            col_map["rendimento"] = i
        elif "yield" in h or "dy" in h or "%" in h:
            col_map["dy_pct"] = i

    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all(["td"])
        if len(cells) < 3:
            continue
        cell_texts = [c.get_text(strip=True) for c in cells]
        row = {
            "ticker": ticker,
            "data_com": None,
            "data_pagamento": None,
            "cotacao_base": None,
            "rendimento": None,
            "dy_pct": None,
        }
        for field, idx in col_map.items():
            if idx < len(cell_texts):
                if field.startswith("data"):
                    row[field] = parse_br_date(cell_texts[idx])
                else:
                    row[field] = parse_br_float(cell_texts[idx])
        rows.append(row)
    return rows


def scrape_ticker(ticker: str) -> list[dict]:
    url = BASE_URL.format(ticker=ticker)
    logger.info("{}: GET {}", ticker, url)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    json_records = extract_json_dividends(resp.text, ticker)
    if json_records:
        rows = parse_json_records(json_records, ticker)
        if rows:
            return rows

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = extract_table_dividends(soup, ticker)
    if rows:
        logger.info("{}: extraiu {} linhas da tabela HTML", ticker, len(rows))
        return rows

    logger.warning("{}: nenhum dado de dividendo encontrado", ticker)
    return []


def main():
    logger.info("=== scrape_fundsexplorer.py ===")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for ticker in TICKERS:
        try:
            rows = scrape_ticker(ticker)
            all_rows.extend(rows)
            logger.info("{}: {} linhas coletadas", ticker, len(rows))
        except Exception as e:
            logger.error("{}: {}", ticker, e)

    if not all_rows:
        logger.warning("Nenhum dado coletado. CSV nao gerado.")
        return

    df = pd.DataFrame(all_rows, columns=["ticker", "data_com", "data_pagamento", "cotacao_base", "rendimento", "dy_pct"])
    df.to_csv(OUTPUT, index=False)
    logger.info("CSV salvo em {} ({} linhas)", OUTPUT, len(df))

    logger.info("--- Resumo por ticker ---")
    for ticker in TICKERS:
        n = len(df[df["ticker"] == ticker])
        logger.info("  {}: {} linhas", ticker, n)


if __name__ == "__main__":
    main()
