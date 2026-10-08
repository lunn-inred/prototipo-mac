"""Metadados da primeira linha das páginas de relatórios GPS."""

import re
import unicodedata
from datetime import datetime

MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _without_accents(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", text) if not unicodedata.combining(char))


def parse_page_header(text: str) -> dict[str, object]:
    """Lê data brasileira e confronto, preservando a ordem equipe x adversário."""
    line = " ".join(text.replace("_", " ").split())
    is_activity_report = bool(re.match(r"RELAT[ÓO]RIO\s+DE\s+ATIVIDADES\b", line, re.I))
    line = re.sub(r"\s*P[ÁA]GINA\s+\d+\s*/\s*\d+\s*$", "", line, flags=re.I)
    line = re.sub(r"^RELAT[ÓO]RIO\s+DE\s+ATIVIDADES\s+", "", line, flags=re.I)
    date_match = re.search(r"\b(\d{2})[./-](\d{2})[./-](\d{4})\b", line)
    if date_match:
        day, month, year = map(int, date_match.groups())
    else:
        date_match = re.search(
            r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),\s*(\d{4})\b",
            _without_accents(line), re.I,
        )
        if date_match:
            month_name, day_text, year_text = date_match.groups()
            day, month, year = int(day_text), MONTHS[month_name.lower()], int(year_text)
    if not date_match:
        raise ValueError("data da coleta não encontrada na primeira linha da página")
    remainder = line[:date_match.start()] + " " + line[date_match.end():]
    time_match = re.search(r"\b(\d{1,2})\s*[:hH]\s*(\d{2})(?:\s*:\s*(\d{2}))?(?:\s*(AM|PM|h))?\b", remainder, re.I)
    if is_activity_report and time_match is None:
        raise ValueError("horário ausente no cabeçalho do relatório de atividades")
    hour, minute, second = (0, 0, 0)
    if time_match:
        hour, minute, second = (int(value or 0) for value in time_match.groups()[:3])
        period = (time_match[4] or "").upper()
        if period in ("AM", "PM"):
            if not 1 <= hour <= 12:
                raise ValueError("horário AM/PM inválido na primeira linha da página")
            hour = hour % 12 + (12 if period == "PM" else 0)
        remainder = remainder[:time_match.start()] + " " + remainder[time_match.end():]
    try:
        collected_at = datetime(year, month, day, hour, minute, second)
    except ValueError as error:
        raise ValueError("data ou horário inválido na primeira linha da página") from error
    remainder = re.sub(r"\b(?:data(?:\s+(?:da\s+)?coleta)?|hor[aá]rio)\s*:?", "", remainder, flags=re.I)
    remainder = re.sub(r"^\s*(?:jogo|partida|confronto)\s*:\s*", "", remainder, flags=re.I)
    remainder = re.sub(r"\s+\(MD(?:\s*[+-]\s*\d+)?\)", "", remainder, flags=re.I)
    remainder = re.sub(
        r"\b(?:DOMINGO|SEGUNDA(?:-FEIRA)?|TER[ÇC]A(?:-FEIRA)?|QUARTA(?:-FEIRA)?|QUINTA(?:-FEIRA)?|SEXTA(?:-FEIRA)?|S[ÁA]BADO)\s*,?",
        "", remainder, flags=re.I,
    )
    parts = re.split(r"\s+(?:[xX×]|[vV][sS]\.?)\s+", remainder.strip(" |;,:–—-()"))
    if len(parts) != 2:
        raise ValueError("confronto EQUIPE x ADVERSÁRIO não encontrado na primeira linha da página")
    team, opponent = (part.strip(" |;,:–—-()") for part in parts)
    if not team or not opponent:
        raise ValueError("equipe e adversário obrigatórios na primeira linha da página")
    return {"equipe": team, "adversario": opponent, "data_coleta": collected_at}
