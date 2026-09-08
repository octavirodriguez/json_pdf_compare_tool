import re
from datetime import datetime

from auditor_text import (
    _SPANISH_MONTHS,
    _VALUE_ALIASES,
    _accent_insensitive_hit,
    _all_words_present,
    _confident_variant_hit,
    _integral_decimal_rendered_as_integer_hit,
    _loose_trace_present,
    _should_skip_low_signal_short_value,
    _strip_diacritics,
    _year_month_table_hit,
    MIN_CONFIDENT_MATCH_LENGTH,
)


def compare_json_with_pdf(json_data, pdf_text, profile=None):
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

        alias_variants = _VALUE_ALIASES.get(value_str.lower())
        if alias_variants:
            variants.extend(alias_variants)

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
            variants.append(
                f"{date_obj.day} de {_SPANISH_MONTHS[date_obj.month]} de {date_obj.year}"
            )
            variants.append(f"{date_obj.day} {_SPANISH_MONTHS[date_obj.month]} {date_obj.year}")
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

        # 4. Variants for Italian city+province renderings where JSON often has
        # "CITY PR" while PDFs print "CITY (PR)".
        comune_match = re.match(r"^(.+?)\s+([A-Z]{2})$", value_str)
        if comune_match:
            city, province = comune_match.groups()
            variants.append(f"{city} ({province})")
            variants.append(f"{city}({province})")

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

            if profile and profile.should_skip_field(path):
                return

            if _should_skip_low_signal_short_value(path, value_str):
                return

            if profile and profile.confident_short_value_hit(pdf_text, path, value_str):
                matches.append((path, value_str))
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
                or _integral_decimal_rendered_as_integer_hit(pdf_text, path, value_str)
            ):
                matches.append((path, value_str))
            elif _loose_trace_present(pdf_text_lower, variants):
                unverifiable.append((path, value_str))
            elif profile and profile.should_mark_unverifiable_if_absent(path):
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


