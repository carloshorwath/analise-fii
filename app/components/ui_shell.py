import html

import streamlit as st


_DIARIO_PAGES = [
    "Hoje",
    "Panorama",
    "Carteira",
    "Radar",
    "Alertas",
]

_INVESTIGACAO_PAGES = [
    "Analise FII",
    "Fundamentos",
    "Event Study",
    "Fund Event Study",
]

_TECNICO_PAGES = [
    "Otimizador V2",
    "Episodios",
    "Walk-Forward",
]


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
        .fi-shell-hero {
            padding: 1.1rem 1.25rem 1rem 1.25rem;
            border: 1px solid #d8e2dc;
            border-radius: 18px;
            background:
                radial-gradient(circle at top right, rgba(15, 92, 77, 0.08), transparent 32%),
                linear-gradient(180deg, #f9fcfa 0%, #f4f8f6 100%);
            margin-bottom: 1rem;
        }
        .fi-shell-eyebrow {
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #0f5c4d;
            margin-bottom: 0.35rem;
        }
        .fi-shell-title {
            font-size: 2rem;
            font-weight: 700;
            color: #14221d;
            margin: 0 0 0.35rem 0;
        }
        .fi-shell-subtitle {
            font-size: 0.98rem;
            line-height: 1.55;
            color: #455a54;
            margin: 0;
            max-width: 980px;
        }
        .fi-shell-card {
            border: 1px solid #d8e2dc;
            border-radius: 16px;
            background: #ffffff;
            padding: 1rem 1rem 0.85rem 1rem;
            min-height: 180px;
        }
        .fi-shell-card h4 {
            margin: 0 0 0.55rem 0;
            color: #14221d;
            font-size: 1.02rem;
        }
        .fi-shell-card p {
            margin: 0 0 0.75rem 0;
            color: #516963;
            font-size: 0.92rem;
            line-height: 1.5;
        }
        .fi-shell-card ul {
            margin: 0;
            padding-left: 1.1rem;
            color: #29433c;
            font-size: 0.88rem;
            line-height: 1.5;
        }
        .fi-shell-inline-note {
            padding: 0.75rem 0.9rem;
            border-left: 4px solid #0f5c4d;
            background: #f4faf8;
            border-radius: 0 12px 12px 0;
            color: #29433c;
            margin: 0.6rem 0 1rem 0;
            font-size: 0.9rem;
        }
        .fi-shell-sidebar-group {
            margin-bottom: 1rem;
            padding: 0.8rem 0.85rem;
            border: 1px solid #e5ece8;
            border-radius: 14px;
            background: #fbfcfb;
        }
        .fi-shell-sidebar-group h4 {
            margin: 0 0 0.45rem 0;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #5f756e;
        }
        .fi-shell-sidebar-group ul {
            margin: 0;
            padding-left: 1rem;
            color: #41554f;
            font-size: 0.87rem;
            line-height: 1.45;
        }
        .fi-shell-sidebar-current {
            font-weight: 700;
            color: #0f5c4d;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str, section: str) -> None:
    inject_app_styles()
    st.markdown(
        f"""
        <div class="fi-shell-hero">
            <div class="fi-shell-eyebrow">{html.escape(section)}</div>
            <div class="fi-shell-title">{html.escape(title)}</div>
            <p class="fi-shell-subtitle">{html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_inline_note(text: str) -> None:
    st.markdown(
        f'<div class="fi-shell-inline-note">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_guide(current_page: str, group: str) -> None:
    inject_app_styles()

    groups = [
        ("Diario", _DIARIO_PAGES),
        ("Investigacao", _INVESTIGACAO_PAGES),
        ("Tecnico", _TECNICO_PAGES),
    ]

    with st.sidebar:
        st.markdown("### Fluxo do Produto")
        st.caption(
            "A navegacao foi organizada para separar uso diario, leitura de fundamentos "
            "e auditoria estatistica."
        )
        for label, pages in groups:
            items = []
            for page in pages:
                css = "fi-shell-sidebar-current" if page == current_page else ""
                items.append(f'<li class="{css}">{html.escape(page)}</li>')
            st.markdown(
                f"""
                <div class="fi-shell-sidebar-group">
                    <h4>{html.escape(label)}</h4>
                    <ul>{''.join(items)}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.caption(f"Contexto atual: {group} → {current_page}")


def render_home_card(title: str, description: str, bullets: list[str]) -> None:
    items = "".join(f"<li>{html.escape(item)}</li>" for item in bullets)
    st.markdown(
        f"""
        <div class="fi-shell-card">
            <h4>{html.escape(title)}</h4>
            <p>{html.escape(description)}</p>
            <ul>{items}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
