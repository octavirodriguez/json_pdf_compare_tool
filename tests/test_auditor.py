"""
Unit tests for auditor.py.

Run with:  pytest tests/test_auditor.py -v
"""
import json
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auditor import (
    MIN_CONFIDENT_MATCH_LENGTH,
    TRAILING_SUFFIX_LENGTH,
    _accent_insensitive_hit,
    _all_words_present,
    _build_phrase_regex,
    _confident_variant_hit,
    _loose_trace_present,
    _strip_diacritics,
    _value_matches_text,
    _year_month_table_hit,
    audit_directory_recursively,
    compare_json_with_pdf,
    derive_base_key,
    extract_pdf_text,
)


# ---------------------------------------------------------------------------
# _strip_diacritics
# ---------------------------------------------------------------------------

class TestStripDiacritics:
    def test_accented_vowels(self):
        assert _strip_diacritics("María") == "Maria"

    def test_tilde_n(self):
        assert _strip_diacritics("España") == "Espana"

    def test_already_plain(self):
        assert _strip_diacritics("hello") == "hello"

    def test_mixed_string(self):
        assert _strip_diacritics("Ángel Pérez") == "Angel Perez"


# ---------------------------------------------------------------------------
# _build_phrase_regex
# ---------------------------------------------------------------------------

class TestBuildPhraseRegex:
    def test_single_word(self):
        pat = _build_phrase_regex("hello")
        assert pat.search("say hello world")
        assert not pat.search("helloing")  # word boundary respected

    def test_multi_word_tolerates_whitespace(self):
        pat = _build_phrase_regex("John Smith")
        assert pat.search("John\nSmith")   # line break between words
        assert pat.search("John  Smith")   # extra spaces

    def test_empty_string_returns_none(self):
        assert _build_phrase_regex("   ") is None

    def test_case_insensitive(self):
        pat = _build_phrase_regex("madrid")
        assert pat.search("MADRID")

    def test_number_immediately_followed_by_letter_still_matches(self):
        # PDF table-cell extraction often drops the whitespace between a
        # boxed numeric value and the label text that follows it.
        pat = _build_phrase_regex("5.242,20")
        assert pat.search("27 5.242,20Codice fiscale del percipiente")

    def test_number_still_blocked_inside_longer_number(self):
        # The digit-aware boundary must still refuse to match a number as a
        # substring of a longer, different number.
        pat = _build_phrase_regex("20")
        assert not pat.search("Year 2025 applies")
        assert not pat.search("applies 1520 here")


# ---------------------------------------------------------------------------
# _value_matches_text
# ---------------------------------------------------------------------------

class TestValueMatchesText:
    def test_exact_match(self):
        assert _value_matches_text("The amount is 100 euros", "100")

    def test_no_match(self):
        assert not _value_matches_text("nothing here", "999")

    def test_word_boundary_not_substring(self):
        # "20" must not match inside "2025"
        assert not _value_matches_text("Year 2025 applies", "20")

    def test_multi_word_phrase(self):
        assert _value_matches_text("Name: John Smith born 1990", "John Smith")


# ---------------------------------------------------------------------------
# _confident_variant_hit
# ---------------------------------------------------------------------------

class TestConfidentVariantHit:
    def test_long_variant_matches(self):
        assert _confident_variant_hit("Total: 1.234,56 EUR", ["1.234,56"])

    def test_short_variant_never_confident(self):
        # variant shorter than MIN_CONFIDENT_MATCH_LENGTH must not count
        short = "x" * (MIN_CONFIDENT_MATCH_LENGTH - 1)
        assert not _confident_variant_hit(f"text {short} here", [short])

    def test_first_variant_fails_second_succeeds(self):
        assert _confident_variant_hit("value 1.234,56", ["999.999,99", "1.234,56"])


# ---------------------------------------------------------------------------
# _all_words_present
# ---------------------------------------------------------------------------

class TestAllWordsPresent:
    def test_words_in_different_order(self):
        assert _all_words_present("Smith born John was here", "John Smith")

    def test_single_word_returns_false(self):
        # function requires at least 2 significant tokens
        assert not _all_words_present("hello world", "hello")

    def test_short_words_ignored(self):
        # "de" is 2 chars, below default min_word_length=3; only "Juan" and "Dios" counted
        assert _all_words_present("Juan de Dios visited", "Juan de Dios")

    def test_missing_word_returns_false(self):
        assert not _all_words_present("only John is here", "John Smith")


# ---------------------------------------------------------------------------
# _loose_trace_present
# ---------------------------------------------------------------------------

class TestLooseTracePresent:
    def test_substring_match(self):
        assert _loose_trace_present("italiana republic", ["italia"])

    def test_no_match(self):
        assert not _loose_trace_present("nothing relevant", ["xyz123"])

    def test_case_insensitive(self):
        # function expects pre-lowercased text
        assert _loose_trace_present("italiana", ["ITALIA"])


# ---------------------------------------------------------------------------
# _accent_insensitive_hit
# ---------------------------------------------------------------------------

class TestAccentInsensitiveHit:
    def test_accented_json_plain_pdf(self):
        pdf_stripped = _strip_diacritics("Maria Garcia lives here")
        assert _accent_insensitive_hit(pdf_stripped, ["María García"])

    def test_plain_json_accented_pdf(self):
        pdf_stripped = _strip_diacritics("Residente en Peniscola")
        assert _accent_insensitive_hit(pdf_stripped, ["Peníscola"])

    def test_short_variant_not_confident(self):
        pdf_stripped = _strip_diacritics("ab text")
        short = "ab"  # len < MIN_CONFIDENT_MATCH_LENGTH
        assert not _accent_insensitive_hit(pdf_stripped, [short])


# ---------------------------------------------------------------------------
# _year_month_table_hit
# ---------------------------------------------------------------------------

class TestYearMonthTableHit:
    def test_year_and_month_name_present_far_apart(self):
        # Simulates a Social-Security-style year x month matrix table: "2026"
        # is a row header, "Junio" a column header elsewhere in the text,
        # with no adjacency and no literal "2026-06"/"06/2026" anywhere.
        pdf = "Base de cotizacion 2026 Enero Febrero Marzo Abril Mayo Junio 2952.69"
        assert _year_month_table_hit(pdf, "2026-06")

    def test_missing_month_name_is_not_a_hit(self):
        pdf = "Base de cotizacion 2026 Enero Febrero Marzo"
        assert not _year_month_table_hit(pdf, "2026-06")

    def test_missing_year_is_not_a_hit(self):
        pdf = "Junio Julio Agosto"
        assert not _year_month_table_hit(pdf, "2026-06")

    def test_non_year_month_value_is_not_a_hit(self):
        assert not _year_month_table_hit("2026 Junio", "not-a-date")
        assert not _year_month_table_hit("2026 Junio", "2026-13")


# ---------------------------------------------------------------------------
# derive_base_key
# ---------------------------------------------------------------------------

class TestDeriveBaseKey:
    def test_strips_suffix(self):
        stem = "Document_Name_W2QADYOZ_ZQW"  # 13-char suffix: _W2QADYOZ_ZQW
        result = derive_base_key(stem)
        assert result == "Document_Name"

    def test_short_stem_returned_as_is(self, capsys):
        short = "short"
        result = derive_base_key(short)
        assert result == short
        assert "⚠️" in capsys.readouterr().out

    def test_exact_boundary_returned_as_is(self):
        stem = "x" * TRAILING_SUFFIX_LENGTH
        result = derive_base_key(stem)
        assert result == stem


# ---------------------------------------------------------------------------
# compare_json_with_pdf — three-tier classification
# ---------------------------------------------------------------------------

class TestCompareJsonWithPdf:
    PDF = textwrap.dedent("""\
        Nombre: John Smith
        Fecha de nacimiento: 15/04/1985
        NIF: 12345678A
        Importe total: 1.234,56
        País: España
    """)

    def test_confirmed_match_name(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"name": "John Smith"}, self.PDF
        )
        assert any("John Smith" in v for _, v in matches)
        assert not mismatches

    def test_date_variant_confirmed(self):
        matches, _, _ = compare_json_with_pdf({"dob": "1985-04-15"}, self.PDF)
        assert any("1985-04-15" in v for _, v in matches)

    def test_european_number_confirmed(self):
        matches, _, _ = compare_json_with_pdf({"amount": "1234.56"}, self.PDF)
        assert any("1234.56" in v for _, v in matches)

    def test_discrepancy_value_absent(self):
        _, mismatches, _ = compare_json_with_pdf({"nif": "99999999Z"}, self.PDF)
        assert any("99999999Z" in v for _, v in mismatches)

    def test_boolean_values_skipped(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"active": "true", "deleted": "false"}, self.PDF
        )
        assert not matches and not mismatches and not unverifiable

    def test_short_value_goes_to_unverifiable(self):
        _, _, unverifiable = compare_json_with_pdf({"code": "AB"}, self.PDF)
        assert any("AB" in v for _, v in unverifiable)

    def test_none_and_empty_values_skipped(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"a": None, "b": "   "}, self.PDF
        )
        assert not matches and not mismatches and not unverifiable

    def test_nested_dict_traversed(self):
        matches, _, _ = compare_json_with_pdf(
            {"person": {"name": "John Smith"}}, self.PDF
        )
        assert any("John Smith" in v for _, v in matches)

    def test_list_traversed(self):
        matches, _, _ = compare_json_with_pdf(
            {"names": ["John Smith"]}, self.PDF
        )
        assert any("John Smith" in v for _, v in matches)

    def test_accent_difference_still_matches(self):
        # PDF has "España", JSON has "Espana" (no tilde)
        matches, mismatches, _ = compare_json_with_pdf({"country": "Espana"}, self.PDF)
        assert any("Espana" in v for _, v in matches)
        assert not mismatches

    def test_loose_trace_goes_to_unverifiable(self):
        # "ITALIA" only appears inside "ITALIANA", not as a standalone word
        pdf = "Cittadinanza: ITALIANA"
        _, mismatches, unverifiable = compare_json_with_pdf({"country": "ITALIA"}, pdf)
        assert any("ITALIA" in v for _, v in unverifiable)
        assert not mismatches

    def test_number_run_into_following_label_still_matches(self):
        # No whitespace between the boxed value and the next label -- a real
        # pypdf extraction artifact seen in Agenzia Entrate CU forms.
        pdf = "27 5.242,20Codice fiscale del percipiente Mod. N."
        matches, mismatches, _ = compare_json_with_pdf({"ammontare": "5242.20"}, pdf)
        assert any("5242.20" in v for _, v in matches)
        assert not mismatches

    def test_number_without_thousands_grouping_matches(self):
        # Not every printed amount gets a thousands separator.
        pdf = "Importo: 5242,20 euro"
        matches, _, _ = compare_json_with_pdf({"amount": "5242.20"}, pdf)
        assert any("5242.20" in v for _, v in matches)

    def test_date_printed_as_space_separated_grid_boxes(self):
        # Italian "giorno mese anno" grid forms print each date component as
        # its own boxed value with only whitespace between them.
        pdf = "365 01 12 2022 X"
        matches, mismatches, _ = compare_json_with_pdf({"dataInizio": "2022-12-01"}, pdf)
        assert any("2022-12-01" in v for _, v in matches)
        assert not mismatches

    def test_date_printed_without_leading_zeros(self):
        pdf = "del 14/3/2026"
        matches, _, _ = compare_json_with_pdf({"data": "2026-03-14"}, pdf)
        assert any("2026-03-14" in v for _, v in matches)

    def test_day_month_only_value_printed_concatenated(self):
        # INAIL insurance-period fields store a bare "giorno-mese" pair with
        # no year; the PDF prints the two components back-to-back with no
        # separator, day zero-padded, month at its natural width.
        pdf = "101 3112 B923Codice fiscale del percipiente"
        matches, mismatches, _ = compare_json_with_pdf(
            {"dataInizioGiornoMese": "10-1", "dataFineGiornoMese": "31-12"}, pdf
        )
        matched_values = {v for _, v in matches}
        assert "10-1" in matched_values
        assert "31-12" in matched_values
        assert not mismatches

    def test_year_month_period_matches_table_layout(self):
        # Spanish Social Security "vida laboral" reports print a bare
        # "período" like "2026-07" as a year x month matrix table -- the
        # year and the Spanish month name appear as separate row/column
        # headers, not as one adjacent date string.
        pdf = "Periodos de cotizacion 2026 Enero Febrero Marzo Abril Mayo Junio Julio Base 4092.07"
        matches, mismatches, _ = compare_json_with_pdf({"periodo": "2026-07"}, pdf)
        assert any("2026-07" in v for _, v in matches)
        assert not mismatches

    def test_year_month_period_matches_adjacent_rendering(self):
        pdf = "Periodo: julio de 2026"
        matches, mismatches, _ = compare_json_with_pdf({"periodo": "2026-07"}, pdf)
        assert any("2026-07" in v for _, v in matches)
        assert not mismatches

    def test_year_month_period_without_month_still_a_discrepancy(self):
        pdf = "Periodos de cotizacion 2026 Enero Febrero"
        _, mismatches, _ = compare_json_with_pdf({"periodo": "2026-07"}, pdf)
        assert any("2026-07" in v for _, v in mismatches)

    def test_settimane_matches_pdf_abbreviation_sett(self):
        pdf = "Tipo contributo: sett."
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"regimeGenerale": [{"tipoContributo": "Settimane"}]},
            pdf,
        )
        assert any("Settimane" in v for _, v in matches)
        assert not mismatches
        assert not unverifiable

    def test_integral_decimal_contribution_matches_plain_integer(self):
        pdf = "Contributi utili diritto: 52"
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"regimeGenerale": [{"contributiUtiliDiritto": "52.0"}]},
            pdf,
        )
        assert any("52.0" in v for _, v in matches)
        assert not mismatches
        assert not unverifiable

    def test_integral_decimal_giorni_matches_plain_integer(self):
        pdf = "Giorni: 17"
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"lavoratoriSpettacoloSport": {"estrattoContoSpettacoloSport": [{"giorni": "17.0"}]}},
            pdf,
        )
        assert any("17.0" in v for _, v in matches)
        assert not mismatches
        assert not unverifiable

    def test_low_signal_short_code_path_is_skipped(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"regimeGenerale": [{"primaNota": {"codice": "O"}}]},
            "",
        )
        assert not matches
        assert not mismatches
        assert not unverifiable

    def test_low_signal_short_mesi_contribuzione_is_skipped(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"regimeParasubordinati": {"estrattoContoMontanteContributivo": [{"mesiContribuzione": "3"}]}},
            "",
        )
        assert not matches
        assert not mismatches
        assert not unverifiable

    def test_comune_sigla_matches_parenthesized_pdf_format(self):
        pdf = "Comune di nascita: NAPOLI (NA)"
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"datiIdentificativi": {"comuneStatoNascita": "NAPOLI NA"}},
            pdf,
        )
        assert any("NAPOLI NA" in v for _, v in matches)
        assert not mismatches
        assert not unverifiable


# ---------------------------------------------------------------------------
# extract_pdf_text — error handling
# ---------------------------------------------------------------------------

class TestExtractPdfText:
    def test_returns_empty_string_on_error(self, tmp_path, capsys):
        bad_pdf = tmp_path / "bad.pdf"
        bad_pdf.write_bytes(b"not a real pdf")
        result = extract_pdf_text(str(bad_pdf))
        assert result is None
        assert "Error reading PDF" in capsys.readouterr().out

    def test_missing_file_returns_none(self, capsys):
        result = extract_pdf_text("/nonexistent/path/file.pdf")
        assert result is None
        assert "Error reading PDF" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# audit_directory_recursively — file pairing and error paths
# ---------------------------------------------------------------------------

class TestAuditDirectoryRecursively:
    def test_nonexistent_directory(self, tmp_path, capsys):
        results, report = audit_directory_recursively(
            str(tmp_path / "does_not_exist"),
            str(tmp_path / "reports"),
        )
        assert results == []
        assert report is None
        assert "does not exist" in capsys.readouterr().out

    def test_no_pairs_found(self, tmp_path, capsys):
        data = tmp_path / "data"
        data.mkdir()
        (data / "only_a_file_W2QADYOZ_ZQW.json").write_text("{}", encoding="utf-8")
        results, report = audit_directory_recursively(str(data), str(tmp_path / "reports"))
        assert results == []
        assert report is None
        assert "No matching" in capsys.readouterr().out

    def test_duplicate_pdf_is_skipped(self, tmp_path, capsys):
        data = tmp_path / "data"
        data.mkdir()
        reports = tmp_path / "reports"
        reports.mkdir()
        # Two PDFs that map to the same base key
        (data / "Doc_Alpha_W2QADYOZ_ZQW.pdf").write_bytes(b"fake pdf")
        (data / "Doc_Alpha_W2QADYOZ_AAA.pdf").write_bytes(b"fake pdf 2")
        (data / "Doc_Alpha_W2QADYOZ_ZQW.json").write_text('{"k": "v"}', encoding="utf-8")
        audit_directory_recursively(str(data), str(reports))
        assert "Multiple" in capsys.readouterr().out

    def test_invalid_json_is_skipped(self, tmp_path, capsys):
        data = tmp_path / "data"
        data.mkdir()
        reports = tmp_path / "reports"
        reports.mkdir()
        (data / "Doc_Alpha_W2QADYOZ_ZQW.json").write_text("not json", encoding="utf-8")

        # Provide a real (minimal) PDF via mocking so extract_pdf_text gets past the read
        with patch("auditor.extract_pdf_text", return_value="some text"):
            # We still need a PDF file to exist so file discovery finds it
            (data / "Doc_Alpha_W2QADYOZ_ZQW.pdf").write_bytes(b"fake")
            results, _ = audit_directory_recursively(str(data), str(reports))

        assert results == []
        assert "Error reading JSON" in capsys.readouterr().out
