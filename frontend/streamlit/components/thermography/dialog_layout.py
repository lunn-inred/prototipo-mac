"""Dimensões do canvas calculadas pela área útil real do diálogo."""
from functools import lru_cache
import streamlit as st

MEASURE_JS = '''
export default function({parentElement, setStateValue, data}) {
    const document = parentElement.ownerDocument;
    const view = document.defaultView;
    let last = JSON.stringify(data.reported || null), timer;
    let candidate = '', candidateSince = 0;
    function measure() {
        const dialog = document.querySelector('[data-testid="stDialog"] [role="dialog"]');
        const root = parentElement.getRootNode();
        const host = root.host || parentElement;
        const top = host.getBoundingClientRect().top;
        if (!dialog || dialog.clientWidth <= 0 || top <= 0) return;
        const available = Math.max(40, view.innerHeight - top - data.reserve);
        const totalWidth = Math.max(160, (dialog?.clientWidth || view.innerWidth * .9) - 96);
        const size = {width: Math.floor((totalWidth - (data.columns - 1) * 24) / data.columns),
                      height: Math.floor(available)};
        const signature = JSON.stringify(size);
        if (signature !== candidate) {
            candidate = signature;
            candidateSince = view.performance.now();
            return;
        }
        // Aguardar a estabilização do layout/animação antes de desenhar o canvas.
        if (view.performance.now() - candidateSince < 180) return;
        if (signature !== last) {
            last = signature;
            setStateValue('size', size);
        }
    }
    function schedule() {clearTimeout(timer); timer = setTimeout(measure, 120);}
    const observer = new ResizeObserver(schedule);
    const dialog = document.querySelector('[data-testid="stDialog"] [role="dialog"]');
    if (dialog) {observer.observe(dialog); if (dialog.parentElement) observer.observe(dialog.parentElement);}
    observer.observe(parentElement.getRootNode().host || parentElement);
    view.addEventListener('resize', schedule);
    // Também cobre montagem tardia: não desistir após um timeout fixo.
    const poll = setInterval(measure, 100);
    schedule();
    return () => {clearTimeout(timer); clearInterval(poll); observer.disconnect(); view.removeEventListener('resize', schedule);};
}
'''


@lru_cache(maxsize=1)
def _measure_component():
    return st.components.v2.component('mac.thermal-dialog-size', html='<span></span>', js=MEASURE_JS)


def dialog_canvas_limits(key, *, columns=1, toolbar=True):
    cache = st.session_state.setdefault('thermal_dialog_sizes', {})
    reported = cache.get(key)
    result = _measure_component()(key=f'dialog_size_{key}', height=0,
                                  data={'columns': columns, 'reserve': 172 + (80 if toolbar else 0), 'reported': reported},
                                  default={'size': None}, on_size_change=lambda: None)
    size = result.get('size') or reported
    if size:
        cache[key] = size
    else:
        st.caption('Ajustando o editor ao tamanho da janela…')
        return None
    return max(40, min(int(size['width']), 1400)), max(40, min(int(size['height']), 650))
