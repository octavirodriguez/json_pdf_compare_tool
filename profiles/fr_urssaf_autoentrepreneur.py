"""Rules for URSSAF auto-entrepreneur monthly declarations."""

import re

from .base import DocumentProfile


_ZERO_FIELD_PATTERNS = (
    re.compile(r"^declaration\.chiffreAffaires.*$"),
    re.compile(r"^montantAPayer\.cotisationsEtContributions\[\d+\]\.montant$"),
    re.compile(r"^montantAPayer\.deductionEventuelle$"),
    re.compile(r"^montantAPayer\.montantAPayer$"),
)
_EURO_ZERO_RE = re.compile(r"(?<!\d)0\s*€")


class FrUrssafAutoentrepreneurProfile(DocumentProfile):
    name = "urssaf_autoentrepreneur"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "déclaration mensuelle de chiffre d'affaires" in normalized_text
            and "régime micro-social simplifié" in normalized_text
        )

    def confident_short_value_hit(self, pdf_text, path, value_str):
        return (
            value_str == "0"
            and any(pattern.match(path) for pattern in _ZERO_FIELD_PATTERNS)
            and bool(_EURO_ZERO_RE.search(pdf_text))
        )