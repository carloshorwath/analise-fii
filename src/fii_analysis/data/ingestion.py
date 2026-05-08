from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from pathlib import Path
from zipfile import ZipFile

import os
import requests
import pandas as pd
import pandas_market_calendars as mcal
import yfinance as yf
from dotenv import load_dotenv
from loguru import logger

load_dotenv(r"C:\Modelos-AI\Brapi\.env")
_b3 = mcal.get_calendar("B3")


def _ex_to_data_com(ex_date: date) -> date:
    """Converte ex-date (yfinance) para data-com (B3): 1 pregão antes, respeitando feriados."""
    start = pd.Timestamp(ex_date) - pd.Timedelta(days=10)
    schedule = _b3.schedule(start_date=start, end_date=pd.Timestamp(ex_date))
    pregoes = schedule.index.date.tolist()
    if not pregoes or pregoes[-1] != ex_date:
        # ex_date não é pregão — retroceder até encontrar o pregão anterior
        pregoes = [d for d in pregoes if d < ex_date]
        return pregoes[-1] if pregoes else ex_date
    return pregoes[-2] if len(pregoes) >= 2 else ex_date
from sqlalchemy import select

from src.fii_analysis.data.database import (
    AtivoPassivo,
    BenchmarkDiario,
    CdiDiario,
    Dividendo,
    PrecoDiario,
    RelatorioMensal,
    Ticker,
)


def load_cvm_zip(
    zip_path: Path,
    year: int,
    keys_to_extract: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    logger.info("Abrindo ZIP {}", zip_path)
    prefixos = {
        "complemento": f"inf_mensal_fii_complemento_{year}",
        "geral": f"inf_mensal_fii_geral_{year}",
        "ativo_passivo": f"inf_mensal_fii_ativo_passivo_{year}",
    }
    resultado = {}
    with ZipFile(zip_path) as zf:
        nomes_no_zip = zf.namelist()
        for chave, prefixo in prefixos.items():
            if keys_to_extract is not None and chave not in keys_to_extract:
                continue
            match = [n for n in nomes_no_zip if n.startswith(prefixo) and n.endswith(".csv")]
            if not match:
                logger.warning("Arquivo {} nao encontrado em {}", prefixo, zip_path)
                resultado[chave] = pd.DataFrame()
                continue
            nome_arquivo = match[0]
            logger.info("Lendo {}", nome_arquivo)
            with zf.open(nome_arquivo) as f:
                df = pd.read_csv(f, sep=";", encoding="latin1", low_memory=False)
            resultado[chave] = df
    return resultado


def load_cvm_to_db(zip_path: Path, year: int, session) -> None:
    dados = load_cvm_zip(zip_path, year, keys_to_extract=["complemento", "geral"])
    complemento = dados["complemento"]
    geral = dados["geral"]
    if complemento.empty:
        logger.warning("Complemento vazio para {}, ano {}", zip_path, year)
        return

    cnpts_monitorados = set(session.scalars(select(Ticker.cnpj)).all())
    if not cnpts_monitorados:
        logger.warning("Nenhum ticker cadastrado na tabela tickers")
        return

    col_cnpj_comp = "CNPJ_Fundo_Classe" if "CNPJ_Fundo_Classe" in complemento.columns else "CNPJ_Fundo"
    complemento = complemento[complemento[col_cnpj_comp].isin(cnpts_monitorados)]
    if complemento.empty:
        logger.info("Nenhum registro para FIIs monitorados no complemento")
        return

    col_cnpj_geral = "CNPJ_Fundo_Classe" if "CNPJ_Fundo_Classe" in geral.columns else "CNPJ_Fundo"
    col_data_ref = "Data_Referencia"
    col_data_entrega = "Data_Entrega"
    geral_filtrado = geral[geral[col_cnpj_geral].isin(cnpts_monitorados)][
        [col_cnpj_geral, col_data_ref, col_data_entrega]
    ].copy()
    geral_filtrado[col_data_ref] = pd.to_datetime(geral_filtrado[col_data_ref]).dt.date
    geral_filtrado[col_data_entrega] = pd.to_datetime(geral_filtrado[col_data_entrega]).dt.date
    entrega_map = geral_filtrado.set_index([col_cnpj_geral, col_data_ref])[col_data_entrega].to_dict()

    complemento = complemento.copy()
    complemento[col_data_ref] = pd.to_datetime(complemento[col_data_ref]).dt.date
    inseridos = 0
    ignorados = 0
    for _, row in complemento.iterrows():
        cnpj = row[col_cnpj_comp]
        data_ref = row[col_data_ref]
        data_entrega = entrega_map.get((cnpj, data_ref))
        exists = session.execute(
            select(RelatorioMensal).where(
                RelatorioMensal.cnpj == cnpj,
                RelatorioMensal.data_referencia == data_ref,
            )
        ).scalar_one_or_none()
        if exists:
            # UPSERT: atualiza data_entrega se a nova for diferente (ex: republicação antecipada)
            if data_entrega is not None and exists.data_entrega != data_entrega:
                exists.data_entrega = data_entrega
                session.flush()
            ignorados += 1
            continue
        registro = RelatorioMensal(
            cnpj=cnpj,
            data_referencia=data_ref,
            data_entrega=data_entrega,
            vp_por_cota=row.get("Valor_Patrimonial_Cotas"),
            patrimonio_liq=row.get("Patrimonio_Liquido"),
            cotas_emitidas=row.get("Cotas_Emitidas"),
            dy_mes_pct=row.get("Percentual_Dividend_Yield_Mes"),
            rentab_efetiva=row.get("Percentual_Rentabilidade_Efetiva_Mes"),
            rentab_patrim=row.get("Percentual_Rentabilidade_Patrimonial_Mes"),
        )
        session.add(registro)
        inseridos += 1
    session.commit()
    logger.info("CVM {}: {} inseridos, {} ja existiam (ignorados)", year, inseridos, ignorados)


def load_prices_yfinance(ticker: str, session) -> None:
    ultimo = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()

    symbol = f"{ticker}.SA"
    if ultimo:
        start = ultimo + timedelta(days=1)
        logger.info("{}: buscando a partir de {}", ticker, start)
    else:
        start = None
        logger.info("{}: buscando historico completo", ticker)

    yf_ticker = yf.Ticker(symbol)
    if start:
        hist = yf_ticker.history(start=start, auto_adjust=False)
    else:
        hist = yf_ticker.history(period="max", auto_adjust=False)
    if hist.empty:
        logger.info("{}: nenhum dado novo", ticker)
        return

    agora = datetime.now()
    inseridos = 0
    for dt_idx, row in hist.iterrows():
        d = dt_idx.date()
        exists = session.execute(
            select(PrecoDiario).where(
                PrecoDiario.ticker == ticker,
                PrecoDiario.data == d,
            )
        ).scalar_one_or_none()
        if exists:
            continue
        registro = PrecoDiario(
            ticker=ticker,
            data=d,
            abertura=row.get("Open"),
            maxima=row.get("High"),
            minima=row.get("Low"),
            fechamento=row.get("Close"),
            fechamento_aj=row.get("Adj Close"),
            volume=row.get("Volume"),
            fonte="yfinance",
            coletado_em=agora,
        )
        session.add(registro)
        inseridos += 1
    session.commit()
    logger.info("{}: {} precos inseridos", ticker, inseridos)


def load_dividends_yfinance(ticker: str, session) -> None:
    symbol = f"{ticker}.SA"
    yf_ticker = yf.Ticker(symbol)
    divs = yf_ticker.dividends
    if divs.empty:
        logger.info("{}: nenhum dividendo encontrado", ticker)
        return

    hoje = date.today()
    divs = divs[divs.index.date <= hoje]
    if divs.empty:
        logger.info("{}: nenhum dividendo passado", ticker)
        return

    inseridos = 0
    for dt_idx, valor in divs.items():
        # yfinance retorna ex-date; data-com na B3 é sempre 1 pregão antes (calendário B3)
        ex_date = dt_idx.date()
        d = _ex_to_data_com(ex_date)
        exists = session.execute(
            select(Dividendo).where(
                Dividendo.ticker == ticker,
                Dividendo.data_com == d,
            )
        ).scalar_one_or_none()
        if exists:
            continue
        registro = Dividendo(
            ticker=ticker,
            data_com=d,
            valor_cota=valor,
            fonte="yfinance",
        )
        session.add(registro)
        inseridos += 1
    session.commit()
    logger.info("{}: {} dividendos inseridos", ticker, inseridos)


def load_ativo_passivo_to_db(zip_path: Path, year: int, session) -> None:
    dados = load_cvm_zip(zip_path, year, keys_to_extract=["ativo_passivo", "geral"])
    ap = dados.get("ativo_passivo")
    if ap is None or ap.empty:
        logger.warning("ativo_passivo vazio para {}, ano {}", zip_path, year)
        return

    cnpts_monitorados = set(session.scalars(select(Ticker.cnpj)).all())
    if not cnpts_monitorados:
        logger.warning("Nenhum ticker cadastrado na tabela tickers")
        return

    col_cnpj = "CNPJ_Fundo_Classe" if "CNPJ_Fundo_Classe" in ap.columns else "CNPJ_Fundo"
    ap = ap[ap[col_cnpj].isin(cnpts_monitorados)].copy()
    if ap.empty:
        logger.info("Nenhum registro para FIIs monitorados no ativo_passivo")
        return

    geral = dados.get("geral", pd.DataFrame())
    entrega_map: dict[tuple[str, object], object] = {}
    if not geral.empty:
        col_cnpj_geral = "CNPJ_Fundo_Classe" if "CNPJ_Fundo_Classe" in geral.columns else "CNPJ_Fundo"
        geral_f = geral[geral[col_cnpj_geral].isin(cnpts_monitorados)][
            [col_cnpj_geral, "Data_Referencia", "Data_Entrega"]
        ].copy()
        geral_f["Data_Referencia"] = pd.to_datetime(geral_f["Data_Referencia"]).dt.date
        geral_f["Data_Entrega"] = pd.to_datetime(geral_f["Data_Entrega"]).dt.date
        entrega_map = geral_f.set_index([col_cnpj_geral, "Data_Referencia"])["Data_Entrega"].to_dict()

    ap["Data_Referencia"] = pd.to_datetime(ap["Data_Referencia"]).dt.date

    # A CVM não expõe coluna Total_Ativo no arquivo ativo_passivo.
    # Ativo total é calculado somando os componentes relevantes.
    # Direitos_Bens_Imoveis é o principal componente para FIIs de tijolo e
    # deve ser incluído — estava ausente na versão anterior (bug).
    ativo_cols_for_total = [
        "Direitos_Bens_Imoveis",
        "Total_Investido",
        "Total_Necessidades_Liquidez",
        "Valores_Receber",
        "Outros_Valores_Mobliarios",
        "Outros_Direitos_Reais",
        "Outros_Valores_Receber",
        "Contas_Receber_Aluguel",
        "Contas_Receber_Venda_Imoveis",
    ]

    inseridos = 0
    ignorados = 0
    for _, row in ap.iterrows():
        cnpj = row[col_cnpj]
        data_ref = row["Data_Referencia"]
        exists = session.execute(
            select(AtivoPassivo).where(
                AtivoPassivo.cnpj == cnpj,
                AtivoPassivo.data_referencia == data_ref,
            )
        ).scalar_one_or_none()
        if exists:
            ignorados += 1
            continue

        data_entrega = entrega_map.get((cnpj, data_ref))

        def _safe_float(val):
            if val is None:
                return None
            try:
                f = float(val)
                return f if pd.notna(f) else None
            except (ValueError, TypeError):
                return None

        ativo_total = 0.0
        for col in ativo_cols_for_total:
            if col in row.index:
                v = _safe_float(row[col])
                if v is not None:
                    ativo_total += v

        registro = AtivoPassivo(
            cnpj=cnpj,
            data_referencia=data_ref,
            data_entrega=data_entrega,
            direitos_bens_imoveis=_safe_float(row.get("Direitos_Bens_Imoveis")),
            cri=_safe_float(row.get("CRI")),
            cri_cra=_safe_float(row.get("CRI_CRA")),
            lci=_safe_float(row.get("LCI")),
            lci_lca=_safe_float(row.get("LCI_LCA")),
            disponibilidades=_safe_float(row.get("Disponibilidades")),
            total_investido=_safe_float(row.get("Total_Investido")),
            total_necessidades_liquidez=_safe_float(row.get("Total_Necessidades_Liquidez")),
            valores_receber=_safe_float(row.get("Valores_Receber")),
            contas_receber_aluguel=_safe_float(row.get("Contas_Receber_Aluguel")),
            outros_valores_mobliarios=_safe_float(row.get("Outros_Valores_Mobliarios")),
            ativo_total=ativo_total if ativo_total > 0 else None,
        )
        session.add(registro)
        inseridos += 1
    session.commit()
    logger.info("ativo_passivo {}: {} inseridos, {} ja existiam", year, inseridos, ignorados)


# ---------------------------------------------------------------------------
# CDI diário — BCB SGS série 12
# ---------------------------------------------------------------------------

_BCB_CDI_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"


def load_cdi_to_db(session, data_inicio: date | None = None) -> None:
    """Carrega CDI diário do BCB (série 12) para a tabela cdi_diario.

    Faz carga incremental: se data_inicio for None, baixa desde o último
    registro no banco; se o banco estiver vazio, baixa desde 2014-01-01.
    O BCB SGS limita requisições diárias a 10 anos; esta função divide
    automaticamente em chunks de 5 anos.
    """
    ultimo = session.execute(
        select(CdiDiario.data).order_by(CdiDiario.data.desc()).limit(1)
    ).scalar_one_or_none()

    if data_inicio is None:
        if ultimo:
            data_inicio = ultimo + timedelta(days=1)
        else:
            # CPTS11 data starts 2015-09; DY Gap needs 12m CDI history,
            # so load from 2014-01-01 to cover all tickers.
            data_inicio = date(2014, 1, 1)

    if data_inicio > date.today():
        logger.info("CDI ja atualizado ate hoje")
        return

    # BCB SGS limits daily series queries to 10 years.
    # Use 5-year chunks for safety.
    hoje = date.today()
    total_inseridos = 0
    chunk_start = data_inicio

    while chunk_start <= hoje:
        chunk_end = min(chunk_start + relativedelta(years=5), hoje)
        url = (
            f"{_BCB_CDI_URL}"
            f"&dataInicial={chunk_start.strftime('%d/%m/%Y')}"
            f"&dataFinal={chunk_end.strftime('%d/%m/%Y')}"
        )
        logger.info("Baixando CDI de {} ate {} via BCB", chunk_start, chunk_end)
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            dados = resp.json()
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.warning("Sem dados CDI (404) para chunk {}-{}. Pulando.", chunk_start, chunk_end)
                chunk_start = chunk_end + timedelta(days=1)
                continue
            logger.warning("BCB falhou para chunk {}-{} ({}). Parando backfill.", chunk_start, chunk_end, exc)
            break
        except Exception as exc:
            logger.warning("BCB falhou para chunk {}-{} ({}). Parando backfill.", chunk_start, chunk_end, exc)
            break

        agora = datetime.now()
        inseridos = 0
        for item in dados:
            d = datetime.strptime(item["data"], "%d/%m/%Y").date()
            taxa = float(item["valor"])
            exists = session.execute(
                select(CdiDiario).where(CdiDiario.data == d)
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(CdiDiario(data=d, taxa_diaria_pct=taxa, coletado_em=agora))
            inseridos += 1

        session.commit()
        total_inseridos += inseridos
        chunk_start = chunk_end + timedelta(days=1)

    logger.info("CDI: {} registros inseridos no total", total_inseridos)


def _load_cdi_yfinance_fallback(session, data_inicio: date) -> None:
    """Fallback: yfinance nao oferece CDI diretamente, mas loga aviso claro."""
    logger.warning("yfinance nao possui CDI brasileiro. Execute novamente quando BCB estiver acessivel.")
    logger.info("Fonte primaria: BCB SGS serie 12 ({})", _BCB_CDI_URL)


# Wrapper: mantém compatibilidade com scripts que importam de ingestion.
# A implementação real vive em data/cdi.py (sem dependência de yfinance).
from src.fii_analysis.data.cdi import get_cdi_acumulado_12m  # noqa: F401 re-export


def load_ifix_to_db(session, anos: int = 5) -> int:
    """Carrega historico do IFIX11 ETF no banco via brapi.dev.
    yfinance nao tem ^IFIX nem IFIX11.SA — brapi e a unica fonte confiavel.
    Armazena com ticker='IFIX11' em PrecoDiario.
    Respeita a regra do projeto: verifica ultimo registro antes de baixar.
    Retorna numero de registros inseridos.
    """
    ticker_banco = "IFIX11"

    ultimo = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker_banco)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()

    hoje = date.today()
    if ultimo:
        start_date = ultimo + timedelta(days=1)
        logger.info("IFIX: buscando a partir de {}", start_date)
    else:
        start_date = hoje - timedelta(days=anos * 365)
        logger.info("IFIX: buscando historico completo ({} anos) a partir de {}", anos, start_date)

    if start_date > hoje:
        logger.info("IFIX ja atualizado ate hoje")
        return 0

    load_dotenv(r"C:\Modelos-AI\Brapi\.env")
    token = os.getenv("BRAPI_API_KEY")
    if not token:
        logger.warning("BRAPI_API_KEY nao encontrado. Momentum IFIX indisponivel.")
        return 0

    # incremental usa 5d; carga inicial usa max (IFIX11 nao tem 5 anos completos)
    brapi_range = "5d" if ultimo else "max"
    url = f"https://brapi.dev/api/quote/IFIX11?range={brapi_range}&interval=1d&history=true&token={token}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        dados = resp.json()
        results = dados.get("results", [])
        if not results:
            logger.warning("Brapi IFIX11: sem resultados (range={})", brapi_range)
            return 0
        hist = results[0].get("historicalDataPrice", [])
        if not hist:
            logger.warning("Brapi IFIX11: historicalDataPrice vazio — verifique plano/token")
            return 0
    except Exception as exc:
        logger.warning("Brapi IFIX11 falhou: {}. Momentum IFIX indisponivel.", exc)
        return 0

    for item in hist:
        ts = item.get("date")
        if ts is None:
            continue
        d = datetime.utcfromtimestamp(ts).date()
        if start_date and d < start_date:
            continue
        if ultimo and d <= ultimo:
            continue

        exists = session.execute(
            select(PrecoDiario).where(
                PrecoDiario.ticker == ticker_banco,
                PrecoDiario.data == d,
            )
        ).scalar_one_or_none()
        if exists:
            continue

        fech = item.get("close") or item.get("adjustedClose")
        if fech is None:
            continue

        registro = PrecoDiario(
            ticker=ticker_banco,
            data=d,
            abertura=item.get("open"),
            maxima=item.get("high"),
            minima=item.get("low"),
            fechamento=fech,
            fechamento_aj=item.get("adjustedClose") or fech,
            volume=item.get("volume"),
            fonte="brapi_ifix11",
            coletado_em=agora,
        )
        session.add(registro)
        inseridos += 1

    session.commit()
    logger.info("IFIX: {} precos inseridos via Brapi", inseridos)
    return inseridos


# ---------------------------------------------------------------------------
# Benchmark diário — IFIX via yfinance (carga inicial) + brapi (atualização)
# ---------------------------------------------------------------------------

def load_benchmark_yfinance(ticker: str, session) -> None:
    """Carga inicial / histórica do benchmark via yfinance."""
    ultimo = session.execute(
        select(BenchmarkDiario.data)
        .where(BenchmarkDiario.ticker == ticker)
        .order_by(BenchmarkDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()

    symbol = ticker if "." in ticker else f"{ticker}.SA"
    yf_ticker = yf.Ticker(symbol)
    if ultimo:
        start = ultimo + timedelta(days=1)
        logger.info("Benchmark {}: buscando a partir de {}", ticker, start)
        hist = yf_ticker.history(start=start, auto_adjust=False)
    else:
        logger.info("Benchmark {}: buscando historico completo", ticker)
        hist = yf_ticker.history(period="max", auto_adjust=False)

    if hist.empty:
        logger.info("Benchmark {}: nenhum dado novo", ticker)
        return

    agora = datetime.now()
    inseridos = 0
    for dt_idx, row in hist.iterrows():
        d = dt_idx.date()
        exists = session.execute(
            select(BenchmarkDiario).where(
                BenchmarkDiario.ticker == ticker,
                BenchmarkDiario.data == d,
            )
        ).scalar_one_or_none()
        if exists:
            continue
        fech = row.get("Close")
        session.add(BenchmarkDiario(
            ticker=ticker,
            data=d,
            fechamento=float(fech) if fech is not None else None,
            coletado_em=agora,
        ))
        inseridos += 1
    session.commit()
    logger.info("Benchmark {}: {} registros inseridos", ticker, inseridos)


def load_benchmark_brapi(ticker: str, session) -> None:
    """Atualização diária do benchmark via brapi. Ticker: 'IFIX.SA'.
    Usa apenas os dados do dia (range=1d) para complementar yfinance.
    Se brapi falhar, loga warning e retorna sem errar.
    """
    token = os.getenv("BRAPI_API_KEY")
    if not token:
        logger.warning("BRAPI_API_KEY nao encontrado; pulando atualizacao brapi do benchmark")
        return

    ultimo = session.execute(
        select(BenchmarkDiario.data)
        .where(BenchmarkDiario.ticker == ticker)
        .order_by(BenchmarkDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()

    url = f"https://brapi.dev/api/quote/{ticker}?token={token}&range=1d&interval=1d"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        dados = resp.json()
        results = dados.get("results", [])
        if not results:
            logger.warning("Benchmark brapi {}: sem resultados", ticker)
            return
        hist = results[0].get("historicalDataPrice", [])
    except Exception as exc:
        logger.warning("Benchmark brapi {} falhou: {}. Usando apenas yfinance.", ticker, exc)
        return

    agora = datetime.now()
    inseridos = 0
    for item in hist:
        ts = item.get("date")
        if ts is None:
            continue
        d = datetime.utcfromtimestamp(ts).date()
        if ultimo and d <= ultimo:
            continue
        exists = session.execute(
            select(BenchmarkDiario).where(
                BenchmarkDiario.ticker == ticker,
                BenchmarkDiario.data == d,
            )
        ).scalar_one_or_none()
        if exists:
            continue
        fech = item.get("close") or item.get("adjustedClose")
        session.add(BenchmarkDiario(
            ticker=ticker,
            data=d,
            fechamento=float(fech) if fech is not None else None,
            coletado_em=agora,
        ))
        inseridos += 1
    session.commit()
    logger.info("Benchmark brapi {}: {} registros inseridos", ticker, inseridos)
