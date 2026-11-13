"""Aviso fixo de honestidade do produto: o app e DESCRITIVO, nao preditivo."""
import streamlit as st

AVISO_CURTO = (
    "Os indicadores descrevem o estado dos fundos. Em teste com os dados disponiveis, "
    "nenhum deles mostrou poder de prever retorno. Nenhum sinal aqui e recomendacao "
    "de compra ou venda."
)

_RESUMO_LOCAL = """
**Estudo em painel pre-registrado** (110 fundos, 04/2022 a 10/2026, 100 testes):
nenhum indicador do sistema (P/VP, DY gap, score, saude, radar, episodios) mostrou
evidencia de prever qual fundo rende mais. Nenhum teste sobreviveu a correcao para
multiplos testes pelo criterio pre-registrado (Benjamini-Hochberg e Bonferroni).
Sem correcao, 11 dos 100 testes tem p < 0.05 (esperado por acaso: ~5); uma variante
mais branda (p normal) aponta 5 pares, nao sustentados pelo criterio principal.

Limites: ~4 anos de dados, horizonte de 12 meses com poder quase nulo.
Ausencia de evidencia nao prova que nao ha efeito, mas o sistema nao deve ser lido como previsao.

Arquivos: `docs/pesquisa/painel_2026-11/` (PREREGISTRO.md, out_04.txt, out_05.txt, tabela_prereg.csv).
"""


def _resumo_backend() -> str | None:
    """Texto do modulo de evidencia do backend, se existir (nomes tolerantes)."""
    try:
        from fii_analysis.decision import evidencia
    except Exception:
        try:
            from src.fii_analysis.decision import evidencia
        except Exception:
            return None
    try:
        txt = evidencia.texto_evidencia()
        cand = getattr(evidencia, "EVIDENCIA", {}).get("candidato_nao_confirmado")
        extra = f"\n\nCandidato nao confirmado: {cand}." if cand else ""
        return txt + extra + "\n\nArquivos: `docs/pesquisa/painel_2026-11/`."
    except Exception:
        return None


def render_aviso_evidencia() -> None:
    st.info(AVISO_CURTO)
    with st.expander("Resumo do estudo de evidencia"):
        st.markdown(_resumo_backend() or _RESUMO_LOCAL)


# Rotulos descritivos para as etiquetas vindas do backend (nunca como chamada de acao).
_ROTULO_ACAO = {
    "COMPRAR": "indicadores favoraveis",
    "VENDER": "indicadores desfavoraveis",
    "AGUARDAR": "neutro",
    "EVITAR": "alerta de risco",
    "AUMENTAR": "indicadores favoraveis",
    "REDUZIR": "indicadores desfavoraveis",
    "SAIR": "indicadores desfavoraveis (forte)",
    "EVITAR_NOVOS_APORTES": "alerta de risco",
    "HOLD": "sem destaque",
}


def rotulo_acao(acao: str | None) -> str:
    return _ROTULO_ACAO.get(acao or "", acao or "")


def rotulo_flags(flags: str | None) -> str:
    """'destr.capital' vira alerta de risco descritivo."""
    return (flags or "").replace("destr.capital", "alerta de risco: VP/cota em queda")


def csv_sem_comentarios(texto: str) -> str:
    """Remove linhas '# ...' do inicio do CSV (o aviso fica na tela, nao no arquivo)."""
    return "\n".join(l for l in texto.splitlines() if not l.startswith("#")) + "\n"
