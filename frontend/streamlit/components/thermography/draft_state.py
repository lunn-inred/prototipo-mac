"""Estado temporário do assistente; não modifica arquivos nem registros."""
import streamlit as st


def clear_analysis_draft():
    generation = st.session_state.get('thermal_upload_generation', 0) + 1
    for key in list(st.session_state):
        if key.startswith(('thermal_', 'wizard_', 'thermography_front_upload',
                           'thermography_back_upload', 'thermography_record_editor_')) or key in {
                'thermography_items', 'thermography_metrics', 'thermography_player',
                'thermography_mass', 'thermography_pain_score', 'thermography_observations'}:
            del st.session_state[key]
    st.session_state['thermal_upload_generation'] = generation
