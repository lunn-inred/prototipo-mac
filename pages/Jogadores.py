from __future__ import annotations

from datetime import date, timedelta
from html import escape

import streamlit as st

from athlete_service import AthleteInUseError
from service_gateway import create_athlete, delete_athlete, update_athlete
from data_filters import PERIODS, alphabetical_key
from player_data import (
    eva_classification,
    group_measurements,
    latest_eva,
    load_player_dashboard_data,
    metric_summary,
    player_name,
)


st.set_page_config(
    page_title="MAC Performance | Jogadores",
    page_icon="👥",
    layout="wide",
)

st.markdown(
    """
    <style>
    .players-grid-title {
        margin-bottom: .15rem;
    }
    .players-subtitle {
        color: var(--mac-muted);
        margin-bottom: 1rem;
    }
    .player-card {
        background: var(--mac-surface);
        border: 1px solid var(--mac-border);
        border-radius: .9rem;
        padding: .9rem 1rem;
        min-height: 188px;
        margin-bottom: 1rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, .025);
    }
    .player-card-header {
        display: flex;
        align-items: flex-start;
        gap: .75rem;
        min-height: 62px;
    }
    .player-avatar {
        width: 58px;
        height: 58px;
        flex: 0 0 58px;
        display: grid;
        place-items: center;
        border-radius: .7rem;
        background: linear-gradient(145deg, #e5e7eb, #cbd5e1);
        color: #334155;
        font-size: 2rem;
    }
    .player-identity {
        min-width: 0;
        flex: 1;
    }
    .player-name {
        color: var(--mac-text);
        font-size: 1rem;
        font-weight: 780;
        line-height: 1.2;
        text-transform: uppercase;
        overflow-wrap: anywhere;
    }
    .player-position, .player-eva {
        color: var(--mac-muted);
        font-size: .75rem;
        margin-top: .22rem;
    }
    .risk-badge {
        border-radius: 999px;
        padding: .27rem .58rem;
        font-size: .62rem;
        font-weight: 800;
        letter-spacing: .035em;
        text-transform: uppercase;
        white-space: nowrap;
    }
    .risk-badge.risk {
        color: #b91c1c;
        background: #fee2e2;
    }
    .risk-badge.attention {
        color: #b45309;
        background: #fef3c7;
    }
    .risk-badge.ok {
        color: #166534;
        background: #dcfce7;
    }
    .risk-badge.neutral {
        color: #475569;
        background: #f1f5f9;
    }
    .player-divider {
        height: 1px;
        background: var(--mac-border);
        margin: .75rem 0;
    }
    .player-metrics {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .75rem;
    }
    .player-metric-label {
        color: var(--mac-muted);
        font-size: .61rem;
        font-weight: 750;
        letter-spacing: .035em;
        text-transform: uppercase;
        white-space: nowrap;
    }
    .player-metric-value {
        color: var(--mac-text);
        font-size: .92rem;
        font-weight: 760;
        margin-top: .22rem;
    }
    .player-metric-deviation {
        color: var(--mac-muted);
        font-size: .65rem;
        margin-top: .15rem;
    }
    @media (max-width: 900px) {
        .player-metrics {
            gap: .4rem;
        }
        .player-metric-label {
            white-space: normal;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def value_text(value: float | None, unit: str) -> str:
    return f"{value:.1f} {unit}" if value is not None else f"— {unit}"


def deviation_text(value: float | None, unit: str) -> str:
    return f"± {value:.2f} {unit}" if value is not None else "Sem histórico no período"


def player_card(
    athlete: dict[str, object],
    records: dict[str, list[tuple[date, float]]],
    start_date: date,
    end_date: date,
) -> str:
    cmj, cmj_deviation = metric_summary(
        records.get("cmj", []), start_date, end_date
    )
    distance, distance_deviation = metric_summary(
        records.get("distance", []), start_date, end_date
    )
    eva = latest_eva(records.get("eva", []))
    status, status_class = eva_classification(eva)
    eva_text = (
        f"EVA Dor: {eva:.0f}"
        if eva is not None
        else "EVA Dor ainda não registrada"
    )

    return f"""
    <div class="player-card">
        <div class="player-card-header">
            <div class="player-avatar" aria-label="Imagem indisponível">👤</div>
            <div class="player-identity">
                <div class="player-name">{escape(player_name(athlete))}</div>
                <div class="player-position">{escape(str(athlete.get("posicao") or "Sem posição"))}</div>
                <div class="player-eva">{escape(eva_text)}</div>
            </div>
            <span class="risk-badge {status_class}">{escape(status)}</span>
        </div>
        <div class="player-divider"></div>
        <div class="player-metrics">
            <div>
                <div class="player-metric-label">Salto (CMJ)</div>
                <div class="player-metric-value">{value_text(cmj, "cm")}</div>
                <div class="player-metric-deviation">{deviation_text(cmj_deviation, "cm")}</div>
            </div>
            <div>
                <div class="player-metric-label">GPS (distância)</div>
                <div class="player-metric-value">{value_text(distance, "km")}</div>
                <div class="player-metric-deviation">{deviation_text(distance_deviation, "km")}</div>
            </div>
            <div>
                <div class="player-metric-label">Térmica (dif.)</div>
                <div class="player-metric-value">— px</div>
                <div class="player-metric-deviation">Sem dados</div>
            </div>
        </div>
    </div>
    """


st.title("Mural do Elenco")
st.caption("Última medida ± desvio padrão no período selecionado.")

if message := st.session_state.pop("athlete_crud_message", None):
    st.success(message)

try:
    athletes, measurements = load_player_dashboard_data()
except Exception:
    st.error("Não foi possível carregar os dados dos jogadores.")
    st.stop()

if not athletes:
    st.warning("A tabela de jogadores não retornou registros.")
    st.stop()

def refresh_after_mutation(message: str) -> None:
    """Limpa dados cacheados após uma transação confirmada."""
    load_player_dashboard_data.clear()
    try:
        from thermography_data import load_thermography_athletes

        load_thermography_athletes.clear()
    except ImportError:
        pass
    st.session_state["athlete_crud_message"] = message
    st.rerun()


with st.expander("Gerenciar jogadores", expanded=False):
    create_tab, edit_tab, delete_tab = st.tabs(
        ["Cadastrar", "Editar", "Excluir"]
    )

    with create_tab:
        with st.form("create_athlete_form", clear_on_submit=True):
            st.caption("Somente o nome é obrigatório.")
            create_columns = st.columns(2)
            with create_columns[0]:
                create_name = st.text_input("Nome *", key="create_athlete_name")
                create_nickname = st.text_input(
                    "Apelido", key="create_athlete_nickname"
                )
                create_position = st.text_input(
                    "Posição", key="create_athlete_position"
                )
            with create_columns[1]:
                create_group = st.text_input(
                    "Grupo", key="create_athlete_group"
                )
                create_birth_date = st.date_input(
                    "Data de nascimento",
                    value=None,
                    format="DD/MM/YYYY",
                    key="create_athlete_birth_date",
                )
            create_submitted = st.form_submit_button(
                "Cadastrar jogador", type="primary"
            )

        if create_submitted:
            try:
                athlete_id = create_athlete(
                    name=create_name,
                    nickname=create_nickname,
                    position=create_position,
                    group=create_group,
                    birth_date=create_birth_date,
                )
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("Não foi possível cadastrar o jogador.")
            else:
                refresh_after_mutation(
                    f"Jogador cadastrado com sucesso (ID {athlete_id})."
                )

    with edit_tab:
        edit_id = st.selectbox(
            "Jogador que será editado",
            [int(athlete["id_atleta"]) for athlete in athletes],
            format_func=lambda athlete_id: player_name(
                next(
                    athlete
                    for athlete in athletes
                    if int(athlete["id_atleta"]) == athlete_id
                )
            ),
            key="edit_athlete_id",
        )
        selected_athlete = next(
            athlete
            for athlete in athletes
            if int(athlete["id_atleta"]) == edit_id
        )
        stored_birth_date = selected_athlete.get("data_nascimento")
        if hasattr(stored_birth_date, "date"):
            stored_birth_date = stored_birth_date.date()

        with st.form(f"edit_athlete_form_{edit_id}"):
            st.caption(
                "Nome alternativo é preservado e não faz parte deste formulário."
            )
            edit_columns = st.columns(2)
            with edit_columns[0]:
                edit_name = st.text_input(
                    "Nome *",
                    value=str(selected_athlete.get("nome") or ""),
                    key=f"edit_athlete_name_{edit_id}",
                )
                edit_nickname = st.text_input(
                    "Apelido",
                    value=str(selected_athlete.get("apelido") or ""),
                    key=f"edit_athlete_nickname_{edit_id}",
                )
                edit_position = st.text_input(
                    "Posição",
                    value=str(selected_athlete.get("posicao") or ""),
                    key=f"edit_athlete_position_{edit_id}",
                )
            with edit_columns[1]:
                edit_group = st.text_input(
                    "Grupo",
                    value=str(selected_athlete.get("grupo") or ""),
                    key=f"edit_athlete_group_{edit_id}",
                )
                edit_birth_date = st.date_input(
                    "Data de nascimento",
                    value=stored_birth_date,
                    format="DD/MM/YYYY",
                    key=f"edit_athlete_birth_date_{edit_id}",
                )
            edit_submitted = st.form_submit_button(
                "Salvar alterações", type="primary"
            )

        if edit_submitted:
            try:
                update_athlete(
                    edit_id,
                    name=edit_name,
                    nickname=edit_nickname,
                    position=edit_position,
                    group=edit_group,
                    birth_date=edit_birth_date,
                )
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("Não foi possível atualizar o jogador.")
            else:
                refresh_after_mutation("Jogador atualizado com sucesso.")

    with delete_tab:
        delete_id = st.selectbox(
            "Jogador que será excluído",
            [int(athlete["id_atleta"]) for athlete in athletes],
            format_func=lambda athlete_id: player_name(
                next(
                    athlete
                    for athlete in athletes
                    if int(athlete["id_atleta"]) == athlete_id
                )
            ),
            key="delete_athlete_id",
        )
        delete_candidate = next(
            athlete
            for athlete in athletes
            if int(athlete["id_atleta"]) == delete_id
        )
        confirmation_name = player_name(delete_candidate)
        st.warning(
            "A exclusão é permanente e só é permitida para jogadores sem "
            "medições vinculadas."
        )
        with st.form(f"delete_athlete_form_{delete_id}"):
            confirmation = st.text_input(
                f'Digite "{confirmation_name}" para confirmar',
                key=f"delete_athlete_confirmation_{delete_id}",
            )
            delete_submitted = st.form_submit_button(
                "Excluir jogador",
                type="primary",
                disabled=confirmation.strip() != confirmation_name,
            )

        if delete_submitted:
            try:
                delete_athlete(delete_id)
            except AthleteInUseError as error:
                st.error(str(error))
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("Não foi possível excluir o jogador.")
            else:
                refresh_after_mutation("Jogador excluído com sucesso.")


measurements_by_athlete = group_measurements(measurements)
positions = sorted(
    {str(athlete["posicao"]) for athlete in athletes if athlete.get("posicao")},
    key=alphabetical_key,
)

filter_columns = st.columns([2.1, 1.5, 1.5, 1.4])
with filter_columns[1]:
    selected_position = st.selectbox(
        "Posição",
        [None, *positions],
        format_func=lambda value: value or "Todas as posições",
    )

available_athletes = [
    athlete
    for athlete in athletes
    if selected_position is None or athlete.get("posicao") == selected_position
]
available_ids = [int(athlete["id_atleta"]) for athlete in available_athletes]
athletes_by_id = {
    int(athlete["id_atleta"]): athlete for athlete in available_athletes
}

with filter_columns[0]:
    selected_ids = st.multiselect(
        "Jogadores",
        available_ids,
        placeholder="Todos os jogadores",
        format_func=lambda athlete_id: player_name(athletes_by_id[athlete_id]),
    )
with filter_columns[2]:
    selected_period = st.selectbox(
        "Período de referência",
        list(PERIODS),
        index=2,
    )
with filter_columns[3]:
    order_by = st.selectbox(
        "Ordenar por",
        ["Risco", "Nome"],
    )

period_days = PERIODS[selected_period]
end_date = date.today()
if period_days is None:
    measurement_dates = [
        record["data"] for record in measurements if record.get("data") is not None
    ]
    start_date = min(measurement_dates) if measurement_dates else end_date
else:
    start_date = end_date - timedelta(days=period_days - 1)

display_athletes = [
    athlete
    for athlete in available_athletes
    if not selected_ids or int(athlete["id_atleta"]) in selected_ids
]


def risk_sort_key(athlete: dict[str, object]) -> tuple[float, str]:
    athlete_records = measurements_by_athlete.get(int(athlete["id_atleta"]), {})
    eva = latest_eva(athlete_records.get("eva", []))
    risk_value = eva if eva is not None else -1
    return -risk_value, alphabetical_key(player_name(athlete))


if order_by == "Risco":
    display_athletes.sort(key=risk_sort_key)
else:
    display_athletes.sort(key=lambda athlete: alphabetical_key(player_name(athlete)))

if not display_athletes:
    st.info("Nenhum jogador corresponde aos filtros selecionados.")
    st.stop()

for row_start in range(0, len(display_athletes), 3):
    columns = st.columns(3, gap="small")
    for column, athlete in zip(columns, display_athletes[row_start:row_start + 3]):
        athlete_records = measurements_by_athlete.get(
            int(athlete["id_atleta"]), {}
        )
        with column:
            st.markdown(
                player_card(athlete, athlete_records, start_date, end_date),
                unsafe_allow_html=True,
            )

if not any(
    records.get("eva") for records in measurements_by_athlete.values()
):
    st.info(
        "Ainda não existem registros de EVA Dor no banco. "
        "Os indicadores de risco serão atualizados automaticamente quando "
        "essa medida estiver disponível."
    )
