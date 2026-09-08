import re
import unicodedata


_WHITESPACE_RE = re.compile(r"\s+")

_SPANISH_MONTHS = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}


# Known domain abbreviations used in PDF renderings.
_VALUE_ALIASES = {
    "settimane": ["sett.", "sett"],
}


# Some contribution counters are stored in JSON as X.0 but are printed in PDFs
# as plain integers (X). For these specific field families, accept that form as
# a confident hit when the integer appears as a standalone token.
_INTEGER_RENDERED_NUMERIC_PATH_HINTS = (
    "contributiUtiliDiritto",
    "contributiUtiliCalcolo",
    ".giorni",
)


# Certain fields are short internal codes/counters that are frequently rendered
# as labels or tightly packed table glyphs in PDFs. A text-search check on
# 1-2 char values here is too noisy to be actionable, so these are skipped when
# their value is below MIN_CONFIDENT_MATCH_LENGTH.
_LOW_SIGNAL_SHORT_PATH_HINTS = (
    ".primaNota.codice",
    ".gruppo.codice",
    ".nota.codice",
    ".anzianitaDiritto.anni",
    ".anzianitaDiritto.mesi",
    ".anzianitaDiritto.giorni",
    ".anzianitaMisura.anni",
    ".anzianitaMisura.mesi",
    ".anzianitaMisura.giorni",
    ".mesiContribuzione",
)


def _build_phrase_regex(value_str):
    """Builds a case-insensitive regex that matches `value_str` as whole word(s),
    tolerating any amount of whitespace (including line breaks) between the
    words it contains. PDF text extraction frequently re-flows or wraps text
    differently than the source JSON, so a literal substring check is too
    strict, and a fully unanchored substring check is too loose (e.g. "20"
    would match inside "2025"). Word boundaries plus flexible inter-word
    whitespace strike a middle ground that works across differently
    structured documents.

    The leading/trailing boundary is digit-aware rather than a blanket `\\w`
    check: it still blocks the value from matching as a substring of a
    *longer number* (so "20" still can't match inside "2025"), but it no
    longer blocks a number or date from matching just because the very next
    character in the extracted text happens to be a letter. That situation
    is common and legitimate here -- PDF table-cell extraction routinely
    drops the whitespace between a boxed numeric value and the label text
    that follows it (e.g. "5.242,20Codice fiscale del percipiente"), which a
    plain `\\w` boundary would wrongly reject as "not a whole match" even
    though the number itself is exactly present.
    """
    tokens = [t for t in _WHITESPACE_RE.split(value_str.strip()) if t]
    if not tokens:
        return None
    body = r"\s+".join(re.escape(t) for t in tokens)
    lead = r"(?<!\d)" if tokens[0][0].isdigit() else r"(?<!\w)"
    trail = r"(?!\d)" if tokens[-1][-1].isdigit() else r"(?!\w)"
    return re.compile(lead + body + trail, re.IGNORECASE)


def _value_matches_text(pdf_text, value_str):
    """Whole-word(s), whitespace-tolerant, case-insensitive match of value_str in pdf_text."""
    pattern = _build_phrase_regex(value_str)
    return bool(pattern and pattern.search(pdf_text))


def _year_month_table_hit(pdf_text, value_str):
    """True if value_str is a bare "YYYY-MM" period (no day) and both its year
    and its Spanish month name show up somewhere in the PDF text.

    Social-Security-style "período de cotización" fields (e.g. "2026-07")
    are frequently rendered in the source PDF as a year-by-month matrix
    table -- the year labels one axis, the month name (in Spanish, e.g.
    "julio") labels the other -- rather than printed as a single date
    string. So neither "2026-07" nor any slash/dash rendering of it ever
    appears verbatim, and the year and month text are typically nowhere
    near each other in the extracted text (they come from different table
    headers, not the same cell). A single variant string can't express
    "these two facts appear separately in the document," so this is
    checked as its own pair-presence rule rather than folded into
    generate_value_variants.
    """
    m = re.match(r"^(\d{4})-(\d{1,2})$", value_str)
    if not m:
        return False
    year, month = m.group(1), int(m.group(2))
    if not 1 <= month <= 12:
        return False
    return _value_matches_text(pdf_text, year) and _value_matches_text(pdf_text, _SPANISH_MONTHS[month])


def _integral_decimal_rendered_as_integer_hit(pdf_text, path, value_str):
    """True when a decimal whole number (e.g. 52.0) is printed as a bare
    integer token (e.g. 52) in the PDF for known contribution-counter fields.
    """
    if not any(hint in path for hint in _INTEGER_RENDERED_NUMERIC_PATH_HINTS):
        return False

    normalized = value_str.replace(",", ".")
    if not re.match(r"^-?\d+\.0+$", normalized):
        return False

    try:
        int_token = str(int(float(normalized)))
    except ValueError:
        return False

    # Require a standalone alphanumeric token to avoid matching inside
    # larger numeric/alphanumeric fragments.
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(int_token)}(?![A-Za-z0-9])")
    return bool(pattern.search(pdf_text))


def _should_skip_low_signal_short_value(path, value_str):
    """True when the value is too short to verify reliably and belongs to a
    known low-signal path family where short literals are often not explicitly
    printed in machine-searchable text.
    """
    return len(value_str) < MIN_CONFIDENT_MATCH_LENGTH and any(
        hint in path for hint in _LOW_SIGNAL_SHORT_PATH_HINTS
    )


def _strip_diacritics(text):
    """Removes accents/diacritical marks (á→a, í→i, ñ→n, ç→c, and so on) via Unicode
    decomposition. A person's name or a place name is often transcribed with and
    without its accents interchangeably across different systems -- "Maria" in the
    JSON and "María" in the PDF, or "Peniscola" vs "Peníscola" -- and a plain user
    reviewing that wouldn't consider it a real discrepancy, just a different way of
    writing the same name. NFKD decomposition splits an accented character into its
    base letter plus a separate combining mark; dropping the combining marks leaves
    just the base letters.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _accent_insensitive_hit(pdf_text_stripped, variants):
    """Like `_confident_variant_hit`, but with diacritics stripped from both the
    candidate variant and the PDF text before comparing, so accent-only differences
    between the JSON and the PDF -- in either direction -- still count as a
    confident Match rather than a false Unverifiable/Discrepancy.
    """
    return any(
        len(v) >= MIN_CONFIDENT_MATCH_LENGTH and _value_matches_text(pdf_text_stripped, _strip_diacritics(v))
        for v in variants
    )


def _confident_variant_hit(pdf_text, variants):
    """Like `_value_matches_text`, but only counts a hit as confident if the specific
    variant that matched is itself long enough to be trustworthy (see
    MIN_CONFIDENT_MATCH_LENGTH). This matters because a variant can be short even when
    the original JSON value isn't -- e.g. "0.00" is 4 characters, but its bare-integer
    variant "0" is 1, and a lone "0" is nearly guaranteed to appear somewhere in a real
    document by coincidence. Checking value_str's length alone would miss that; this
    checks every candidate variant individually instead.
    """
    return any(
        len(v) >= MIN_CONFIDENT_MATCH_LENGTH and _value_matches_text(pdf_text, v)
        for v in variants
    )


def _all_words_present(pdf_text, value_str, min_word_length=3):
    """Fallback for multi-word values whose exact phrase isn't found as-is: true if
    every significant word appears *somewhere* in the text on its own, regardless
    of order or adjacency. This catches cases like a PDF that prints a person's
    name as separate 'Cognome' / 'Nome' fields (in surname-first order) while the
    JSON stores it as a single combined 'given name + surname' string — the exact
    phrase never appears verbatim, but every word making up the name does.
    Short connector words (below min_word_length) are ignored to avoid spurious
    matches on common short tokens.
    """
    tokens = [t for t in _WHITESPACE_RE.split(value_str.strip()) if len(t) >= min_word_length]
    if len(tokens) < 2:
        return False
    return all(_value_matches_text(pdf_text, t) for t in tokens)


def _loose_trace_present(pdf_text_lower, variants):
    """Weak, unanchored, case-insensitive substring check (no word boundaries) —
    the old (pre-fix) matching behavior. Used only as a fallback signal *after*
    the strict checks above have already failed.

    A hit here does NOT mean the field is verified — it means some textual trace
    of the value exists somewhere in the PDF, but only as part of a longer word
    or in a form the strict checks correctly refuse to count as confirmation
    (e.g. "ITALIA" only ever appearing as part of "ITALIANA" — a different fact,
    citizenship rather than birth country). That's ambiguous, not confirmatory,
    so it's surfaced separately as "unverifiable" rather than lumped in with
    fields that have zero trace in the document at all (which is stronger
    evidence of a genuine discrepancy).
    """
    return any(var.lower() in pdf_text_lower for var in variants)


# Very short values (single letters/digits, 2-character codes) show up constantly
# in structured data as internal classification codes -- e.g. a "clave" of "A" or
# "F1", a "tipo" of "3". A bare presence-in-text hit on something this short is
# weak evidence: in any document of realistic length, a 1-2 character token is
# likely to turn up somewhere by pure coincidence, unrelated to the field being
# checked (a lone "A" matches constantly just because "a" is a common Spanish
# word; a lone "3" matches any stray digit). So a hit on a value shorter than
# this is never treated as a confident Match -- at best it's Unverifiable.
MIN_CONFIDENT_MATCH_LENGTH = 3


