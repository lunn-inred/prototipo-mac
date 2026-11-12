"""Estado temporário do assistente; não modifica arquivos nem registros."""
import streamlit as st


def set_metadata_widgets(draft, *, overwrite=True):
    """Sincronizar antes de renderizar; sobrescrever só ao abrir/limpar análise."""
    values = dict(thermography_player=draft.get('player'), thermography_mass=draft.get('mass'),
                  thermography_pain_score=draft.get('pain'), thermography_observations=draft.get('notes') or '')
    for key, value in values.items():
        if overwrite or key not in st.session_state:
            st.session_state[key] = value


def clear_analysis_draft():
    generation = st.session_state.get('thermal_upload_generation', 0) + 1
    for key in list(st.session_state):
        if key.startswith(('thermal_', 'wizard_', 'thermography_front_upload',
                           'thermography_back_upload', 'thermography_record_editor_', 'parts_side_', 'parts_canvas_')) or key in {
                'thermography_items', 'thermography_metrics', 'thermography_player',
                'thermography_mass', 'thermography_pain_score', 'thermography_observations'}:
            del st.session_state[key]
    st.session_state['thermal_upload_generation'] = generation


def reset_after_saved_analysis():
    """Limpar antes de criar widgets; o aviso sobrevive ao rerun, não os dados."""
    if st.session_state.pop('thermal_reset_after_save', False):
        clear_analysis_draft()
        # Os widgets da primeira etapa podem continuar montados no navegador.
        # Excluir as chaves limpa o Python, mas não envia set_value ao cliente.
        set_metadata_widgets({})
        st.session_state.pop('thermography_flash', None)
        st.session_state['thermal_step'] = 0
