"""Tests for file pairing, PDF extraction, and Markdown reports."""

import json
from pathlib import Path
from unittest.mock import patch

from auditor import (
    TRAILING_SUFFIX_LENGTH,
    audit_directory_recursively,
    derive_base_key,
    extract_pdf_text,
)
from auditor_pairing import _json_value_lines

# ---------------------------------------------------------------------------
# derive_base_key
# ---------------------------------------------------------------------------

class TestDeriveBaseKey:
    def test_strips_suffix(self):
        stem = "Document_Name_W2QADYOZ_ZQW"  # 13-char suffix: _W2QADYOZ_ZQW
        result = derive_base_key(stem)
        assert result == "Document_Name"

    def test_preserves_long_name_without_generated_suffix(self):
        stem = "alice-2023-730"
        assert derive_base_key(stem) == stem

    def test_short_stem_returned_as_is(self, capsys):
        short = "short"
        result = derive_base_key(short)
        assert result == short
        assert "⚠️" in capsys.readouterr().out

    def test_exact_boundary_returned_as_is(self):
        stem = "x" * TRAILING_SUFFIX_LENGTH
        result = derive_base_key(stem)
        assert result == stem


class TestJsonValueLines:
    def test_tracks_nested_values_in_objects_and_arrays(self):
        source = '{\n  "person": {\n    "name": "John",\n    "ids": [\n      "A",\n      "B"\n    ]\n  }\n}'

        assert _json_value_lines(source) == {
            "person.name": 3,
            "person.ids[0]": 5,
            "person.ids[1]": 6,
        }
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
        with patch("auditor_pairing.extract_pdf_text", return_value="some text"):
            # We still need a PDF file to exist so file discovery finds it
            (data / "Doc_Alpha_W2QADYOZ_ZQW.pdf").write_bytes(b"fake")
            results, _ = audit_directory_recursively(str(data), str(reports))

        assert results == []
        assert "Error reading JSON" in capsys.readouterr().out

    def test_report_includes_json_line_for_discrepancy(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        reports = tmp_path / "reports"
        reports.mkdir()
        (data / "example-document.pdf").write_bytes(b"fake")
        (data / "example-document.json").write_text(
            '{\n  "person": {\n    "name": "Expected Name"\n  }\n}',
            encoding="utf-8",
        )

        with patch("auditor_pairing.extract_pdf_text", return_value="Other Name"):
            results, report = audit_directory_recursively(str(data), str(reports))

        assert results[0]["mismatches"] == [("person.name", "Expected Name")]
        content = Path(report).read_text(encoding="utf-8")
        assert "* **JSON Source:** `example-document.json`, line 3" in content

    def test_minified_json_reports_line_in_formatted_view(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        reports = tmp_path / "reports"
        reports.mkdir()
        (data / "example-document.pdf").write_bytes(b"fake")
        (data / "example-document.json").write_text(
            '{"a": {"b": "Present Value"}, "c": ["x", "Missing Value"]}',
            encoding="utf-8",
        )

        with patch("auditor_pairing.extract_pdf_text", return_value="Present Value"):
            _, report = audit_directory_recursively(str(data), str(reports))

        content = Path(report).read_text(encoding="utf-8")
        assert "`example-document.json`, line 7" in content

    def test_unrelated_filenames_are_paired_using_profile_and_content(
        self, tmp_path
    ):
        data = tmp_path / "data"
        data.mkdir()
        reports = tmp_path / "reports"
        reports.mkdir()
        pdf_path = data / "official-certificate.pdf"
        json_path = data / "export-from-provider.json"
        pdf_path.write_bytes(b"fake")
        json_path.write_text(
            json.dumps({"person": {"name": "John Doe"}}), encoding="utf-8"
        )

        pdf_text = (
            "Anagrafe Nazionale della Popolazione Residente "
            "Certificato contestuale John Doe"
        )
        with patch("auditor_pairing.extract_pdf_text", return_value=pdf_text):
            results, report = audit_directory_recursively(str(data), str(reports))

        assert report is not None
        assert len(results) == 1
        assert results[0]["name"] == "official-certificate + export-from-provider"
        assert results[0]["matches"] == [("person.name", "John Doe")]

    def test_unrelated_filenames_are_paired_for_aeat_modelo_130(
        self, tmp_path
    ):
        data = tmp_path / "data"
        data.mkdir()
        reports = tmp_path / "reports"
        reports.mkdir()
        (data / "official-return.pdf").write_bytes(b"fake")
        (data / "provider-export.json").write_text(
            json.dumps({"declaracion": {"estadoCivil": "1"}}),
            encoding="utf-8",
        )

        pdf_text = (
            "Agencia Tributaria Modelo 130\n"
            "INFORMACIÓN DE LA PRESENTACIÓN DE LA DECLARACIÓN\n"
            "NIF Presentador: 12345678Z\n"
            "Apellidos y Nombre: TEST PERSON\n"
            "Estado civil (1) Soltero/a\n"
        )
        with patch("auditor_pairing.extract_pdf_text", return_value=pdf_text):
            results, report = audit_directory_recursively(str(data), str(reports))

        assert report is not None
        assert len(results) == 1
        assert results[0]["matches"] == [("declaracion.estadoCivil", "1")]

    def test_unrelated_filenames_are_paired_for_italian_modello_730(
        self, tmp_path
    ):
        data = tmp_path / "data"
        data.mkdir()
        reports = tmp_path / "reports"
        reports.mkdir()
        (data / "official-return.pdf").write_bytes(b"fake")
        (data / "provider-export.json").write_text(
            json.dumps(
                {
                    "prospettoLiquidazione730_3": {},
                    "quadros": [],
                    "contribuente": {"codiceFiscale": "ABC123XYZ"},
                }
            ),
            encoding="utf-8",
        )

        pdf_text = "Agenzia delle Entrate Modello 730 Codice fiscale ABC123XYZ"
        with patch("auditor_pairing.extract_pdf_text", return_value=pdf_text):
            results, report = audit_directory_recursively(str(data), str(reports))

        assert report is not None
        assert len(results) == 1
        assert results[0]["matches"] == [
            ("contribuente.codiceFiscale", "ABC123XYZ")
        ]
