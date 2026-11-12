import sys
import json
from pathlib import Path
from datetime import date
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.snapshot_ui import load_opportunities_snapshot, render_snapshot_info
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.decision.decision_journal import registrar_decisao, get_fechamento_on_or_before
from src.fii_analysis.llm.context_builder import build_opportunity_context
from src.fii_analysis.llm.prompts import render_prompt
from src.fii_analysis.llm.gateway import export_prompt_pack

safe_set_page_config(page_title="Oportunidades", page_icon="compare_arrows", layout="wide")

_CSS = """
<style>
.opp-card {
    background: #ffffff;
    border-radius: 16px;
    border: 1px solid #d8e2dc;
    padding: 24px;
    margin-bottom: 24px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
    transition: transform 0.2s, box-shadow 0.2s;
}
.opp-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.06);
}
.opp-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #f0f4f2;
    padding-bottom: 14px;
    margin-bottom: 16px;
}
.opp-title {
    font-size: 1.35rem;
    font-weight: 700;
    color: #14221d;
    display: flex;
    align-items: center;
    gap: 8px;
}
.opp-badge {
    background: #e8faf4;
    color: #0f5c4d;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 20px;
    border: 1px solid #c2ebd9;
    text-transform: uppercase;
}
.opp-metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
}
.opp-metric-box {
    background: #f8faf8;
    border: 1px solid #e5ece8;
    border-radius: 10px;
    padding: 12px;
    text-align: center;
}
.opp-metric-label {
    font-size: 0.75rem;
    color: #5f756e;
    text-transform: uppercase;
    font-weight: 600;
    margin-bottom: 4px;
}
.opp-metric-val {
    font-size: 1.15rem;
    font-weight: 700;
    color: #14221d;
}
.opp-metric-val-positive {
    color: #2e7d32;
}
.opp-metric-val-negative {
    color: #c62828;
}
.opp-section-title {
    font-size: 0.85rem;
    text-transform: uppercase;
    font-weight: 700;
    color: #455a54;
    letter-spacing: 0.05em;
    margin-top: 14px;
    margin-bottom: 6px;
}
.opp-rationale {
    background: #fcfdfc;
    border-left: 3px solid #0f5c4d;
    padding: 10px 14px;
    border-radius: 0 8px 8px 0;
    margin-bottom: 12px;
    font-size: 0.9rem;
    line-height: 1.5;
    color: #29433c;
}
.opp-vetos {
    background: #fff5f5;
    border-left: 3px solid #e53935;
    padding: 10px 14px;
    border-radius: 0 8px 8px 0;
    margin-bottom: 12px;
    font-size: 0.9rem;
    line-height: 1.5;
    color: #b71c1c;
}
</style>
"""

@safe_page
def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    render_sidebar_guide("Oportunidades", "Diário")
    
    render_page_header(
        "Oportunidades de Rotação",
        "Sugestões de arbitragem relativa intra-segmento. Venda posições caras e realoque em candidatos subvalorizados com base nos dados mais recentes.",
        "Diário",
    )
    
    render_inline_note(
        "Pares DESCRITIVOS: cada sugestão passa por filtros de liquidez, saúde financeira, "
        "valuation relativo e custos — mas o motor de rotação ainda NÃO tem validação "
        "estatística de retorno futuro. Use como ponto de partida de investigação, não como ordem."
    )

    # Botão de refresh manual
    if st.button("Atualizar Oportunidades", type="primary"):
        load_opportunities_snapshot.clear()
        st.rerun()

    with st.spinner("Carregando oportunidades do banco..."):
        meta, df = load_opportunities_snapshot()

    # Informações do snapshot
    render_snapshot_info(meta)

    if df.empty:
        st.info("Nenhuma oportunidade de rotação acionável ativa no último snapshot. O mercado está equilibrado para o seu portfólio.")
        render_footer()
        return

    # KPIs superiores
    col1, col2, col3 = st.columns(3)
    col1.metric("Oportunidades Ativas", len(df))
    
    max_spread = df["spread_liquido_pct"].max()
    col2.metric("Maior Spread Líquido", f"{max_spread:+.1f} pp")
    
    critic_ver = df["critic_veredicto"].iloc[0] if "critic_veredicto" in df.columns else "N/A"
    col3.metric("Validação CriticAgent", critic_ver, 
               help="Resultado do CriticAgent sobre as premissas estatísticas da estratégia de rotação.")

    st.markdown("---")

    for idx, row in df.iterrows():
        opp_id = int(row["id"])
        vender = row["vender"]
        comprar = row["comprar"]
        segmento = row["segmento"]
        spread_pvp = row["spread_pvp_pct"]
        custo = row["custo_estimado_pct"]
        spread_liq = row["spread_liquido_pct"]
        delta_score = row["delta_score"]
        persistencia = row["dias_persistencia"]
        critic_veredicto = row.get("critic_veredicto", "N/A")
        
        # Desserialização de racionais e vetos
        try:
            racionais = json.loads(row["racional_json"]) if isinstance(row["racional_json"], str) else row["racional_json"]
        except Exception:
            racionais = [row["racional_json"]] if row["racional_json"] else []
            
        try:
            vetos = json.loads(row["vetos_json"]) if isinstance(row["vetos_json"], str) else row["vetos_json"]
        except Exception:
            vetos = [row["vetos_json"]] if row["vetos_json"] else []

        # Card wrapper
        st.markdown(f"""
        <div class="opp-card">
            <div class="opp-header">
                <div class="opp-title">
                    <span style="color: #c62828;">{vender}</span> 
                    <span style="color: #5f756e; font-size: 1.1rem;">➔</span> 
                    <span style="color: #2e7d32;">{comprar}</span>
                </div>
                <div class="opp-badge">{segmento}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Colunas Streamlit para as métricas e conteúdo do card
        m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
        m_col1.metric("Spread PVP", f"{spread_pvp:+.1f} pp")
        m_col2.metric("Custo Est.", f"{custo:.2%}")
        m_col3.metric("Spread Líquido", f"{spread_liq:+.1f} pp")
        m_col4.metric("Delta Score", f"{delta_score:+.0f}")
        m_col5.metric("Persistência", f"{persistencia} dias")

        # Racionais
        if racionais:
            st.markdown('<div class="opp-section-title">Análise de Racional</div>', unsafe_allow_html=True)
            for r in racionais:
                st.markdown(f'<div class="opp-rationale">✓ {r}</div>', unsafe_allow_html=True)

        # Vetos
        if vetos and any(vetos):
            st.markdown('<div class="opp-section-title">Vetos e Alertas Ativos</div>', unsafe_allow_html=True)
            for v in vetos:
                if v:
                    st.markdown(f'<div class="opp-vetos">⚠️ Veto: {v}</div>', unsafe_allow_html=True)

        # Ações na parte inferior do card (Gerar Prompt & Registrar Decisão)
        btn_col1, btn_col2 = st.columns(2)
        
        with btn_col1:
            # Gerar Prompt Pack
            if st.button(f"Generate Prompt Pack ({vender} ➔ {comprar})", key=f"prompt_{opp_id}"):
                with get_session_ctx() as session:
                    ctx = build_opportunity_context(vender, comprar, session)
                    if "erro" in ctx:
                        st.error(ctx["erro"])
                    else:
                        sys_prompt, user_prompt, _ = render_prompt("oportunidade_rotacao", ctx)
                        ticker_pair = f"{vender}_{comprar}"
                        filepath = export_prompt_pack(sys_prompt, user_prompt, "oportunidade_rotacao", ticker_pair)
                        
                        st.success(f"Prompt Pack exportado com sucesso em: {filepath}")
                        with st.expander("Ver prompt copiado", expanded=True):
                            st.info("Copie o conteúdo abaixo e cole no seu modelo de IA (e.g. ChatGPT ou Gemini) para obter a análise qualitativa completa:")
                            st.text_area("System Prompt", value=sys_prompt, height=120)
                            st.text_area("User Prompt", value=user_prompt, height=350)
                            
        with btn_col2:
            # Registrar Decisão
            with st.expander(f"Registrar Operação/Decisão"):
                with st.form(key=f"form_decision_{opp_id}"):
                    tipo_op = st.selectbox("Ação", ["ROTACAO", "IGNORADA"], key=f"tipo_{opp_id}")
                    qtd = st.number_input("Quantidade de Cotas", min_value=1, value=100, step=10, key=f"qtd_{opp_id}")
                    
                    # Carregar último preço de fechamento para sugerir
                    with get_session_ctx() as session:
                        preco_sugerido = get_fechamento_on_or_before(session, comprar, date.today()) or 100.0
                        
                    preco_exec = st.number_input("Preço Executado (R$)", min_value=0.01, value=float(preco_sugerido), format="%.2f", key=f"preco_{opp_id}")
                    racional_user = st.text_area("Racional/Comentários do Usuário", value="Operação executada conforme sinal do modelo.", key=f"racional_user_{opp_id}")
                    
                    submit_btn = st.form_submit_button("Registrar Decisão")
                    if submit_btn:
                        with get_session_ctx() as session:
                            try:
                                registrar_decisao(
                                    session=session,
                                    tipo=tipo_op,
                                    ticker_vendido=vender,
                                    ticker_comprado=comprar,
                                    quantidade=qtd if tipo_op == "ROTACAO" else None,
                                    preco=preco_exec if tipo_op == "ROTACAO" else None,
                                    opportunity_id=opp_id,
                                    racional_usuario=racional_user,
                                    data=date.today(),
                                )
                                st.success("Decisão registrada com sucesso no log histórico!")
                                st.toast("Decisão registrada!")
                            except Exception as e:
                                st.error(f"Erro ao registrar decisão: {e}")
                                
        st.markdown("<hr style='border: 1px solid #e5ece8; margin: 20px 0;'>", unsafe_allow_html=True)

    render_footer()

if __name__ == "__main__":
    main()
