"""Cartões clicáveis do seletor; não altera os cartões do mural de jogadores."""
import re
import streamlit as st
from frontend.streamlit.presentation.player_data import player_name


def _plain_markdown(value):
    """Exibir dados de cadastro como texto, sem imagens ou links Markdown."""
    text = ' '.join(str(value).split())
    return re.sub(r'([\\`*_{}\[\]()<>#+.!|~\-])', r'\\\1', text)


def render_player_card_style():
    # Escopo exclusivo dos botões de atletas, sem afetar o mural ou outros botões.
    st.html('''<style>
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] button {
            width: 100%;
            min-height: 112px;
            padding: .9rem 1rem;
            border: 1px solid var(--mac-border, #d6dfeb);
            border-radius: .9rem;
            background: var(--mac-surface, white);
            color: var(--mac-text, #111827);
            justify-content: flex-start;
            align-items: center;
            gap: .75rem;
            text-align: left;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .025);
            cursor: pointer;
        }
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] button:hover {
            border-color: #0866c6;
            background: #f0f6ff;
        }
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] button:focus-visible {
            outline: 2px solid #0866c6;
            outline-offset: 2px;
        }
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] button > div,
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] button > div > span {
            display: flex;
            width: 100%;
            justify-content: flex-start;
            align-items: flex-start;
            gap: .75rem;
        }
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] span:has(> [data-testid="stIconEmoji"]) {
            width: 58px;
            height: 58px;
            flex: 0 0 58px;
            margin: 0;
        }
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] [data-testid="stMarkdownContainer"] {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            flex: 1;
            text-align: left;
            min-width: 0;
            overflow-wrap: anywhere;
        }
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] button p {
            display: block;
            width: 100%;
            white-space: normal;
            color: var(--mac-muted, #64748b);
            font-size: .75rem;
            margin: .15rem 0;
        }
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] button strong {
            color: var(--mac-text, #111827);
            font-size: 1rem;
            text-transform: uppercase;
        }
        .st-key-analysis_browser_results [class*="st-key-analysis_player_"] [data-testid="stIconEmoji"] {
            display: grid;
            place-items: center;
            width: 58px;
            height: 58px;
            flex: 0 0 58px;
            border-radius: .7rem;
            background: linear-gradient(145deg, #e5e7eb, #cbd5e1);
            font-size: 2rem;
        }
    </style>''')


def selectable_player_card(athlete, *, on_click):
    name = _plain_markdown(player_name(athlete))
    position = _plain_markdown(athlete.get('posicao') or 'Sem posição')
    status = _plain_markdown(athlete.get('status') or 'ativo')
    return st.button(
        f'**{name}**\n\n{position}\n\nCadastro: {status}',
        icon='👤', width='stretch', key=f'analysis_player_{athlete["id_atleta"]}',
        on_click=on_click, args=(int(athlete['id_atleta']),),
    )
