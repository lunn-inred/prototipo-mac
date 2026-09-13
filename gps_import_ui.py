from __future__ import annotations

import pandas as pd
import streamlit as st

from gps_extraction import META, csv_bytes, extract_uploaded_pdfs, flatten
from gps_data import load_gps_records
from gps_import_service import (
    GpsImportPreview,
    GpsImportResult,
    import_gps_documents,
    normalize_position_if_known,
    payload_signature,
    prepare_gps_documents,
    preview_gps_documents,
)


def _render_preview(previews: list[GpsImportPreview]) -> None:
    st.markdown("#### Resumo antes do envio")
    for preview in previews:
        metadata = preview.document.metadata
        with st.expander(preview.document.filename, expanded=True):
            if metadata:
                st.caption(
                    f"{metadata.collected_at:%d/%m/%Y %H:%M} · "
                    f"{metadata.team} x {metadata.opponent}"
                )
            if preview.errors:
                for error in preview.errors:
                    st.error(error)
                continue
            first, second, third = st.columns(3)
            first.metric("Medições novas", preview.new_measurements)
            second.metric("Duplicatas ignoradas", preview.duplicate_measurements)
            third.metric("Nova partida", "Sim" if preview.new_match else "Não")
            if preview.new_athletes:
                st.write("**Novos atletas:** " + ", ".join(preview.new_athletes))
            if preview.new_metrics:
                st.write("**Novas métricas:** " + ", ".join(preview.new_metrics))
            for warning in preview.warnings:
                st.warning(warning)


def _render_results(results: list[GpsImportResult]) -> None:
    st.markdown("#### Resultado do envio")
    for result in results:
        if result.error:
            st.error(f"{result.filename}: envio desfeito — {result.error}")
            continue
        st.success(
            f"{result.filename}: {result.inserted_measurements} medição(ões) "
            f"inserida(s) e {result.duplicate_measurements} duplicata(s) ignorada(s)."
        )
        st.caption(
            f"Cadastros criados: {result.created_athletes} atleta(s), "
            f"{result.created_metrics} métrica(s), "
            f"partida: {'sim' if result.created_match else 'não'}."
        )


def render_gps_import() -> None:
    """Renderiza o fluxo de extração e revisão sem persistir no banco."""
    if "gps_extraction_open" not in st.session_state:
        st.session_state["gps_extraction_open"] = False

    button_label = (
        "Fechar importação"
        if st.session_state["gps_extraction_open"]
        else "Adicionar novos arquivos"
    )
    if st.button(button_label, icon="📄"):
        st.session_state["gps_extraction_open"] = not st.session_state[
            "gps_extraction_open"
        ]
        st.rerun()

    if not st.session_state["gps_extraction_open"]:
        return

    with st.container(border=True):
        st.subheader("Adicionar relatórios GPS")
        st.caption(
            "Envie um ou vários PDFs. As duas últimas páginas de cada arquivo "
            "serão analisadas sem gravar dados no banco nesta etapa."
        )

        uploads = st.file_uploader(
            "Relatórios GPS",
            type=["pdf"],
            accept_multiple_files=True,
            help="Você pode selecionar vários PDFs de uma vez.",
            key="gps_pdf_uploads",
        )

        if st.button(
            "Extrair dados",
            type="primary",
            disabled=not uploads,
            key="gps_extract_button",
        ):
            input_files = [(upload.name, upload.getvalue()) for upload in uploads]
            try:
                with st.spinner(
                    "Lendo os relatórios. O OCR pode levar alguns minutos..."
                ):
                    st.session_state[
                        "gps_extraction_documents"
                    ] = extract_uploaded_pdfs(input_files)
                    st.session_state["gps_extraction_revision"] = (
                        st.session_state.get("gps_extraction_revision", 0) + 1
                    )
                    st.session_state["gps_extraction_edited"] = {}
                    st.session_state.pop("gps_import_validation", None)
                    st.session_state.pop("gps_import_results", None)
            except Exception as error:
                st.session_state.pop("gps_extraction_documents", None)
                st.session_state.pop("gps_extraction_edited", None)
                st.error(f"Não foi possível executar a extração: {error}")

        documents = st.session_state.get("gps_extraction_documents")
        if not documents:
            return

        original_rows = flatten(documents)
        processed = len(documents)
        tables = sum(len(document["tabelas"]) for document in documents)
        first, second, third = st.columns(3)
        first.metric("PDFs processados", processed)
        second.metric("Tabelas encontradas", tables)
        third.metric("Linhas extraídas", len(original_rows))

        if not original_rows:
            st.warning(
                "Nenhuma linha foi reconhecida. Verifique se as tabelas estão "
                "nas duas últimas páginas e se o PDF possui boa resolução."
            )
            return

        st.markdown("#### Conferência dos dados")
        st.caption(
            "Clique em uma célula para corrigir o valor reconhecido pelo OCR. "
            "A coluna de arquivo identifica a origem e fica bloqueada."
        )

        revision = st.session_state.get("gps_extraction_revision", 0)
        saved_edits = st.session_state.setdefault("gps_extraction_edited", {})
        edited_documents: list[list[dict[str, object]]] = []
        import_payload: list[dict[str, object]] = []

        for document_index, document in enumerate(documents):
            rows = flatten([document])
            with st.expander(
                f"{document['arquivo']} — {len(rows)} linha(s)",
                expanded=processed == 1,
            ):
                st.caption(
                    "Páginas analisadas: "
                    + ", ".join(map(str, document["paginas_analisadas"]))
                )
                if not rows:
                    st.info("Nenhuma tabela válida foi encontrada neste PDF.")
                    continue

                editor_source = [
                    {
                        **row,
                        "Posição": normalize_position_if_known(
                            row.get("Posição", "")
                        ),
                    }
                    for row in saved_edits.get(document_index, rows)
                ]
                edited_frame = st.data_editor(
                    pd.DataFrame(editor_source),
                    width="stretch",
                    hide_index=True,
                    disabled=META,
                    key=f"gps_editor_{revision}_{document_index}",
                )
                edited_frame = edited_frame.astype(object).where(
                    pd.notna(edited_frame), ""
                )
                edited_rows = edited_frame.to_dict(orient="records")
                saved_edits[document_index] = edited_rows
                edited_documents.append(edited_rows)
                import_payload.append(
                    {"arquivo": document["arquivo"], "linhas": edited_rows}
                )

                filename = str(document["arquivo"]).rsplit(".", 1)[0] + ".csv"
                st.download_button(
                    "Baixar CSV revisado deste relatório",
                    data=csv_bytes(edited_rows),
                    file_name=filename,
                    mime="text/csv",
                    key=f"gps_download_{revision}_{document_index}",
                )

        consolidated_rows = [row for rows in edited_documents for row in rows]
        if consolidated_rows:
            st.download_button(
                "Baixar CSV consolidado revisado",
                data=csv_bytes(consolidated_rows),
                file_name="tabelas_gps_consolidadas.csv",
                mime="text/csv",
                type="primary",
                key=f"gps_consolidated_{revision}",
            )

        signature = payload_signature(import_payload)
        validation = st.session_state.get("gps_import_validation")
        if validation and validation["signature"] != signature:
            st.session_state.pop("gps_import_validation", None)
            st.session_state.pop("gps_import_results", None)
            validation = None
            st.warning(
                "Os dados foram alterados. Valide novamente antes de confirmar o envio."
            )

        if st.button("Validar para envio", key=f"gps_validate_{revision}"):
            prepared = prepare_gps_documents(import_payload)
            with st.spinner("Conferindo cadastros e duplicatas no banco..."):
                previews = preview_gps_documents(prepared)
            validation = {"signature": signature, "previews": previews}
            st.session_state["gps_import_validation"] = validation
            st.session_state.pop("gps_import_results", None)

        if validation and validation["signature"] == signature:
            previews = validation["previews"]
            _render_preview(previews)
            has_errors = any(preview.errors for preview in previews)
            if st.button(
                "Confirmar envio ao banco",
                type="primary",
                disabled=has_errors,
                key=f"gps_confirm_{revision}",
            ):
                with st.spinner("Enviando medições por relatório..."):
                    results = import_gps_documents(
                        [preview.document for preview in previews]
                    )
                st.session_state["gps_import_results"] = results
                load_gps_records.clear()

        results = st.session_state.get("gps_import_results")
        if results:
            _render_results(results)

        st.info(
            "Upload, OCR e edição não alteram o banco. A gravação só ocorre após "
            "Validar para envio e Confirmar envio ao banco."
        )
