import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


def price_volume_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    x_data = pd.to_datetime(df["data"])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=x_data, y=df["fechamento"], mode="lines", name="Preco",
        line=dict(color="#1f77b4", width=1.5),
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=x_data, y=df["volume"], name="Volume",
        marker_color="rgba(100,100,200,0.3)",
    ), secondary_y=True)
    fig.update_layout(
        title=f"{ticker} — Preco e Volume",
        template="plotly_white", height=400,
    )
    fig.update_xaxes(type="date", tickformat="%d/%m/%y")
    fig.update_yaxes(title_text="Preco (R$)", secondary_y=False)
    fig.update_yaxes(title_text="Volume", secondary_y=True)
    return fig


def pvp_historico_com_bandas(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    x_data = pd.to_datetime(df["data"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_data, y=df["pvp"], mode="lines", name="P/VP", line=dict(color="#1f77b4")))
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="P/VP = 1.0")
    fig.update_layout(
        title=f"{ticker} — P/VP Historico",
        yaxis_title="P/VP",
        template="plotly_white", height=400,
    )
    fig.update_xaxes(type="date", tickformat="%d/%m/%y")
    return fig


def pvp_gauge(pvp: float | None, ticker: str) -> go.Figure:
    if pvp is None:
        fig = go.Figure()
        fig.add_annotation(text="P/VP indisponivel", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    color = "green" if pvp < 0.9 else ("orange" if pvp < 1.1 else "red")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pvp,
        title={"text": f"{ticker} P/VP"},
        gauge={"axis": {"range": [0.5, 1.5]},
               "bar": {"color": color},
               "steps": [
                   {"range": [0.5, 0.9], "color": "rgba(0,200,0,0.15)"},
                   {"range": [0.9, 1.1], "color": "rgba(255,165,0,0.15)"},
                   {"range": [1.1, 1.5], "color": "rgba(255,0,0,0.15)"},
               ]},
    ))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=60, b=20))
    return fig


def dy_trailing_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    x_data = pd.to_datetime(df["data"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_data, y=df["dy"] * 100, mode="lines", name="DY 12m %", line=dict(color="#2ca02c")))
    fig.update_layout(
        title=f"{ticker} — Dividend Yield 12m",
        yaxis_title="DY (%)",
        template="plotly_white", height=400,
    )
    fig.update_xaxes(type="date", tickformat="%d/%m/%y")
    return fig


def pl_trend_chart(df: pd.DataFrame, ticker: str, destruicao_info: dict | None = None) -> go.Figure:
    """Gráfico de PL + VP/cota com cores indicando destruição/recuperação.

    Args:
        df: DataFrame com colunas data_ref, patrimonio_liq, vp_por_cota.
        ticker: Código do FII.
        destruicao_info: Dict retornado por flag_destruicao_capital (opcional).
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    import numpy as np
    from scipy import stats as sp_stats

    x_data = pd.to_datetime(df["data_ref"])
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Cor das barras de PL: vermelho se VP/cota caindo, verde se estável/subindo
    vp_vals = df["vp_por_cota"].values
    bar_colors = []
    for i in range(len(vp_vals)):
        if i == 0:
            bar_colors.append("#636efa")
        else:
            if pd.notna(vp_vals[i]) and pd.notna(vp_vals[i - 1]) and vp_vals[i - 1] > 0:
                var = (vp_vals[i] - vp_vals[i - 1]) / vp_vals[i - 1]
                if var < -0.005:
                    bar_colors.append("#e74c3c")  # vermelho — VP caindo
                elif var > 0.005:
                    bar_colors.append("#2ecc71")  # verde — VP subindo
                else:
                    bar_colors.append("#636efa")  # azul — estável
            else:
                bar_colors.append("#636efa")

    fig.add_trace(go.Bar(
        x=x_data, y=df["patrimonio_liq"] / 1e6, name="PL (mi)",
        marker_color=bar_colors,
    ), secondary_y=False)

    # Linha VP/cota com espessura e cor baseada na gravidade
    vp_line_color = "#ef553b"
    vp_line_width = 2
    if destruicao_info:
        grav = destruicao_info.get("gravidade", "saudavel")
        if grav == "saudavel":
            vp_line_color = "#2ecc71"
        elif grav == "em_recuperacao":
            vp_line_color = "#f39c12"
        elif grav == "alerta":
            vp_line_color = "#e67e22"
        else:
            vp_line_color = "#e74c3c"

    fig.add_trace(go.Scatter(
        x=x_data, y=df["vp_por_cota"], mode="lines+markers", name="VP/cota",
        line=dict(color=vp_line_color, width=vp_line_width),
    ), secondary_y=True)

    # Linha de tendência (regressão) sobre VP/cota
    vp_valid = df.dropna(subset=["vp_por_cota"])
    if len(vp_valid) >= 3:
        x_trend = np.arange(len(vp_valid), dtype=float)
        y_trend = vp_valid["vp_por_cota"].values.astype(float)
        slope, intercept, r_value, _, _ = sp_stats.linregress(x_trend, y_trend)
        y_fit = slope * x_trend + intercept
        trend_color = "#e74c3c" if slope < 0 else "#2ecc71"
        trend_name = f"Tendência VP (slope={slope:.3f})"
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(vp_valid["data_ref"]), y=y_fit,
            mode="lines", name=trend_name,
            line=dict(dash="dash", color=trend_color, width=1.5),
        ), secondary_y=True)

    # Badge de gravidade no título
    title = f"{ticker} — Patrimonio Liquido 24m"
    if destruicao_info:
        grav = destruicao_info.get("gravidade", "")
        tend = destruicao_info.get("tendencia", "")
        score = destruicao_info.get("score_saude", 100)
        _GRAV_EMOJI = {
            "critica": "🔴", "alerta": "🟠",
            "em_recuperacao": "🟡", "saudavel": "🟢",
        }
        _TEND_ARROW = {"piorando": "⬇", "estavel": "➡", "melhorando": "⬆"}
        emoji = _GRAV_EMOJI.get(grav, "")
        arrow = _TEND_ARROW.get(tend, "")
        title = f"{ticker} — PL 24m {emoji} {grav.replace('_', ' ').title()} ({score}/100) {arrow} {tend}"

    fig.update_layout(
        title=title,
        template="plotly_white", height=400,
    )
    fig.update_xaxes(type="date", tickformat="%m/%y")
    fig.update_yaxes(title_text="PL (R$ milhoes)", secondary_y=False)
    fig.update_yaxes(title_text="VP/cota (R$)", secondary_y=True)
    return fig


def composicao_pie(comp: dict, ticker: str) -> go.Figure:
    labels = []
    values = []
    _COLORS = {
        "Imoveis": "#636efa",
        "Recebiveis (Titulos)": "#ef553b",
        "Caixa e Liquidez": "#00cc96",
        "Outros Invest.": "#ffa15a",
        "Valores a Receber": "#ab63fa",
        "Outros": "#b6b6b6",
    }
    _fields = [
        ("pct_imoveis", "Imoveis"),
        ("pct_recebiveis", "Recebiveis (Titulos)"),
        ("pct_caixa", "Caixa e Liquidez"),
        ("pct_investimentos", "Outros Invest."),
        ("pct_valores_receber", "Valores a Receber"),
        ("pct_outros", "Outros"),
    ]
    for key, label in _fields:
        val = comp.get(key)
        if val is not None and val > 0.001:  # > 0.1%
            labels.append(label)
            values.append(val * 100)

    if not labels:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados de composicao", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    colors = [_COLORS.get(l, "#cccccc") for l in labels]
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.4, marker_colors=colors))
    fig.update_layout(title=f"{ticker} — Composicao do Ativo", height=400)
    return fig


def car_plot(es_df: pd.DataFrame, ticker: str, title_suffix: str = "") -> go.Figure:
    if es_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados de event study", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    fig = go.Figure()
    fig.add_trace(go.Bar(x=es_df["dia_relativo"], y=es_df["retorno_medio"] * 100, name="Retorno Medio %", marker_color="#636efa"))
    fig.add_trace(go.Scatter(x=es_df["dia_relativo"], y=es_df["retorno_acumulado"] * 100, mode="lines", name="CAR %", line=dict(color="#ef553b", width=2)))
    fig.add_vline(x=0, line_dash="dash", line_color="gray", annotation_text="Data-com")
    fig.update_layout(
        title=f"{ticker} — Event Study{title_suffix}",
        xaxis_title="Dia Relativo", yaxis_title="Retorno (%)",
        template="plotly_white", height=400, barmode="group",
    )
    return fig


def carteira_alocacao_pie(df: pd.DataFrame, value_col: str = "valor_mercado") -> go.Figure:
    if df.empty or "ticker" not in df.columns:
        return go.Figure()

    labels = df["ticker"].tolist()
    values = df.get(value_col, pd.Series([1] * len(df))).tolist()
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.4))
    fig.update_layout(title="Alocacao por FII", height=400)
    return fig


def carteira_segmento_pie(df: pd.DataFrame) -> go.Figure:
    if df.empty or "segmento" not in df.columns:
        return go.Figure()

    val_col = "valor_mercado" if "valor_mercado" in df.columns else "valor_total" if "valor_total" in df.columns else None
    if val_col:
        grp = df.groupby("segmento")[val_col].sum().reset_index(name="value")
    else:
        grp = df.groupby("segmento").size().reset_index(name="value")
        
    fig = go.Figure(go.Pie(labels=grp["segmento"], values=grp["value"], hole=0.4))
    fig.update_layout(title="Alocacao por Segmento", height=400)
    return fig


def radar_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()

    cols = ["pvp_baixo", "dy_gap_alto", "saude_ok", "liquidez_ok"]
    labels = ["P/VP ↓", "DY Gap ↑", "Saúde", "Liquidez"]

    # Texto ✓/✗ legível em vez de 0/1
    z_vals = df[cols].astype(int).values.tolist()
    text_vals = [["✓" if v else "✗" for v in row] for row in z_vals]

    fig = go.Figure(data=go.Heatmap(
        z=z_vals,
        x=labels,
        y=df["ticker"].tolist(),
        colorscale=[[0, "#fce4e4"], [1, "#e4f5e4"]],
        showscale=False,
        text=text_vals,
        texttemplate="%{text}",
        textfont={"size": 18},
    ))
    fig.update_layout(
        title="Radar — Visão Macro",
        height=max(260, len(df) * 48 + 80),
        xaxis_side="top",
        margin=dict(t=60, b=20, l=80, r=20),
        template="plotly_white",
    )
    fig.update_yaxes(autorange="reversed")
    return fig


def dividend_heatmap(divs_df: pd.DataFrame, prices_df: pd.DataFrame, ticker: str) -> go.Figure:
    if divs_df.empty or prices_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados de dividendos", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    import numpy as np

    dc = divs_df.copy()
    dc["ano"] = dc["data_com"].apply(lambda d: d.year if hasattr(d, "year") else int(str(d)[:4]))
    dc["mes"] = dc["data_com"].apply(lambda d: d.month if hasattr(d, "month") else int(str(d)[5:7]))

    preco_mensal = prices_df.copy()
    preco_mensal["ano"] = preco_mensal["data"].apply(lambda d: d.year if hasattr(d, "year") else int(str(d)[:4]))
    preco_mensal["mes"] = preco_mensal["data"].apply(lambda d: d.month if hasattr(d, "month") else int(str(d)[5:7]))
    last_month = preco_mensal.groupby(["ano", "mes"])["fechamento"].last().reset_index()
    preco_map = {(r["ano"], r["mes"]): r["fechamento"] for _, r in last_month.iterrows()}

    agg = dc.groupby(["ano", "mes"])["valor_cota"].sum().reset_index()
    anos = sorted(agg["ano"].unique())
    meses_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

    z = []
    text_z = []
    for ano in anos:
        row = []
        row_text = []
        for mes in range(1, 13):
            match = agg[(agg["ano"] == ano) & (agg["mes"] == mes)]
            div_val = float(match["valor_cota"].values[0]) if not match.empty else 0.0
            preco = preco_map.get((ano, mes))
            if div_val > 0 and preco and preco > 0:
                pct = div_val / preco * 100
                row.append(round(pct, 2))
                row_text.append(f"{pct:.2f}%")
            else:
                row.append(0.0)
                row_text.append("")
        z.append(row)
        text_z.append(row_text)

    fig = go.Figure(data=go.Heatmap(
        z=z, x=meses_labels, y=[str(a) for a in anos],
        text=text_z, texttemplate="%{text}",
        colorscale=[[0, "#f0f0f0"], [0.5, "#a6d96a"], [1, "#1a9850"]],
        colorbar=dict(title="% mes"),
    ))
    fig.update_layout(
        title=f"{ticker} — Yield Mensal (Dividendo / Preco Fechamento)",
        xaxis_title="Mes", yaxis_title="Ano",
        template="plotly_white", height=max(300, len(anos) * 40 + 100),
    )
    return fig
