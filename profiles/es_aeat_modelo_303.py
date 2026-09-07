"""Rules for Spanish AEAT Modelo 303 IVA self-assessments."""

import re

from .base import DocumentProfile


_PERIOD_RE = re.compile(
    r"per[ií]odo\s+(?P<period>[1-4]T)\b",
    re.IGNORECASE,
)


class EsAeatModelo303Profile(DocumentProfile):
    name = "aeat_modelo_303_iva_autoliquidacion"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "modelo 303" in normalized_text
            and "impuesto sobre el valor añadido" in normalized_text
            and "autoliquidación" in normalized_text
        )

    def confident_short_value_hit(self, pdf_text, path, value_str):
        if len(value_str) != 2 or value_str[0] not in "1234" or value_str[1].upper() != "T":
            return False

        path_lower = path.casefold()
        if not any(token in path_lower for token in ("period", "períod", "periodo")):
            return False

        return any(match.group("period").casefold() == value_str.casefold() for match in _PERIOD_RE.finditer(pdf_text))