import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
import pypdf


def extract_pdf_text(pdf_path):
    """Extracts all plain text from a PDF file."""
    try:
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"❌ Error reading PDF {pdf_path}: {e}")
        return None


_WHITESPACE_RE = re.compile(r"\s+")

_SPANISH_MONTHS = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}


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


def compare_json_with_pdf(json_data, pdf_text):
    """Recursively walks through the JSON and verifies if values exist within the PDF text."""
    mismatches = []
    matches = []
    unverifiable = []
    pdf_text_lower = pdf_text.lower()
    # Computed once per document rather than once per field, since stripping
    # diacritics from the full PDF text is the same work every time either way.
    pdf_text_stripped = _strip_diacritics(pdf_text)

    def generate_value_variants(value_str):
        variants = [value_str]

        # 1. Variants for float/currency numbers
        try:
            val_float = float(value_str)
            # European format with dot for thousands and comma for decimals (1.166,34)
            variants.append(f"{val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            # European format with dot for thousands and dot for decimals (1.166.34)
            variants.append(f"{val_float:,.2f}".replace(",", "."))
            # Plain European decimal-comma with NO thousands grouping at all
            # (5242,20). Not every printed amount gets a thousands separator --
            # smaller amounts in these forms are frequently printed exactly as
            # they're stored, just with the decimal point swapped for a comma.
            if "." in value_str:
                variants.append(value_str.replace(".", ","))
            # Not every decimal value is currency rounded to 2 places -- e.g. an
            # investment fund's number of shares can carry 6 decimal digits
            # ("0.685843"). Forcing 2-decimal rounding there produces "0.69",
            # which never appears in the PDF because the PDF prints the value's
            # full original precision. So also try a variant that preserves
            # however many decimal places the source value actually has.
            if "." in value_str:
                native_places = len(value_str.split(".", 1)[1])
                if native_places != 2:
                    variants.append(
                        f"{val_float:,.{native_places}f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    )
                    variants.append(f"{val_float:,.{native_places}f}".replace(",", "."))
            # Whole numbers are frequently printed without a redundant ",00"/".00"
            # suffix -- e.g. a 100% ownership share is printed as "100%", never
            # "100,00%". Real-world testing against Spanish tax documents showed
            # this causes false discrepancies for whole-number percentages, so
            # whole values also get a bare-integer variant, in both European
            # thousands-separator style and plain.
            if val_float == int(val_float):
                variants.append(f"{int(val_float):,}".replace(",", "."))
                variants.append(str(int(val_float)))
        except ValueError:
            pass

        # 2. Variants for ISO dates (YYYY-MM-DD -> other common renderings)
        try:
            date_obj = datetime.strptime(value_str, "%Y-%m-%d")
            variants.append(date_obj.strftime("%d/%m/%Y"))
            variants.append(date_obj.strftime("%d-%m-%Y"))
            variants.append(date_obj.strftime("%d.%m.%Y"))
            # Grid-style official forms ("giorno mese anno") often print each
            # date component as its own boxed value with nothing but
            # whitespace between them -- no slash or dash at all, e.g.
            # "01 12 2022" for 2022-12-01.
            variants.append(date_obj.strftime("%d %m %Y"))
            # Some printed dates skip the leading zero on day/month
            # ("14/3/2026" rather than "14/03/2026").
            variants.append(f"{date_obj.day}/{date_obj.month}/{date_obj.year}")
            variants.append(f"{date_obj.day}-{date_obj.month}-{date_obj.year}")
        except ValueError:
            pass

        # 2b. Variants for year-month-only values (YYYY-MM, no day) that ARE
        # printed together somewhere in the PDF, rather than split across a
        # table's separate row/column headers (see _year_month_table_hit for
        # that case) -- e.g. "07/2026" or "julio 2026" for period "2026-07".
        year_month_match = re.match(r"^(\d{4})-(\d{1,2})$", value_str)
        if year_month_match:
            year_str, month_str = year_month_match.groups()
            month_num = int(month_str)
            if 1 <= month_num <= 12:
                variants.append(f"{month_num:02d}/{year_str}")
                variants.append(f"{month_num}/{year_str}")
                variants.append(f"{_SPANISH_MONTHS[month_num]} {year_str}")
                variants.append(f"{_SPANISH_MONTHS[month_num]} de {year_str}")

        # 3. Variants for day-month-only values with no year, e.g. "10-1" or
        # "31-12". These show up in insurance/registration-period fields
        # where the JSON stores a bare "giorno-mese" pair. The source PDF's
        # grid boxes print the two components back-to-back with no separator
        # at all, with the day always zero-padded to two digits but the
        # month printed at its natural width -- day=10/month=1 becomes
        # "101", not "0101".
        day_month_match = re.match(r"^(\d{1,2})-(\d{1,2})$", value_str)
        if day_month_match:
            day, month = int(day_month_match.group(1)), int(day_month_match.group(2))
            variants.append(f"{day:02d}{month}")
            variants.append(f"{day:02d}{month:02d}")
            variants.append(f"{day:02d}/{month}")
            variants.append(f"{day:02d} {month}")

        return variants

    def search_recursive(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                search_recursive(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, elem in enumerate(obj):
                search_recursive(elem, f"{path}[{i}]")
        elif obj is not None and str(obj).strip() != "":
            value_str = str(obj).strip()

            if value_str.lower() in ["true", "false"]:
                return

            if len(value_str) < MIN_CONFIDENT_MATCH_LENGTH:
                # Too short for a text search to say anything trustworthy either
                # way -- see MIN_CONFIDENT_MATCH_LENGTH above. Real-world testing
                # confirmed both directions of this: a short code can coincidentally
                # match unrelated text (false Match), and short internal codes are
                # also frequently never printed verbatim at all -- the PDF prints a
                # human-readable label instead (e.g. clave "F1" is printed as
                # "Cursos, conferencias, obras lit., art. o científicas") -- which
                # would otherwise look like a confident Discrepancy for something
                # that was never wrong to begin with. So values this short always
                # land in Unverifiable, never a confident Match or Discrepancy.
                unverifiable.append((path, value_str))
                return

            variants = generate_value_variants(value_str)
            if (
                _confident_variant_hit(pdf_text, variants)
                or _all_words_present(pdf_text, value_str)
                or _accent_insensitive_hit(pdf_text_stripped, variants)
                or _year_month_table_hit(pdf_text, value_str)
            ):
                matches.append((path, value_str))
            elif _loose_trace_present(pdf_text_lower, variants):
                unverifiable.append((path, value_str))
            else:
                mismatches.append((path, value_str))

    search_recursive(json_data)
    return matches, mismatches, unverifiable


# Discrepancies at or below this length get an extra hint in the generated report.
# Real-world testing turned up several 3-4 character classification/regime codes
# (e.g. "C13", "0521") that never appear literally in the PDF at all -- the PDF
# prints a human-readable label instead. But values of that same length are also
# genuinely, correctly confirmed elsewhere in the very same documents (cadastral
# parcel numbers, small withheld amounts), so there's no length threshold that can
# safely auto-reclassify these without also hiding real errors in those fields.
# Rather than guess, the report just flags the possibility so a human can check.
SHORT_CODE_HINT_LENGTH = 5


def generate_markdown_report(results, reports_dir):
    """Generates a clean and structured Markdown audit report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_filename = f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_path = os.path.join(reports_dir, report_filename)

    total_docs = len(results)
    fully_verified_docs = sum(1 for r in results if not r["mismatches"] and not r["unverifiable"])
    needs_review_docs = sum(1 for r in results if not r["mismatches"] and r["unverifiable"])
    issues_docs = sum(1 for r in results if r["mismatches"])
    total_issues = sum(len(r["mismatches"]) for r in results)
    total_unverifiable = sum(len(r["unverifiable"]) for r in results)

    def doc_status(r):
        if r["mismatches"]:
            return "❌ ISSUES FOUND"
        if r["unverifiable"]:
            return "🟡 NEEDS REVIEW"
        return "✅ OK"

    md = []
    md.append("# 📊 JSON-PDF Compare Tool — Audit Report\n")
    md.append(f"**Execution Date:** `{now}`  \n")
    md.append(f"**Report Path:** `{report_path}`\n")
    md.append("---\n")

    # Executive Summary
    md.append("## 📈 Executive Summary\n")
    md.append(f"- **Analyzed Documents:** {total_docs}")
    md.append(f"- **Fully Verified Documents:** {fully_verified_docs} ✅")
    md.append(f"- **Documents Needing Review:** {needs_review_docs} 🟡")
    md.append(f"- **Documents with Issues:** {issues_docs} ❌")
    md.append(f"- **Total Discrepancies Found:** {total_issues}")
    md.append(f"- **Total Unverifiable Fields:** {total_unverifiable}\n")

    # Status Table
    md.append("### 📑 Document Status Overview\n")
    md.append("| Document | Matches | Unverifiable | Discrepancies | Status |")
    md.append("| :--- | :---: | :---: | :---: | :---: |")
    for r in results:
        md.append(
            f"| `{r['name']}` | {len(r['matches'])} | {len(r['unverifiable'])} | "
            f"{len(r['mismatches'])} | {doc_status(r)} |"
        )
    md.append("\n---\n")

    # Detailed Audit
    md.append("## 🔍 Detailed Audit per Document\n")
    for r in results:
        md.append(f"### 📄 Document: `{r['name']}`\n")
        if r.get("pdf_read_error"):
            md.append(
                "> ⚠️ **PDF could not be read.** The file may be corrupted, password-protected, or "
                "not a valid PDF. All fields below are shown as Discrepancies only because the PDF "
                "text was unavailable — they do not reflect actual data problems.\n"
            )
        md.append(f"- **Matching Fields:** {len(r['matches'])}")
        md.append(f"- **Unverifiable Fields:** {len(r['unverifiable'])}")
        md.append(f"- **Discrepancies:** {len(r['mismatches'])}\n")

        if r["mismatches"]:
            md.append("#### ❌ Discrepancies to Review:\n")
            md.append(
                "> **Note:** The JSON field exists, but no trace of its value — not even a "
                "partial or coincidental one — was found anywhere in the PDF text. This is the "
                "strongest signal of a genuine data problem.\n"
            )
            for path, val in r["mismatches"]:
                md.append(f"* **JSON Path:** `{path}`")
                md.append(f"  * **Expected Value (JSON):** `{val}`")
                action = "Check if this value appears in a different format, is truncated, or if pages are missing from the PDF."
                if len(val) <= SHORT_CODE_HINT_LENGTH:
                    action += (
                        " Short values like this are sometimes internal classification or regime codes "
                        "that the source PDF prints as a descriptive label instead of the literal code "
                        "(e.g. a code of \"F1\" printed as \"Cursos, conferencias, obras lit., art. o "
                        "científicas\") -- if that's the case here, this may not be an error at all, just "
                        "something the tool can't confirm by text search. Worth a quick look before treating "
                        "it as a real discrepancy."
                    )
                md.append(f"  * *Action:* {action}\n")

        if r["unverifiable"]:
            md.append("#### 🟡 Unverifiable Fields:\n")
            md.append(
                "> **Note:** The JSON field's value wasn't confirmed in the PDF text, but a weak or "
                "coincidental textual trace was found (e.g. only as part of a longer, different word). "
                "This isn't necessarily wrong — the fact may simply not be stated explicitly in the "
                "document — but it also couldn't be confirmed automatically, so it's worth a quick "
                "manual look rather than treating it as either pass or fail.\n"
            )
            for path, val in r["unverifiable"]:
                md.append(f"* **JSON Path:** `{path}`")
                md.append(f"  * **Expected Value (JSON):** `{val}`")
                md.append("  * *Action:* Manually confirm whether this fact is stated (even implicitly) in the PDF.\n")

        if not r["mismatches"] and not r["unverifiable"]:
            md.append("🎉 **All extracted JSON fields have been successfully validated against the PDF.**\n")

        md.append("---\n")

    # Write file
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines("\n".join(md))

    return report_path


# PDF/JSON pairs share a common base name, but each file has its own
# system-generated suffix tacked on before the extension, e.g.:
#   ..._W2IWIZ2W_DBS.pdf
#   ..._W2IWIZ9C_4US.json
# Stripping this fixed-length suffix from both stems is what lets us pair
# files by base name instead of requiring identical filenames, which in turn
# is what allows dropping whole batches of pairs into the data folder at once.
TRAILING_SUFFIX_LENGTH = 13


def derive_base_key(stem):
    """Strips the trailing system-generated suffix from a filename stem so PDF/JSON pairs can be matched.

    Falls back to the full stem (with a warning) if the name is too short to safely strip a suffix from.
    """
    if len(stem) <= TRAILING_SUFFIX_LENGTH:
        print(
            f"⚠️ Filename '{stem}' is too short to strip a {TRAILING_SUFFIX_LENGTH}-character "
            "suffix from; using it as-is as the pairing key."
        )
        return stem
    return stem[:-TRAILING_SUFFIX_LENGTH]


def audit_directory_recursively(root_dir, reports_dir):
    """Searches for PDF/JSON pairs, compares them, generates a report, and returns structured results."""
    pdf_map = {}
    json_map = {}

    root_path = Path(root_dir)
    if not root_path.exists():
        print(f"❌ Directory '{root_dir}' does not exist.")
        return [], None

    for file in root_path.rglob("*"):
        if not file.is_file():
            continue

        suffix = file.suffix.lower()
        if suffix not in (".pdf", ".json"):
            continue

        base_key = derive_base_key(file.stem)
        target_map = pdf_map if suffix == ".pdf" else json_map

        if base_key in target_map:
            print(
                f"⚠️ Multiple {suffix} files map to the same base name '{base_key}': "
                f"keeping '{target_map[base_key].name}', ignoring '{file.name}'."
            )
            continue

        target_map[base_key] = file

    common_names = set(pdf_map.keys()).intersection(set(json_map.keys()))

    if not common_names:
        print(f"⚠️ No matching PDF and JSON file pairs found in '{root_dir}'.")
        return [], None

    print(f"\n🔍 Running audit for {len(common_names)} file pairs...\n" + "=" * 60)

    results = []

    for name in sorted(common_names):
        pdf_path = pdf_map[name]
        json_path = json_map[name]

        pdf_text = extract_pdf_text(pdf_path)
        pdf_read_error = pdf_text is None

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
        except Exception as e:
            print(f"❌ Error reading JSON {json_path.name}: {e}")
            continue

        matches, mismatches, unverifiable = compare_json_with_pdf(json_data, pdf_text or "")

        results.append({
            "name": name,
            "pdf_read_error": pdf_read_error,
            "matches": matches,
            "mismatches": mismatches,
            "unverifiable": unverifiable
        })

        print(
            f"📄 Processed: {name} | ✅ {len(matches)} ok | "
            f"🟡 {len(unverifiable)} unverifiable | ❌ {len(mismatches)} errors"
        )

    # Generate Markdown Report
    report_path = generate_markdown_report(results, reports_dir)

    print("\n" + "=" * 60)
    print("📊 Audit completed!")
    print(f"📁 Report successfully generated at: {report_path}")
 
    return results, report_path


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "./data"
    reports_dir = "./reports"

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    audit_directory_recursively(data_dir, reports_dir)