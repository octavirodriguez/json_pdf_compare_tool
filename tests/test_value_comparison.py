"""Tests for generic JSON/PDF value comparison."""

import textwrap

from auditor import compare_json_with_pdf


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

    def test_short_zero_without_profile_remains_unverifiable(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"code": "0"}, "Code: 0"
        )
        assert not matches and not mismatches
        assert unverifiable == [("code", "0")]

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
        matches, mismatches, _ = compare_json_with_pdf({"country": "Espana"}, self.PDF)
        assert any("Espana" in v for _, v in matches)
        assert not mismatches

    def test_loose_trace_goes_to_unverifiable(self):
        pdf = "Cittadinanza: ITALIANA"
        _, mismatches, unverifiable = compare_json_with_pdf(
            {"country": "ITALIA"}, pdf
        )
        assert any("ITALIA" in v for _, v in unverifiable)
        assert not mismatches

    def test_number_run_into_following_label_still_matches(self):
        pdf = "27 5.242,20Codice fiscale del percipiente Mod. N."
        matches, mismatches, _ = compare_json_with_pdf({"ammontare": "5242.20"}, pdf)
        assert any("5242.20" in v for _, v in matches)
        assert not mismatches

    def test_number_without_thousands_grouping_matches(self):
        pdf = "Importo: 5242,20 euro"
        matches, _, _ = compare_json_with_pdf({"amount": "5242.20"}, pdf)
        assert any("5242.20" in v for _, v in matches)

    def test_date_printed_as_space_separated_grid_boxes(self):
        pdf = "365 01 12 2022 X"
        matches, mismatches, _ = compare_json_with_pdf(
            {"dataInizio": "2022-12-01"}, pdf
        )
        assert any("2022-12-01" in v for _, v in matches)
        assert not mismatches

    def test_date_printed_without_leading_zeros(self):
        matches, _, _ = compare_json_with_pdf({"data": "2026-03-14"}, "del 14/3/2026")
        assert any("2026-03-14" in v for _, v in matches)

    def test_day_month_only_value_printed_concatenated(self):
        pdf = "101 3112 B923Codice fiscale del percipiente"
        matches, mismatches, _ = compare_json_with_pdf(
            {"dataInizioGiornoMese": "10-1", "dataFineGiornoMese": "31-12"}, pdf
        )
        matched_values = {v for _, v in matches}
        assert "10-1" in matched_values
        assert "31-12" in matched_values
        assert not mismatches

    def test_year_month_period_matches_table_layout(self):
        pdf = "Periodos de cotizacion 2026 Enero Febrero Marzo Abril Mayo Junio Julio Base 4092.07"
        matches, mismatches, _ = compare_json_with_pdf({"periodo": "2026-07"}, pdf)
        assert any("2026-07" in v for _, v in matches)
        assert not mismatches

    def test_year_month_period_matches_adjacent_rendering(self):
        matches, mismatches, _ = compare_json_with_pdf(
            {"periodo": "2026-07"}, "Periodo: julio de 2026"
        )
        assert any("2026-07" in v for _, v in matches)
        assert not mismatches

    def test_year_month_period_without_month_still_a_discrepancy(self):
        _, mismatches, _ = compare_json_with_pdf(
            {"periodo": "2026-07"}, "Periodos de cotizacion 2026 Enero Febrero"
        )
        assert any("2026-07" in v for _, v in mismatches)

    def test_settimane_matches_pdf_abbreviation_sett(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"regimeGenerale": [{"tipoContributo": "Settimane"}]},
            "Tipo contributo: sett.",
        )
        assert any("Settimane" in v for _, v in matches)
        assert not mismatches and not unverifiable

    def test_integral_decimal_contribution_matches_plain_integer(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"regimeGenerale": [{"contributiUtiliDiritto": "52.0"}]},
            "Contributi utili diritto: 52",
        )
        assert any("52.0" in v for _, v in matches)
        assert not mismatches and not unverifiable

    def test_integral_decimal_giorni_matches_plain_integer(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"lavoratoriSpettacoloSport": {"estrattoContoSpettacoloSport": [{"giorni": "17.0"}]}},
            "Giorni: 17",
        )
        assert any("17.0" in v for _, v in matches)
        assert not mismatches and not unverifiable

    def test_low_signal_short_code_path_is_skipped(self):
        result = compare_json_with_pdf(
            {"regimeGenerale": [{"primaNota": {"codice": "O"}}]}, ""
        )
        assert result == ([], [], [])

    def test_low_signal_short_mesi_contribuzione_is_skipped(self):
        result = compare_json_with_pdf(
            {"regimeParasubordinati": {"estrattoContoMontanteContributivo": [{"mesiContribuzione": "3"}]}},
            "",
        )
        assert result == ([], [], [])

    def test_comune_sigla_matches_parenthesized_pdf_format(self):
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"datiIdentificativi": {"comuneStatoNascita": "NAPOLI NA"}},
            "Comune di nascita: NAPOLI (NA)",
        )
        assert any("NAPOLI NA" in v for _, v in matches)
        assert not mismatches and not unverifiable
