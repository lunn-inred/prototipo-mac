"""Interface de cadastro, edição, exclusão e importação de saltos."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from frontend.streamlit.api_client.contracts import (athlete_selection_label)
from frontend.streamlit.presentation.jump_data import load_jump_records
from frontend.streamlit.api_client.service_gateway import (
    create_jump,
    delete_jump,
    extract_jump_workbooks,
    import_jump_payload,
    load_athletes,
    load_jump_collections,
    preview_jump_payload,
    update_jump,
)

METRICS = (
    "cmj1", "cmj2", "cmj3", "maior_cmj",
    "sj1", "sj2", "sj3", "maior_sj",
)
METRIC_LABELS = {
    "cmj1": "CMJ 1", "cmj2": "CMJ 2", "cmj3": "CMJ 3",
    "maior_cmj": "Maior CMJ", "sj1": "SJ 1", "sj2": "SJ 2",
    "sj3": "SJ 3", "maior_sj": "Maior SJ",
}


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _payload_signature(rows: list[dict[str, Any]]) -> str:
    serializable = json.dumps(rows, default=str, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serializable.encode()).hexdigest()


def _clear_after_mutation(message: str) -> None:
    load_jump_records.clear()
    st.session_state["jump_crud_message"] = message
    st.session_state.pop("jump_import_validation", None)
    st.rerun()


def _measurement_inputs(prefix: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
    values = values or {}
    result: dict[str, Any] = {}
    for group in (METRICS[:4], METRICS[4:]):
        columns = st.columns(4)
        for column, metric in zip(columns, group):
            stored = values.get(metric)
            with column:
                result[metric] = st.number_input(
                    METRIC_LABELS[metric], min_value=0.0,
                    value=float(stored) if stored is not None else None,
                    step=0.1, format="%.2f", key=f"{prefix}_{metric}",
                )
    return result


def _collection_label(record: dict[str, Any]) -> str:
    nickname = str(record.get("apelido") or "").strip()
    athlete = nickname or str(record.get("atleta") or "Jogador")
    return f"{_date(record['data_coleta']):%d/%m/%Y} · {athlete} · ID {record['id_atleta']}"


def _render_import(athletes: list[dict[str, Any]]) -> None:
    st.caption(
        "Envie uma ou mais planilhas XLSX. A extração e a conferência não alteram "
        "o banco; a gravação exige uma confirmação separada."
    )
    labels = [athlete_selection_label(item) for item in athletes]
    id_by_label = {
        athlete_selection_label(item): int(item["id_atleta"]) for item in athletes
    }
    uploads = st.file_uploader(
        "Planilhas de salto", type=["xlsx"], accept_multiple_files=True,
        key="jump_xlsx_uploads",
    )
    if st.button("Extrair planilhas", type="primary", disabled=not uploads):
        try:
            documents = extract_jump_workbooks(
                [(item.name, item.getvalue()) for item in uploads], athletes
            )
        except Exception as error:
            st.error(f"Não foi possível extrair as planilhas: {error}")
        else:
            st.session_state["jump_import_documents"] = documents
            st.session_state["jump_import_revision"] = (
                st.session_state.get("jump_import_revision", 0) + 1
            )
            st.session_state.pop("jump_import_validation", None)
            st.session_state.pop("jump_import_result", None)

    documents = st.session_state.get("jump_import_documents")
    if not documents:
        return
    rows = [row for document in documents for row in document.get("linhas", [])]
    ignored = [
        f"{document['arquivo']}: {', '.join(document.get('abas_ignoradas', []))}"
        for document in documents if document.get("abas_ignoradas")
    ]
    for document in documents:
        for error in document.get("erros", []):
            st.error(error)
    first, second, third = st.columns(3)
    first.metric("Arquivos processados", len(documents))
    second.metric("Coletas extraídas", len(rows))
    third.metric("Abas ignoradas", sum(len(item.get("abas_ignoradas", [])) for item in documents))
    if ignored:
        st.caption("Abas sem data ignoradas: " + " | ".join(ignored))
    if not rows:
        st.warning("Nenhuma coleta válida foi encontrada nas planilhas.")
        return

    source_errors = {
        (row.get("arquivo"), row.get("aba"), row.get("linha")): list(
            row.get("erros", [])
        )
        for row in rows
    }
    editor_rows = [
        {
            key: value
            for key, value in row.items()
            if key not in {"athlete_id", "erros"}
        }
        for row in rows
    ]
    st.caption(
        "Clique na célula Jogador para selecionar um atleta cadastrado. "
        "Nomes sem correspondência automática permanecem vazios."
    )
    frame = pd.DataFrame(editor_rows)
    edited = st.data_editor(
        frame,
        width="stretch", hide_index=True,
        disabled=["arquivo", "aba", "linha", "nome_reconhecido"],
        column_order=[
            "arquivo", "aba", "linha", "data_coleta", "nome_reconhecido",
            "jogador", *METRICS,
        ],
        column_config={
            "arquivo": "Arquivo", "aba": "Aba", "linha": "Linha",
            "data_coleta": st.column_config.DateColumn("Data", format="DD/MM/YYYY", required=True),
            "nome_reconhecido": "Nome na planilha",
            "jogador": st.column_config.SelectboxColumn(
                "Jogador", options=labels, required=False
            ),
            **{metric: st.column_config.NumberColumn(METRIC_LABELS[metric], min_value=0.0, format="%.2f") for metric in METRICS},
        },
        key=f"jump_import_editor_{st.session_state.get('jump_import_revision', 0)}",
    )
    edited = edited.astype(object).where(pd.notna(edited), None)
    payload = edited.to_dict(orient="records")
    for row in payload:
        row["athlete_id"] = id_by_label.get(row.get("jogador"))
        # A escolha manual resolve a pendência de correspondência automática.
        source_key = (row.get("arquivo"), row.get("aba"), row.get("linha"))
        raw_errors = [str(error) for error in source_errors.get(source_key, [])]
        row["erros"] = [
            error for error in raw_errors
            if "não identificado unicamente" not in error
            and "correspondem a jogadores diferentes" not in error
        ]

    missing_athletes = sum(not row.get("athlete_id") for row in payload)
    if missing_athletes:
        st.warning(
            f"Selecione um jogador cadastrado em {missing_athletes} linha(s) "
            "antes de validar para envio."
        )

    signature = _payload_signature(payload)
    validation = st.session_state.get("jump_import_validation")
    if validation and validation["signature"] != signature:
        validation = None
        st.session_state.pop("jump_import_validation", None)
        st.info("Os dados foram alterados. Valide novamente antes do envio.")
    if st.button(
        "Validar para envio",
        disabled=not athletes or missing_athletes > 0,
    ):
        try:
            previews = preview_jump_payload(payload)
        except Exception as error:
            st.error(f"Não foi possível validar o lote: {error}")
        else:
            validation = {"signature": signature, "previews": previews}
            st.session_state["jump_import_validation"] = validation

    if validation and validation["signature"] == signature:
        previews = validation["previews"]
        counts = {status: sum(item.get("status") == status for item in previews) for status in ("novo", "duplicado", "conflito", "erro")}
        summary = st.columns(4)
        for column, status in zip(summary, counts):
            column.metric(status.capitalize(), counts[status])
        st.dataframe(pd.DataFrame(previews), width="stretch", hide_index=True)
        blocked = counts["conflito"] > 0 or counts["erro"] > 0
        if blocked:
            st.warning("Corrija conflitos e erros antes de confirmar a importação.")
        if st.button("Confirmar envio ao banco", type="primary", disabled=blocked):
            try:
                result = import_jump_payload(payload)
            except Exception as error:
                st.error(f"Não foi possível importar as coletas: {error}")
            else:
                st.session_state["jump_import_result"] = result
                load_jump_records.clear()
    result = st.session_state.get("jump_import_result")
    if result:
        st.success(
            f"{result['inserted_collections']} coleta(s) e "
            f"{result['inserted_measurements']} medição(ões) inseridas; "
            f"{result['duplicate_collections']} duplicata(s) ignorada(s)."
        )


def render_jump_management() -> None:
    if message := st.session_state.pop("jump_crud_message", None):
        st.success(message)
    try:
        athletes = load_athletes()
        collections = load_jump_collections()
    except Exception as error:
        st.error(f"Não foi possível carregar o gerenciamento de saltos: {error}")
        return
    if not athletes:
        st.warning("Cadastre um jogador antes de registrar coletas de salto.")
        return
    ids = [int(item["id_atleta"]) for item in athletes]
    by_id = {int(item["id_atleta"]): item for item in athletes}
    athlete_format = lambda athlete_id: athlete_selection_label(by_id[athlete_id])

    with st.expander("Gerenciar coletas de salto", expanded=False):
        create_tab, edit_tab, delete_tab, import_tab = st.tabs(
            ["Cadastrar", "Editar", "Excluir", "Importar planilha"]
        )
        with create_tab:
            with st.form("jump_create_form", clear_on_submit=True):
                header = st.columns(2)
                athlete_id = header[0].selectbox("Jogador *", ids, format_func=athlete_format)
                collected_at = header[1].date_input("Data da coleta *", format="DD/MM/YYYY")
                values = _measurement_inputs("jump_create")
                submitted = st.form_submit_button("Cadastrar coleta", type="primary")
            if submitted:
                try:
                    count = create_jump({"athlete_id": athlete_id, "collected_at": collected_at, **values})
                except Exception as error:
                    st.error(str(error))
                else:
                    _clear_after_mutation(f"Coleta cadastrada com {count} medição(ões).")

        with edit_tab:
            if not collections:
                st.info("Não há coletas cadastradas para editar.")
            else:
                selected_index = st.selectbox(
                    "Coleta que será editada", range(len(collections)),
                    format_func=lambda index: _collection_label(collections[index]),
                    key="jump_edit_collection",
                )
                selected = collections[selected_index]
                with st.form(f"jump_edit_form_{selected['id_atleta']}_{selected['data_coleta']}"):
                    header = st.columns(2)
                    edit_athlete = header[0].selectbox(
                        "Jogador *", ids, index=ids.index(int(selected["id_atleta"])),
                        format_func=athlete_format,
                    )
                    edit_date = header[1].date_input("Data da coleta *", value=_date(selected["data_coleta"]), format="DD/MM/YYYY")
                    edit_values = _measurement_inputs("jump_edit", selected)
                    edit_submitted = st.form_submit_button("Salvar alterações", type="primary")
                if edit_submitted:
                    try:
                        count = update_jump(int(selected["id_atleta"]), _date(selected["data_coleta"]), {"athlete_id": edit_athlete, "collected_at": edit_date, **edit_values})
                    except Exception as error:
                        st.error(str(error))
                    else:
                        _clear_after_mutation(f"Coleta atualizada com {count} medição(ões).")

        with delete_tab:
            if not collections:
                st.info("Não há coletas cadastradas para excluir.")
            else:
                selected_index = st.selectbox(
                    "Coleta que será excluída", range(len(collections)),
                    format_func=lambda index: _collection_label(collections[index]),
                    key="jump_delete_collection",
                )
                selected = collections[selected_index]
                confirmation = st.checkbox("Confirmo a exclusão permanente desta coleta.")
                if st.button("Excluir coleta", type="primary", disabled=not confirmation):
                    try:
                        count = delete_jump(int(selected["id_atleta"]), _date(selected["data_coleta"]))
                    except Exception as error:
                        st.error(str(error))
                    else:
                        _clear_after_mutation(f"Coleta excluída ({count} medição(ões)).")

        with import_tab:
            _render_import(athletes)
