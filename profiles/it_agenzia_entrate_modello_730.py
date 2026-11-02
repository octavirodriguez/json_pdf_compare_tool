"""Rules for Italian Agenzia delle Entrate Modello 730 returns."""

import re

from .base import DocumentProfile


_PROSPETTO_VALUE_PATH_RE = re.compile(
    r"^prospettoLiquidazione730_3\.quadros\[(\d+)\]\.value\[(\d+)\]\.value$",
    re.IGNORECASE,
)
_ZERO_CENTS_RE = re.compile(r"^(-?\d+)[.,]00$")


class ItAgenziaEntrateModello730Profile(DocumentProfile):
    name = "agenzia_entrate_modello_730"

    def detect(self, pdf_text, json_data):
        normalized_text = pdf_text.casefold()
        return (
            "modello 730" in normalized_text
            and isinstance(json_data, dict)
            and "prospettoLiquidazione730_3" in json_data
            and "quadros" in json_data
        )

    def should_skip_field(self, path):
        normalized_path = path.casefold()
        return (
            normalized_path.startswith(
                ("quadros[", "prospettoliquidazione730_3.")
            )
            and normalized_path.rsplit(".", 1)[-1] in {"name", "ref"}
        )

    def confident_row_value_hit(self, pdf_layout_text, json_data, path, value_str):
        if not pdf_layout_text or not isinstance(json_data, dict):
            return False

        path_match = _PROSPETTO_VALUE_PATH_RE.fullmatch(path)
        amount_match = _ZERO_CENTS_RE.fullmatch(value_str)
        if not path_match or not amount_match:
            return False

        quadro_index, cell_index = (int(part) for part in path_match.groups())
        prospetto = json_data.get("prospettoLiquidazione730_3")
        quadros = prospetto.get("quadros") if isinstance(prospetto, dict) else None
        if not isinstance(quadros, list) or quadro_index >= len(quadros):
            return False

        row = quadros[quadro_index]
        if not isinstance(row, dict):
            return False

        cells = row.get("value")
        if not isinstance(cells, list) or cell_index >= len(cells):
            return False

        cell = cells[cell_index]
        if (
            not isinstance(cell, dict)
            or str(cell.get("value", "")).strip() != value_str
        ):
            return False

        populated_cells = [
            item
            for item in cells
            if isinstance(item, dict)
            and item.get("value") is not None
            and str(item.get("value")).strip()
        ]
        row_name = row.get("name")
        row_ref = row.get("ref")
        if (
            len(populated_cells) != 1
            or populated_cells[0] is not cell
            or not isinstance(row_name, str)
            or not row_name.strip()
            or not isinstance(row_ref, str)
            or not row_ref.strip()
        ):
            return False

        amount_tokens = {
            f"{amount_match.group(1)},00",
            f"{amount_match.group(1)}.00",
        }
        row_name_normalized = " ".join(row_name.casefold().split())
        row_ref_pattern = re.compile(
            rf"(?<!\d){re.escape(row_ref.strip())}(?!\d)"
        )
        amount_patterns = [
            re.compile(rf"(?<!\d){re.escape(token)}(?!\d)")
            for token in amount_tokens
        ]

        for line in pdf_layout_text.splitlines():
            normalized_line = " ".join(line.casefold().split())
            if (
                row_name_normalized in normalized_line
                and row_ref_pattern.search(line)
                and any(pattern.search(line) for pattern in amount_patterns)
            ):
                return True

        return False