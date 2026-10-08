"""Fluxo guiado; imagens e rascunho permanecem somente na sessão."""
import hashlib
import io

import numpy as np
import streamlit as st
from PIL import Image
from streamlit_drawable_konva import st_canvas

from frontend.streamlit.api_client.thermal_client import (
    annotate_boxes, image_regions, leg_part_metrics, DEFAULT_PART_CUTS,
    temperature_from_scale_percentage, scale_percentage_from_temperature,
)
from frontend.streamlit.components.thermography.editor import (
    LEGS, VIEW_LABELS, DEFAULT_MIN_TEMPERATURE, DEFAULT_MAX_TEMPERATURE,
    load_thermography, image_signature, cached_temperature_scale,
    _display_image, _parts_preview,
    edit_thermal_boxes, edit_thermal_mask, segmented_analysis,
)
from frontend.streamlit.presentation.thermography_data import athlete_label

STEPS = ('Dados da coleta', 'Imagens e rotação', 'Caixas e escala térmica',
         'Segmentação', 'Divisão anatômica', 'Revisão')


def rotated_view(content, degrees):
    image = load_thermography(content).rotate(degrees, expand=True)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    normalized = buffer.getvalue()
    return image, normalized, image_signature(normalized)


def cuts_from_objects(objects, extent, foot_at_end, coordinate='x'):
    """Converte as três linhas arrastadas em percentuais da coxa ao pé."""
    if len(objects) != 3 or extent <= 0:
        raise ValueError('Mantenha as três divisões na imagem.')
    positions = [float(obj[coordinate]) for obj in objects]
    if not all(np.isfinite(position) for position in positions):
        raise ValueError('As posições devem ser finitas.')
    percentages = sorted(round(100 * (p / extent if foot_at_end else 1 - p / extent))
                         for p in positions)
    if not 0 < percentages[0] < percentages[1] < percentages[2] < 100:
        raise ValueError('Os limites devem ficar dentro da perna e separados entre si.')
    return percentages


@st.dialog('Editar divisão anatômica', width='large')
def edit_parts(item_key, image, analysis):
    item = st.session_state['thermography_items'][item_key]
    side_label = st.radio('Perna', list(LEGS), horizontal=True,
                         key=f'parts_side_{item_key}')
    side = LEGS[side_label]
    setting = item['part_settings_v4'][side]
    axis = st.radio('Orientação', ['Vertical', 'Horizontal'],
                    index=0 if setting['axis'] == 'vertical' else 1,
                    horizontal=True, key=f'parts_axis_gui_{item_key}_{side}')
    direction = st.radio('Onde está a coxa?', ['Início (cima/esquerda)', 'Fim (baixo/direita)'],
                         index=0 if setting['foot_at_end'] else 1,
                         key=f'parts_direction_gui_{item_key}_{side}')
    vertical = axis == 'Vertical'
    foot_at_end = direction.startswith('Início')
    mask = analysis['masks'][side]
    ys, xs = np.nonzero(mask)
    if not len(xs):
        st.error('A máscara está vazia. Corrija a segmentação primeiro.')
        return
    bounds = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    preview = analysis['overlay'].crop(bounds)
    background, _ = _display_image(preview, max_width=620, max_height=300)
    extent = background.height if vertical else background.width
    coordinate = 'y' if vertical else 'x'
    drawing = {'objects': [dict(type='rect',
                               x=0 if vertical else extent * (cut / 100 if foot_at_end else 1-cut/100),
                               y=extent * (cut / 100 if foot_at_end else 1-cut/100) if vertical else 0,
                               width=background.width if vertical else 5,
                               height=5 if vertical else background.height,
                               fill=color, stroke=color, strokeWidth=0,
                               scalable=False, rotatable=False, deletable=False,
                               dragConstraint={'type': 'axis', 'axis': {'x': 0 if vertical else 1, 'y': 1 if vertical else 0}})
                           for cut, color in zip(setting['cuts'], ['#00e5ff', '#ffff00', '#ff9f1c'])]}
    st.caption('Arraste cada linha diretamente na imagem para separar coxa, joelho, canela e pé.')
    canvas = st_canvas(background_image=background, width=background.width,
                       height=background.height, drawing_mode='transform',
                       initial_drawing=drawing, display_toolbar=False,
                       transform_options={'allow_scale': False, 'allow_rotate': False, 'allow_delete': False},
                       key=f'parts_canvas_{item_key}_{side}_{axis}_{foot_at_end}_{item.get("parts_revision", 0)}')
    apply, close = st.columns(2)
    if apply.button('Aplicar divisões', type='primary'):
        try:
            cuts = cuts_from_objects((canvas.json_data or drawing)['objects'], extent, foot_at_end, coordinate)
        except (ValueError, KeyError, TypeError) as error:
            st.error(str(error))
        else:
            setting.update(cuts=cuts, axis=axis.lower(), foot_at_end=foot_at_end)
            item['parts_revision'] = item.get('parts_revision', 0) + 1
            st.success('Divisões aplicadas. Você pode continuar ajustando ou concluir.')
    if close.button('Concluir'):
        st.rerun()


@st.dialog('Iniciar outra análise')
def restart_analysis():
    st.warning('Os dados e imagens da análise atual serão descartados da sessão. '
               'Registros no banco e coletas já adicionadas à timeline não serão alterados.')
    if st.button('Confirmar nova análise', type='primary'):
        for key in list(st.session_state):
            if key.startswith(('thermal_', 'wizard_', 'thermography_front_upload',
                               'thermography_back_upload', 'thermography_record_editor_')) or key in {
                                   'thermography_items', 'thermography_metrics', 'thermography_player',
                                   'thermography_mass', 'thermography_pain_score', 'thermography_observations'}:
                del st.session_state[key]
        st.rerun()


def navigate(step, valid=True):
    left, right = st.columns(2)
    if left.button('Voltar', disabled=step == 0, key='thermal_previous'):
        st.session_state['thermal_step'] = step - 1
        st.rerun()
    if step < len(STEPS)-1 and right.button('Continuar', type='primary',
                                           disabled=not valid, key='thermal_next'):
        st.session_state['thermal_step'] = step + 1
        st.rerun()
    if step == len(STEPS)-1 and right.button('Iniciar outra análise'):
        restart_analysis()


def render_wizard(athletes_by_id):
    step = st.session_state.setdefault('thermal_step', 0)
    draft = st.session_state.setdefault('thermal_draft', {})
    st.subheader('Nova análise térmica')
    st.progress((step+1)/len(STEPS), text=f'Etapa {step+1} de 6 — {STEPS[step]}')
    if step == 0:
        columns = st.columns(3)
        ids = list(athletes_by_id)
        with columns[0]:
            selected = draft.get('player')
            player = st.selectbox('Jogador *', ids,
                                  index=ids.index(selected) if selected in ids else None,
                                  format_func=lambda value: athlete_label(athletes_by_id[value]),
                                  key='thermography_player')
        with columns[1]:
            mass = st.number_input('Massa (kg) *', min_value=0.1, value=draft.get('mass'),
                                   step=0.1, key='thermography_mass')
        with columns[2]:
            pain = st.number_input('EVA Dor *', min_value=0, max_value=10,
                                   value=draft.get('pain'), step=1, key='thermography_pain_score')
        notes = st.text_area('Observações', value=draft.get('notes', ''), key='thermography_observations')
        draft.update(player=player, mass=mass, pain=pain, notes=notes)
        navigate(step, player is not None and mass is not None and pain is not None)
        return None
    uploads = st.session_state.setdefault('thermal_uploads', {})
    if step == 1:
        for column, view in zip(st.columns(2), VIEW_LABELS):
            with column:
                uploaded = st.file_uploader(f'Imagem de {VIEW_LABELS[view].lower()}',
                                            type=['png', 'jpg', 'jpeg'], key=f'thermography_{view}_upload')
                if uploaded is not None:
                    content = uploaded.getvalue()
                    if uploads.get(view, {}).get('content') != content:
                        uploads[view] = dict(name=uploaded.name, content=content, rotation=0)
                if view in uploads:
                    entry = uploads[view]
                    degrees = st.select_slider('Rotação (anti-horária)', options=[0, 90, 180, 270],
                                               value=entry['rotation'],
                                               key=f'thermal_rotation_{view}_{image_signature(entry["content"])}')
                    entry['rotation'] = degrees
                    try:
                        image, _, _ = rotated_view(entry['content'], degrees)
                        st.image(_display_image(image, max_width=500, max_height=330)[0], caption=entry['name'])
                        entry.pop('error', None)
                    except ValueError as error:
                        entry['error'] = str(error)
                        st.error(str(error))
        navigate(step, all(view in uploads and not uploads[view].get('error') for view in VIEW_LABELS))
        return None
    views, metrics = {}, {}
    items = st.session_state.setdefault('thermography_items', {})
    valid = True
    for view in VIEW_LABELS:
        entry = uploads[view]
        image, content, signature = rotated_view(entry['content'], entry['rotation'])
        views[view] = dict(name=entry['name'], image=image, content=content, signature=signature)
        key = f'{view}:{signature}'
        if key not in items:
            try:
                scale = cached_temperature_scale(entry['content'])
            except ValueError:
                scale = dict(minimum_temperature=DEFAULT_MIN_TEMPERATURE,
                             maximum_temperature=DEFAULT_MAX_TEMPERATURE)
            items[key] = {**scale, 'threshold_percentage': 90.0, 'image_rotation': entry['rotation']}
    tabs = st.tabs(['Frente', 'Verso'])
    for tab, view in zip(tabs, VIEW_LABELS):
        with tab:
            source = views[view]
            image = source['image']
            key = f'{view}:{source["signature"]}'
            item = items[key]
            if step == 2:
                columns = st.columns(3)
                item['minimum_temperature'] = columns[0].number_input('Tmin (°C)', value=float(item['minimum_temperature']), step=0.1, key=f'wizard_tmin_{key}')
                item['maximum_temperature'] = columns[1].number_input('Tmax (°C)', value=float(item['maximum_temperature']), step=0.1, key=f'wizard_tmax_{key}')
                mode = columns[2].radio('Limiar', ['Porcentagem', 'Temperatura (°C)'],
                                        index=0 if item.get('threshold_mode', 'Porcentagem') == 'Porcentagem' else 1,
                                        horizontal=True, key=f'wizard_mode_{key}')
                if item['maximum_temperature'] > item['minimum_temperature']:
                    if mode != item.get('threshold_mode', 'Porcentagem'):
                        st.session_state.pop(f'wizard_threshold_{key}', None)
                        st.session_state.pop(f'wizard_threshold_celsius_{key}', None)
                    if mode == 'Porcentagem':
                        item['threshold_percentage'] = columns[2].slider('Limiar de pixels quentes (%)', 0.0, 100.0, float(item['threshold_percentage']), key=f'wizard_threshold_{key}')
                    else:
                        temperature = temperature_from_scale_percentage(item['minimum_temperature'], item['maximum_temperature'], item['threshold_percentage'])
                        widget_key = f'wizard_threshold_celsius_{key}'
                        if widget_key in st.session_state:
                            st.session_state[widget_key] = min(item['maximum_temperature'], max(item['minimum_temperature'], st.session_state[widget_key]))
                        temperature = columns[2].slider('Temperatura mínima do pixel quente (°C)', float(item['minimum_temperature']), float(item['maximum_temperature']), float(temperature), step=0.01, key=widget_key)
                        item['threshold_percentage'] = scale_percentage_from_temperature(item['minimum_temperature'], item['maximum_temperature'], temperature)
                    item['threshold_mode'] = mode
                try:
                    regions = image_regions(image, view, item['image_rotation'])
                    automatic, colorbar = regions['boxes'], regions['colorbar_box']
                    boxes = {**automatic, **item.get('manual_boxes', {})}
                    preview = annotate_boxes(image, {'Perna direita': boxes['right'], 'Perna esquerda': boxes['left'], 'Barra térmica': item.get('manual_colorbar_box', colorbar)})
                except ValueError as error:
                    st.error(str(error))
                    valid = False
                    continue
                st.image(_display_image(preview, max_width=700, max_height=380)[0])
                if st.button('Corrigir caixas e barra de cores', key=f'wizard_boxes_{key}'):
                    edit_thermal_boxes(key, image, automatic, colorbar)
                if item['maximum_temperature'] <= item['minimum_temperature']:
                    st.error('Tmax deve ser maior que Tmin.')
                    valid = False
                continue
            threshold = temperature_from_scale_percentage(item['minimum_temperature'], item['maximum_temperature'], item['threshold_percentage'])
            item['threshold_temperature'] = threshold
            try:
                analysis = segmented_analysis(image, view, item['minimum_temperature'], item['maximum_temperature'], threshold, item)
            except ValueError as error:
                st.error(str(error))
                valid = False
                continue
            settings = item.setdefault('part_settings_v4', {side: dict(cuts=list(DEFAULT_PART_CUTS), axis='vertical', foot_at_end=True) for side in LEGS.values()})
            metrics[view] = analysis['metrics']
            preview = _parts_preview(image, analysis, settings) if step >= 4 else analysis['overlay']
            columns = st.columns(2)
            columns[0].image(_display_image(preview, max_width=550, max_height=330)[0], caption='Área segmentada' if step == 3 else '1 coxa · 2 joelho · 3 canela · 4 pé')
            columns[1].image(_display_image(analysis['hot_overlay'], max_width=550, max_height=330)[0], caption=f'Pixels quentes ≥ {threshold:.1f} °C')
            if step == 3 and st.button('Corrigir segmentação', key=f'wizard_mask_{key}'):
                edit_thermal_mask(key, image, analysis)
            if step == 4 and st.button('Editar divisões na imagem', key=f'wizard_parts_{key}'):
                edit_parts(key, image, analysis)
            if step == 5:
                for column, (label, side) in zip(st.columns(2), LEGS.items()):
                    metric = analysis['metrics'][side]
                    column.metric(f'Pixels quentes — {label}', f'{metric["hot_pixels"]:,} px')
                    column.caption(f'Área: {metric["total_pixels"]:,} px · {metric["hot_percentage"]:.1f}% quentes')
                    setting = settings[side]
                    parts, _ = leg_part_metrics(analysis['temperatures'], analysis['masks'][side], threshold, tuple(setting['cuts']), axis=setting['axis'], foot_at_end=setting['foot_at_end'])
                    for name, part in parts.items():
                        column.write(f'{name.capitalize()}: {part["hot_pixels"]} px quentes · {part["total_pixels"]} px de área · {part["hot_percentage"]:.1f}%')
    navigate(step, valid)
    if step != 5 or not valid:
        return None
    signature = hashlib.sha256((views['front']['signature']+views['back']['signature']).encode()).hexdigest()
    return draft, views, items, metrics, signature
