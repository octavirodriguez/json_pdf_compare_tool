"""Rules for INPS income/contributive certificates."""

from .base import DocumentProfile


class InpsProfile(DocumentProfile):
    name = "inps"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "estratto conto" in normalized_text
            and (
                "previdenziale" in normalized_text
                or "regime generale" in normalized_text
            )
        ) or (
            "regime generale" in normalized_text
            and "codice fiscale" in normalized_text
        )
