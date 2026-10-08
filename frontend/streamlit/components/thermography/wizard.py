"""Fluxo guiado; imagens e rascunho permanecem somente na sessão."""
import hashlib
import io

import numpy as np
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
from PIL import Image, ImageDraw, ImageFont
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

STEPS = ('Dados da coleta', 'Imagens e rotação', 'Caixas das pernas e barra de cores',
         'Divisão anatômica', 'Segmentação', 'Cálculo da termografia')


def centered_preview(image, caption=None, max_width=550, max_height=330):
    preview, _ = _display_image(image, max_width=max_width, max_height=max_height)
    with st.container(horizontal=True, horizontal_alignment='center'):
        st.image(preview, caption=caption, width='content')


def rotate_right(view):
    entry = st.session_state['thermal_uploads'][view]
    # O backend recebe graus anti-horários: -90 equivale a 270.
    entry['rotation'] = (entry['rotation'] - 90) % 360


def segmented_preview_image(image, masks):
    """Prévia visual sem fundo e sem alterar a matriz usada nos cálculos."""
    mask = np.logical_or.reduce(list(masks.values()))
    return Image.composite(image.convert('RGB'), Image.new('RGB', image.size, 'black'),
                           Image.fromarray(mask.astype(np.uint8) * 255))


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
    setting.update(axis='vertical', foot_at_end=True)
    mask = analysis['masks'][side]
    ys, xs = np.nonzero(mask)
    if not len(xs):
        st.error('A máscara está vazia. Corrija a segmentação primeiro.')
        return
    bounds = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    preview = analysis['overlay'].crop(bounds)
    background, _ = _display_image(preview, max_width=620, max_height=300)
    extent = background.height
    draw = ImageDraw.Draw(background)
    try:
        font = ImageFont.truetype('DejaVuSans.ttf', 14)
    except OSError:
        font = ImageFont.load_default()
    limits = [0, *[extent * cut / 100 for cut in setting['cuts']], extent]
    for label, first, last in zip(('Coxa', 'Joelho', 'Canela', 'Pé'), limits, limits[1:]):
        draw.text((background.width / 2, (first + last) / 2), label,
                  fill='white', font=font, anchor='mm', stroke_width=2, stroke_fill='black')
    drawing = {'objects': [dict(type='rect', id=f'boundary_{index}',
                               x=0, y=extent * cut / 100,
                               width=background.width, height=7,
                               fill=color, stroke=color, strokeWidth=0,
                               scalable=False, rotatable=False, deletable=False,
                               dragConstraint={'type': 'axis', 'axis': {'x': 0, 'y': 1}})
                           for index, (cut, color) in enumerate(zip(setting['cuts'], ['#00e5ff', '#ffff00', '#ff9f1c']))]}
    scenes = item.setdefault('part_scenes', {})
    geometries = item.setdefault('part_scene_geometry', {})
    geometry = (bounds, background.size)
    if geometries.get(side) != geometry:
        scenes.pop(side, None)
        geometries[side] = geometry
    drawing = scenes.get(side, drawing)
    st.caption('Arraste e solte as linhas. As posições são salvas automaticamente, de cima para baixo.')
    canvas = st_canvas(background_image=background, width=background.width,
                       height=background.height, drawing_mode='transform',
                       initial_drawing=drawing, display_toolbar=False,
                       transform_options={'allow_scale': False, 'allow_rotate': False, 'allow_delete': False},
                       key=f'parts_canvas_{item_key}_{side}_vertical')
    if canvas.json_data:
        try:
            cuts = cuts_from_objects(canvas.json_data['objects'], extent, True, 'y')
        except (ValueError, KeyError, TypeError) as error:
            st.error(str(error))
        else:
            scenes[side] = canvas.json_data
            if cuts != setting['cuts']:
                setting['cuts'] = cuts
                # Atualizar rótulos sem fechar o diálogo. O primeiro desenho
                # ainda pode ocorrer num rerun completo, que não aceita este scope.
                context = get_script_run_ctx()
                if context is not None and context.fragment_ids_this_run:
                    st.rerun(scope='fragment')
    if st.button('Concluir', width='stretch'):
        st.rerun()


@st.dialog('Iniciar outra análise')
def restart_analysis():
    st.warning('Os dados e imagens da análise atual serão descartados da sessão. '
               'Registros no banco e coletas já adicionadas à timeline não serão alterados.')
    if st.button('Confirmar nova análise', type='primary', width='stretch'):
        for key in list(st.session_state):
            if key.startswith(('thermal_', 'wizard_', 'thermography_front_upload',
                               'thermography_back_upload', 'thermography_record_editor_')) or key in {
                                   'thermography_items', 'thermography_metrics', 'thermography_player',
                                   'thermography_mass', 'thermography_pain_score', 'thermography_observations'}:
                del st.session_state[key]
        st.rerun()


def navigate(step, valid=True):
    left, right = st.columns(2)
    if left.button('Voltar', disabled=step == 0, key='thermal_previous', width='stretch'):
        st.session_state['thermal_step'] = step - 1
        st.rerun()
    if step < len(STEPS)-1 and right.button('Continuar', type='primary',
                                           disabled=not valid, key='thermal_next', width='stretch'):
        st.session_state['thermal_step'] = step + 1
        st.rerun()
    if step == len(STEPS)-1 and right.button('Iniciar outra análise', width='stretch'):
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
                    st.button('Girar 90° para a direita', width='stretch',
                              key=f'thermal_rotation_{view}_{image_signature(entry["content"])}',
                              on_click=rotate_right, args=(view,))
                    try:
                        image, _, _ = rotated_view(entry['content'], entry['rotation'])
                        centered_preview(image, caption=entry['name'], max_width=500)
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
    for column, view in zip(st.columns(2, gap='large'), VIEW_LABELS):
        with column:
            st.markdown(f'#### {VIEW_LABELS[view]}')
            source = views[view]
            image = source['image']
            key = f'{view}:{source["signature"]}'
            item = items[key]
            if step == 5:
                columns = st.columns(2)
                item['minimum_temperature'] = columns[0].number_input('Tmin (°C)', value=float(item['minimum_temperature']), step=0.1, key=f'wizard_tmin_{key}')
                item['maximum_temperature'] = columns[1].number_input('Tmax (°C)', value=float(item['maximum_temperature']), step=0.1, key=f'wizard_tmax_{key}')
                mode = st.radio('Limiar', ['Porcentagem', 'Temperatura (°C)'],
                                        index=0 if item.get('threshold_mode', 'Porcentagem') == 'Porcentagem' else 1,
                                        horizontal=True, key=f'wizard_mode_{key}')
                if item['maximum_temperature'] > item['minimum_temperature']:
                    if mode != item.get('threshold_mode', 'Porcentagem'):
                        st.session_state.pop(f'wizard_threshold_{key}', None)
                        st.session_state.pop(f'wizard_threshold_celsius_{key}', None)
                    if mode == 'Porcentagem':
                        item['threshold_percentage'] = st.slider('Limiar de pixels quentes (%)', 0.0, 100.0, float(item['threshold_percentage']), key=f'wizard_threshold_{key}')
                    else:
                        temperature = temperature_from_scale_percentage(item['minimum_temperature'], item['maximum_temperature'], item['threshold_percentage'])
                        widget_key = f'wizard_threshold_celsius_{key}'
                        if widget_key in st.session_state:
                            st.session_state[widget_key] = min(item['maximum_temperature'], max(item['minimum_temperature'], st.session_state[widget_key]))
                        temperature = st.slider('Temperatura mínima do pixel quente (°C)', float(item['minimum_temperature']), float(item['maximum_temperature']), float(temperature), step=0.01, key=widget_key)
                        item['threshold_percentage'] = scale_percentage_from_temperature(item['minimum_temperature'], item['maximum_temperature'], temperature)
                    item['threshold_mode'] = mode
                else:
                    st.error('Tmax deve ser maior que Tmin.')
                    valid = False
                    continue
            if step == 2:
                try:
                    regions = image_regions(image, view, item['image_rotation'])
                    automatic, colorbar = regions['boxes'], regions['colorbar_box']
                    boxes = {**automatic, **item.get('manual_boxes', {})}
                    preview = annotate_boxes(image, {'Perna direita': boxes['right'], 'Perna esquerda': boxes['left'], 'Barra térmica': item.get('manual_colorbar_box', colorbar)})
                except ValueError as error:
                    st.error(str(error))
                    valid = False
                    continue
                centered_preview(preview, max_width=700, max_height=380)
                if st.button('Corrigir Áreas', key=f'wizard_boxes_{key}', width='stretch'):
                    edit_thermal_boxes(key, image, automatic, colorbar)
                continue
            minimum, maximum = item['minimum_temperature'], item['maximum_temperature']
            if step != 5 and maximum <= minimum:
                # A geometria pode ser ajustada mesmo com escala ainda inválida;
                # o envio só é liberado após a correção na etapa de cálculo.
                minimum, maximum = DEFAULT_MIN_TEMPERATURE, DEFAULT_MAX_TEMPERATURE
            threshold = temperature_from_scale_percentage(minimum, maximum, item['threshold_percentage'])
            item['threshold_temperature'] = threshold
            try:
                analysis = segmented_analysis(image, view, minimum, maximum, threshold, item)
            except ValueError as error:
                st.error(str(error))
                valid = False
                continue
            settings = item.setdefault('part_settings_v4', {side: dict(cuts=list(DEFAULT_PART_CUTS), axis='vertical', foot_at_end=True) for side in LEGS.values()})
            for setting in settings.values():
                setting.update(axis='vertical', foot_at_end=True)
            metrics[view] = analysis['metrics']
            if step == 5:
                original = annotate_boxes(image, {'Perna direita': analysis['boxes']['right'],
                                                 'Perna esquerda': analysis['boxes']['left'],
                                                 'Barra térmica': analysis['colorbar_box']})
                previews = (original, segmented_preview_image(image, analysis['masks']), analysis['hot_overlay'])
                captions = ('Original com caixas', 'Pernas segmentadas — área completa',
                            f'Pixels quentes ≥ {threshold:.1f} °C')
                for preview_column, preview, caption in zip(st.columns(3), previews, captions):
                    with preview_column:
                        centered_preview(preview, caption=caption)
            elif step == 3:
                centered_preview(_parts_preview(image, analysis, settings),
                                 caption='Coxa · Joelho · Canela · Pé (de cima para baixo)')
            else:
                columns = st.columns(2)
                with columns[0]:
                    centered_preview(analysis['overlay'], caption='Área segmentada')
                with columns[1]:
                    centered_preview(segmented_preview_image(image, analysis['masks']),
                                     caption='Pernas segmentadas — área completa')
            if step == 4 and st.button('Corrigir segmentação', key=f'wizard_mask_{key}', width='stretch'):
                edit_thermal_mask(key, image, analysis)
            if step == 3 and st.button('Editar divisões na imagem', key=f'wizard_parts_{key}', width='stretch'):
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
