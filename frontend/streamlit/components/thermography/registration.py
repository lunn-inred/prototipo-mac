from __future__ import annotations

import streamlit as st
from frontend.streamlit.api_client.contracts import current_sao_paulo_date
from frontend.streamlit.api_client.local_analyses import register_analysis
from frontend.streamlit.presentation.thermography_data import load_thermography_history
from frontend.streamlit.presentation.player_data import load_player_dashboard_data
from frontend.streamlit.components.thermography.timeline import views_for_storage, remember_timeline_entry


def register_prepared_analysis(*, athlete_id, athlete_name, collected_at, mass,
                               pain_score, observations, views, items, pair_signature):
    result = register_analysis(
        athlete_id, athlete_name, collected_at, views_for_storage(views, items),
        mass=mass, pain_score=pain_score, observations=observations,
    )
    remember_timeline_entry(result['analysis'])
    load_thermography_history.clear()
    load_player_dashboard_data.clear()
    st.session_state['thermal_registered_analysis'] = {
        'signature': pair_signature, 'id': result['analysis']['id'],
        'date': collected_at, 'athlete_id': athlete_id,
    }
    st.session_state['thermography_flash'] = (
        f"Análise de {collected_at:%d/%m/%Y} registrada no banco local e adicionada à timeline."
    )
    return result


def _submit(date_key, values):
    if st.session_state.get('thermal_registered_analysis', {}).get('signature') == values['pair_signature']:
        return
    st.session_state.pop('thermal_registration_error', None)
    try:
        register_prepared_analysis(collected_at=st.session_state[date_key], **values)
    except ValueError as error:
        st.session_state['thermal_registration_error'] = str(error)
    except Exception:
        st.session_state['thermal_registration_error'] = 'Não foi possível concluir o registro. Confira a API e o banco local antes de tentar novamente.'


@st.dialog('Registrar Análise')
def confirm_analysis_registration(**values):
    signature = values['pair_signature']
    saved = st.session_state.get('thermal_registered_analysis', {})
    if saved.get('signature') == signature:
        st.rerun()
    st.caption('Confirme a data. As medidas serão salvas no banco local e as imagens ficarão disponíveis na timeline.')
    date_key = f'thermal_collection_date_{signature}'
    st.date_input('Data de registro da coleta', value=current_sao_paulo_date(), key=date_key)
    st.button('Confirmar registro', type='secondary', width='stretch',
              key=f'confirm_analysis_{signature}', on_click=_submit, args=(date_key, values))
    if error := st.session_state.get('thermal_registration_error'):
        st.error(error)
    if st.button('Concluir', type='primary', width='stretch', key=f'close_analysis_{signature}'):
        st.rerun()

