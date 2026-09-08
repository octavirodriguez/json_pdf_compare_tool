"""Rules for Spanish AEAT Modelo 390 annual VAT summaries."""

from .base import DocumentProfile


class EsAeatModelo390Profile(DocumentProfile):
    name = "aeat_modelo_390_iva_resumen_anual"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "modelo 390" in normalized_text
            and "impuesto sobre el valor añadido" in normalized_text
            and "declaración-resumen anual" in normalized_text
        )