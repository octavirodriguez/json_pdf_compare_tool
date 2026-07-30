# JSON-PDF Compare Tool

An automated auditing tool to ingest, validate, and compare IRS Model 3 document pairs (PDF vs. JSON) for fiscal compliance.

---

## 📋 Features

* **Automated File Pairing:** Automatically matches `.pdf` and `.json` files recursively across directories.
* **Smart Verification:** Checks JSON key-value pairs against PDF text content, supporting European numeric formats (`1.166,34`), standard floats (`1.166.34`), and ISO dates (`YYYY-MM-DD` to `DD/MM/YYYY`).
* **macOS Automation (Folder Actions):** Supports real-time folder watching to automatically normalize and standardize incoming IRS files.
* **Markdown Audit Reports:** Automatically generates detailed execution reports with executive summaries and field-level discrepancy breakdowns.
* **UI Ready:** Fully modular backend ready for `customtkinter` integration.

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
pip install pypdf customtkinter
````

---

## 💻 CLI Usage

1. Place your matching PDF and JSON file pairs into the `./data` folder (subdirectories are supported).
2. Run the audit script:
   ````Bash
   python auditor.py
   ````
   
   Optional: You can also specify a custom input directory:
   python auditor.py ./path/to/custom_folder

3. View the generated Markdown report inside the `./reports` directory (`audit_report_YYYYMMDD_HHMMSS.md`).
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
├── data/              # Input directory for PDF/JSON pairs
├── reports/           # Generated Markdown audit reports
├── venv/              # Python virtual environment (git-ignored)
├── auditor.py         # Core auditing engine
├── README.md          # Project documentation
└── .gitignore         # Git ignore rules
```
---

## 🤝 Contributing

Contributions are welcome! Please feel free to open an issue or submit a Pull Request.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.