"""Correspondência segura entre nomes extraídos e atletas cadastrados."""

from __future__ import annotations

from typing import Iterable, Mapping
from unicodedata import combining, normalize


def normalized_athlete_name(value: object) -> str:
    text = "" if value is None else str(value)
    decomposed = normalize("NFKD", text.casefold().strip())
    return "".join(
        character
        for character in decomposed
        if not combining(character) and character.isalnum()
    )


def athlete_display_name(athlete: Mapping[str, object]) -> str:
    athlete_id = int(athlete["id_atleta"])
    nickname = str(athlete.get("apelido") or "").strip()
    name = str(athlete.get("nome") or "").strip()
    return nickname or name or f"Jogador {athlete_id}"


def athlete_selection_label(athlete: Mapping[str, object]) -> str:
    return f"{athlete_display_name(athlete)} — ID {int(athlete['id_atleta'])}"


def athlete_names(athlete: Mapping[str, object]) -> Iterable[str]:
    yield str(athlete.get("nome") or "")
    yield str(athlete.get("apelido") or "")
    yield from (
        part.strip()
        for part in str(athlete.get("nome_alternativo") or "").split(",")
    )


def matching_athlete_ids(
    entered_name: object,
    athletes: Iterable[Mapping[str, object]],
) -> list[int]:
    target = normalized_athlete_name(entered_name)
    if not target:
        return []
    return sorted({
        int(athlete["id_atleta"])
        for athlete in athletes
        if any(
            normalized_athlete_name(candidate) == target
            for candidate in athlete_names(athlete)
        )
    })


def unique_matching_athlete_id(
    entered_name: object,
    athletes: Iterable[Mapping[str, object]],
) -> int | None:
    matches = matching_athlete_ids(entered_name, athletes)
    return matches[0] if len(matches) == 1 else None
