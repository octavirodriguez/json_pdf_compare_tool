"""Rules for Agenzia Entrate receipt documents."""

from .base import DocumentProfile


class RicevutaAgenziaEntrateProfile(DocumentProfile):
    name = "ricevuta_agenzia_entrate"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "comunicazione di avvenuto ricevimento" in normalized_text
            and (
                "dichiarazione 730" in normalized_text
                or "protocollo" in normalized_text
            )
        )
