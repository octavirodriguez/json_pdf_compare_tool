"""Tests for text normalization and value matching helpers."""

from auditor import (
    MIN_CONFIDENT_MATCH_LENGTH,
    _accent_insensitive_hit,
    _all_words_present,
    _build_phrase_regex,
    _confident_variant_hit,
    _loose_trace_present,
    _strip_diacritics,
    _value_matches_text,
    _year_month_table_hit,
)


class TestStripDiacritics:
    def test_accented_vowels(self):
        assert _strip_diacritics("María") == "Maria"

    def test_tilde_n(self):
        assert _strip_diacritics("España") == "Espana"

    def test_already_plain(self):
        assert _strip_diacritics("hello") == "hello"

    def test_mixed_string(self):
        assert _strip_diacritics("Ángel Pérez") == "Angel Perez"


class TestBuildPhraseRegex:
    def test_single_word(self):
        pat = _build_phrase_regex("hello")
        assert pat.search("say hello world")
        assert not pat.search("helloing")

    def test_multi_word_tolerates_whitespace(self):
        pat = _build_phrase_regex("John Smith")
        assert pat.search("John\nSmith")
        assert pat.search("John  Smith")

    def test_empty_string_returns_none(self):
        assert _build_phrase_regex("   ") is None

    def test_case_insensitive(self):
        pat = _build_phrase_regex("madrid")
        assert pat.search("MADRID")

    def test_number_immediately_followed_by_letter_still_matches(self):
        pat = _build_phrase_regex("5.242,20")
        assert pat.search("27 5.242,20Codice fiscale del percipiente")

    def test_number_still_blocked_inside_longer_number(self):
        pat = _build_phrase_regex("20")
        assert not pat.search("Year 2025 applies")
        assert not pat.search("applies 1520 here")


class TestValueMatchesText:
    def test_exact_match(self):
        assert _value_matches_text("The amount is 100 euros", "100")

    def test_no_match(self):
        assert not _value_matches_text("nothing here", "999")

    def test_word_boundary_not_substring(self):
        assert not _value_matches_text("Year 2025 applies", "20")

    def test_multi_word_phrase(self):
        assert _value_matches_text("Name: John Smith born 1990", "John Smith")


class TestConfidentVariantHit:
    def test_long_variant_matches(self):
        assert _confident_variant_hit("Total: 1.234,56 EUR", ["1.234,56"])

    def test_short_variant_never_confident(self):
        short = "x" * (MIN_CONFIDENT_MATCH_LENGTH - 1)
        assert not _confident_variant_hit(f"text {short} here", [short])

    def test_first_variant_fails_second_succeeds(self):
        assert _confident_variant_hit("value 1.234,56", ["999.999,99", "1.234,56"])


class TestAllWordsPresent:
    def test_words_in_different_order(self):
        assert _all_words_present("Smith born John was here", "John Smith")

    def test_single_word_returns_false(self):
        assert not _all_words_present("hello world", "hello")

    def test_short_words_ignored(self):
        assert _all_words_present("Juan de Dios visited", "Juan de Dios")

    def test_missing_word_returns_false(self):
        assert not _all_words_present("only John is here", "John Smith")


class TestLooseTracePresent:
    def test_substring_match(self):
        assert _loose_trace_present("italiana republic", ["italia"])

    def test_no_match(self):
        assert not _loose_trace_present("nothing relevant", ["xyz123"])

    def test_case_insensitive(self):
        assert _loose_trace_present("italiana", ["ITALIA"])


class TestAccentInsensitiveHit:
    def test_accented_json_plain_pdf(self):
        pdf_stripped = _strip_diacritics("Maria Garcia lives here")
        assert _accent_insensitive_hit(pdf_stripped, ["María García"])

    def test_plain_json_accented_pdf(self):
        pdf_stripped = _strip_diacritics("Residente en Peniscola")
        assert _accent_insensitive_hit(pdf_stripped, ["Peníscola"])

    def test_short_variant_not_confident(self):
        pdf_stripped = _strip_diacritics("ab text")
        assert not _accent_insensitive_hit(pdf_stripped, ["ab"])


class TestYearMonthTableHit:
    def test_year_and_month_name_present_far_apart(self):
        pdf = "Base de cotizacion 2026 Enero Febrero Marzo Abril Mayo Junio 2952.69"
        assert _year_month_table_hit(pdf, "2026-06")

    def test_missing_month_name_is_not_a_hit(self):
        pdf = "Base de cotizacion 2026 Enero Febrero Marzo"
        assert not _year_month_table_hit(pdf, "2026-06")

    def test_missing_year_is_not_a_hit(self):
        assert not _year_month_table_hit("Junio Julio Agosto", "2026-06")

    def test_non_year_month_value_is_not_a_hit(self):
        assert not _year_month_table_hit("2026 Junio", "not-a-date")
        assert not _year_month_table_hit("2026 Junio", "2026-13")