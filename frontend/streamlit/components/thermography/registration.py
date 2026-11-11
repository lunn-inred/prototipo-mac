from __future__ import annotations

import streamlit as st
from frontend.streamlit.api_client.contracts import current_sao_paulo_date
from frontend.streamlit.api_client.local_analyses import register_analysis, save_analysis_changes
from frontend.streamlit.api_client.service_gateway import ApiClientError
from frontend.streamlit.presentation.thermography_data import load_thermography_history
from frontend.streamlit.presentation.player_data import load_player_dashboard_data
from frontend.streamlit.components.thermography.timeline import views_for_storage, remember_timeline_entry


def register_prepared_analysis(*, athlete_id, athlete_name, collected_at, mass,
                               pain_score, observations, views, items, pair_signature, overwrite=False):
    source = st.session_state.get('thermal_edit_source')
    save = save_analysis_changes if source or overwrite else register_analysis
    extra = dict(source=source, overwrite=overwrite) if source or overwrite else {}
    result = save(
        athlete_id, athlete_name, collected_at, views_for_storage(views, items),
        mass=mass, pain_score=pain_score, observations=observations, **extra,
    )
    remember_timeline_entry(result['analysis'])
    st.session_state.setdefault('thermal_draft', {}).update(player=athlete_id, mass=float(mass), pain=int(pain_score), notes=observations)
    for key, value in {'thermography_player': athlete_id, 'thermography_mass': float(mass),
                       'thermography_pain_score': int(pain_score), 'thermography_observations': observations}.items():
        st.session_state[key] = value
    st.session_state.pop(f'thermography_record_editor_{pair_signature}', None)
    load_thermography_history.clear()
    load_player_dashboard_data.clear()
    st.session_state['thermal_registered_analysis'] = {
        'signature': pair_signature, 'id': result['analysis']['id'],
        'date': collected_at, 'athlete_id': athlete_id,
    }
    st.session_state['thermography_flash'] = (
        f"Análise de {collected_at:%d/%m/%Y} registrada no banco local e adicionada à timeline."
    )
    if source:
        st.session_state['thermal_edit_source'] = {key: result['analysis'][key]
            for key in ('athlete_id', 'collected_at', 'id', 'created_at')}
        st.session_state['thermography_flash'] = f'Alterações de {collected_at:%d/%m/%Y} salvas no banco local e na timeline.'
    st.session_state['thermal_registration_complete'] = True
    st.session_state.pop('thermal_overwrite_request', None)
    return result


def _submit(date_key, values, overwrite=False):
    if not st.session_state.get('thermal_edit_source') and not overwrite and st.session_state.get('thermal_registered_analysis', {}).get('signature') == values['pair_signature']:
        return
    st.session_state.pop('thermal_registration_error', None)
    try:
        register_prepared_analysis(collected_at=st.session_state[date_key], overwrite=overwrite, **values)
    except ApiClientError as error:
        if isinstance(error.detail, dict) and error.detail.get('code') == 'analysis_date_conflict':
            st.session_state['thermal_overwrite_request'] = dict(date=st.session_state[date_key], values=values)
        else:
            st.session_state.pop('thermal_overwrite_request', None)
            st.session_state['thermal_registration_error'] = str(error)
    except ValueError as error:
        st.session_state.pop('thermal_overwrite_request', None)
        st.session_state['thermal_registration_error'] = str(error)
    except Exception:
        st.session_state.pop('thermal_overwrite_request', None)
        st.session_state['thermal_registration_error'] = 'Não foi possível concluir o registro. Confira a API e o banco local antes de tentar novamente.'


def cancel_overwrite():
    st.session_state.pop('thermal_overwrite_request', None)
    st.session_state.pop('thermal_registration_error', None)


@st.dialog('Salvar análise')
def confirm_analysis_registration(**values):
    signature = values['pair_signature']
    if st.session_state.pop('thermal_registration_complete', False):
        st.rerun()
    st.caption('Confirme a data. As medidas serão salvas no banco local e as imagens ficarão disponíveis na timeline.')
    date_key = f'thermal_collection_date_{signature}'
    source = st.session_state.get('thermal_edit_source')
    pending = st.session_state.get('thermal_overwrite_request')
    st.date_input('Data de registro da coleta', value=source['collected_at'] if source else current_sao_paulo_date(),
                  key=date_key, disabled=bool(pending))
    if pending:
        st.warning('Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?')
        yes, no = st.columns(2)
        yes.button('Sim, sobrescrever', type='secondary', width='stretch', key='thermal_overwrite_yes',
                   on_click=_submit, args=(date_key, pending['values'], True))
        no.button('Não, voltar', width='stretch', key='thermal_overwrite_no', on_click=cancel_overwrite)
    else:
        st.button('Salvar alterações' if source else 'Confirmar registro', type='secondary', width='stretch',
                  key=f'confirm_analysis_{signature}', on_click=_submit, args=(date_key, values))
    if error := st.session_state.get('thermal_registration_error'):
        st.error(error)
    if st.button('Concluir', type='primary', width='stretch', key=f'close_analysis_{signature}'):
        st.rerun()

