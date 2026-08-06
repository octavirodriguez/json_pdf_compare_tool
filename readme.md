# JSON-PDF Compare Tool

An automated auditing tool to ingest, validate, and compare different administration document pairs (PDF vs. JSON) for fiscal compliance.

---

## 📋 Features

* **Batch File Pairing:** Automatically matches `.pdf` and `.json` files recursively across directories by base filename, ignoring each file's trailing 13-character system-generated suffix (e.g. `..._W2IWIZ2W_DBS.pdf` / `..._W2IWIZ9C_4US.json`) — so you can drop many document pairs into `./data` at once without renaming anything. If two files would resolve to the same base name, the tool warns instead of silently dropping one.
* **Smart Verification:** Checks JSON key-value pairs against PDF text content, supporting European numeric formats (`1.166,34`), standard floats (`1.166.34`), and ISO dates (`YYYY-MM-DD` to `DD/MM/YYYY`). Matching is case-insensitive and tolerant of line wraps/whitespace differences between the PDF and JSON, and a word-order-independent fallback catches fields a PDF splits differently than the JSON (e.g. a full name stored as one JSON field but printed as separate "Cognome" / "Nome" lines).
* **Three-Tier Audit Outcome:** Each JSON field is reported as a **Match** (confidently verified), a **Discrepancy** (no trace of the value found anywhere in the PDF — the strongest signal of a real data problem), or **Unverifiable** (a weak/coincidental textual trace was found, but not enough to confirm — worth a quick manual look rather than treating it as pass or fail).
* **macOS Automation (Folder Actions):** Supports real-time folder watching to automatically normalize and standardize incoming files.
* **Markdown Audit Reports:** Automatically generates detailed execution reports with executive summaries and field-level match/unverifiable/discrepancy breakdowns.
* **Desktop App:** A `customtkinter` GUI (`auditor_gui.py`) drives the same audit engine — pick a folder, click *Run Audit*, and view results — and can be packaged into a standalone macOS app that runs without Python installed (see [buildApp.md](buildApp.md)).

---

## ⚙️ Prerequisites

* **Python:** `3.9` or higher

---

## 🚀 Installation & Setup

1. **Clone the repository:**
````Bash
git clone [https://github.com/octavirodriguez/json_pdf_compare_tool.git](https://github.com/octavirodriguez/json_pdf_compare_tool.git)
cd json_pdf_compare_tool
````
2. **Create and activate a Virtual Environment:**
````Bash
python3 -m venv venv
source venv/bin/activate
````
3. **Install dependencies:**
````Bash
pip install -r requirements.txt
````

---

## 🖥️ Desktop App

Prefer a GUI over the command line? Run:
````Bash
python auditor_gui.py
````
Pick a data folder, click **Run Audit**, then use **Open Report** or **Reveal
Reports Folder** to see the results. It uses the exact same audit engine as
the CLI (`auditor.py`) — nothing about the matching or report logic differs.

**Want a standalone app you can hand to someone without Python installed?**
See [BUILD.md](BUILD.md) for packaging this into a double-clickable
`JSON-PDF Compare Tool.app` with `py2app`.

---

## 💻 CLI Usage

1. Place your PDF and JSON file pairs into the `./data` folder (subdirectories are supported). You can drop in a whole batch at once — files are paired by base filename once each one's trailing 13-character suffix is stripped, so `.pdf` and `.json` files don't need identical names.

   > ⚠️ `./data` is git-ignored on purpose, since these are typically real fiscal/personal documents. Never remove `data/` from `.gitignore` or force-add files from it.

2. Run the audit script:
   ````Bash
   python auditor.py
   ````
   
   Optional: You can also specify a custom input directory:
   python auditor.py ./path/to/custom_folder

3. View the generated Markdown report inside the `./reports` directory (`audit_report_YYYYMMDD_HHMMSS.md`). Each document is scored ✅ OK (all fields matched), 🟡 NEEDS REVIEW (no discrepancies, but some fields were unverifiable), or ❌ ISSUES FOUND (at least one discrepancy).
<!--
---

## ⚙️ macOS Automation Setup (Folder Actions)

To automatically ingest, extract metadata (Taxpayer Name, Year, Model), and rename incoming fiscal documents to a standardized format (`[Prefix]_[Model]_[Name]_[Year].[ext]`):

1. Open Automator on macOS and create a new Folder Action.
2. Select your target drop folder at the top of the workflow window.
3. Add a Run Shell Script action with the following settings:
   * Shell: /bin/bash
   * Pass input: as arguments
4. Use your virtual environment's Python path to run the automation logic:
   /Users/YOUR_USER/path/to/json_pdf_compare_tool/venv/bin/python3 -c '
   import sys, os, re
   # Custom automated renaming script logic
   ' "$@"
-->
---

## 📁 Repository Structure
```text
json_pdf_compare_tool/
├── data/              # Input directory for PDF/JSON pairs (git-ignored — may hold real personal data)
├── reports/           # Generated Markdown audit reports (git-ignored)
├── build/, dist/      # py2app build output (git-ignored — see BUILD.md)
├── venv/              # Python virtual environment (git-ignored)
├── tests/             # pytest unit tests
├── auditor.py         # Core auditing engine
├── auditor_gui.py     # customtkinter desktop GUI, built on auditor.py
├── setup.py           # py2app packaging config
├── requirements.txt  # Runtime dependencies
├── BUILD.md           # How to build the standalone macOS app
├── README.md          # Project documentation
└── .gitignore         # Git ignore rules
```
---

## 🔬 Running the Tests

```bash
pytest tests/
```

The suite covers all matching logic, variant generation, the three-tier classification, PDF read error handling, and file pairing edge cases (45 tests).

---

## �🤝 Contributing

Contributions are welcome! Please feel free to open an issue or submit a Pull Request.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
