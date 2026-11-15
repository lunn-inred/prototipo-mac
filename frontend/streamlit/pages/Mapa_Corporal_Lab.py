"""Laboratório temporário: regiões originais, sem gravação no banco."""
import streamlit as st
from frontend.streamlit.components.body_muscles import body_muscles_map, region_catalog
from frontend.streamlit.components.body_muscles_groups import custom_groups

st.set_page_config(page_title='MAC Performance | Mapa corporal (experimental)', page_icon='🧍', layout='wide')
st.title('Mapa corporal — experimental')
st.info('Área de exploração: os valores ficam somente nesta sessão. Não são vinculados a um atleta nem salvos no banco, nas análises ou no Drive.')

controls = st.columns([2, 1, 1, 2])
views = {'Frente e costas': 'BOTH', 'Frente': 'FRONT', 'Costas': 'BACK'}
view = controls[0].selectbox('Vista', list(views), key='body_lab_view')
tooltip = controls[1].checkbox('Mostrar nomes', value=True, key='body_lab_tooltip')
transitions = controls[2].checkbox('Animações', value=True, key='body_lab_transitions')
custom_grouping = controls[3].checkbox('Agrupamento personalizado', value=False, key='body_lab_custom_grouping')
if custom_grouping:
    st.caption('Modo personalizado: 16 áreas das pernas. As outras regiões ficam esmaecidas e não são editáveis. As linhas internas do SVG original foram mantidas.')

def reset():
    st.session_state['body_lab_generation'] = st.session_state.get('body_lab_generation', 0) + 1
    st.session_state.pop('body_lab_state', None)
    st.session_state.pop('body_lab_custom_state', None)

st.button('Limpar exploração', on_click=reset, key='body_lab_reset', width='stretch')
mode = '_custom' if custom_grouping else ''
value = body_muscles_map(key=f'body_lab_map_{st.session_state.get("body_lab_generation", 0)}{mode}',
                        state_key='body_lab_custom_state' if custom_grouping else 'body_lab_state', view=views[view], show_tooltip=tooltip,
                        transitions=transitions, custom_grouping=custom_grouping)
catalog = custom_groups() if custom_grouping else region_catalog()
st.caption(f'Body Muscles 2.1.1 · {len(catalog)} regiões {"personalizadas" if custom_grouping else "originais"} · clique numa região e ajuste a intensidade ao lado do mapa. Esquerda e direita são as do atleta.')

with st.expander('Valores recebidos no Python'):
    rows = [dict(Região=catalog[identifier]['name'], ID=identifier,
                 Vista=catalog[identifier]['view'], Intensidade=entry['intensity'], Selecionada=entry['selected'])
            for identifier, entry in value['bodyState'].items()]
    if rows:
        st.dataframe(rows, hide_index=True, width='stretch')
    else:
        st.write('Nenhuma região editada ou selecionada.')
    st.json(value)

with st.expander('Créditos e licença'):
    st.markdown('Body Muscles: © 2024 Ivan Vulović; versão `@emmorts/body-muscles` mantida por emmorts. '
                '[Projeto original](https://github.com/vulovix/body-muscles) · '
                '[Distribuição utilizada](https://github.com/emmorts/body-muscles). '
                'Apache License 2.0; LICENSE e NOTICE completos acompanham os arquivos do aplicativo. '
                'Integração e agrupamento MAC em código separado; geometria e paleta do fornecedor preservadas.')
