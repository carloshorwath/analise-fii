import pandas as pd
import numpy as np
from datetime import date
from sqlalchemy import select
from scipy import stats

from src.fii_analysis.data.database import PrecoDiario, RelatorioMensal, CdiDiario, get_cnpj_by_ticker, get_session_ctx
from src.fii_analysis.features.valuation import get_pvp_percentil, get_dy_gap_percentil
from src.fii_analysis.features.indicators import get_pvp, get_pvp_serie, get_dy_serie
from src.fii_analysis.config_yaml import get as config_get

def get_sinais_config():
    return config_get("sinais", {})

def get_meses_alerta_em_t(ticker: str, t: date, session) -> int:
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return 0

    rows = session.execute(
        select(
            RelatorioMensal.rentab_efetiva,
            RelatorioMensal.rentab_patrim,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.rentab_efetiva.isnot(None),
            RelatorioMensal.rentab_patrim.isnot(None),
            RelatorioMensal.data_entrega <= t,
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(12)
    ).all()

    if not rows:
        return 0

    consec = 0
    for r in rows:
        ef = float(r.rentab_efetiva)
        pa = float(r.rentab_patrim)
        # Alerta se patrimonial > efetiva (distribuindo mais que gera)
        if pa > ef:
            consec += 1
        else:
            break
    return consec

def is_dist_maior_geracao_em_t(ticker: str, t: date, session) -> bool:
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return False

    r = session.execute(
        select(
            RelatorioMensal.rentab_efetiva,
            RelatorioMensal.rentab_patrim,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.rentab_efetiva.isnot(None),
            RelatorioMensal.rentab_patrim.isnot(None),
            RelatorioMensal.data_entrega <= t,
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(1)
    ).first()

    if not r:
        return False

    return float(r.rentab_patrim) > float(r.rentab_efetiva)

def _avaliar_score_core(pvp, pvp_pct, dy_gap_pct, meses_alerta, dist_maior, buy_rules, sell_rules, cfg):
    score = 0
    condicoes = {}

    # Buy conditions
    if "pvp_percentil_max" in buy_rules:
        met = pvp_pct is not None and not np.isnan(pvp_pct) and pvp_pct <= buy_rules["pvp_percentil_max"]
        condicoes["buy_pvp_percentil_max"] = met
        if met: score += 1
    
    if "dy_gap_percentil_min" in buy_rules:
        met = dy_gap_pct is not None and not np.isnan(dy_gap_pct) and dy_gap_pct >= buy_rules["dy_gap_percentil_min"]
        condicoes["buy_dy_gap_percentil_min"] = met
        if met: score += 1

    if "meses_alerta_max" in buy_rules:
        met = meses_alerta is not None and meses_alerta <= buy_rules["meses_alerta_max"]
        condicoes["buy_meses_alerta_max"] = met
        if met: score += 1

    if "pvp_max" in buy_rules:
        met = pvp is not None and not np.isnan(pvp) and pvp <= buy_rules["pvp_max"]
        condicoes["buy_pvp_max"] = met
        if met: score += 1

    # Sell conditions
    if "pvp_percentil_min" in sell_rules:
        met = pvp_pct is not None and not np.isnan(pvp_pct) and pvp_pct >= sell_rules["pvp_percentil_min"]
        condicoes["sell_pvp_percentil_min"] = met
        if met: score -= 1

    if "dist_maior_geracao" in sell_rules:
        met = dist_maior == sell_rules["dist_maior_geracao"]
        condicoes["sell_dist_maior_geracao"] = met
        if met: score -= 1

    if "meses_alerta_min" in sell_rules:
        met = meses_alerta is not None and meses_alerta >= sell_rules["meses_alerta_min"]
        condicoes["sell_meses_alerta_min"] = met
        if met: score -= 1
        
    if "pvp_min" in sell_rules:
        met = pvp is not None and not np.isnan(pvp) and pvp >= sell_rules["pvp_min"]
        condicoes["sell_pvp_min"] = met
        if met: score -= 1

    sinal = "NEUTRO"
    if score >= cfg.get("score_buy_threshold", 2):
        sinal = "COMPRA"
    elif score <= cfg.get("score_sell_threshold", -2):
        sinal = "VENDA"

    return score, sinal, condicoes

def calcular_score_ticker(ticker, data, session):
    cfg = get_sinais_config()
    tickers_cfg = cfg.get("tickers", {})
    if ticker not in tickers_cfg:
        return {"score": 0, "condicoes": {}, "sinal": "NEUTRO", "valores": {}}

    rules = tickers_cfg[ticker]
    buy_rules = rules.get("buy", {})
    sell_rules = rules.get("sell", {})

    # Fetch point-in-time indicators
    pvp = get_pvp(ticker, data, session)
    pvp_pct, _ = get_pvp_percentil(ticker, data, session=session)
    dy_gap_pct = get_dy_gap_percentil(ticker, data, session=session)
    meses_alerta = get_meses_alerta_em_t(ticker, data, session)
    dist_maior = is_dist_maior_geracao_em_t(ticker, data, session)

    score, sinal, condicoes = _avaliar_score_core(
        pvp, pvp_pct, dy_gap_pct, meses_alerta, dist_maior,
        buy_rules, sell_rules, cfg
    )

    return {
        "score": score, 
        "condicoes": condicoes, 
        "sinal": sinal, 
        "valores": {
            "pvp": pvp, 
            "pvp_pct": pvp_pct, 
            "dy_gap_pct": dy_gap_pct, 
            "meses_alerta": meses_alerta, 
            "dist_maior": dist_maior
        }
    }

def gerar_historico_sinais(ticker, session):
    """
    Gera DataFrame com histórico de scores e sinais usando processamento em bulk (vetorizado).
    """
    cfg = get_sinais_config()
    tickers_cfg = cfg.get("tickers", {})
    if ticker not in tickers_cfg:
        return pd.DataFrame()

    # 1. PVP Serie (contém data, fechamento, vp_por_cota, pvp)
    df = get_pvp_serie(ticker, session)
    if df.empty:
        return df
    
    # 2. Relatorios Mensais (meses_alerta, dist_maior)
    cnpj = get_cnpj_by_ticker(ticker, session)
    rel_rows = session.execute(
        select(RelatorioMensal.data_entrega, RelatorioMensal.rentab_efetiva, RelatorioMensal.rentab_patrim)
        .where(RelatorioMensal.cnpj == cnpj)
        .order_by(RelatorioMensal.data_entrega.asc())
    ).all()
    
    if rel_rows:
        df_rel = pd.DataFrame(rel_rows)
        df_rel['alerta'] = (df_rel['rentab_patrim'].astype(float) > df_rel['rentab_efetiva'].astype(float)).astype(int)
        df_rel['meses_alerta_rel'] = df_rel['alerta'].rolling(window=12, min_periods=1).sum()
        df_rel['dist_maior_rel'] = df_rel['rentab_patrim'].astype(float) > df_rel['rentab_efetiva'].astype(float)
        
        df['data_dt'] = pd.to_datetime(df['data'])
        df_rel['data_entrega_dt'] = pd.to_datetime(df_rel['data_entrega'])
        
        df = pd.merge_asof(
            df.sort_values('data_dt'),
            df_rel[['data_entrega_dt', 'meses_alerta_rel', 'dist_maior_rel']].sort_values('data_entrega_dt'),
            left_on='data_dt',
            right_on='data_entrega_dt',
            direction='backward'
        )
        df.rename(columns={'meses_alerta_rel': 'meses_alerta', 'dist_maior_rel': 'dist_maior'}, inplace=True)
    else:
        df['meses_alerta'] = 0
        df['dist_maior'] = False

    # 3. DY Gap
    df_dy = get_dy_serie(ticker, session)
    df = pd.merge(df, df_dy[['data', 'dy']], on='data', how='left')
    
    cdi_rows = session.execute(
        select(CdiDiario.data, CdiDiario.taxa_diaria_pct)
        .order_by(CdiDiario.data.asc())
    ).all()
    if cdi_rows:
        df_cdi = pd.DataFrame(cdi_rows)
        df_cdi['data_dt'] = pd.to_datetime(df_cdi['data'])
        df_cdi['taxa'] = 1.0 + df_cdi['taxa_diaria_pct'].astype(float) / 100.0
        df_cdi['cumprod'] = df_cdi['taxa'].cumprod()
        
        df_cdi['data_minus_12m'] = df_cdi['data_dt'] - pd.DateOffset(years=1)
        df_cdi_past = df_cdi[['data_dt', 'cumprod']].rename(columns={'data_dt': 'data_past', 'cumprod': 'cumprod_past'})
        
        df_cdi = pd.merge_asof(
            df_cdi.sort_values('data_minus_12m'),
            df_cdi_past.sort_values('data_past'),
            left_on='data_minus_12m',
            right_on='data_past',
            direction='backward'
        )
        df_cdi['cdi_12m'] = df_cdi['cumprod'] / df_cdi['cumprod_past'] - 1.0
        df = pd.merge(df, df_cdi[['data', 'cdi_12m']], on='data', how='left')
        df['dy_gap'] = df['dy'] - df['cdi_12m']
    else:
        df['dy_gap'] = np.nan

    # 4. Rolling Percentiles
    window_pvp = config_get("valuation", {}).get("pvp_janela_pregoes", 504)
    df['pvp_pct'] = df['pvp'].rolling(window=window_pvp, min_periods=63).rank(pct=True) * 100
    
    window_dy = config_get("valuation", {}).get("dy_janela_pregoes", 252)
    df['dy_gap_pct'] = df['dy_gap'].rolling(window=window_dy, min_periods=252).rank(pct=True) * 100

    # 5. Calcular Scores e Sinais (Vetorizado onde possível, mas regras são dinâmicas)
    buy_rules = tickers_cfg[ticker].get("buy", {})
    sell_rules = tickers_cfg[ticker].get("sell", {})
    
    def apply_rules(row):
        score, sinal, conds = _avaliar_score_core(
            row['pvp'], row['pvp_pct'], row['dy_gap_pct'], row['meses_alerta'], row['dist_maior'],
            buy_rules, sell_rules, cfg
        )
        res = {"score": score, "sinal": sinal}
        res.update(conds)
        return pd.Series(res)

    res_df = df.apply(apply_rules, axis=1)
    df = pd.concat([df, res_df], axis=1)
    
    # Retorna os últimos 504 pregões
    return df.tail(504).sort_values('data')

def calcular_confianca(ticker, session, forward_days=20):
    cfg = get_sinais_config()
    forward_days = cfg.get("forward_days", forward_days)
    
    hist = gerar_historico_sinais(ticker, session)
    if hist.empty:
        return {}

    # Precos para retorno forward (fechamento ajustado para total return)
    precos_all = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    
    if not precos_all:
        return {}
        
    df_precos = pd.DataFrame(precos_all, columns=["data", "fechamento_aj"])
    df_precos.set_index("data", inplace=True)

    # Identificar mudanças de sinal (gatilhos)
    hist["sinal_ant"] = hist["sinal"].shift(1)
    entradas_buy = hist[(hist["sinal"] == "COMPRA") & (hist["sinal_ant"] != "COMPRA")]
    entradas_sell = hist[(hist["sinal"] == "VENDA") & (hist["sinal_ant"] != "VENDA")]

    def get_fwd_ret(d):
        try:
            idx = df_precos.index.get_loc(d)
        except KeyError:
            # Se não achar a data exata, pega a anterior mais próxima
            idx_arr = df_precos.index.get_indexer([d], method='pad')
            idx = idx_arr[0]
            
        if idx == -1 or idx + forward_days >= len(df_precos):
            return None
            
        p0 = df_precos.iloc[idx]["fechamento_aj"]
        p1 = df_precos.iloc[idx + forward_days]["fechamento_aj"]
        
        if p0 and p1 and float(p0) > 0:
            return (float(p1) / float(p0)) - 1.0
        return None

    buy_rets = entradas_buy["data"].apply(get_fwd_ret).dropna()
    sell_rets = entradas_sell["data"].apply(get_fwd_ret).dropna()

    n_buy = len(buy_rets)
    n_sell = len(sell_rets)
    
    pct_buy_acerto = (buy_rets > 0).mean() if n_buy > 0 else 0
    pct_sell_acerto = (sell_rets < 0).mean() if n_sell > 0 else 0
    
    car_buy = buy_rets.mean() if n_buy > 0 else 0
    car_sell = sell_rets.mean() if n_sell > 0 else 0

    p_value_buy = None
    if n_buy > 1 and buy_rets.std() > 0:
        try:
            p_value_buy = stats.ttest_1samp(buy_rets, 0).pvalue
        except: pass
        
    p_value_sell = None
    if n_sell > 1 and sell_rets.std() > 0:
        try:
            p_value_sell = stats.ttest_1samp(sell_rets, 0).pvalue
        except: pass

    return {
        "n_buy": n_buy,
        "n_sell": n_sell,
        "pct_buy_acerto": float(pct_buy_acerto),
        "pct_sell_acerto": float(pct_sell_acerto),
        "car_buy": float(car_buy),
        "car_sell": float(car_sell),
        "p_value_buy": float(p_value_buy) if p_value_buy is not None else None,
        "p_value_sell": float(p_value_sell) if p_value_sell is not None else None,
    }

def sinal_atual(ticker, session):
    ultimo_d = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()
    
    if not ultimo_d:
        return {}
        
    res = calcular_score_ticker(ticker, ultimo_d, session)
    conf = calcular_confianca(ticker, session)
    
    return {
        "data": ultimo_d,
        "score": res["score"],
        "sinal": res["sinal"],
        "condicoes_detalhadas": res["condicoes"],
        "valores": res["valores"],
        "confianca_historica": conf
    }
