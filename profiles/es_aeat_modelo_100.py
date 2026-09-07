"""Rules for Spanish AEAT Modelo 100 income-tax declarations."""

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


class EsAeatModelo100Profile(DocumentProfile):
    name = "aeat_modelo_100"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "modelo 100" in normalized_text
            and "impuesto sobre la renta de las personas físicas" in normalized_text
            and "agencia tributaria" in normalized_text
        )

    def confident_short_value_hit(self, pdf_text, path, value_str):
        if value_str not in {"1", "2", "3", "4"}:
            return False

        if path.casefold().endswith(("estadocivil", "estado_civil", "estado civil")):
            return any(code == value_str for code in _CIVIL_STATUS_RE.findall(pdf_text))

        if path.casefold().endswith(("situacion", "situación")):
            return any(code == value_str for code in _PROPERTY_SITUATION_RE.findall(pdf_text))

        return False