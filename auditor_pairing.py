import json
from pathlib import Path

from auditor_comparison import compare_json_with_pdf
from auditor_pdf import extract_pdf_text
from auditor_reporting import generate_markdown_report
from profiles import detect_profile


TRAILING_SUFFIX_LENGTH = 13


def derive_base_key(stem):
    """Strips the trailing system-generated suffix from a filename stem so PDF/JSON pairs can be matched.

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
    """Searches for PDF/JSON pairs, compares them, generates a report, and returns structured results."""
    pdf_map = {}
    json_map = {}

    root_path = Path(root_dir)
    if not root_path.exists():
        print(f"❌ Directory '{root_dir}' does not exist.")
        return [], None

    pdf_files = []
    json_files = []
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
        (pdf_files if suffix == ".pdf" else json_files).append(file)

    json_data_by_path = {}
    for json_path in json_files:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data_by_path[json_path] = json.load(f)
        except Exception as e:
            print(f"❌ Error reading JSON {json_path.name}: {e}")

    pairs = []
    paired_pdfs = set()
    paired_jsons = set()
    for name in sorted(set(pdf_map.keys()).intersection(set(json_map.keys()))):
        pdf_path = pdf_map[name]
        json_path = json_map[name]
        if json_path in json_data_by_path:
            pairs.append((name, pdf_path, json_path, None))
            paired_pdfs.add(pdf_path)
            paired_jsons.add(json_path)

    # When filenames are unrelated, use the detected document profile and the
    # comparison signal to select a unique, evidence-backed candidate.
    pdf_text_by_path = {}
    candidates = []
    for pdf_path in pdf_files:
        if pdf_path in paired_pdfs:
            continue
        pdf_text = extract_pdf_text(pdf_path)
        pdf_text_by_path[pdf_path] = pdf_text
        if pdf_text is None:
            continue
        for json_path, json_data in json_data_by_path.items():
            if json_path in paired_jsons:
                continue
            profile = detect_profile(pdf_text, json_data)
            if profile is None:
                continue
            matches, mismatches, unverifiable = compare_json_with_pdf(
                json_data, pdf_text, profile=profile
            )
            if matches:
                candidates.append((
                    len(matches),
                    -len(mismatches),
                    -len(unverifiable),
                    pdf_path,
                    json_path,
                    profile,
                ))

    for _, _, _, pdf_path, json_path, profile in sorted(
        candidates, key=lambda candidate: candidate[:3], reverse=True
    ):
        if pdf_path in paired_pdfs or json_path in paired_jsons:
            continue
        score = next(
            candidate[:3]
            for candidate in candidates
            if candidate[3] == pdf_path and candidate[4] == json_path
        )
        equally_good_alternatives = [
            candidate
            for candidate in candidates
            if candidate[:3] == score
            and (candidate[3] == pdf_path or candidate[4] == json_path)
        ]
        if len(equally_good_alternatives) > 1:
            print(
                f"⚠️ Ambiguous content-based match for '{pdf_path.name}' and "
                f"'{json_path.name}'; leaving candidates unpaired."
            )
            continue
        pair_name = f"{pdf_path.stem} + {json_path.stem}"
        pairs.append((pair_name, pdf_path, json_path, profile))
        paired_pdfs.add(pdf_path)
        paired_jsons.add(json_path)

    if not pairs:
        print(f"⚠️ No matching PDF and JSON file pairs found in '{root_dir}'.")
        return [], None

    print(f"\n🔍 Running audit for {len(pairs)} file pairs...\n" + "=" * 60)

    results = []

    for name, pdf_path, json_path, detected_profile in pairs:

        pdf_text = pdf_text_by_path.get(pdf_path)
        if pdf_text is None:
            pdf_text = extract_pdf_text(pdf_path)
        pdf_read_error = pdf_text is None

        json_data = json_data_by_path.get(json_path)
        if json_data is None:
            continue

        profile = detected_profile
        if profile is None and pdf_text is not None:
            profile = detect_profile(pdf_text, json_data)

        matches, mismatches, unverifiable = compare_json_with_pdf(
            json_data, pdf_text or "", profile=profile
        )

        results.append({
            "name": name,
            "pdf_read_error": pdf_read_error,
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