"""Tests for file pairing, PDF extraction, and Markdown reports."""

import json
from unittest.mock import patch

from auditor import (
    TRAILING_SUFFIX_LENGTH,
    audit_directory_recursively,
    derive_base_key,
    extract_pdf_text,
)

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


