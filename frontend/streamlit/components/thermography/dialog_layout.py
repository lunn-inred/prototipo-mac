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
        const hostTop = host.getBoundingClientRect().top;
        // Em alguns WebViews o host de altura zero reporta top=0.
        const top = hostTop > 0 ? hostTop : Math.floor(view.innerHeight * .3);
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
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(schedule);
    const dialog = document.querySelector('[data-testid="stDialog"] [role="dialog"]');
    if (dialog && observer) {observer.observe(dialog); if (dialog.parentElement) observer.observe(dialog.parentElement);}
    if (observer) observer.observe(parentElement.getRootNode().host || parentElement);
    view.addEventListener('resize', schedule);
    // Também cobre montagem tardia: não desistir após um timeout fixo.
    const poll = setInterval(measure, 100);
    schedule();
    return () => {clearTimeout(timer); clearInterval(poll); observer?.disconnect(); view.removeEventListener('resize', schedule);};
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
        # Mantém o editor utilizável mesmo quando o WebView não informa o tamanho.
        size = {'width': 600 if columns == 1 else 360, 'height': 320 if not toolbar else 260}
    return max(40, min(int(size['width']), 1400)), max(40, min(int(size['height']), 650))
