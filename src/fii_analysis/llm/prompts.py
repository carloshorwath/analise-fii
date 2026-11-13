from __future__ import annotations

import json
from typing import Optional

# Versionamento estático de prompts
PROMPTS = {
    "analise_ticker": {
        "version": "1.0",
        "system": (
            "Você é um analista sênior de Fundos Imobiliários (FIIs) no mercado brasileiro. "
            "Sua tarefa é analisar o ticker fornecido com base em dados quantitativos e históricos. "
            "IMPORTANTE: Os números fornecidos são a única verdade estatística (calculados de forma rigorosa point-in-time). "
            "Não invente ou altere qualquer valor numérico ou indicador. Seja crítico e imparcial."
        ),
        "user_template": (
            "Análise detalhada do ticker: **{ticker}**\n"
            "Data de referência: {data_contexto}\n\n"
            "### Dados Quantitativos Locais (Snapshots):\n"
            "- Score Total: {score_total}/100\n"
            "- Decomposição dos Sub-Scores: {score_breakdown_json}\n"
            "- Indicadores Operacionais: {indicadores_json}\n"
            "- Sinais Estatísticos dos Motores de Recomendação: {decisao_json}\n"
            "- Análise de Sensibilidade ao CDI & Focus: {cdi_focus_json}\n"
            "- Flags de Risco Ativas: {flags_risco_json}\n"
            "- Histórico de P/VP das últimas 52 semanas: {historico_52w_json}\n"
            "- Saúde Financeira (Relatórios CVM dos últimos 6 meses): {saude_6m_json}\n\n"
            "### Pergunta Extra do Usuário:\n"
            "{pergunta}\n\n"
            "Gere uma resposta estruturada exatamente nas seguintes seções em Markdown:\n"
            "1. **Sumário Executivo** (Breve panorama geral do ativo)\n"
            "2. **Análise dos Indicadores e Score** (Interpretação detalhada do Valuation, Risco e CDI)\n"
            "3. **Riscos e Red Flags** (Análise aprofundada baseada nas flags e relatórios CVM)\n"
            "4. **Diretrizes para o Relatório Gerencial** (Pontos específicos do último relatório de gestão que devem ser verificados manualmente pelo usuário)\n"
            "5. **Veredito Qualitativo** (Recomendação qualitativa: AÇÃO LOCAL recomendada {acao_local} - Concordância: {concordancia_local})"
        ),
    },
    "oportunidade_rotacao": {
        "version": "1.0",
        "system": (
            "Você é um analista sênior de FIIs especialista em alocação tática de portfólio. "
            "Sua missão é avaliar uma oportunidade de rotação relativa de ativos (troca intra-segmento). "
            "O motor de rotação local LISTOU, de forma apenas DESCRITIVA (sem evidência estatística de que antecipe retorno melhor), o par vender X / comprar Y. "
            "Avalie criticamente se essa troca faz sentido do ponto de vista fundamentalista e macro."
        ),
        "user_template": (
            "Oportunidade de Rotação Intra-Segmento no segmento **{segmento}**:\n"
            "**VENDER: {vender_ticker}** ➔ **COMPRAR: {comprar_ticker}**\n\n"
            "### Métricas de Rotação:\n"
            "- Spread PVP (Percentil Vender - Percentil Comprar): {spread_pvp_percentil} pp\n"
            "- Spread DY Gap (Comprar - Vender): {spread_dy_gap_percentil} pp\n"
            "- Delta Score Composto (Comprar - Vender): {delta_score} pontos\n\n"
            "### Dados de {vender_ticker} (Vender):\n"
            "- Score Total: {vender_score_total}/100\n"
            "- Indicadores: {vender_indicadores_json}\n"
            "- Flags de Risco: {vender_flags_risco_json}\n"
            "- Decisão Local: {vender_decisao_json}\n\n"
            "### Dados de {comprar_ticker} (Comprar):\n"
            "- Score Total: {comprar_score_total}/100\n"
            "- Indicadores: {comprar_indicadores_json}\n"
            "- Flags de Risco: {comprar_flags_risco_json}\n"
            "- Decisão Local: {comprar_decisao_json}\n\n"
            "### Pergunta Extra do Usuário:\n"
            "{pergunta}\n\n"
            "Gere uma resposta estruturada exatamente nas seguintes seções em Markdown:\n"
            "1. **Tese de Rotação** (Resumo do que o par mostra descritivamente — não é previsão de retorno)\n"
            "2. **Comparativo Fundamentalista** (Diferenças qualitativas e de risco entre os dois fundos)\n"
            "3. **Riscos Não Capturados** (Riscos específicos do fundo Y que podem desabonar a compra e não estão nos números)\n"
            "4. **Veredito de Alocação** (Confirmação qualitativa da rotação com base nas premissas)"
        ),
    },
    "revisao_carteira": {
        "version": "1.0",
        "system": (
            "Você é um consultor financeiro de FIIs. Sua tarefa é revisar um portfólio completo "
            "e propor ajustes com base na distribuição de ativos, pesos, e sugestões do portfolio_advisor."
        ),
        "user_template": (
            "Revisão da Carteira de FIIs:\n"
            "Data de referência: {data_contexto}\n\n"
            "### Detalhes das Posições e Conselhos:\n"
            "{posicoes_json}\n\n"
            "### Alertas de Concentração e Estruturais:\n"
            "{alertas_json}\n\n"
            "### Pergunta Extra do Usuário:\n"
            "{pergunta}\n\n"
            "Gere uma resposta estruturada em Markdown com análise de concentração por segmento, "
            "pontos de atenção e proposta de rebalanceamento qualitativa."
        ),
    },
    "briefing_semanal": {
        "version": "1.0",
        "system": (
            "Você é um analista macroeconômico focado no mercado de FIIs. Sua missão é resumir as "
            "principais mudanças ocorridas no portfólio e no mercado ao longo da última semana."
        ),
        "user_template": (
            "Briefing Macro e de Carteira:\n"
            "Data de referência: {data_contexto}\n\n"
            "### Mudanças no Radar e Decisões Recentes:\n"
            "{alteracoes_radar_json}\n\n"
            "### Contexto de Juros (Selic & Focus):\n"
            "{macro_json}\n\n"
            "### Pergunta Extra do Usuário:\n"
            "{pergunta}\n\n"
            "Gere um briefing analítico em Markdown focando no impacto do cenário macro sobre o portfólio."
        ),
    }
}


def render_prompt(
    template_name: str,
    context: dict,
    pergunta: Optional[str] = None
) -> tuple[str, str, str]:
    """Renderiza os prompts do sistema e do usuário para o template informado.

    Retorna (system_prompt, user_prompt, version).
    """
    if template_name not in PROMPTS:
        raise ValueError(f"Template '{template_name}' desconhecido.")

    p_info = PROMPTS[template_name]
    sys_prompt = p_info["system"]
    version = p_info["version"]
    user_templ = p_info["user_template"]

    perg_str = pergunta if pergunta else "Nenhuma pergunta extra fornecida pelo usuário."

    if template_name == "analise_ticker":
        user_prompt = user_templ.format(
            ticker=context.get("ticker", "N/D"),
            data_contexto=context.get("data_contexto", "N/D"),
            score_total=context.get("score_total") if context.get("score_total") is not None else "n/d",
            score_breakdown_json=json.dumps(context.get("score_breakdown"), ensure_ascii=False),
            indicadores_json=json.dumps(context.get("indicadores"), ensure_ascii=False),
            decisao_json=json.dumps(context.get("decisao"), ensure_ascii=False),
            cdi_focus_json=json.dumps(context.get("cdi_focus"), ensure_ascii=False),
            flags_risco_json=json.dumps(context.get("flags_risco"), ensure_ascii=False),
            historico_52w_json=json.dumps(context.get("historico_52w"), ensure_ascii=False),
            saude_6m_json=json.dumps(context.get("saude_financeira_6m"), ensure_ascii=False),
            pergunta=perg_str,
            acao_local=context.get("decisao", {}).get("acao", "AGUARDAR"),
            concordancia_local=context.get("decisao", {}).get("nivel_concordancia", "BAIXA")
        )
    elif template_name == "oportunidade_rotacao":
        user_prompt = user_templ.format(
            segmento=context.get("segmento", "N/D"),
            vender_ticker=context.get("vender_ticker", "N/D"),
            comprar_ticker=context.get("comprar_ticker", "N/D"),
            spread_pvp_percentil=context.get("spread_pvp_percentil") if context.get("spread_pvp_percentil") is not None else "n/d",
            spread_dy_gap_percentil=context.get("spread_dy_gap_percentil") if context.get("spread_dy_gap_percentil") is not None else "n/d",
            delta_score=context.get("delta_score") if context.get("delta_score") is not None else "n/d",
            vender_score_total=context.get("vender", {}).get("score_total") if context.get("vender", {}).get("score_total") is not None else "n/d",
            vender_indicadores_json=json.dumps(context.get("vender", {}).get("indicadores"), ensure_ascii=False),
            vender_flags_risco_json=json.dumps(context.get("vender", {}).get("flags_risco"), ensure_ascii=False),
            vender_decisao_json=json.dumps(context.get("vender", {}).get("decisao"), ensure_ascii=False),
            comprar_score_total=context.get("comprar", {}).get("score_total") if context.get("comprar", {}).get("score_total") is not None else "n/d",
            comprar_indicadores_json=json.dumps(context.get("comprar", {}).get("indicadores"), ensure_ascii=False),
            comprar_flags_risco_json=json.dumps(context.get("comprar", {}).get("flags_risco"), ensure_ascii=False),
            comprar_decisao_json=json.dumps(context.get("comprar", {}).get("decisao"), ensure_ascii=False),
            pergunta=perg_str
        )
    elif template_name == "revisao_carteira":
        user_prompt = user_templ.format(
            data_contexto=context.get("data_contexto", "N/D"),
            posicoes_json=json.dumps(context.get("posicoes"), ensure_ascii=False),
            alertas_json=json.dumps(context.get("alertas"), ensure_ascii=False),
            pergunta=perg_str
        )
    elif template_name == "briefing_semanal":
        user_prompt = user_templ.format(
            data_contexto=context.get("data_contexto", "N/D"),
            alteracoes_radar_json=json.dumps(context.get("alteracoes_radar"), ensure_ascii=False),
            macro_json=json.dumps(context.get("macro"), ensure_ascii=False),
            pergunta=perg_str
        )
    else:
        raise ValueError(f"Pre-processamento para '{template_name}' não implementado.")

    return sys_prompt, user_prompt, version
