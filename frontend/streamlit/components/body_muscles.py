"""Ponte experimental Streamlit/Body Muscles; não acessa API nem persistência.

O build Apache-2.0 é incorporado sem modificações funcionais. A interface e a
ponte abaixo são próprias do MAC; licença e proveniência ficam em assets/vendor.
"""
from functools import lru_cache
import json
from pathlib import Path
import streamlit as st
from .body_muscles_groups import custom_groups

VENDOR = Path(__file__).resolve().parents[1] / 'assets/vendor/body-muscles/2.1.1'

BRIDGE_JS = '''
export default function({parentElement, data, setStateValue}) {
    const host = parentElement.querySelector('.body-lab');
    // Streamlit v2 pode reutilizar o DOM e chamar o renderer novamente antes
    // de desmontar o componente. Não acumular mapas nem handlers nesse caso.
    host.macBodyMuscles?.dispose();
    const map = parentElement.querySelector('[data-body-map]');
    const name = parentElement.querySelector('[data-region-name]');
    const identifier = parentElement.querySelector('[data-region-id]');
    const number = parentElement.querySelector('[data-intensity-number]');
    const slider = parentElement.querySelector('[data-intensity-slider]');
    let state = {...data.value.bodyState};
    let active = data.value.active;
    const {BodyChart, MUSCLE_METADATA} = BodyMuscles;
    const groups = data.customGrouping ? data.groups : null;
    const catalog = groups || MUSCLE_METADATA;
    const membership = {};
    if (groups) for (const group of Object.values(groups)) {
        for (const member of group.members) membership[member] = group.id;
    }
    function renderState() {
        if (!groups) return state;
        const expanded = {};
        for (const [id, entry] of Object.entries(state)) {
            for (const member of groups[id].members) expanded[member] = {...entry};
        }
        return expanded;
    }
    function showEditor() {
        const region = active && catalog[active];
        name.textContent = region ? region.name : 'Selecione uma região no mapa';
        identifier.textContent = region ? region.id : 'Frente e costas têm regiões independentes.';
        number.disabled = slider.disabled = !region;
        number.value = slider.value = region ? (state[active]?.intensity ?? 0) : 0;
    }
    function emit() {
        setStateValue('value', {active, bodyState: state});
    }
    const chart = new BodyChart(map, {
        view: data.view,
        bodyState: renderState(),
        showTooltip: data.showTooltip,
        enableTransitions: data.enableTransitions,
        ...(groups ? {
            labels: {
                regionName: (muscle) => groups[membership[muscle.id]]?.name || muscle.name,
                region: (muscle, entry) => `${groups[membership[muscle.id]]?.name || muscle.name}; ${muscle.id}; intensidade ${entry?.intensity ?? 0}`,
            },
        } : {}),
        onMuscleClick(id) {
            if (groups) {
                id = membership[id];
                if (!id) return;
            }
            active = id;
            const previous = state[id] || {intensity: 0, selected: false};
            state = Object.fromEntries(Object.entries(state).map(([key, entry]) =>
                [key, {...entry, selected: false}]));
            state[id] = {...previous, selected: true};
            chart.update({bodyState: renderState()});
            showEditor();
            emit();
        },
    });
    if (groups) for (const path of map.querySelectorAll('path[role="button"]')) {
        const member = path.getAttribute('aria-label').split(';')[1]?.trim();
        path.dataset.macRegion = member;
        if (!membership[member]) {
            path.dataset.macDisabled = 'true';
            path.setAttribute('aria-disabled', 'true');
            path.setAttribute('tabindex', '-1');
        } else {
            path.dataset.macGroup = membership[member];
        }
    }
    function changeIntensity(event) {
        const value = Number(event.target.value);
        if (!active || event.target.value === '' || !Number.isInteger(value) || value < 0 || value > 10) {
            showEditor();
            return;
        }
        state = {...state, [active]: {intensity: value, selected: true}};
        chart.update({bodyState: renderState()});
        showEditor();
        emit();
    }
    number.addEventListener('change', changeIntensity);
    slider.addEventListener('change', changeIntensity);
    function previewIntensity() {number.value = slider.value;}
    slider.addEventListener('input', previewIntensity);
    showEditor();
    let disposed = false;
    const instance = {dispose() {
        if (disposed) return;
        disposed = true;
        number.removeEventListener('change', changeIntensity);
        slider.removeEventListener('change', changeIntensity);
        slider.removeEventListener('input', previewIntensity);
        chart.destroy();
    }};
    host.macBodyMuscles = instance;
    return () => {
        instance.dispose();
        if (host.macBodyMuscles === instance) delete host.macBodyMuscles;
    };
}
'''

HTML = '''
<div class="body-lab">
  <div data-body-map></div>
  <section class="body-editor" aria-label="Editar intensidade da região">
    <h3 data-region-name>Selecione uma região no mapa</h3>
    <p data-region-id></p>
    <label>Intensidade (0–10)
      <input data-intensity-number type="number" min="0" max="10" step="1" disabled>
    </label>
    <input data-intensity-slider aria-label="Intensidade da região" type="range" min="0" max="10" step="1" disabled>
    <p>0: sem dor · 10: intensidade máxima</p>
  </section>
</div>
'''

CSS = '''
.body-lab {display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:24px;
  max-width:1200px;margin:0 auto;font-family:Arial,sans-serif;color:var(--st-text-color,#172033);}
.body-editor {padding:16px;border:1px solid #d6dfeb;border-radius:12px;align-self:start;}
.body-editor h3 {font-size:16px;margin:0 0 8px;}
.body-editor p {font-size:13px;overflow-wrap:anywhere;}
.body-editor input {box-sizing:border-box;width:100%;margin:12px 0;font:inherit;}
.body-editor input[type=number] {padding:8px;}
[data-body-map] {min-width:0;--bm-max-height:65vh;}
[data-mac-disabled=true] {pointer-events:none !important;opacity:.12 !important;}
@media(max-width:700px) {.body-lab {grid-template-columns:1fr;} .body-editor {width:auto;}}
'''


@lru_cache(maxsize=1)
def region_catalog():
    data = json.loads((VENDOR / 'body-muscles-data.json').read_text(encoding='utf-8'))
    return {region['id']: {k: v for k, v in region.items() if k != 'path'}
            for region in data['frontMuscles'] + data['backMuscles']}


def normalize_state(value, *, custom_grouping=False):
    catalog = custom_groups() if custom_grouping else region_catalog()
    value = value or {'active': None, 'bodyState': {}}
    active, entries = value.get('active'), value.get('bodyState', {})
    if active is not None and active not in catalog:
        raise ValueError('Região desconhecida no mapa corporal.')
    result = {}
    for identifier, entry in entries.items():
        intensity = entry.get('intensity')
        selected = entry.get('selected')
        if (identifier not in catalog or type(intensity) is not int or not 0 <= intensity <= 10
                or type(selected) is not bool):
            raise ValueError('Estado inválido: use regiões conhecidas e intensidades inteiras de 0 a 10.')
        # Compatibilidade com sessões antigas que permitiam múltipla seleção.
        result[identifier] = dict(intensity=intensity, selected=selected and identifier == active)
    return dict(active=active, bodyState=result)


@lru_cache(maxsize=1)
def _component():
    vendor_js = (VENDOR / 'body-muscles.umd.min.js').read_text(encoding='utf-8')
    return st.components.v2.component('mac.body-muscles-lab', html=HTML, css=CSS,
                                      js=vendor_js + '\n' + BRIDGE_JS)


def body_muscles_map(*, key, state_key, view='BOTH', show_tooltip=True, transitions=True,
                     custom_grouping=False):
    if view not in ('FRONT', 'BACK', 'BOTH'):
        raise ValueError('Vista desconhecida do mapa corporal.')
    # O estado do widget contém o evento mais recente ANTES deste rerun.
    widget = st.session_state.get(key, {})
    value = normalize_state(widget.get('value') or st.session_state.get(state_key), custom_grouping=custom_grouping)
    result = _component()(key=key, data=dict(value=value, view=view, showTooltip=show_tooltip,
        enableTransitions=transitions, customGrouping=bool(custom_grouping),
        groups=custom_groups() if custom_grouping else {}),
        default={'value': value}, height='content',
        on_value_change=lambda: None)
    current = normalize_state(result.get('value') or value, custom_grouping=custom_grouping)
    # Espelho não-widget: preserva a exploração ao navegar para outra página.
    st.session_state[state_key] = current
    return current
