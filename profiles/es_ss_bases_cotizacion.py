"""Rules for Spanish Seguridad Social contribution-base reports."""

import re

from .base import DocumentProfile


_REPORT_TITLE_RE = re.compile(
    r"informe\s+integral\s+de\s+bases\s+de\s+coti\s*zaci[oó]n",
    re.IGNORECASE,
)


class EsSsBasesCotizacionProfile(DocumentProfile):
    name = "seguridad_social_bases_cotizacion"

    def detect(self, pdf_text, json_data):
        return bool(_REPORT_TITLE_RE.search(pdf_text))