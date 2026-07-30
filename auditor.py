import json
import os
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


def compare_json_with_pdf(json_data, pdf_text):
    """Recursively walks through the JSON and verifies if values exist within the PDF text."""
    mismatches = []
    matches = []

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
            if any(var in pdf_text for var in variants):
                matches.append((path, value_str))
            else:
                mismatches.append((path, value_str))

    search_recursive(json_data)
    return matches, mismatches


def generate_markdown_report(results, reports_dir):
    """Generates a clean and structured Markdown audit report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_filename = f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_path = os.path.join(reports_dir, report_filename)

    total_docs = len(results)
    successful_docs = sum(1 for r in results if len(r["mismatches"]) == 0)
    failed_docs = total_docs - successful_docs
    total_issues = sum(len(r["mismatches"]) for r in results)

    md = []
    md.append("# 📊 IRS Audit Report (Model 3)\n")
    md.append(f"**Execution Date:** `{now}`  \n")
    md.append(f"**Report Path:** `{report_path}`\n")
    md.append("---\n")

    # Executive Summary
    md.append("## 📈 Executive Summary\n")
    md.append(f"- **Analyzed Documents:** {total_docs}")
    md.append(f"- **Fully Verified Documents:** {successful_docs} ✅")
    md.append(f"- **Documents with Issues:** {failed_docs} ⚠️")
    md.append(f"- **Total Discrepancies Found:** {total_issues}\n")

    # Status Table
    md.append("### 📑 Document Status Overview\n")
    md.append("| Document | Matches | Discrepancies | Status |")
    md.append("| :--- | :---: | :---: | :---: |")
    for r in results:
        status = "✅ OK" if len(r["mismatches"]) == 0 else "❌ ISSUES FOUND"
        md.append(f"| `{r['name']}` | {len(r['matches'])} | {len(r['mismatches'])} | {status} |")
    md.append("\n---\n")

    # Detailed Audit
    md.append("## 🔍 Detailed Audit per Document\n")
    for r in results:
        md.append(f"### 📄 Document: `{r['name']}`\n")
        md.append(f"- **Matching Fields:** {len(r['matches'])}")
        md.append(f"- **Discrepancies:** {len(r['mismatches'])}\n")

        if r["mismatches"]:
            md.append("#### ⚠️ Issues to Review:\n")
            md.append("> **Note:** The JSON field exists, but its value was not found in exact text or standard numeric format within the PDF.\n")
            for path, val in r["mismatches"]:
                md.append(f"* **JSON Path:** `{path}`")
                md.append(f"  * **Expected Value (JSON):** `{val}`")
                md.append("  * *Action:* Check if this value appears in a different format, is truncated, or if pages are missing from the PDF.\n")
        else:
            md.append("🎉 **All extracted JSON fields have been successfully validated against the PDF.**\n")

        md.append("---\n")

    # Write file
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines("\n".join(md))

    return report_path


def audit_directory_recursively(root_dir, reports_dir):
    """Searches for PDF/JSON pairs, compares them, generates a report, and returns structured results."""
    pdf_map = {}
    json_map = {}

    root_path = Path(root_dir)
    if not root_path.exists():
        print(f"❌ Directory '{root_dir}' does not exist.")
        return [], None

    for file in root_path.rglob("*"):
        if file.is_file():
            if file.suffix.lower() == ".pdf":
                pdf_map[file.stem] = file
            elif file.suffix.lower() == ".json":
                json_map[file.stem] = file

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

        matches, mismatches = compare_json_with_pdf(json_data, pdf_text)

        results.append({
            "name": name,
            "matches": matches,
            "mismatches": mismatches
        })

        print(f"📄 Processed: {name} | ✅ {len(matches)} ok | ❌ {len(mismatches)} errors")

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