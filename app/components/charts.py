import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


def pvp_historico_com_bandas(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["data"], y=df["pvp"], mode="lines", name="P/VP", line=dict(color="#1f77b4")))
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="P/VP = 1.0")
    fig.update_layout(
        title=f"{ticker} — P/VP Historico",
        xaxis_title="Data", yaxis_title="P/VP",
        template="plotly_white", height=400,
    )
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

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["data"], y=df["dy"] * 100, mode="lines", name="DY 12m %", line=dict(color="#2ca02c")))
    fig.update_layout(
        title=f"{ticker} — Dividend Yield 12m",
        xaxis_title="Data", yaxis_title="DY (%)",
        template="plotly_white", height=400,
    )
    return fig


def pl_trend_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["data_ref"], y=df["patrimonio_liq"] / 1e6, name="PL (mi)", marker_color="#636efa"), secondary_y=False)
    fig.add_trace(go.Scatter(x=df["data_ref"], y=df["vp_por_cota"], mode="lines+markers", name="VP/cota", line=dict(color="#ef553b")), secondary_y=True)
    fig.update_layout(title=f"{ticker} — Patrimonio Liquido 24m", template="plotly_white", height=400)
    fig.update_yaxes(title_text="PL (R$ milhoes)", secondary_y=False)
    fig.update_yaxes(title_text="VP/cota (R$)", secondary_y=True)
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
