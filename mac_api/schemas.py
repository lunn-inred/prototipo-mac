from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AthleteInput(BaseModel):
    name: str = Field(min_length=1, examples=["Maria Silva"])
    nickname: str | None = None
    position: str | None = None
    group: str | None = None
    birth_date: date | None = None


class AthleteCreated(BaseModel):
    id_atleta: int


class GpsPayload(BaseModel):
    documents: list[dict[str, Any]]


class ThermographyInput(BaseModel):
    athlete_id: int
    collected_at: datetime
    mass: float
    pain_score: int
    front_right: int
    front_left: int
    back_right: int
    back_left: int
    observations: str | None = None


class LegacyRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    athlete_id: int
    collected_at: date | datetime
    mass: float
    pain_score: int
    front: int
    back: int
    observations: str | None = None


class LegacyImport(BaseModel):
    records: list[LegacyRow]


class LegacyValidation(BaseModel):
    rows: list[dict[str, Any]]
