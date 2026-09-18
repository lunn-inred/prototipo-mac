"""Conversões entre os contratos JSON da API e os objetos de domínio."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from gps_import_service import (
    GpsFileMetadata,
    GpsImportPreview,
    GpsImportResult,
    GpsMeasurement,
    PreparedGpsDocument,
    gps_view_preview_rows,
)


def gps_document_to_dict(document: PreparedGpsDocument) -> dict[str, Any]:
    metadata = document.metadata
    return {
        "filename": document.filename,
        "metadata": None if metadata is None else {
            "filename": metadata.filename,
            "collected_at": metadata.collected_at.isoformat(),
            "team": metadata.team,
            "opponent": metadata.opponent,
        },
        "measurements": [
            {
                "athlete": item.athlete,
                "position": item.position,
                "metric": item.metric,
                "value": item.value,
                "text_value": item.text_value,
                "row_number": item.row_number,
            }
            for item in document.measurements
        ],
        "errors": list(document.errors),
    }


def gps_document_from_dict(payload: dict[str, Any]) -> PreparedGpsDocument:
    raw_metadata = payload.get("metadata")
    metadata = None
    if raw_metadata:
        metadata = GpsFileMetadata(
            filename=str(raw_metadata["filename"]),
            collected_at=datetime.fromisoformat(str(raw_metadata["collected_at"])),
            team=str(raw_metadata["team"]),
            opponent=str(raw_metadata["opponent"]),
        )
    return PreparedGpsDocument(
        metadata=metadata,
        filename=str(payload["filename"]),
        measurements=tuple(
            GpsMeasurement(
                athlete=str(item["athlete"]),
                position=str(item["position"]),
                metric=str(item["metric"]),
                value=float(item["value"]),
                text_value=str(item["text_value"]),
                row_number=int(item["row_number"]),
            )
            for item in payload.get("measurements", [])
        ),
        errors=tuple(str(item) for item in payload.get("errors", [])),
    )


def gps_preview_to_dict(preview: GpsImportPreview) -> dict[str, Any]:
    return {
        "document": gps_document_to_dict(preview.document),
        "new_athletes": list(preview.new_athletes),
        "new_match": preview.new_match,
        "new_metrics": list(preview.new_metrics),
        "new_measurements": preview.new_measurements,
        "duplicate_measurements": preview.duplicate_measurements,
        "warnings": list(preview.warnings),
        "errors": list(preview.errors),
        "view_rows": gps_view_preview_rows(preview.document),
    }


def gps_preview_from_dict(payload: dict[str, Any]) -> GpsImportPreview:
    return GpsImportPreview(
        document=gps_document_from_dict(payload["document"]),
        new_athletes=tuple(payload.get("new_athletes", [])),
        new_match=bool(payload.get("new_match")),
        new_metrics=tuple(payload.get("new_metrics", [])),
        new_measurements=int(payload.get("new_measurements", 0)),
        duplicate_measurements=int(payload.get("duplicate_measurements", 0)),
        warnings=tuple(payload.get("warnings", [])),
        errors=tuple(payload.get("errors", [])),
    )


def gps_result_to_dict(result: GpsImportResult) -> dict[str, Any]:
    return {
        "filename": result.filename,
        "inserted_measurements": result.inserted_measurements,
        "duplicate_measurements": result.duplicate_measurements,
        "created_athletes": result.created_athletes,
        "created_match": result.created_match,
        "created_metrics": result.created_metrics,
        "error": result.error,
    }


def gps_result_from_dict(payload: dict[str, Any]) -> GpsImportResult:
    return GpsImportResult(
        filename=str(payload["filename"]),
        inserted_measurements=int(payload.get("inserted_measurements", 0)),
        duplicate_measurements=int(payload.get("duplicate_measurements", 0)),
        created_athletes=int(payload.get("created_athletes", 0)),
        created_match=bool(payload.get("created_match")),
        created_metrics=int(payload.get("created_metrics", 0)),
        error=payload.get("error"),
    )
