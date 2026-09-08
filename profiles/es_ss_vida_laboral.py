"""Rules for Spanish Seguridad Social Vida Laboral reports."""

import re

from .base import DocumentProfile


_TABLE_VALUE_LINE_RE = re.compile(
    r"^.*?\d{2}\.\d{2}\.\d{4}\s+"
    r"\d{2}\.\d{2}\.\d{4}\s+"
    r"(?:\d{2}\.\d{2}\.\d{4}|---)\s+"
    r"(?:---|\d{3})\s+"
    r"(?:---|\d{1,2},\d)\s+"
    r"(?P<group>\d{2}|--)\s+"
    r"(?P<days>\d+(?:[.,]\d+)?)\s*$",
    re.MULTILINE,
)


class EsSsVidaLaboralProfile(DocumentProfile):
    name = "seguridad_social_vida_laboral"

    def should_skip_field(self, path):
        return False

    def should_mark_unverifiable_if_absent(self, path):
        return path.casefold() == "informacionpersonal.identificacion"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "informe de vida laboral" in normalized_text
            and "tesorería general de la seguridad social" in normalized_text
            and "informe de vida laboral - situaciones" in normalized_text
        )

    def confident_short_value_hit(self, pdf_text, path, value_str):
        if path.casefold() == "informacionpersonal.identificacion":
            padded_value_pattern = re.compile(
                rf"(?<![A-Za-z0-9])0*{re.escape(value_str)}(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
            return bool(padded_value_pattern.search(pdf_text))

        if not value_str.isdigit() or len(value_str) >= 3:
            return False

        if path.casefold().startswith("resumen."):
            return bool(
                re.search(rf"(?<!\d){re.escape(value_str)}(?!\d)", pdf_text)
            )

        table_values = [
            match.groupdict()
            for match in _TABLE_VALUE_LINE_RE.finditer(pdf_text)
        ]
        path_lower = path.casefold()
        if any(token in path_lower for token in ("grupo", "cotizacion", "cotización")):
            return any(values["group"] == value_str for values in table_values)
        if "dia" in path_lower or "día" in path_lower:
            return any(values["days"] == value_str for values in table_values)
        return False