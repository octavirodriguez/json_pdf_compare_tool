"""Rules for ANPR certificates."""

from .base import DocumentProfile


class AnprProfile(DocumentProfile):
    name = "anpr"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "anagrafe nazionale" in normalized_text
            and "certificato contestuale" in normalized_text
        ) or "protocollo anpr" in normalized_text
