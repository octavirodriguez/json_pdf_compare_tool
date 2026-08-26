"""Rename a JSON file to match the PDF beside it.

Designed for a macOS Folder Action. The action may invoke this script once per
incoming file, so the script discovers pairs in each affected parent folder.
Only folders containing exactly one PDF and one JSON are changed.
"""

import os
import shutil
import sys
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data"


def _files_by_extension(folder, extension):
    return sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == extension
    )


def rename_json_for_pdf(folder, data_dir=DATA_DIR):
    """Rename and move the only PDF/JSON pair in *folder* into ``data_dir``.

    Returns the destination folder when a pair is moved, otherwise ``None``.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return None

    pdfs = _files_by_extension(folder, ".pdf")
    jsons = _files_by_extension(folder, ".json")
    if len(pdfs) != 1 or len(jsons) != 1:
        return None

    pdf_path = pdfs[0]
    json_path = jsons[0]
    destination = pdf_path.with_suffix(".json")

    if json_path == destination:
        return None
    data_dir = Path(data_dir)
    target_pdf = data_dir / pdf_path.name
    target_json = data_dir / destination.name
    if target_pdf.exists() or target_json.exists():
        print(f"Skipped: destination pair already exists in {data_dir}")
        return None
    if destination.exists():
        print(f"Skipped: destination already exists: {destination}")
        return None

    os.rename(json_path, destination)
    print(f"Renamed: {json_path.name} -> {destination.name}")
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdf_path), str(target_pdf))
    shutil.move(str(destination), str(target_json))
    print(f"Moved pair to: {data_dir}")
    return data_dir


def main(arguments):
    """Process the parent folders of paths supplied by Folder Actions."""
    folders = {Path(path).parent for path in arguments}
    for folder in sorted(folders):
        rename_json_for_pdf(folder)


if __name__ == "__main__":
    main(sys.argv[1:])