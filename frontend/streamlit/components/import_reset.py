"""Descarte local de uma importação; nenhuma operação de banco é executada."""
import streamlit as st


def upload_key(kind: str, base: str) -> str:
    generation = st.session_state.get(f'{kind}_upload_generation', 0)
    return f'{base}_{generation}' if generation else base


def clear_import(kind: str) -> None:
    if kind not in ('gps', 'jump'):
        raise ValueError('Importação desconhecida.')
    prefixes = (('gps_extraction_', 'gps_editor_', 'gps_validate_', 'gps_confirm_', 'gps_consolidated_')
                if kind == 'gps' else ('jump_import_',))
    extra_keys = {'gps_import_validation', 'gps_import_results'} if kind == 'gps' else set()
    for key in list(st.session_state):
        if key in extra_keys or key.startswith(prefixes):
            st.session_state.pop(key, None)
    # Não atribuir valores ao file_uploader já instanciado. Uma chave nova
    # cria um upload vazio no próximo rerun, inclusive para o mesmo arquivo.
    generation_key = f'{kind}_upload_generation'
    st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1
    st.session_state[f'{kind}_import_clear_message'] = 'Arquivos e dados extraídos foram limpos. Nenhum registro do banco foi alterado.'


@st.dialog('Limpar dados extraídos')
def confirm_clear_import(kind: str) -> None:
    st.warning('Os arquivos selecionados, os dados extraídos e suas edições serão descartados deste componente. Registros já enviados ao banco não serão alterados.')
    cancel, confirm = st.columns(2)
    if cancel.button('Cancelar', key=f'{kind}_clear_cancel', width='stretch'):
        st.rerun()
    if confirm.button('Confirmar limpeza', type='primary', key=f'{kind}_clear_confirm',
                      width='stretch', on_click=clear_import, args=(kind,)):
        st.rerun()


@st.fragment
def render_clear_import(kind: str) -> None:
    """Abre a confirmação sem repetir consultas ou reconstruir a importação."""
    if st.button('Limpar dados extraídos', key=f'{kind}_clear_extraction', width='stretch'):
        confirm_clear_import(kind)


def show_clear_message(kind: str) -> None:
    if message := st.session_state.pop(f'{kind}_import_clear_message', None):
        st.success(message)
