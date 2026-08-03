import json
import os
import re
import sys
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
        return ""


_WHITESPACE_RE = re.compile(r"\s+")


def _build_phrase_regex(value_str):
    """
    Builds a case-insensitive regex that matches `value_str` as whole word(s),
    tolerating any amount of whitespace (including line breaks) between the
    words it contains. PDF text extraction frequently re-flows or wraps text
    differently than the source JSON, so a literal substring check is too
    strict, and a fully unanchored substring check is too loose (e.g. "20"
    would match inside "2025"). Word boundaries plus flexible inter-word
    whitespace strike a middle ground that works across differently
    structured documents.
    """
    tokens = [t for t in _WHITESPACE_RE.split(value_str.strip()) if t]
    if not tokens:
        return None
    body = r"\s+".join(re.escape(t) for t in tokens)
    return re.compile(r"(?<!\w)" + body + r"(?!\w)", re.IGNORECASE)


def _value_matches_text(pdf_text, value_str):
    """
    Whole-word(s), whitespace-tolerant, case-insensitive match of value_str in pdf_text.
    """
    pattern = _build_phrase_regex(value_str)
    return bool(pattern and pattern.search(pdf_text))


def _all_words_present(pdf_text, value_str, min_word_length=3):
    """
    Fallback for multi-word values whose exact phrase isn't found as-is: true if
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
    """
    Weak, unanchored, case-insensitive substring check (no word boundaries) —
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


def compare_json_with_pdf(json_data, pdf_text):
    """
    Recursively walks through the JSON and verifies if values exist within the PDF text.
    """
    mismatches = []
    matches = []
    unverifiable = []
    pdf_text_lower = pdf_text.lower()

    def generate_value_variants(value_str):
        variants = [value_str]

        # 1. Variants for float/currency numbers
        try:
            val_float = float(value_str)
            # European format with dot for thousands and comma for decimals (1.166,34)
            variants.append(f"{val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            # European format with dot for thousands and dot for decimals (1.166.34)
            variants.append(f"{val_float:,.2f}".replace(",", "."))
        except ValueError:
            pass

        # 2. Variants for ISO dates (YYYY-MM-DD -> DD/MM/YYYY)
        try:
            date_obj = datetime.strptime(value_str, "%Y-%m-%d")
            variants.append(date_obj.strftime("%d/%m/%Y"))
            variants.append(date_obj.strftime("%d-%m-%Y"))
        except ValueError:
            pass

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

            variants = generate_value_variants(value_str)
            if any(_value_matches_text(pdf_text, var) for var in variants):
                matches.append((path, value_str))
            elif _all_words_present(pdf_text, value_str):
                matches.append((path, value_str))
            elif _loose_trace_present(pdf_text_lower, variants):
                unverifiable.append((path, value_str))
            else:
                mismatches.append((path, value_str))

    search_recursive(json_data)
    return matches, mismatches, unverifiable


def generate_markdown_report(results, reports_dir):
    """
    Generates a clean and structured Markdown audit report.
    """
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
                md.append("  * *Action:* Check if this value appears in a different format, is truncated, or if pages are missing from the PDF.\n")

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
# Stripping this fixed-length suffix (13 characters) from both stems is what lets us pair
# files by base name instead of requiring identical filenames, which in turn
# is what allows dropping whole batches of pairs into the data folder at once.
TRAILING_SUFFIX_LENGTH = 13


def derive_base_key(stem):
    """
    Strips the trailing system-generated suffix from a filename stem so PDF/JSON pairs can be matched.

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
    """
    Searches for PDF/JSON pairs, compares them, generates a report, and returns structured results.
    """
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

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
        except Exception as e:
            print(f"❌ Error reading JSON {json_path.name}: {e}")
            continue

        matches, mismatches, unverifiable = compare_json_with_pdf(json_data, pdf_text)

        results.append({
            "name": name,
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