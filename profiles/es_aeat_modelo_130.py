"""Rules for Spanish AEAT Modelo 130 tax return filing information."""

import re

from .base import DocumentProfile


_CIVIL_STATUS_RE = re.compile(
    r"estado\s+civil.{0,180}\(\s*([1-4])\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_PROPERTY_SITUATION_RE = re.compile(
    r"situaci[oó]n\s*\.?.{0,80}?\b([1-4])\s+0065\b",
    re.IGNORECASE | re.DOTALL,
)
_PERIOD_RE = re.compile(
    r"per[ií]odo\s+([1-4]T)\b",
    re.IGNORECASE,
)


class EsAeatModelo130Profile(DocumentProfile):
    name = "aeat_modelo_130"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "modelo 130" in normalized_text
            and "información de la presentación de la declaración" in normalized_text
            and "nif presentador" in normalized_text
            and "apellidos y nombre" in normalized_text
        )

    def confident_short_value_hit(self, pdf_text, path, value_str):
        path_lower = path.casefold()
        if len(value_str) == 2 and value_str[0] in "1234" and value_str[1].upper() == "T":
            if any(token in path_lower for token in ("period", "períod", "periodo")):
                return any(
                    match.group(1).casefold() == value_str.casefold()
                    for match in _PERIOD_RE.finditer(pdf_text)
                )

        if value_str not in {"1", "2", "3", "4"}:
            return False

        if path_lower.endswith(("estadocivil", "estado_civil", "estado civil")):
            return any(code == value_str for code in _CIVIL_STATUS_RE.findall(pdf_text))

        if path_lower.endswith(("situacion", "situación")):
            return any(code == value_str for code in _PROPERTY_SITUATION_RE.findall(pdf_text))

        return False

    