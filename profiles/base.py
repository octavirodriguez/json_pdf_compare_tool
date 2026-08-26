"""Interface for document-model-specific audit rules."""


class DocumentProfile:
    """Base class for optional rules layered on top of the generic auditor."""

    name = "generic"

    def detect(self, pdf_text, json_data):
        """Return whether this profile applies to the document."""
        return False

    def confident_short_value_hit(self, pdf_text, path, value_str):
        """Return whether a short value is confidently represented in the PDF."""
        return False