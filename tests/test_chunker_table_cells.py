from __future__ import annotations

import unittest

from services.chunker.stages.parser_docx import _parse_multi_column_table
from services.chunker.stages.parser_pdf import _build_table_blocks


EXPECTED_CELLS = [
    {
        "column_index": 0,
        "header": "Measure",
        "value": "Efficacy",
        "content_start": 0,
        "content_end": 17,
        "value_start": 9,
        "value_end": 17,
    },
    {
        "column_index": 1,
        "header": "Target",
        "value": ">= 75%",
        "content_start": 19,
        "content_end": 33,
        "value_start": 27,
        "value_end": 33,
    },
]


class ChunkerTableCellTests(unittest.TestCase):
    def test_docx_retains_cells_from_the_same_parse_that_builds_row_text(self) -> None:
        blocks = _parse_multi_column_table(
            [["Measure", "Target"], ["Efficacy", ">= 75%"]],
            "profile",
            0,
            [],
            2,
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].content, "Measure: Efficacy, Target: >= 75%")
        self.assertEqual(blocks[0].structural_meta["table_cells"], EXPECTED_CELLS)

    def test_pdf_retains_the_same_table_cell_contract(self) -> None:
        blocks = _build_table_blocks(
            rows=[["Measure", "Target"], ["Efficacy", ">= 75%"]],
            doc_id="profile",
            table_index=0,
            page_number=1,
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].content, "Measure: Efficacy, Target: >= 75%")
        self.assertEqual(blocks[0].structural_meta["table_cells"], EXPECTED_CELLS)


if __name__ == "__main__":
    unittest.main()
