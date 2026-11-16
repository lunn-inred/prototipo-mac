"""Cartões de análise clicáveis, com miniatura no próprio botão nativo."""
import base64
import io
import streamlit as st
from PIL import Image


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
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: .25rem .75rem;
            width: 100%;
            min-width: 0;
            text-align: center;
        }
        [class*="st-key-analysis_card_"] button p {
            grid-column: 1 / -1;
            display: block;
            width: 100%;
            margin: .25rem 0;
            white-space: normal;
            overflow-wrap: anywhere;
            font-size: .8rem;
            line-height: 1.25rem;
            color: var(--mac-muted, #64748b);
        }
        [class*="st-key-analysis_card_"] button p:has(img):has(strong) {
            grid-column: auto;
            display: flex;
            flex-direction: column;
            align-items: center;
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


def _image_markdown(image, description):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'![{description}](data:image/png;base64,{encoded})'


def selectable_analysis_card(entry, *, key, on_click, args, details):
    date_label = entry['collected_at'].strftime('%d/%m/%Y')
    if 'thumbnails' in entry:
        blocks = []
        for view, name in (('front', 'Frente'), ('back', 'Costas')):
            image = entry['thumbnails'].get(view)
            missing = image is None
            if missing:
                image = Image.new('RGB', (240,180), '#eef1f5')
            block = f'**{name}**\n{_image_markdown(image, name)}'
            # Reservar também a linha da legenda nas vistas disponíveis.
            block += '  \n' + ('Imagem não enviada' if missing else '\u200b')
            blocks.append(block)
        preview = '\n\n'.join(blocks)
    else:
        # Compatibilidade com resumos de APIs/fixtures anteriores.
        preview = _image_markdown(entry['thumbnail'], f'Análise de {date_label}')
    # A linha de status existe em ambos os casos, sem texto extra nas completas.
    status = '\n\n' + (':red[Análise incompleta]' if entry.get('is_draft') else '\u200b')
    label = f'{preview}\n\n**{date_label}**{status}\n\n{details}'
    with st.container(key=f'analysis_card_{key}'):
        return st.button(label, key=key, width='stretch',
                         on_click=on_click, args=args)
