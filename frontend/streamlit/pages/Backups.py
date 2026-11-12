"""Backup completo e restauração confirmada no banco local, via API."""
from datetime import datetime
import streamlit as st
from frontend.streamlit.api_client import backups

st.set_page_config(page_title='MAC Performance | Backups', page_icon='☁️', layout='wide')
st.title('Backups')
st.write('Banco local e análises térmicas na pasta do Google Drive configurada para a equipe.')


def _running():
    return st.session_state.get('backup_job', {}).get('status') in ('queued', 'running')


def _record(job):
    st.session_state['backup_job'] = job
    st.session_state.pop('backup_job_handled', None)


def _restore(entry):
    try:
        _record(backups.restore_backup(entry))
        st.session_state.pop('backup_restore_error', None)
        st.session_state['backup_dialog_done'] = True
    except ValueError as error:
        st.session_state['backup_restore_error'] = str(error)


def _dismiss_restore():
    st.session_state.pop('backup_restore_entry', None)
    st.session_state.pop('backup_restore_error', None)


@st.dialog('Baixar e restaurar backup', on_dismiss=_dismiss_restore)
def confirm_restore(entry):
    if st.session_state.pop('backup_dialog_done', False):
        _dismiss_restore()
        st.rerun()
    st.write(f'Backup: {entry["name"]}')
    st.warning('O banco local será substituído pelo backup. GPS, saltos, cadastros e demais dados não incluídos nele podem ser perdidos. Análises térmicas locais iguais, mais recentes ou ausentes no backup e suas medidas serão preservadas quando não houver conflitos.')
    st.write('Uma cópia preventiva local será criada antes da alteração. Rascunhos não registrados não fazem parte do backup e serão limpos nesta interface após a restauração.')
    confirmed = st.checkbox('Entendi e autorizo a substituição do banco local.', key='backup_confirm_replace')
    st.button('Baixar e restaurar', type='primary', width='stretch', key='backup_restore_confirm',
              disabled=not confirmed or _running(), on_click=_restore, args=(entry,))
    if error := st.session_state.get('backup_restore_error'):
        st.error(error)


@st.fragment(run_every='2s')
def render_job():
    job = st.session_state.get('backup_job')
    if not job:
        return
    if job['status'] in ('queued', 'running'):
        try:
            job = backups.job_status(job['id'])
        except ValueError as error:
            st.error(str(error))
            st.caption('Não repita uma restauração sem conferir o estado do backend e a cópia preventiva.')
            return
    st.session_state['backup_job'] = job
    if job['status'] in ('queued', 'running'):
        st.info(job['message'])
    elif job['status'] == 'failed':
        if st.session_state.get('backup_job_handled') != job['id']:
            st.session_state['backup_job_handled'] = job['id']
            st.rerun()
        st.error(job['message'])
    else:
        if st.session_state.get('backup_job_handled') != job['id']:
            if job['kind'] == 'restore':
                # O banco foi trocado: evitar referências e rascunhos antigos na interface.
                for key in list(st.session_state):
                    if not key.startswith(('backup_', 'mac_', 'google_')):
                        st.session_state.pop(key, None)
                st.cache_data.clear()
            backups.refresh_backups()
            st.session_state['backup_job_handled'] = job['id']
            st.rerun()
        st.success(job['message'])
        result = job.get('result', {})
        if job['kind'] == 'restore':
            st.write(f'Análises disponíveis: {result.get("analyses", 0)} · Mantidas do local: {result.get("preserved_local", 0)}')
            st.caption(f'Cópia preventiva no backend: {result.get("recovery_copy", "—")}')
        else:
            st.caption('Cada envio cria um backup independente, sem substituir os anteriores.')


render_job()
with st.container(border=True):
    st.subheader('Fazer backup')
    st.write('Envia todas as análises registradas e os dados do schema public do banco local. Não inclui .env, autorizações Google ou arquivos de sessão.')
    if st.button('Fazer backup', type='primary', width='stretch', key='backup_create', disabled=_running()):
        try:
            with st.spinner('Iniciando backup...'):
                _record(backups.create_backup())
            st.rerun()
        except ValueError as error:
            st.error(str(error))

with st.container(border=True):
    st.subheader('Baixar e restaurar backup')
    if st.button('Atualizar lista', width='stretch', key='backup_refresh', disabled=_running()):
        backups.refresh_backups()
    try:
        with st.spinner('Consultando backups no Drive...'):
            entries = backups.list_backups()
    except ValueError as error:
        st.error(str(error))
        entries = []
    if not entries:
        st.info('Nenhum backup disponível foi carregado.')
    else:
        by_id = {entry['id']: entry for entry in entries}
        def label(identity):
            entry = by_id[identity]
            try:
                timestamp = datetime.fromisoformat(entry['createdTime'].replace('Z', '+00:00')).astimezone().strftime('%d/%m/%Y %H:%M')
            except (KeyError, ValueError):
                timestamp = 'Data não disponível'
            size = int(entry.get('size', 0)) / (1024 * 1024)
            return f'{timestamp} · {size:.1f} MB · {entry["name"]}'
        selected = st.selectbox('Backup disponível', list(by_id), format_func=label, key='backup_selected', disabled=_running())
        if st.button('Baixar e restaurar', width='stretch', key='backup_restore_open', disabled=_running()):
            st.session_state['backup_confirm_replace'] = False
            st.session_state.pop('backup_restore_error', None)
            st.session_state.pop('backup_dialog_done', None)
            st.session_state['backup_restore_entry'] = by_id[selected]

if pending := st.session_state.get('backup_restore_entry'):
    confirm_restore(pending)
