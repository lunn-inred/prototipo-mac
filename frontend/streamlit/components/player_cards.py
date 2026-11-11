"""Cartões compactos do seletor de atletas; o mural mantém seu HTML original."""
from html import escape
import streamlit as st
from frontend.streamlit.presentation.player_data import player_name


def render_player_card_style():
    st.markdown(
        """
        <style>
        .players-grid-title {
            margin-bottom: .15rem;
        }
        .players-subtitle {
            color: var(--mac-muted);
            margin-bottom: 1rem;
        }
        .player-card {
            background: var(--mac-surface);
            border: 1px solid var(--mac-border);
            border-radius: .9rem;
            padding: .9rem 1rem;
            min-height: 188px;
            margin-bottom: 1rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .025);
        }
        .player-card-header {
            display: flex;
            align-items: flex-start;
            gap: .75rem;
            min-height: 62px;
        }
        .player-avatar {
            width: 58px;
            height: 58px;
            flex: 0 0 58px;
            display: grid;
            place-items: center;
            border-radius: .7rem;
            background: linear-gradient(145deg, #e5e7eb, #cbd5e1);
            color: #334155;
            font-size: 2rem;
        }
        .player-identity {
            min-width: 0;
            flex: 1;
        }
        .player-name {
            color: var(--mac-text);
            font-size: 1rem;
            font-weight: 780;
            line-height: 1.2;
            text-transform: uppercase;
            overflow-wrap: anywhere;
        }
        .player-position, .player-eva {
            color: var(--mac-muted);
            font-size: .75rem;
            margin-top: .22rem;
        }
        .risk-badge {
            border-radius: 999px;
            padding: .27rem .58rem;
            font-size: .62rem;
            font-weight: 800;
            letter-spacing: .035em;
            text-transform: uppercase;
            white-space: nowrap;
        }
        .risk-badge.risk {
            color: #b91c1c;
            background: #fee2e2;
        }
        .risk-badge.attention {
            color: #b45309;
            background: #fef3c7;
        }
        .risk-badge.ok {
            color: #166534;
            background: #dcfce7;
        }
        .risk-badge.neutral {
            color: #475569;
            background: #f1f5f9;
        }
        .player-divider {
            height: 1px;
            background: var(--mac-border);
            margin: .75rem 0;
        }
        .player-metrics {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: .75rem;
        }
        .player-metric-label {
            color: var(--mac-muted);
            font-size: .61rem;
            font-weight: 750;
            letter-spacing: .035em;
            text-transform: uppercase;
            white-space: nowrap;
        }
        .player-metric-value {
            color: var(--mac-text);
            font-size: .92rem;
            font-weight: 760;
            margin-top: .22rem;
        }
        .player-metric-deviation {
            color: var(--mac-muted);
            font-size: .65rem;
            margin-top: .15rem;
        }
        @media (max-width: 900px) {
            .player-metrics {
                gap: .4rem;
            }
            .player-metric-label {
                white-space: normal;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<style>.player-card.compact { min-height: unset; }</style>', unsafe_allow_html=True)


def player_identity(athlete, *, extra='', badge=''):
    return f'''
        <div class="player-card-header">
            <div class="player-avatar" aria-label="Imagem indisponível">👤</div>
            <div class="player-identity">
                <div class="player-name">{escape(player_name(athlete))}</div>
                <div class="player-position">{escape(str(athlete.get('posicao') or 'Sem posição'))}</div>
                {extra}
                <div class="player-eva">Cadastro: {escape(str(athlete.get('status', 'ativo')))}</div>
            </div>
            {badge}
        </div>
    '''


def compact_player_card(athlete):
    return f'<div class="player-card compact">{player_identity(athlete)}</div>'
