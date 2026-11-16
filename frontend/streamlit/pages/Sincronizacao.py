"""Sincronização explícita; arquivos, conflitos e banco são tratados pela API."""
import streamlit as st
from frontend.streamlit.api_client import backups

st.set_page_config(page_title='MAC Performance | Sincronização', page_icon='☁️', layout='wide')
st.title('Sincronização')
st.write('Compartilhe jogadores, GPS, saltos e análises térmicas entre os computadores pela pasta Analises MAC no Google Drive.')


@st.fragment(run_every='2s')
def render_sync():
    job = st.session_state.get('sync_job')
    if job and job['status'] in ('queued', 'running'):
        try:
            job = backups.job_status(job['id'])
            st.session_state['sync_job'] = job
        except ValueError as error:
            st.error(str(error))
            st.warning('Confira o estado da API antes de repetir a operação.')
            return
    running = bool(job and job['status'] in ('queued', 'running'))
    if st.button('Sincronizar dados', type='primary', width='stretch', disabled=running, key='sync_start'):
        try:
            st.session_state['sync_job'] = backups.synchronize()
            st.session_state.pop('sync_handled', None)
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    if not job:
        return
    if running:
        st.info(job['message'])
    elif job['status'] == 'failed':
        st.error(job['message'])
        st.caption('Conflitos não escolhem um vencedor automaticamente. Preserve as cópias para revisão.')
    else:
        if st.session_state.get('sync_handled') != job['id']:
            st.cache_data.clear()
            st.session_state['sync_handled'] = job['id']
        st.success(job['message'])
        result = job.get('result', {})
        st.write(f'Análises: {result.get("analyses", 0)} · ZIPs enviados: {result.get("uploaded", 0)} · ZIPs baixados: {result.get("downloaded", 0)}')
        st.caption(f'Cópia preventiva local: {result.get("recovery_copy", "—")}')


with st.container(border=True):
    st.subheader('Sincronizar com a equipe')
    st.write('A operação envia as alterações locais e recebe as alterações compartilhadas. Apenas análises novas ou alteradas precisam de transferência de ZIP.')
    st.warning('Salve suas alterações antes de sincronizar. Use um computador por vez para publicar; alterações concorrentes no mesmo registro exigem revisão.')
    render_sync()

with st.expander('Como funciona'):
    st.write('Cada análise possui seu próprio ZIP. Um índice separado guarda revisões, hashes e os dados do banco. Os registros são mesclados, sem substituir o banco inteiro.')
    st.write('Diferenças na estrutura do banco bloqueiam a operação: atualize o aplicativo e aplique as migrações locais compatíveis. Nenhuma tabela ou view é copiada automaticamente do Drive.')
    st.write('A pasta é localizada pelo ID já configurado e será renomeada para Analises MAC na sincronização. Backups antigos não são apagados nem importados automaticamente.')
