"""Cartões de análise clicáveis, com miniatura no próprio botão nativo."""
import base64
import io
import streamlit as st


def render_analysis_card_style():
    st.html('''<style>
        [class*="st-key-analysis_card_"] button {
            width: 100%;
            padding: .9rem;
            border: 1px solid var(--mac-border, #d6dfeb);
            border-radius: .9rem;
            background: var(--mac-surface, white);
            cursor: pointer;
        }
        [class*="st-key-analysis_card_"] button:hover {
            border-color: #0866c6;
            background: #f0f6ff;
        }
        [class*="st-key-analysis_card_"] button:focus-visible {
            outline: 2px solid #0866c6;
            outline-offset: 2px;
        }
        [class*="st-key-analysis_card_"] button > div,
        [class*="st-key-analysis_card_"] button > div > span {
            width: 100%;
        }
        [class*="st-key-analysis_card_"] [data-testid="stMarkdownContainer"] {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 100%;
            min-width: 0;
            text-align: center;
        }
        [class*="st-key-analysis_card_"] button p {
            display: block;
            width: 100%;
            margin: .25rem 0;
            white-space: normal;
            overflow-wrap: anywhere;
            font-size: .8rem;
            color: var(--mac-muted, #64748b);
        }
        [class*="st-key-analysis_card_"] button strong {
            font-size: 1rem;
            color: var(--mac-text, #111827);
        }
        [class*="st-key-analysis_card_"] button img {
            display: block;
            width: 100% !important;
            height: 180px !important;
            max-height: 180px !important;
            max-width: 100%;
            object-fit: contain;
            margin: 0 auto .4rem;
        }
    </style>''')


def selectable_analysis_card(entry, *, key, on_click, args, details):
    thumbnail = entry['thumbnail'].copy()
    thumbnail.thumbnail((250, 180))
    buffer = io.BytesIO()
    thumbnail.save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    date_label = entry['collected_at'].strftime('%d/%m/%Y')
    status = '\n\n:red[Análise incompleta]' if entry.get('is_draft') else ''
    label = (f'![Análise de {date_label}](data:image/png;base64,{encoded})'
             f'\n\n**{date_label}**{status}\n\n{details}')
    with st.container(key=f'analysis_card_{key}'):
        return st.button(label, key=key, width='stretch', wrap=True,
                         on_click=on_click, args=args)
