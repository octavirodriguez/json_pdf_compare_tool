"""Public facade for the JSON/PDF audit engine."""

import os
import sys

from auditor_comparison import compare_json_with_pdf
from auditor_pairing import (
    TRAILING_SUFFIX_LENGTH,
    audit_directory_recursively,
    derive_base_key,
)
from auditor_pdf import extract_pdf_text
from auditor_reporting import generate_markdown_report
from auditor_text import (
    MIN_CONFIDENT_MATCH_LENGTH,
    _accent_insensitive_hit,
    _all_words_present,
    _build_phrase_regex,
    _confident_variant_hit,
    _integral_decimal_rendered_as_integer_hit,
    _loose_trace_present,
    _should_skip_low_signal_short_value,
    _strip_diacritics,
    _value_matches_text,
    _year_month_table_hit,
)


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "./data"
    reports_dir = "./reports"

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    audit_directory_recursively(data_dir, reports_dir)
