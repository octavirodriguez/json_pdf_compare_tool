import os
from datetime import datetime


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
                md.append(f"* ❌ **JSON Path:** <mark>`{path}`</mark>")
                md.append(f"  * **Expected Value (JSON):** <mark>`{val}`</mark>")
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
                md.append(f"* 🟡 **JSON Path:** <mark>`{path}`</mark>")
                md.append(f"  * **Expected Value (JSON):** <mark>`{val}`</mark>")
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
# Stripping this fixed-length suffix from both stems lets us pair files by base
# name instead of requiring identical filenames. Unrelated names are handled
# later using profile detection and matching field content.
TRAILING_SUFFIX_LENGTH = 13


