from __future__ import annotations

import streamlit as st
from frontend.streamlit.api_client.local_analyses import register_analysis, save_analysis_changes
from frontend.streamlit.presentation.thermography_data import load_thermography_history
from frontend.streamlit.presentation.player_data import load_player_dashboard_data
from frontend.streamlit.components.thermography.timeline import views_for_storage, remember_timeline_entry


def register_prepared_analysis(*, athlete_id, athlete_name, collected_at, mass,
                               pain_score, observations, views, items, pair_signature, overwrite=False, sync_widgets=True):
    source = st.session_state.get('thermal_edit_source')
    draft = st.session_state.get('thermal_saved_draft')
    save = save_analysis_changes if source or overwrite or draft else register_analysis
    extra = dict(source=source, overwrite=overwrite) if source or overwrite or draft else {}
    if draft:
        extra['draft'] = draft
    result = save(
        athlete_id, athlete_name, collected_at, views_for_storage(views, items),
        mass=mass, pain_score=pain_score, observations=observations, **extra,
    )
    remember_timeline_entry(result['analysis'])
    st.session_state.setdefault('thermal_draft', {}).update(player=athlete_id, mass=float(mass), pain=int(pain_score), notes=observations, collected_at=collected_at)
    updates = {'thermography_player': athlete_id, 'thermography_mass': float(mass),
               'thermography_pain_score': int(pain_score), 'thermography_observations': observations}
    if sync_widgets:
        st.session_state.update(updates)
        st.session_state.pop(f'thermography_record_editor_{pair_signature}', None)
    else:
        st.session_state['thermal_metadata_sync'] = dict(updates=updates, editor=f'thermography_record_editor_{pair_signature}')
    load_thermography_history.clear()
    load_player_dashboard_data.clear()
    st.session_state['thermal_registered_analysis'] = {
        'signature': pair_signature, 'id': result['analysis']['id'],
        'date': collected_at, 'athlete_id': athlete_id,
    }
    st.session_state['thermography_flash'] = (
        f"Análise de {collected_at:%d/%m/%Y} registrada no banco local e adicionada à timeline."
    )
    if all(key in result['analysis'] for key in ('athlete_id', 'collected_at', 'id', 'created_at')):
        st.session_state['thermal_edit_source'] = {key: result['analysis'][key]
            for key in ('athlete_id', 'collected_at', 'id', 'created_at')}
    if source:
        st.session_state['thermography_flash'] = f'Alterações de {collected_at:%d/%m/%Y} salvas no banco local e na timeline.'
    st.session_state['thermal_registration_complete'] = True
    st.session_state.pop('thermal_saved_draft', None)
    st.session_state.pop('thermal_overwrite_request', None)
    return result

