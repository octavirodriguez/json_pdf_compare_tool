"""Rules for Spanish AEAT Datos Fiscales."""

from .base import DocumentProfile


class EsAeatDatosFiscalesProfile(DocumentProfile):
    name = "aeat_datos_fiscales"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "consulta de datos fiscales" in normalized_text
            and "datos identificativos" in normalized_text
            and "domicilio fiscal" in normalized_text
        )

    