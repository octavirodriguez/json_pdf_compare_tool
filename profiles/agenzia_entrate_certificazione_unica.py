"""Rules for Agenzia Entrate certification models."""

from .base import DocumentProfile


class AgenziaEntrateCertificazioneUnicaProfile(DocumentProfile):
    name = "agenzia_entrate_certificazione_unica"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "dati anagrafici" in normalized_text
            and (
                "certificazione lavoro dipendente" in normalized_text
                or "certificazione redditi" in normalized_text
                or "certificazione unica" in normalized_text
            )
        )
