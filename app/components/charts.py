import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


def _no_gap_layout(fig: go.Figure) -> go.Figure:
    if fig.data and hasattr(fig.data[0], 'x') and len(fig.data[0].x) > 0:
        fig.update_xaxes(type="category", tickangle=-45, dtick=max(1, len(fig.data[0].x) // 10))
    return fig


def price_volume_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    labels = [d.strftime("%d/%m") if hasattr(d, "strftime") else str(d) for d in df["data"]]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=labels, y=df["fechamento"], mode="lines", name="Preco",
        line=dict(color="#1f77b4", width=1.5),
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=labels, y=df["volume"], name="Volume",
        marker_color="rgba(100,100,200,0.3)",
    ), secondary_y=True)
    fig.update_layout(
        title=f"{ticker} — Preco e Volume",
        template="plotly_white", height=400, xaxis_type="category",
    )
    fig.update_yaxes(title_text="Preco (R$)", secondary_y=False)
    fig.update_yaxes(title_text="Volume", secondary_y=True)
    fig.update_xaxes(tickangle=-45, dtick=max(1, len(labels) // 12))
    return fig


def pvp_historico_com_bandas(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    labels = [d.strftime("%d/%m/%y") if hasattr(d, "strftime") else str(d) for d in df["data"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=labels, y=df["pvp"], mode="lines", name="P/VP", line=dict(color="#1f77b4")))
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="P/VP = 1.0")
    fig.update_layout(
        title=f"{ticker} — P/VP Historico",
        yaxis_title="P/VP",
        template="plotly_white", height=400, xaxis_type="category",
    )
    fig.update_xaxes(tickangle=-45, dtick=max(1, len(labels) // 10))
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
    fig.update_layout(height=300)
    return fig


def dy_trailing_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    labels = [d.strftime("%d/%m/%y") if hasattr(d, "strftime") else str(d) for d in df["data"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=labels, y=df["dy"] * 100, mode="lines", name="DY 12m %", line=dict(color="#2ca02c")))
    fig.update_layout(
        title=f"{ticker} — Dividend Yield 12m",
        yaxis_title="DY (%)",
        template="plotly_white", height=400, xaxis_type="category",
    )
    fig.update_xaxes(tickangle=-45, dtick=max(1, len(labels) // 10))
    return fig


def pl_trend_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    labels = [d.strftime("%m/%y") if hasattr(d, "strftime") else str(d) for d in df["data_ref"]]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=labels, y=df["patrimonio_liq"] / 1e6, name="PL (mi)", marker_color="#636efa"), secondary_y=False)
    fig.add_trace(go.Scatter(x=labels, y=df["vp_por_cota"], mode="lines+markers", name="VP/cota", line=dict(color="#ef553b")), secondary_y=True)
    fig.update_layout(
        title=f"{ticker} — Patrimonio Liquido 24m",
        template="plotly_white", height=400, xaxis_type="category",
    )
    fig.update_yaxes(title_text="PL (R$ milhoes)", secondary_y=False)
    fig.update_yaxes(title_text="VP/cota (R$)", secondary_y=True)
    fig.update_xaxes(tickangle=-45, dtick=max(1, len(labels) // 10))
    return fig


def composicao_pie(comp: dict, ticker: str) -> go.Figure:
    labels = []
    values = []
    if comp.get("pct_imoveis") is not None:
        labels.append("Imoveis")
        values.append(comp["pct_imoveis"] * 100)
    if comp.get("pct_recebiveis") is not None:
        labels.append("Recebiveis")
        values.append(comp["pct_recebiveis"] * 100)
    if comp.get("pct_caixa") is not None:
        labels.append("Caixa")
        values.append(comp["pct_caixa"] * 100)
    outros = 100 - sum(values) if values else 0
    if outros > 0.5:
        labels.append("Outros")
        values.append(outros)

    if not labels:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados de composicao", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.4,
                           marker_colors=["#636efa", "#ef553b", "#00cc96", "#ab63fa"]))
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


def carteira_alocacao_pie(df: pd.DataFrame) -> go.Figure:
    if df.empty or "ticker" not in df.columns:
        return go.Figure()

    labels = df["ticker"].tolist()
    values = df.get("valor_total", pd.Series([1] * len(df))).tolist()
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.4))
    fig.update_layout(title="Alocacao por FII", height=400)
    return fig


def carteira_segmento_pie(df: pd.DataFrame) -> go.Figure:
    if df.empty or "segmento" not in df.columns:
        return go.Figure()

    grp = df.groupby("segmento").size().reset_index(name="count")
    fig = go.Figure(go.Pie(labels=grp["segmento"], values=grp["count"], hole=0.4))
    fig.update_layout(title="Alocacao por Segmento", height=400)
    return fig


def radar_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()

    cols = ["pvp_baixo", "dy_gap_alto", "saude_ok", "liquidez_ok"]
    labels = ["P/VP Baixo", "DY Gap Alto", "Saude OK", "Liquidez OK"]

    fig = go.Figure(data=go.Heatmap(
        z=df[cols].astype(int).values.tolist(),
        x=labels,
        y=df["ticker"].tolist(),
        colorscale=[[0, "#ffcccc"], [1, "#ccffcc"]],
        showscale=False,
        text=df[cols].astype(int).values.tolist(),
        texttemplate="%{text}",
    ))
    fig.update_layout(title="Radar — Matriz Booleana", height=max(300, len(df) * 50 + 100), xaxis_side="top")
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
