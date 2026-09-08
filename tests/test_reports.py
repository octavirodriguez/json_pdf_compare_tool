"""Tests for Markdown audit report generation."""

from pathlib import Path

from auditor import generate_markdown_report


class TestGenerateMarkdownReport:
    def test_highlights_discrepancies_and_unverifiable_fields(self, tmp_path):
        results = [
            {
                "name": "sample_doc",
                "matches": [("person.name", "John Doe")],
                "mismatches": [("person.taxId", "XYZ999")],
                "unverifiable": [("person.status", "1")],
            }
        ]
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        report_path = generate_markdown_report(results, str(reports_dir))
        content = Path(report_path).read_text(encoding="utf-8")

        assert "* ❌ **JSON Path:** <mark>`person.taxId`</mark>" in content
        assert "* **Expected Value (JSON):** <mark>`XYZ999`</mark>" in content
        assert "* 🟡 **JSON Path:** <mark>`person.status`</mark>" in content
        assert "* **Expected Value (JSON):** <mark>`1`</mark>" in content