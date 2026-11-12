"""Salvar em qualquer etapa; rascunhos e confirmação explícita de sobrescrita."""
import base64
import hashlib
import math
import streamlit as st
from frontend.streamlit.api_client.local_analyses import save_draft
from frontend.streamlit.api_client.service_gateway import ApiClientError
from frontend.streamlit.api_client.contracts import current_sao_paulo_date
from .registration import register_prepared_analysis

ITEM_FIELDS = {'minimum_temperature', 'maximum_temperature', 'threshold_percentage', 'threshold_temperature',
               'threshold_mode', 'image_rotation', 'manual_boxes', 'manual_colorbar_box', 'part_settings_v4',
               'mask_seeds', 'mask_revision', 'saved_analysis', 'saved_analysis_revision'}


def snapshot_state():
    from .wizard import rotated_view
    state = dict(step=st.session_state.get('thermal_step', 0),
                 draft=dict(st.session_state.get('thermal_draft', {})), uploads={}, items={})
    day = state['draft'].get('collected_at')
    state['draft']['collected_at'] = day.isoformat() if day else None
    source = st.session_state.get('thermal_edit_source')
    state['source'] = {**source, 'collected_at': source['collected_at'].isoformat()} if source else None
    for view, upload in st.session_state.get('thermal_uploads', {}).items():
        state['uploads'][view] = dict(name=upload['name'], rotation=upload['rotation'],
            content=base64.b64encode(upload['content']).decode('ascii'))
        _image, _content, signature = rotated_view(upload['content'], upload['rotation'])
        key = f'{view}:{signature}'
        original = st.session_state.get('thermography_items', {}).get(key)
        if not original:
            continue
        item = {name: value for name, value in original.items() if name in ITEM_FIELDS}
        analysis = original.get('analysis')
        if analysis:
            from .editor import analysis_configuration
            config = analysis_configuration(original['minimum_temperature'], original['maximum_temperature'],
                                            original.get('threshold_temperature'), original)
            if original.get('analysis_config') == config:
                item['saved_analysis'] = dict(masks=analysis['masks'], temperatures=analysis['temperatures'], boxes=analysis['boxes'],
                    minimum_temperature=original['minimum_temperature'], maximum_temperature=original['maximum_temperature'],
                    colorbar_box=original.get('manual_colorbar_box'), image_rotation=upload['rotation'])
            else:
                item.pop('saved_analysis', None)
        state['items'][key] = item
    return state


def _ready_analysis(item, rotation):
    """Reutilizar somente matrizes/máscaras compatíveis com os ajustes atuais."""
    from .editor import analysis_configuration
    try:
        minimum, maximum = item['minimum_temperature'], item['maximum_temperature']
        threshold = item.get('threshold_temperature')
        if not all(math.isfinite(value) for value in (minimum, maximum, threshold)) or not minimum < maximum or not minimum <= threshold <= maximum:
            return None
        if item.get('image_rotation', 0) != rotation:
            return None
        analysis = item.get('analysis')
        if analysis is not None:
            if item.get('analysis_config') != analysis_configuration(minimum, maximum, threshold, item):
                return None
        else:
            saved = item.get('saved_analysis')
            if not saved or saved['minimum_temperature'] != minimum or saved['maximum_temperature'] != maximum or saved['image_rotation'] != rotation:
                return None
            if item.get('manual_colorbar_box') != saved.get('colorbar_box') or any(
                box != saved['boxes'].get(side) for side, box in item.get('manual_boxes', {}).items()
            ):
                return None
            analysis = dict(masks=saved['masks'], temperatures=saved['temperatures'],
                            boxes=saved['boxes'], colorbar_box=saved.get('colorbar_box'), threshold=threshold)
        if not all(side in analysis['masks'] and side in analysis['boxes'] for side in ('left', 'right')):
            return None
        if analysis['temperatures'] is None:
            return None
        return analysis
    except (KeyError, TypeError, ValueError):
        return None


def _complete_values(step):
    if step == 6:
        # A tabela desta etapa é a fonte atual dos campos editáveis, inclusive nulos.
        return st.session_state.get('thermal_prepared_record')
    from .wizard import rotated_view
    uploads = st.session_state.get('thermal_uploads', {})
    if not all(view in uploads for view in ('front', 'back')):
        return None
    draft = st.session_state.get('thermal_draft', {})
    views, items = {}, {}
    current_items = st.session_state.get('thermography_items', {})
    for view in ('front', 'back'):
        upload = uploads[view]
        if upload.get('error'):
            return None
        try:
            image, content, signature = rotated_view(upload['content'], upload['rotation'])
        except ValueError:
            return None
        key = f'{view}:{signature}'
        item = current_items.get(key)
        analysis = _ready_analysis(item, upload['rotation']) if item else None
        if analysis is None:
            return None
        views[view] = dict(image=image, content=content, signature=signature, name=upload['name'])
        items[key] = {**item, 'analysis': analysis}
    signature = hashlib.sha256((views['front']['signature'] + views['back']['signature']).encode()).hexdigest()
    players = st.session_state.get('thermal_available_players', {})
    player = draft.get('player')
    return dict(athlete_id=player, athlete_name=players.get(player, {}).get('nome', ''), mass=draft.get('mass'),
        pain_score=draft.get('pain'), observations=draft.get('notes', ''), collected_at=draft.get('collected_at'),
        views=views, items=items, pair_signature=signature)


def _attempt(request, overwrite=False):
    player = request['state']['draft'].get('player') if request['kind'] == 'draft' else request['values'].get('athlete_id')
    if not _require_player(player):
        return False
    st.session_state.pop('thermal_save_error', None)
    try:
        if request['kind'] == 'draft':
            entry = save_draft(request['state'], draft=st.session_state.get('thermal_saved_draft'), overwrite=overwrite)
            st.session_state['thermal_saved_draft'] = {key: entry[key] for key in ('id', 'created_at')}
            from frontend.streamlit.presentation.thermography_data import load_thermography_history
            from frontend.streamlit.presentation.player_data import load_player_dashboard_data
            load_thermography_history.clear()
            load_player_dashboard_data.clear()
        else:
            register_prepared_analysis(**request['values'], overwrite=overwrite, sync_widgets=False)
        label = 'Análise parcial' if request['kind'] == 'draft' else 'Análise'
        st.session_state['thermography_saved_notice'] = f'{label} salva. Você poderá visualizá-la em Ver análises anteriores.'
        st.session_state.pop('thermography_flash', None)
        st.session_state['thermal_reset_after_save'] = True
        st.session_state.pop('thermal_save_prompt', None)
        st.session_state.pop('thermal_save_request', None)
        st.session_state['thermal_save_done'] = True
        return True
    except ApiClientError as error:
        if isinstance(error.detail, dict) and error.detail.get('code') == 'analysis_date_conflict':
            st.session_state['thermal_save_request'] = request
            st.session_state['thermal_save_prompt'] = 'overwrite'
        else:
            st.session_state['thermal_save_error'] = str(error)
    except ValueError as error:
        st.session_state['thermal_save_error'] = str(error)
    except Exception:
        st.session_state['thermal_save_error'] = 'Não foi possível salvar. Confira a API e os arquivos locais antes de tentar novamente.'
    return False


def _cancel():
    st.session_state.pop('thermal_save_prompt', None)
    st.session_state.pop('thermal_save_request', None)
    st.session_state.pop('thermal_save_error', None)
    st.session_state['thermal_save_done'] = True


def _require_player(player):
    if player:
        return True
    for key in ('thermal_save_prompt', 'thermal_save_request', 'thermal_save_error'):
        st.session_state.pop(key, None)
    st.session_state['thermal_step'] = 0
    st.session_state['thermal_player_required'] = True
    st.session_state['thermal_save_done'] = True
    return False


@st.dialog('Salvar análise', on_dismiss=_cancel)
def confirm_save():
    if st.session_state.pop('thermal_save_done', False):
        st.rerun()
    request = st.session_state.get('thermal_save_request')
    if not request:
        st.rerun()
    player = request['state']['draft'].get('player') if request['kind'] == 'draft' else request['values'].get('athlete_id')
    if not _require_player(player):
        st.rerun()
    incomplete = st.session_state.get('thermal_save_prompt') == 'incomplete'
    st.warning('A análise atual possui etapas pendentes. Deseja salvar mesmo assim?' if incomplete else
               'Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?')
    no, yes = st.columns(2)
    no.button('Não, voltar', width='stretch', key='thermal_save_cancel', on_click=_cancel)
    yes.button('Salvar mesmo assim' if incomplete else 'Sim, sobrescrever', type='primary', width='stretch',
               key='thermal_save_confirm', on_click=_attempt, args=(request, not incomplete))
    if error := st.session_state.get('thermal_save_error'):
        st.error(error)


def render_pending_save():
    if notice := st.session_state.pop('thermography_saved_notice', None):
        st.toast(notice, icon='✅')
    if st.session_state.pop('thermal_player_required', False):
        st.toast('Selecione um jogador antes de salvar a análise.', icon='⚠️')
    if st.session_state.get('thermal_save_prompt'):
        confirm_save()
    elif error := st.session_state.get('thermal_save_error'):
        st.error(error)


def render_save_button(step):
    if st.button('Salvar análise', key='thermal_save_analysis', width='stretch'):
        st.session_state.pop('thermal_save_done', None)
        st.session_state.pop('thermal_save_error', None)
        values = _complete_values(step)
        player = values.get('athlete_id') if values is not None else st.session_state.get('thermal_draft', {}).get('player')
        if not _require_player(player):
            st.rerun()
        complete = values and values.get('athlete_id') and values.get('mass') is not None and values.get('pain_score') is not None and values.get('collected_at')
        if complete:
            if _attempt(dict(kind='complete', values=values)):
                st.rerun()
        else:
            st.session_state['thermal_save_request'] = dict(kind='draft', state=snapshot_state())
            st.session_state['thermal_save_prompt'] = 'incomplete'
