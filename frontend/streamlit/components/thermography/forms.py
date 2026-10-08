from __future__ import annotations
import hashlib
import io
from datetime import date
from typing import Any
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from streamlit_drawable_konva import crop_box_from_json, st_canvas
from frontend.streamlit.api_client.contracts import (unique_matching_athlete_id)
from frontend.streamlit.api_client.thermal_client import (annotate_boxes, compare_hot_masks, count_hot_pixels, detect_colorbar_box, detect_leg_boxes, hot_pixels_overlay, segmentation_overlay, segment_leg_mask, temperature_matrix, DEFAULT_PART_CUTS, LEG_PARTS, leg_part_metrics, scale_percentage_from_temperature, temperature_from_scale_percentage)
from frontend.streamlit.presentation.thermography_data import (
    athlete_label,
    load_thermography_athletes,
    load_thermography_history,
)
from frontend.streamlit.api_client.contracts import (DuplicateThermographyError, LegacyThermographyRecord, current_sao_paulo_date)
from frontend.streamlit.api_client.service_gateway import (
    extract_thermography_scale,
    extract_legacy_documents,
    save_image_thermography,
    save_legacy_thermography,
)
from frontend.streamlit.components.thermography.editor import LEGS, VIEW_LABELS

def render_forms(athletes, editor_label_by_athlete_id, athlete_id_by_editor_label) -> None:
    """Renderiza o fluxo opcional de importação de formulários manuscritos."""
    with st.expander("Formulários", expanded=False):
        legacy_documents = st.file_uploader(
            "Planilhas e fichas preenchidas manualmente",
            type=["pdf", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            help=(
                "Os documentos são enviados ao LlamaParse Cloud para extração. "
                "Se o serviço falhar ou a tabela não for reconhecida, o sistema "
                "usa o OCR local como alternativa."
            ),
            key="thermography_legacy_documents",
        )

        if legacy_documents:
            batch_signature = hashlib.sha256(
                b"".join(
                    hashlib.sha256(document.getvalue()).digest()
                    for document in legacy_documents
                )
            ).hexdigest()
            if st.session_state.get("legacy_batch_signature") != batch_signature:
                st.session_state.pop("legacy_extraction_results", None)
                st.session_state.pop("legacy_edited_rows", None)

            if st.button(
                "Extrair conteúdo",
                type="primary",
                key="extract_legacy_documents",
            ):
                extracted_documents = []
                progress = st.progress(0, text="Preparando documentos...")
                for index, document in enumerate(legacy_documents):
                    try:
                        _, extraction = extract_legacy_documents(
                            [(document.name, document.getvalue())]
                        )[0]
                        extracted_documents.append(
                            {
                                "filename": document.name,
                                "pages": extraction.pages,
                                "used_fallback": extraction.used_fallback,
                                "fallback_reason": extraction.fallback_reason,
                                "error": None,
                            }
                        )
                    except Exception as error:
                        extracted_documents.append(
                            {
                                "filename": document.name,
                                "pages": [],
                                "error": str(error),
                            }
                        )
                    progress.progress(
                        (index + 1) / len(legacy_documents),
                        text=f"Processando {document.name}",
                    )
                progress.empty()
                st.session_state["legacy_batch_signature"] = batch_signature
                st.session_state["legacy_extraction_results"] = extracted_documents
        else:
            st.session_state.pop("legacy_batch_signature", None)
            st.session_state.pop("legacy_extraction_results", None)
            st.session_state.pop("legacy_edited_rows", None)
            st.caption(
                "Envie os documentos e execute a extração. "
                "Nenhum arquivo é persistido pelo protótipo."
            )

        extraction_results = st.session_state.get("legacy_extraction_results", [])
        if extraction_results:
            extracted_rows = []
            for document_result in extraction_results:
                with st.expander(document_result["filename"]):
                    if document_result["error"]:
                        st.error(document_result["error"])
                        continue
                    if document_result.get("used_fallback"):
                        st.warning(
                            "LlamaParse não pôde concluir a extração; foi utilizado "
                            "o OCR local (Tesseract). "
                            + str(document_result.get("fallback_reason") or "")
                        )
                    for page_number, page_result in enumerate(
                        document_result["pages"], start=1
                    ):
                        st.markdown(f"**Página {page_number}**")
                        diagnostic = page_result["diagnostic"].copy()
                        diagnostic.thumbnail((900, 700))
                        st.image(
                            diagnostic,
                            caption=(
                                "Linhas candidatas identificadas em verde"
                                if document_result.get("used_fallback")
                                else "Página enviada para extração"
                            ),
                            width=700,
                        )
                        if page_result.get("error"):
                            st.error(page_result["error"])
                            continue
                        if page_result["date"]:
                            st.caption(f"Data identificada: {page_result['date']}")
                        else:
                            st.warning("A data da página não foi identificada.")
                        for row in page_result["rows"]:
                            review_row = {
                                key: value
                                for key, value in row.items()
                                if key not in {
                                    "_raw",
                                    "Confiança OCR",
                                    "Revisão",
                                }
                            }
                            recognized_name = review_row.get("Jogador", "")
                            matched_athlete_id = unique_matching_athlete_id(
                                recognized_name, athletes
                            )
                            review_row["Nome reconhecido"] = recognized_name
                            review_row["Jogador"] = (
                                editor_label_by_athlete_id.get(matched_athlete_id)
                                if matched_athlete_id is not None else None
                            )
                            extracted_rows.append(review_row)
                        if not page_result["rows"]:
                            st.warning("Nenhuma linha preenchida foi identificada.")

            if extracted_rows:
                st.markdown("#### Revisão da extração")
                st.caption(
                    "Confira os valores e selecione um jogador cadastrado em todas "
                    "as linhas antes de registrar no banco."
                )
                review_columns = [
                    "Nome reconhecido",
                    "Jogador",
                    "Massa",
                    "EVA Dor",
                    "Frente",
                    "Verso",
                    "Observações",
                    "Data",
                ]
                review_frame = pd.DataFrame(extracted_rows).reindex(columns=review_columns)
                review_frame["Nome reconhecido"] = review_frame[
                    "Nome reconhecido"
                ].astype("string")
                review_frame["Jogador"] = review_frame["Jogador"].astype("string")
                review_frame["Massa"] = pd.to_numeric(
                    review_frame["Massa"], errors="coerce"
                ).astype("Float64")
                for numeric_column in ("EVA Dor", "Frente", "Verso"):
                    review_frame[numeric_column] = pd.to_numeric(
                        review_frame[numeric_column], errors="coerce"
                    ).astype("Int64")
                review_frame["Observações"] = (
                    review_frame["Observações"].fillna("").astype("string")
                )
                review_frame["Data"] = pd.to_datetime(
                    review_frame["Data"], errors="coerce"
                )
                editor_batch_key = st.session_state.get(
                    "legacy_batch_signature", "sem_lote"
                )
                edited_rows = st.data_editor(
                    review_frame,
                    width="stretch",
                    hide_index=True,
                    num_rows="dynamic",
                    disabled=["Nome reconhecido"],
                    column_order=review_columns,
                    column_config={
                        "Nome reconhecido": st.column_config.TextColumn(),
                        "Jogador": st.column_config.SelectboxColumn(
                            options=sorted(athlete_id_by_editor_label),
                            required=True,
                        ),
                        "Massa": st.column_config.NumberColumn(
                            min_value=0.1, format="%.1f"
                        ),
                        "EVA Dor": st.column_config.NumberColumn(
                            min_value=0, max_value=10, step=1, format="%d"
                        ),
                        "Frente": st.column_config.NumberColumn(
                            min_value=0, step=1, format="%d"
                        ),
                        "Verso": st.column_config.NumberColumn(
                            min_value=0, step=1, format="%d"
                        ),
                        "Observações": st.column_config.TextColumn(
                            width="large",
                            default="",
                        ),
                        "Data": st.column_config.DateColumn(
                            format="DD/MM/YYYY",
                            required=True,
                        ),
                    },
                    key=f"legacy_review_editor_{editor_batch_key}",
                )
                edited_records = (
                    edited_rows.astype(object)
                    .where(pd.notna(edited_rows), None)
                    .to_dict("records")
                )
                st.session_state["legacy_edited_rows"] = edited_records
                selected_athlete_ids = [
                    athlete_id_by_editor_label.get(row.get("Jogador"))
                    for row in edited_records
                ]
                has_unselected_athletes = any(
                    athlete_id is None for athlete_id in selected_athlete_ids
                )
                if has_unselected_athletes:
                    st.warning(
                        "Selecione um jogador cadastrado para todas as linhas."
                    )
                else:
                    st.success("Todos os jogadores estão vinculados a cadastros.")

                st.info(
                    "Frente e Verso dos documentos serão associados às medidas "
                    "SOMA_FRENTE e SOMA_VERSO. As quatro medidas individuais por "
                    "perna permanecerão vazias nos registros legados."
                )
                if st.button(
                    "Registrar documentos revisados no banco",
                    type="primary",
                    key="save_legacy_thermography",
                    disabled=has_unselected_athletes or not athletes,
                ):
                    try:
                        legacy_records = []
                        for row_number, (row, athlete_id) in enumerate(
                            zip(edited_records, selected_athlete_ids), start=1
                        ):
                            if athlete_id is None:
                                raise ValueError(
                                    f"Linha {row_number}: selecione um jogador."
                                )
                            raw_date = row.get("Data")
                            if raw_date is None or pd.isna(raw_date):
                                raise ValueError(
                                    f"Linha {row_number}: informe a data da coleta."
                                )
                            parsed_date = pd.to_datetime(raw_date, errors="raise").date()
                            raw_observations = row.get("Observações")
                            observations_value = (
                                None
                                if raw_observations is None or pd.isna(raw_observations)
                                else str(raw_observations)
                            )
                            legacy_records.append(
                                LegacyThermographyRecord(
                                    athlete_id=athlete_id,
                                    collected_at=parsed_date,
                                    mass=row.get("Massa"),
                                    pain_score=row.get("EVA Dor"),
                                    front=row.get("Frente"),
                                    back=row.get("Verso"),
                                    observations=observations_value,
                                )
                            )
                        inserted = save_legacy_thermography(legacy_records)
                    except (ValueError, RuntimeError, DuplicateThermographyError) as error:
                        st.error(str(error))
                    except Exception:
                        st.error("Não foi possível registrar os documentos no banco.")
                    else:
                        load_thermography_history.clear()
                        st.session_state["thermography_flash"] = (
                            f"{len(legacy_records)} coleta(s) legada(s) registrada(s) "
                            f"com {inserted} medida(s)."
                        )
                        st.rerun()
