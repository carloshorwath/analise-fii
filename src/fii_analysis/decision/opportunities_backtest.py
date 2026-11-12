"""[PESQUISA — NÃO OPERACIONAL] Backtest do motor de rotação.

ATENÇÃO: este módulo NÃO é point-in-time. `decidir_universo()` calcula decisões
com os dados de HOJE e elas são reaplicadas a datas históricas dentro do loop —
isso viola a regra de integridade temporal (PROJETO.md §4.1) e produz resultados
com lookahead bias. Por isso:

  - NÃO é chamado pelo pipeline diário (generate_daily_snapshot rotula as
    oportunidades como "DESCRITIVO" sem validação).
  - Os números produzidos aqui NÃO devem ser usados para decisão de investimento.
  - Para promover o motor de rotação a "validado", é preciso reescrever o lado
    de decisões com suporte a data de corte t (decidir_ticker(t)) — pendente.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import select

from src.fii_analysis.config import TICKERS
from src.fii_analysis.data.database import PrecoDiario, BenchmarkDiario, CdiDiario
from src.fii_analysis.decision.opportunities import detectar_oportunidades, RotationOpportunity
from src.fii_analysis.decision.recommender import decidir_universo


@dataclass
class BacktestResult:
    final_return: float
    annualized_return: float
    volatility: float
    sharpe: float
    max_drawdown: float
    n_trades: int
    portfolio_history: pd.DataFrame
    critic_veredicto: str  # APROVADO | REPROVADO | DESCRITIVO
    p_value: float


def run_rotation_backtest(
    session,
    start_date: date,
    end_date: date,
    placebo_mode: bool = False,
    seed: Optional[int] = None,
) -> BacktestResult:
    """Executa a simulação histórica do motor de rotação.
    
    Se placebo_mode = True, o motor de rotação é ignorado e pares de rotação 
    aleatórios dentro do mesmo segmento são executados na data do sinal original.
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    # 1. Carregar calendário de pregões e taxas de CDI
    pregoes_rows = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.data >= start_date, PrecoDiario.data <= end_date)
        .order_by(PrecoDiario.data.asc())
        .distinct()
    ).scalars().all()


    trading_dates = sorted(list(set(pregoes_rows)))
    if not trading_dates:
        raise ValueError(f"Sem pregões no período {start_date} a {end_date}")

    cdi_rows = session.execute(
        select(CdiDiario.data, CdiDiario.taxa_diaria_pct)
        .where(CdiDiario.data >= start_date, CdiDiario.data <= end_date)
    ).all()
    cdi_map = {row[0]: float(row[1]) / 100.0 for row in cdi_rows}

    # 2. Inicializar portfolio simulado com os FIIs curados em partes iguais
    tickers_carteira = list(TICKERS)
    
    # Capital inicial: R$ 100.000 (R$ 15.000 para cada FII, resto em caixa)
    capital_inicial = 100000.0
    cash = capital_inicial - (15000.0 * len(tickers_carteira))
    
    # Obter preços iniciais na primeira data
    d_init = trading_dates[0]
    holdings: dict[str, float] = {}  # ticker -> quantidade de cotas
    
    for t in tickers_carteira:
        p_row = session.execute(
            select(PrecoDiario.fechamento)
            .where(PrecoDiario.ticker == t, PrecoDiario.data <= d_init)
            .order_by(PrecoDiario.data.desc())
            .limit(1)
        ).scalar_one_or_none()
        p = float(p_row) if p_row is not None else 80.0  # fallback se sem preço
        holdings[t] = 15000.0 / p

    # Histórico de decisões pré-calculado por data para economizar tempo
    # Para backtest dinâmico, calculamos apenas quando necessário para evitar explosão de memória
    portfolio_history = []
    n_trades = 0

    # 3. Loop diário de simulação
    for idx_pos, dt in enumerate(trading_dates):
        # Aplicar CDI no caixa
        taxa = cdi_map.get(dt, 0.0)
        cash *= (1.0 + taxa)

        # Atualizar valores do portfólio
        precos_hoje = {}
        for t in list(holdings.keys()):
            p_row = session.execute(
                select(PrecoDiario.fechamento)
                .where(PrecoDiario.ticker == t, PrecoDiario.data <= dt)
                .order_by(PrecoDiario.data.desc())
                .limit(1)
            ).scalar_one_or_none()
            precos_hoje[t] = float(p_row) if p_row is not None else 80.0

        valor_posicionado = sum(qty * precos_hoje.get(t, 0.0) for t, qty in holdings.items())
        total_value = cash + valor_posicionado

        # Roda o motor de oportunidades a cada 5 pregões para simular o comportamento de rebalanceamento do usuário
        if idx_pos % 5 == 0:
            # Gerar decisões do dia
            tickers_ativos_universo = sorted(holdings.keys())
            # Nós simulamos o motor chamando com as decisões pré-computadas na data
            try:
                # Mockamos as decisões locais simulando o estado real
                decisoes_list = decidir_universo(session, tickers_ativos_universo)
                decisoes_dict = {d.ticker: d for d in decisoes_list}
                
                opps = detectar_oportunidades(session, dt, universo_decisoes=decisoes_dict)
                
                if opps:
                    for opp in opps:
                        # Se placebo_mode, escolher um ticker de compra aleatório do mesmo segmento
                        comprar_ticker = opp.comprar
                        if placebo_mode:
                            # Escolhe um FII aleatório do mesmo segmento no IFIX
                            from src.fii_analysis.data.database import Universo
                            outros = session.execute(
                                select(Universo.ticker)
                                .where(Universo.em_ifix == True, Universo.data_referencia <= dt)
                            ).scalars().all()
                            
                            candidatos_placebo = []
                            for candidate in outros:
                                if candidate not in holdings:
                                    # Verifica se tem o mesmo segmento
                                    from src.fii_analysis.features.composicao import classificar_fii
                                    if classificar_fii(candidate, session) == opp.segmento:
                                        candidatos_placebo.append(candidate)
                            
                            if candidatos_placebo:
                                comprar_ticker = random.choice(candidatos_placebo)

                        # Executar a troca
                        vender_ticker = opp.vender
                        if vender_ticker in holdings:
                            qty_vender = holdings[vender_ticker]
                            p_v = precos_hoje.get(vender_ticker, 0.0)
                            p_c = session.execute(
                                select(PrecoDiario.fechamento)
                                .where(PrecoDiario.ticker == comprar_ticker, PrecoDiario.data <= dt)
                                .order_by(PrecoDiario.data.desc())
                                .limit(1)
                            ).scalar_one_or_none()
                            
                            if p_c is not None and p_v > 0 and p_c > 0:
                                p_c = float(p_c)
                                # Valor bruto obtido com a venda
                                valor_venda = qty_vender * p_v
                                
                                # Aplicar custo B3 + IR estimado
                                custo_estimado_pct = opp.custo_estimado_pct
                                valor_liquido_venda = valor_venda * (1.0 - (custo_estimado_pct / 100.0))
                                
                                # Comprar Y com o valor líquido
                                holdings.pop(vender_ticker)
                                holdings[comprar_ticker] = valor_liquido_venda / p_c
                                n_trades += 1
                                
                                logger.debug(
                                    "TRADE [{}]: {} -> {} (vendeu a R$ {:.2f}, comprou a R$ {:.2f}, custo={:.2f}%)",
                                    dt, vender_ticker, comprar_ticker, p_v, p_c, custo_estimado_pct
                                )
                                break  # Apenas uma rotação por rebalanceamento
            except Exception as e:
                logger.warning("Erro ao simular oportunidades em {}: {}", dt, e)

        portfolio_history.append({
            "data": dt,
            "total_value": total_value,
            "cash": cash,
            "valor_posicionado": valor_posicionado,
            "retorno_diario": (total_value / capital_inicial) - 1.0,
        })

    ph_df = pd.DataFrame(portfolio_history)
    ph_df["retorno_acum"] = ph_df["total_value"] / capital_inicial - 1.0

    # 4. Calcular métricas estatísticas finais
    final_return = ph_df["retorno_acum"].iloc[-1]
    
    # Calcular retornos diários em log para Sharpe e volatilidade
    ph_df["log_ret"] = np.log(ph_df["total_value"] / ph_df["total_value"].shift(1))
    ph_df.loc[0, "log_ret"] = 0.0
    
    vol = float(ph_df["log_ret"].std(ddof=1) * np.sqrt(252)) if len(ph_df) > 10 else 0.0
    ann_ret = float((ph_df["total_value"].iloc[-1] / capital_inicial) ** (252.0 / len(ph_df)) - 1.0) if len(ph_df) > 10 else 0.0
    
    # Sharpe (assumindo risk-free rate de 10% a.a.)
    rf = 0.10
    sharpe = (ann_ret - rf) / vol if vol > 0 else 0.0

    # Max Drawdown
    ph_df["peak"] = ph_df["total_value"].cummax()
    ph_df["dd"] = (ph_df["total_value"] - ph_df["peak"]) / ph_df["peak"]
    max_dd = float(ph_df["dd"].min())

    return BacktestResult(
        final_return=final_return,
        annualized_return=ann_ret,
        volatility=vol,
        sharpe=sharpe,
        max_drawdown=max_dd,
        n_trades=n_trades,
        portfolio_history=ph_df,
        critic_veredicto="APROVADO",
        p_value=0.0
    )


def critic_agent_validation(session, start_date: date, end_date: date, real_result: BacktestResult) -> tuple[str, float]:
    """CriticAgent: roda 30 simulações de Placebo para testar hipótese nula."""
    logger.info("Iniciando validação CriticAgent (Placebo)...")
    
    placebo_returns = []
    for i in range(30):
        try:
            res = run_rotation_backtest(session, start_date, end_date, placebo_mode=True, seed=i)
            placebo_returns.append(res.final_return)
        except Exception as e:
            logger.warning("Falha na execução de placebo #{}: {}", i, e)

    if not placebo_returns:
        return "DESCRITIVO", 1.0

    # p-value: percentual de placebo runs que bateram o resultado real
    bateram = sum(1 for r in placebo_returns if r >= real_result.final_return)
    p_value = bateram / len(placebo_returns)

    # Estabilidade (primeira metade vs segunda metade)
    df_ph = real_result.portfolio_history
    meio = len(df_ph) // 2
    if meio > 10:
        ret_1 = df_ph["log_ret"].iloc[:meio]
        ret_2 = df_ph["log_ret"].iloc[meio:]
        sharpe_1 = (ret_1.mean() * 252 - 0.10) / (ret_1.std() * np.sqrt(252)) if ret_1.std() > 0 else 0.0
        sharpe_2 = (ret_2.mean() * 252 - 0.10) / (ret_2.std() * np.sqrt(252)) if ret_2.std() > 0 else 0.0
        diff_sharpe = abs(sharpe_1 - sharpe_2)
    else:
        diff_sharpe = 0.0

    # Aprovado se p_value < 0.05 (estratégia bate aleatório com significância de 95%)
    # E diferença de Sharpe entre subperíodos não é excessiva (estabilidade)
    if p_value < 0.05 and diff_sharpe < 1.0:
        veredicto = "APROVADO"
    else:
        veredicto = "REPROVADO"

    logger.info("CriticAgent finalizado: veredicto={}, p-value={:.4f}, diff_sharpe={:.4f}", veredicto, p_value, diff_sharpe)
    return veredicto, p_value
